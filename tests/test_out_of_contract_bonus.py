import ast
import json
from pathlib import Path
import re
import sys
import types
import unicodedata
import unittest

import pandas as pd
from resources.out_of_contract_bonus import is_out_of_contract_bonus_sheet
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
