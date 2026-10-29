import ast
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class ApiError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


class QualityComplaintTest(unittest.TestCase):
    def function(self, db):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'pwa_api.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_quality_complaint')
        node.decorator_list = []
        ns = dict(QualityComplaintRequest=Any, Cookie=lambda **k: None, date=date,
                  require_user=lambda _: {'username': 'courier'},
                  courier_identity=lambda _: ('6498', 'Futár'),
                  parse_month=lambda m: date.fromisoformat(m + '-01'),
                  HTTPException=ApiError, supabase_rest=db)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'quality_complaints', 'exec'), ns)
        return ns['create_quality_complaint']

    def payload(self, **changes):
        values = dict(request_id='request', month='2026-10', topic='lateShift',
                      message='Indoklás', items=[{'date': '2026-10-13', 'label': '08:45–13:15'}])
        return SimpleNamespace(**(values | changes))

    def test_identity_from_session_and_confirmed_insert(self):
        calls = []
        def db(method, table, **kwargs):
            calls.append((method, table, kwargs))
            return [{'id': 'saved', 'created_at': 'now'}]
        self.assertEqual(self.function(db)(self.payload())['id'], 'saved')
        self.assertEqual(calls[0][1], 'pwa_quality_complaints')
        self.assertEqual(calls[0][2]['payload']['courier_id'], '6498')
        self.assertEqual(calls[0][2]['payload']['affected_items'][0]['date'], '2026-10-13')

    def test_retry_reads_existing_record(self):
        calls = []
        def db(method, table, **kwargs):
            calls.append(method)
            return [] if method == 'POST' else [{'id': 'existing'}]
        self.assertEqual(self.function(db)(self.payload())['id'], 'existing')
        self.assertEqual(calls, ['POST', 'GET'])

    def test_no_false_success_and_wrong_month_rejected(self):
        fn = self.function(lambda *a, **k: [])
        with self.assertRaises(ApiError) as error:
            fn(self.payload())
        self.assertEqual(error.exception.status_code, 502)
        with self.assertRaises(ApiError) as error:
            fn(self.payload(items=[{'date': '2026-11-01'}]))
        self.assertEqual(error.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()
