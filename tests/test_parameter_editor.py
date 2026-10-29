"""Real Streamlit regression: selecting another bonus rule must hydrate its form."""
import ast
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def editor_app_source():
    tree = ast.parse((ROOT / 'page/settlement_parameter_catalog.py').read_text(encoding='utf-8'))
    names = {'_clean', '_text', '_number', '_int', '_date', '_index', '_money', '_range', '_editor_row', '_common_period', '_show_performance'}
    constants = {'DAY_LABELS', 'ROUTE_LABELS', 'UNIT_LABELS', 'CALCULATION_MODE_LABELS'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    source = 'from __future__ import annotations\nfrom typing import Any\nfrom datetime import date\nimport pandas as pd\nimport streamlit as st\n'
    source += '\n'.join(ast.unparse(n) for n in nodes)
    source += '''
rows = [dict(id='rule-a', level_code='LEVEL-2', day_type='any', route_type='express', calculation_mode='excel', company_amount_huf=750, courier_amount_huf=500, valid_from='2026-05-01', valid_to=None, is_active=True, priority=100), dict(id='rule-b', level_code='LEVEL-1', day_type='normal', route_type='normal', calculation_mode='excel', company_amount_huf=3000, courier_amount_huf=3000, valid_from='2026-06-01', valid_to=None, is_active=True, priority=100)]
for row in rows:
    for field in ['threshold_min','threshold_max','duration_min_hours','duration_max_hours']:
        row[field] = None
read_items = lambda client, table: pd.DataFrame(rows)
_excel_source_headers = lambda client: ['Compliance Bonus']
_delete_control = lambda *args: None
_actor = lambda: 'test'
_mark_parameters_changed = lambda client: None
validate_performance_rule = lambda payload: payload

def save_item(client, table, payload, actor, item_id):
    st.session_state['saved_item'] = dict(id=item_id, **payload)

_show_performance(None, 'compliance', 'Compliance', 'compliance')
'''
    return source


class ParameterEditorTest(unittest.TestCase):
    def test_select_edit_save_and_new(self):
        app = AppTest.from_string(editor_app_source()).run()
        self.assertFalse(app.exception)
        app.selectbox(key='compliance_select').select('LEVEL-2 · 2026-05-01 · rule-a').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='compliance_form_rule-a_Szint').value, 'LEVEL-2')
        self.assertEqual(app.selectbox(key='compliance_form_rule-a_Naptípus').value, 'any')
        self.assertEqual(app.number_input(key='compliance_form_rule-a_JITT összege (Ft)').value, 750)
        app.number_input(key='compliance_form_rule-a_JITT összege (Ft)').set_value(666)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['saved_item']['id'], 'rule-a')
        self.assertEqual(app.session_state['saved_item']['company_amount_huf'], 666)
        self.assertIsNone(app.session_state['saved_item']['valid_to'])
        app.selectbox(key='compliance_select').select('LEVEL-1 · 2026-06-01 · rule-b').run()
        self.assertEqual(app.text_input(key='compliance_form_rule-b_Szint').value, 'LEVEL-1')
        self.assertEqual(app.number_input(key='compliance_form_rule-b_JITT összege (Ft)').value, 3000)
        app.selectbox(key='compliance_select').select('Új tétel').run()
        self.assertEqual(app.text_input(key='compliance_form_new_Szint').value, '')
        self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
