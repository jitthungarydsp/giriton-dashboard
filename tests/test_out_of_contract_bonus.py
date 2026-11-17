import ast
import json
from pathlib import Path
import re
import sys
import types
import unicodedata
import unittest
from datetime import date
from types import SimpleNamespace

import pandas as pd
from resources.out_of_contract_bonus import is_out_of_contract_bonus_sheet
from resources.out_of_contract_bonus import (
    enrich_out_of_contract_bonus, validate_out_of_contract_snapshot_consistency,
)
from resources.settlement_parser import (
    ImportedExcelRow, DEFAULT_PARSERS, _parse_name_identified_sheet,
    detect_sheet_type_from_name,
)

ROOT = Path(__file__).resolve().parents[1]


def load_bonus_functions(records):
    tree = ast.parse((ROOT / 'devtest.py').read_text(encoding='utf-8'))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    ns = dict(pd=pd, re=re, json=json, unicodedata=unicodedata)
    ns['_load_imported_table_rows'] = lambda tables, sid: records if tables[0] == 'bonus_route_row' else []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith('IMPORTED_'):
                try: ns[name] = ast.literal_eval(node.value)
                except (ValueError, TypeError): pass
    pending = ['load_excel_stop_count_bonus_totals', 'load_imported_balance_components']
    selected = set()
    while pending:
        name = pending.pop()
        if name in ns or name in selected or name not in functions: continue
        selected.add(name)
        pending.extend(n.id for n in ast.walk(functions[name]) if isinstance(n, ast.Name) and n.id in functions)
    nodes = [functions[n] for n in selected]
    for node in nodes: node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), 'devtest.py', 'exec'), ns)
    return ns


class OutOfContractBonusTest(unittest.TestCase):
    def test_recalculation_restores_missing_or_stale_bonus_from_monthly_source(self):
        for amount in (31020, 93240, 0):
            for original in ({'Futár': 'Jamal Wasil'}, {'Szerződésen kívüli bónusz': 0},
                             {'Szerződésen kívüli bónusz': 31020}):
                with self.subTest(amount=amount, original=original):
                    summary = {'other_route_bonus_huf': amount}
                    updated = enrich_out_of_contract_bonus(pd.Series(original), summary)
                    self.assertEqual(updated['Szerződésen kívüli bónusz'], amount)
                    # Repeated refreshes are stable, and never mutate the cached list.
                    self.assertEqual(enrich_out_of_contract_bonus(updated, summary), updated)
        self.assertNotIn('Szerződésen kívüli bónusz', enrich_out_of_contract_bonus({}, {}))

    def test_snapshot_writer_rejects_bonus_loss_before_any_database_access(self):
        tree = ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'save_devtest_finance_snapshot_version')
        ns = dict(date=date, _courier_id_key=str,
                  validate_loyalty_snapshot_consistency=lambda *args: None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'devtest.py', 'exec'), ns)
        with self.assertRaisesRegex(ValueError, 'hibás pénzügyi mentés leállítva'):
            ns[node.name](courier_id='7440', courier_name='Jamal Wasil',
                period_start=date(2026,10,1), session_id='session', calculation_mode='Excel',
                warehouse_label='Összes', finance_rows=[{'item_key':'address_bonus_kifli','amount_value':0}],
                tig_rows=[], source_payloads=[{'source_key':'settlement_summary',
                    'payload':{'other_route_bonus_huf':31020}}], metadata={}, updated_by='test')

    def test_payment_income_includes_contract_bonus(self):
        tree=ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        detail=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_courier_detail_page')
        assignment=next(n for n in ast.walk(detail) if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id=='final_total_income' for t in n.targets))
        ns={name:0 for name in ('base_total','tip_total','delay_total','compliance_total',
            'route_other_bonus_total','imported_bonus_total','manual_bonus_total','loyalty_total',
            'customer_rating_total','correction_income_total')}
        ns.update(base_total=200000,tip_total=50000,route_other_bonus_total=31020)
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),'devtest.py','exec'),ns)
        self.assertEqual(ns['final_total_income'],281020)

    def test_snapshot_validation_allows_explicit_zero_but_rejects_missing_duplicate_or_invalid(self):
        sources = [{'source_key':'settlement_summary', 'payload':{'other_route_bonus_huf':0}}]
        item = {'item_key':'address_bonus_kifli', 'amount_value':0}
        validate_out_of_contract_snapshot_consistency([item], sources)
        for rows in ([], [item, item], [dict(item, amount_value=float('nan'))],
                     [dict(item, amount_value=31020)]):
            with self.assertRaises(ValueError):
                validate_out_of_contract_snapshot_consistency(rows, sources)

    def test_fast_list_keeps_individual_bonus_and_full_refresh_uses_source(self):
        summaries = [dict(courier_id=cid, driver_name=name, other_route_bonus_huf=amount,
                          payable_huf=100000, route_bonus_total_huf=amount)
                     for cid, name, amount in [('7440','Jamal Wasil',31020),
                                               ('6959','Bárándi Bendegúz',93240), ('6956','Árva Tamás',0)]]
        class Query:
            def schema(self, *_): return self
            def table(self, *_): return self
            def select(self, *_): return self
            def eq(self, *_): return self
            def execute(self): return SimpleNamespace(data=summaries)
        # Fast SQL view lacks the individual bonus; its total is not a substitute.
        fast = [{k:v for k,v in s.items() if k!='other_route_bonus_huf'} for s in summaries]
        ns = dict(pd=pd, date=date, get_db=Query,
                  load_fast_admin_settlement_dashboard_rows=lambda *_: fast,
                  _courier_id_key=lambda v:str(v or ''), parse_huf_value=lambda v:float(v or 0),
                  load_courier_master=lambda *_:pd.DataFrame(),
                  augment_settlement_courier_master=lambda x,*_:x,
                  settlement_dashboard_status_from_row=lambda row:dict(label='Elszámolás'))
        for name in ('apply_peopleforce_workflow_status','apply_monthly_closure_status',
                     'apply_salary_advance_request_status','apply_expense_request_status',
                     'apply_effective_payment_total_column','restore_open_complaint_status'):
            ns[name] = lambda x,*_:x
        tree = ast.parse((ROOT/'devtest.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
                 {'build_fast_settlement_overview_data','_streamlit_status_from_dashboard_label'}]
        for node in nodes: node.decorator_list=[]
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'devtest.py','exec'),ns)
        result=ns['build_fast_settlement_overview_data']('session',date(2026,10,1),date(2026,10,31),None)
        self.assertEqual(result.set_index('Courier ID')['Szerződésen kívüli bónusz'].to_dict(),
                         {'7440':31020,'6959':93240,'6956':0})
        # Execute the actual detail-page enrichment statement against a stale session row.
        detail=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_courier_detail_page')
        enrichment=next(n for n in detail.body if isinstance(n,ast.Assign) and 'enrich_out_of_contract_bonus(row, summary_row)' in ast.unparse(n))
        for summary in summaries:
            state=dict(pd=pd,enrich_out_of_contract_bonus=enrich_out_of_contract_bonus,
                       row=pd.Series({'Courier ID':summary['courier_id']}),summary_row=summary)
            exec(compile(ast.Module(body=[enrichment],type_ignores=[]),'devtest.py','exec'),state)
            self.assertEqual(state['row']['Szerződésen kívüli bónusz'],summary['other_route_bonus_huf'])

    def test_workbook_two_column_sheet_is_recognized_and_preserves_zero(self):
        title = 'Out_of_contract_Bonus Routes'
        rows = [ImportedExcelRow('session', i, title, i, {'column_1': name, 'column_2': amount})
                for i, (name, amount) in enumerate([('Driver', 'Bonus'), ('Minta 1234 Futár', 12500), ('Másik Futár', 0)], 1)]
        parsed = _parse_name_identified_sheet(rows, detect_sheet_type_from_name(title), DEFAULT_PARSERS)
        self.assertEqual(parsed.records, [{'Driver': 'Minta 1234 Futár', 'Bonus': 12500}, {'Driver': 'Másik Futár', 'Bonus': 0}])

    def test_special_bonus_is_not_also_added_as_imported_bonus(self):
        records = [
            {'source_sheet': 'Out_of_contract_Bonus Routes', 'normalized_data': {'Driver': 'Minta 1234 Futár', 'Bonus': 12500}},
            {'source_sheet': 'Out_of_contract_Bonus Routes', 'normalized_data': {'Driver': 'Másik 5678 Futár', 'Bonus': 0}},
            {'source_sheet': 'Bonus Routes', 'normalized_data': {'Driver': 'Minta 1234 Futár', 'Bonus': 3000}},
        ]
        ns = load_bonus_functions(records)
        totals = ns['load_excel_stop_count_bonus_totals']('session')
        self.assertEqual(totals['stop_count_bonus_huf'].sum(), 12500)
        self.assertEqual(len(totals), 2)
        imported = ns['load_imported_balance_components']('session')
        self.assertEqual(imported['Importált bónusz'].sum(), 3000)

    def test_unrelated_bonus_sheet_is_not_reclassified(self):
        self.assertTrue(is_out_of_contract_bonus_sheet('Out of contract Bonus Routes'))
        self.assertFalse(is_out_of_contract_bonus_sheet('Bonus Routes'))

    def test_pwa_reads_special_bonus_separately_from_general_bonus(self):
        records = [
            {'source_sheet': 'Out_of_contract_Bonus Routes', 'normalized_data': {'Driver': '1234', 'Bonus': 12500}},
            {'source_sheet': 'Bonus Routes', 'normalized_data': {'Driver': '1234', 'Bonus': 3000}},
        ]
        def read(table, **options):
            if table != 'bonus_route_row': return []
            return [r for r in records if 'source_sheet' not in options['params'] or options['params']['source_sheet'] == 'eq.' + r['source_sheet']]
        ns = dict(optional_supabase_rows=read,
                  imported_balance_payload=lambda row: row['normalized_data'],
                  imported_balance_matches_courier=lambda payload, cid, name: payload['Driver'] == cid,
                  imported_balance_amount=lambda payload, *keys: payload['Bonus'],
                  imported_balance_note=lambda payload: '',
                  signed_item=lambda key, label, amount, **kwargs: dict(amountHuf=amount))
        tree = ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'read_imported_bonus_malus_items', 'read_out_of_contract_bonus_amount'}]
        for node in nodes: node.decorator_list = []
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])), 'pwa_api.py', 'exec'), ns)
        bonus, malus = ns['read_imported_bonus_malus_items']('session','1234','Minta')
        self.assertEqual(sum(row['amountHuf'] for row in bonus),3000)
        self.assertEqual(malus,[])
        self.assertEqual(ns['read_out_of_contract_bonus_amount']('session','1234','Minta'),12500)


if __name__ == '__main__': unittest.main()
