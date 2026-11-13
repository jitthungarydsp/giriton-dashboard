from datetime import datetime
import importlib.util
from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('draft_management',ROOT/'resources/route_delay_form_drafts.py')
service=importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class DraftManagementTest(unittest.TestCase):
    def data(self):
        return {'Dátum':'2026-10-01','Futár ID':'6498','Futár':'Abonyi György','Túra ID':'1557743',
                'Raktár':'BUD1','Javasolt kategória száma':4,'Kategóriajavaslat':'Optimalizálatlan túra',
                'Adat / megfontolás':'4 külön cím 15 perc alatt','Forrásegyezés':'Egyezik',
                'Kategória futárral egyeztetve':'Igen','Reklamáció indoklása':'Ellenőrzött indoklás.'}
    def record(self):
        return service.make_record(self.data(),2,'source.xlsx','admin')
    def test_import_is_idempotent_and_sent_rows_are_not_overwritten(self):
        row=self.record()
        merged,counts=service.merge_import([row],[row])
        self.assertEqual(counts,dict(added=0,updated=0,skipped=1))
        sent=service.confirm_record(service.prepare_record(row,'admin'),'Google visszaigazolás: 123','admin',True)
        changed=service.make_record({**self.data(),'Reklamáció indoklása':'Új szöveg'},2)
        merged,counts=service.merge_import([sent],[changed],True)
        self.assertEqual(merged,[sent]);self.assertEqual(counts['updated'],0)
    def test_changed_saved_fields_change_prefill_and_reset_review(self):
        row=service.prepare_record(self.record(),'admin')
        changed={**self.data(),'Futár':'Módosított név','Túra ID':'99999','Reklamáció indoklása':'Új végleges indoklás.'}
        updated=service.edit_record(row,changed,'editor')
        self.assertEqual(updated['id'],row['id']);self.assertEqual(updated['state'],'draft')
        draft=service.preparation.prepare_row(updated['data'],updated['source_row'])
        query=parse_qs(urlparse(draft['prefill_url']).query)
        self.assertEqual(query['entry.139333198'],['Módosított név'])
        self.assertEqual(query['entry.584723978'],['99999'])
        self.assertIn('Új végleges indoklás.',query['entry.1757898114'][0])
    def test_preview_does_not_confirm_and_confirmation_requires_evidence(self):
        row=self.record()
        service.preparation.prepare_row(row['data'],2)
        self.assertEqual(row['state'],'draft')
        with self.assertRaises(ValueError):service.confirm_record(row,'proof','admin',True)
        prepared=service.prepare_record(row,'admin')
        with self.assertRaises(ValueError):service.confirm_record(prepared,'proof','admin',False)
        with self.assertRaises(ValueError):service.confirm_record(prepared,'','admin',True)
    def test_missing_checks_block_review_and_sent_edit_is_blocked(self):
        row=service.make_record({**self.data(),'Kategória futárral egyeztetve':'Nem'},2)
        with self.assertRaises(ValueError):service.prepare_record(row,'admin')
        sent=service.confirm_record(service.prepare_record(self.record(),'admin'),'Google proof','admin',True)
        with self.assertRaises(ValueError):service.edit_record(sent,self.data(),'admin')
    def test_excel_dates_and_editable_headers_are_normalized(self):
        row=self.data();row.pop('Javasolt kategória száma');row.pop('Reklamáció indoklása')
        row.update({'Dátum':datetime(2026,10,1),'Kategória száma':4,'Végleges indoklás':'Módosított Excel-indoklás'})
        record=service.make_record(row,2)
        self.assertEqual(record['work_date'],'2026-10-01')
        self.assertEqual(record['data']['Reklamáció indoklása'],'Módosított Excel-indoklás')
    def test_courier_route_collision_is_rejected(self):
        row=self.record()
        with self.assertRaises(ValueError):service.assert_unique([row,{**row,'id':'other'}])
    def test_work_copy_restores_confirmed_state_but_rejects_changed_content(self):
        sent=service.confirm_record(service.prepare_record(self.record(),'admin'),'Google proof 123','admin',True)
        restored=service.read_backup(json.dumps([sent]),'editor')[0]
        self.assertEqual(restored['state'],'sent');self.assertEqual(restored['submitted_at'],sent['submitted_at'])
        sent['data']['Futár']='Different'
        with self.assertRaises(ValueError):service.read_backup(json.dumps([sent]),'editor')
    def test_concurrent_save_requires_matching_version_and_state(self):
        db=Mock();query=db.schema.return_value.table.return_value.update.return_value
        query.eq.return_value=query;query.execute.return_value.data=[]
        row=self.record()
        with self.assertRaisesRegex(ValueError,'közben más'):service.store_edit(db,row,row)
        fields=[call.args[0]for call in query.eq.call_args_list]
        self.assertEqual(fields,['id','content_hash','state','updated_at'])

    def test_invoice_paste_keeps_blank_route_and_exact_partner_message(self):
        message='Októberi flottás elszámolási reklamáció.'
        pasted=(
            '2026-10-04\tNagy Ákos\t9067\t\tBUD2\t15:00:00\t\t14:36:00\t\\\n'
            '2026-10-05\tMásik Futár\t8001\t1561488\tBUD2\t08:00:00\t09:10:50\t07:39:00\t11:12:35\\\n'
            'A táblázat alatti magyarázatot hagyja figyelmen kívül.\n'
        )
        rows=service.read_invoice_paste(pasted,message,actor='admin')
        self.assertEqual(len(rows),2)
        self.assertEqual(service.display_route_id(rows[0]),'')
        self.assertEqual(rows[0]['data']['Űrlap kategória'],'Elszámolás')
        draft=service.preparation.prepare_row(rows[0]['data'],rows[0]['source_row'])
        self.assertEqual(draft['payload']['category'],'Elszámolás')
        self.assertEqual(draft['payload']['description'],message)
        fields=parse_qs(urlparse(draft['prefill_url']).query)
        self.assertEqual(fields['entry.608543996'],['Elszámolás / Invoice'])
        self.assertEqual(fields['entry.1609979400'],['9067'])
        self.assertEqual(fields['entry.949548968'],[message])

    def test_invoice_records_do_not_collide_with_a_route_delay_record(self):
        route=self.record()
        invoice=service.make_record({
            'Dátum':'2026-10-01','Futár ID':'6498','Futár':'Abonyi György','Túra ID':'1557743',
            'Raktár':'BUD1','Űrlap kategória':'Elszámolás',
            'Reklamáció indoklása':'Októberi flottás elszámolási reklamáció.',
        },2,'source.xlsx','admin')
        self.assertNotEqual(route['id'],invoice['id'])
        self.assertNotEqual(route['route_id'],invoice['route_id'])
        self.assertEqual(service.display_route_id(invoice),'1557743')
        service.assert_unique([route,invoice])

    def test_first_shift_workbook_uses_invoice_importer_from_common_excel_entry(self):
        original=service.read_invoice_excel
        try:
            service.read_invoice_excel=lambda content, filename, actor, message: [
                {'id':'invoice','data':{'Űrlap kategória':'Elszámolás'},'route_id':'Elszámolás:1'}
            ]
            book=Mock();book.sheetnames=['Első műszak késések'];book.close=Mock()
            with patch('openpyxl.load_workbook',return_value=book):
                rows=service.read_excel(b'xlsx','first-shifts.xlsx','admin')
            self.assertEqual(rows[0]['id'],'invoice')
        finally:
            service.read_invoice_excel=original


if __name__=='__main__':unittest.main()
