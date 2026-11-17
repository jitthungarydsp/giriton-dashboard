import ast
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from pypdf import PdfReader
from resources import settlement_pdf as pdf

ROOT = Path(__file__).resolve().parents[1]


class CashDatesTest(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(pdf, 'datetime').start()
        self.addCleanup(patch.stopall)
        # UTC is still the previous day; local invoice day must be Budapest's.
        self.clock.now.side_effect = lambda tz: datetime(2026,11,16,23,30,tzinfo=timezone.utc).astimezone(tz)
        self.courier = dict(id='9136',name='Teszt Futár',company_name='Teszt Vállalkozás',
                            address='Budapest',tax_number='12345678-1-42',tig_type='AAM',document_month=date(2026,10,1))
        self.amounts = dict(payable=100000,tip=20000,cash=34656)

    def test_cash_uses_local_issue_day_without_changing_transfer_terms_or_money(self):
        for tax in ('AAM','VAT'):
            with self.subTest(tax=tax):
                result=pdf.build_tig_breakdown(dict(self.courier,tig_type=tax),self.amounts)
                cash=next(r for r in result['rows'] if r['key']=='cash_service')
                self.assertEqual(cash['performanceDate'],'2026-11-17')
                self.assertEqual(cash['paymentDueDate'],'2026-11-17')
                self.assertEqual(cash['grossHuf'],34656)
                self.assertEqual(result['cashDocumentMeta']['periodLabel'],'2026.10.01 - 2026.10.31')
                self.assertEqual(result['documentMeta']['paymentDueDate'],(date.today()+pdf.timedelta(days=8)).isoformat())
                self.assertNotEqual(result['documentMeta']['paymentDueDate'],cash['paymentDueDate'])

    def load_api(self,name,ns):
        tree=ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        node.decorator_list=[]
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'pwa_api.py','exec'),ns)
        return ns[name]

    def test_snapshot_pilot_with_old_dates_gets_correct_cash_metadata(self):
        old=pdf.build_tig_breakdown(self.courier,self.amounts)
        old.pop('cashDocumentMeta')
        cash=next(r for r in old['rows'] if r['key']=='cash_service')
        cash.update(performanceDate='2026-11-25',paymentDueDate='2026-11-25')
        original=deepcopy(old)
        ns=dict(courier_identity=lambda u:('9136','Teszt Futár'),optional_supabase_rows=lambda *a,**k:[self.courier],
                money_int=lambda v:int(v or 0),workflow_cash_amount_from_financial_breakdown=lambda f:34656,
                tig_document_meta=lambda *a:old['documentMeta'],make_document_reference=lambda *a:'TEST')
        build=self.load_api('build_tig_breakdown_from_snapshot',ns)
        result=build({},date(2026,10,1),dict(totalPayableHuf=100000,cards=[],worksheetTig=old))
        self.assertEqual(result['cashDocumentMeta']['performanceDate'],'2026-11-17')
        self.assertEqual(next(r for r in result['rows'] if r['key']=='cash_service')['paymentDueDate'],'2026-11-17')
        self.assertEqual(old,original)

    def test_kp_only_flow_updates_buyer_and_fallback_cash_row(self):
        monthly=dict(available=True,rows=[],cashGrossHuf=34656,
                     buyer=dict(name='Vevő',periodLabel='2026.10.01 - 2026.10.31',performanceDate='2026-11-25',paymentDueDate='2026-11-25'))
        ns=dict(build_financial_breakdown=lambda *a,**k:{},build_workflow_tig_breakdown=lambda *a,**k:monthly,
                workflow_cash_amount_from_financial_breakdown=lambda f:34656,money_int=lambda v:int(v or 0),
                KP_INVOICE_THRESHOLD_HUF=1000,courier_identity=lambda u:('9136','Teszt Futár'))
        result=self.load_api('build_kp_invoice_tig_breakdown',ns)({},date(2026,10,1))
        self.assertEqual(result['buyer']['performanceDate'],'2026-11-17')
        self.assertEqual(result['buyer']['paymentDueDate'],'2026-11-17')
        self.assertEqual(result['rows'][0]['performanceDate'],'2026-11-17')
        self.assertEqual(result['finalTotalHuf'],34656)
        self.assertEqual(monthly['buyer']['performanceDate'],'2026-11-25')

    def test_pdf_cash_header_and_old_cash_row_use_same_day(self):
        old=pdf.build_tig_breakdown(self.courier,self.amounts)
        next(r for r in old['rows'] if r['key']=='cash_service').update(performanceDate='2026-11-25',paymentDueDate='2026-11-25')
        data=pdf.build_tig_pdf(self.courier,self.amounts,old)
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(data)).pages)
        cash_text=text.split('KÜLÖN KP SZÁMLA SZÜKSÉGES',1)[1]
        self.assertIn('2026-11-17',cash_text)
        self.assertNotIn('2026-11-25',cash_text)


if __name__=='__main__':unittest.main()
