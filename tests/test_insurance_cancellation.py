import ast
from datetime import date
from pathlib import Path
from unittest.mock import Mock
import unittest
from resources.insurance_cancellation import insurance_active_for_period, insurance_cancelled_for_period

ROOT = Path(__file__).resolve().parents[1]


class InsuranceCancellationTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'calculate_target_reserve_month')
        self.ns = {'date': date, 'parse_huf_value': lambda value: float(value or 0),
                   'load_active_reserve_insurance_rule': lambda *args: {},
                   'RESERVE_TARGET_HUF': 50000, 'RESERVE_RATE': .1, 'INSURANCE_FEE_HUF': 10000,
                   'resolve_target_reserve_opening_balance': lambda *args: 100000}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'devtest.py', 'exec'), self.ns)

    def calculate(self, period, end='2026-10-15', events=None):
        return self.ns['calculate_target_reserve_month'](
            {'insurance_active': True, 'row': {'insurance_end_date': end}}, 200000, period,
            manual_events=events or {})

    def test_end_month_is_inclusive_and_following_month_has_no_deductions(self):
        for period in [date(2026, 9, 1), date(2026, 10, 1)]:
            result = self.calculate(period)
            self.assertEqual((result['reserve_addition_huf'], result['insurance_fee_huf']), (20000, 10000))
        result = self.calculate(date(2026, 11, 1))
        self.assertEqual((result['reserve_addition_huf'], result['insurance_fee_huf']), (0, 0))
        self.assertEqual(result['reserve_after_huf'], 100000)
        self.assertEqual(result['payable_after_insurance_huf'], 200000)

    def test_year_boundary_and_blank_end_date(self):
        self.assertFalse(insurance_cancelled_for_period({'insurance_end_date':'2026-12-31'}, date(2026,12,1)))
        self.assertTrue(insurance_cancelled_for_period({'insurance_end_date':'2026-12-31'}, date(2027,1,1)))
        for end in [None, '']:
            self.assertEqual(self.calculate(date(2026,11,1), end)['insurance_fee_huf'], 10000)

    def test_closing_later_month_does_not_disable_earlier_month(self):
        result = self.calculate(date(2026,11,1))
        self.assertTrue(result['insurance_active_before'])
        self.assertTrue(result['insurance_active_after'])
        self.assertTrue(insurance_active_for_period({'insurance_active':result['insurance_active_after'], 'insurance_end_date':'2026-10-15'}, date(2026,9,1)))

    def test_manual_release_still_credits_existing_reserve(self):
        result = self.calculate(date(2026,11,1), events={'payment':50000, 'deduction':10000})
        self.assertEqual(result['reserve_addition_huf'], -60000)
        self.assertEqual(result['insurance_fee_huf'], 0)
        self.assertEqual(result['reserve_after_huf'], 40000)
        self.assertEqual(result['payable_after_insurance_huf'], 260000)

    def test_invalid_end_date_cannot_silently_enable_deductions(self):
        with self.assertRaises(ValueError):
            self.calculate(date(2026,11,1), 'bad-date')

    def test_save_targets_only_exact_courier_and_changes_only_end_date(self):
        tree = ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        names = {'save_insurance_end_date','target_reserve_id_key','normalized_target_reserve_column'}
        nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        import re
        db=Mock();table=db.schema.return_value.table.return_value
        table.update.return_value.eq.return_value.execute.return_value.data=[{'courier_ID':'42'}]
        ns={'date':date,'re':re,'get_db':lambda:db,'load_target_reserve_status':Mock(),
            'load_target_reserve_rows_bulk':Mock(),'clear_settlement_overview_data_cache':Mock(),
            'request_courier_finance_refresh':Mock()}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'devtest.py','exec'),ns)
        ns['save_insurance_end_date']('42', {'courier_ID':42,'CT_Z_FT':100000}, date(2026,10,31))
        table.update.assert_called_once_with({'insurance_end_date':'2026-10-31'})
        table.update.return_value.eq.assert_called_once_with('courier_ID',42)
        with self.assertRaises(ValueError):ns['save_insurance_end_date']('43', {'courier_ID':42}, None)

    def test_cancelled_month_does_not_reuse_closed_month_deductions(self):
        tree = ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='resolve_target_reserve_month')
        expected=self.calculate(date(2026,11,1))
        self.ns.update(load_target_reserve_monthly=lambda *a:{'status':'done','insurance_fee_huf':10000},
                       calculate_target_reserve_month=Mock(return_value=expected),
                       save_target_reserve_monthly=Mock())
        exec(compile(ast.Module(body=[node],type_ignores=[]),'devtest.py','exec'),self.ns)
        result=self.ns['resolve_target_reserve_month']('session','42',date(2026,11,1),date(2026,11,30),
            {'insurance_active':True,'row':{'insurance_end_date':'2026-10-31'}},200000)
        self.assertEqual(result['insurance_fee_huf'],0)
        self.assertEqual(result['reserve_addition_huf'],0)

    def test_invoice_summary_also_stops_both_deductions(self):
        import pandas as pd
        tree=ast.parse((ROOT/'resources/invoice_summary.py').read_text(encoding='utf-8'))
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='calculate_reserve_and_insurance')
        ns={'pd':pd,'normalize_text':lambda v:str(v or ''),'money':lambda v:float(v or 0),
            'reserve_by_id':{'42':{'insurance_active':True,'insurance_end_date':'2026-10-31','current_reserve_huf':100000}},
            'reserve_by_name':{},'period_start':date(2026,11,1),
            'TARGET_RESERVE_RATE':.1,'TARGET_RESERVE_MAX_HUF':50000,'INSURANCE_DEDUCTION_HUF':10000}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'invoice_summary.py','exec'),ns)
        row={'courier_id':'42','payable_before_reserve_huf':200000}
        after=ns['calculate_reserve_and_insurance'](row)
        self.assertEqual(after['reserve_deduction_huf'],0)
        self.assertEqual(after['insurance_deduction_huf'],0)
        ns['period_start']=date(2026,10,1)
        before=ns['calculate_reserve_and_insurance'](row)
        self.assertEqual(before['reserve_deduction_huf'],20000)
        self.assertEqual(before['insurance_deduction_huf'],10000)


if __name__ == '__main__':unittest.main()
