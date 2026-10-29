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


class ComplaintManagementTest(unittest.TestCase):
    def functions(self, role, db):
        from uuid import UUID
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'pwa_api.py').read_text(encoding='utf-8'))
        names = {'quality_complaint_manager', 'manage_quality_complaint', 'list_quality_complaints'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for node in nodes:
            node.decorator_list = []
        ns = dict(Any=Any, UUID=UUID, QualityComplaintActionRequest=Any,
                  Cookie=lambda **k: None, Query=lambda **k: k.get('default'),
                  require_user=lambda _: {'username': 'Operator', 'role': role},
                  courier_identity=lambda _: ('6498', 'Futár'),
                  HTTPException=ApiError, supabase_rest=db)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'management', 'exec'), ns)
        return ns

    def test_admin_only_mutations(self):
        for role in ['courier', 'coordinator', 'hr']:
            ns = self.functions(role, lambda *a, **k: self.fail('Unauthorized DB write'))
            with self.assertRaises(ApiError) as error:
                ns['manage_quality_complaint']('id', SimpleNamespace(action='close', message='Válasz', reference=''))
            self.assertEqual(error.exception.status_code, 403)

    def test_close_requires_text_and_forward_requires_reference(self):
        ns = self.functions('admin', lambda *a, **k: self.fail('Invalid DB write'))
        for action in ['close', 'reply', 'forward']:
            with self.assertRaises(ApiError) as error:
                ns['manage_quality_complaint']('id', SimpleNamespace(action=action, message='', reference=''))
            self.assertEqual(error.exception.status_code, 422)

    def test_confirmed_admin_close_and_identity(self):
        calls = []
        def db(*args, **kwargs):
            calls.append((args, kwargs))
            return [{'id': 'id', 'status': 'closed'}]
        ns = self.functions('admin', db)
        result = ns['manage_quality_complaint']('id', SimpleNamespace(action='close', message='Megvizsgáltuk.', reference=''))
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0][0], ('POST', 'rpc/pwa_manage_quality_complaint'))
        self.assertEqual(calls[0][1]['payload']['p_actor'], 'Operator')

    def test_courier_cannot_read_other_couriers(self):
        calls = []
        def db(*args, **kwargs):
            calls.append(kwargs)
            return []
        result = self.functions('courier', db)['list_quality_complaints']()
        self.assertFalse(result['canManage'])
        self.assertEqual(calls[0]['params']['courier_id'], 'eq.6498')


if __name__ == '__main__':
    unittest.main()
