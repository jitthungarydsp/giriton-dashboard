import ast
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


class RobotlogRejectionsTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'resources/giriton_auto_booking.py').read_text(encoding='utf-8'))
        names = {'booking_rejection_reason', 'robotlog_row_allowed', '_append_success_robotlog', 'log_giriton_booking_result'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.ns = {'clean': lambda v: str(v or '').strip(),
                   'ROBOTLOG_SHEET_STATUSES': {'COURIER_ADDED', 'ALREADY_BOOKED', 'COURIER_DELETED'}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'booking.py', 'exec'), self.ns)

    def test_nested_http_200_overlap_is_not_a_success(self):
        payload = {'hub_response': {'hubResponse': {'results': [{'decision': 'REJECTED', 'reason': 'OVERLAP'}]}}}
        self.assertFalse(self.ns['robotlog_row_allowed']({'status': 'COURIER_ADDED', 'response_json': payload}))
        self.assertEqual(self.ns['_append_success_robotlog'](payload, 'COURIER_ADDED'), 'SKIPPED_STATUS')

    def test_rejected_status_is_not_exported(self):
        self.assertFalse(self.ns['robotlog_row_allowed']({'status': 'HUB_API_REJECTED_OVERLAP'}))

    def test_genuine_acceptance_is_preserved(self):
        payload = {'results': [{'decision': 'ACCEPTED', 'reason': None}]}
        self.assertTrue(self.ns['robotlog_row_allowed']({'status': 'COURIER_ADDED', 'response_json': payload}))
        self.assertTrue(self.ns['robotlog_row_allowed']({'status': 'COURIER_DELETED'}))

    def test_mislabelled_success_is_stored_as_rejection_with_original_evidence(self):
        written = []
        self.ns.update({
            'datetime': datetime, 'uuid4': lambda: 'id', 'LOG_TABLE': 'log',
            'ROBOTLOG_SUCCESS_STATUSES': {'COURIER_ADDED'},
            '_supabase_headers': lambda: ('https://example.invalid', {}),
            '_legacy_candidate_serial': lambda row: 'serial',
            '_is_missing_table_response': lambda response: False,
            'raise_for_supabase_error': lambda response: None,
            'requests': SimpleNamespace(post=lambda url, **kw: written.extend(kw['json'])),
        })
        payload = {'hub_response': {'results': [{'decision': 'REJECTED', 'reason': 'OVERLAP'}]}}
        self.ns['log_giriton_booking_result'](payload, 'COURIER_ADDED', 'HTTP 200')
        self.assertEqual(written[0]['status'], 'HUB_API_REJECTED_OVERLAP')
        self.assertEqual(written[0]['response_json'], payload)
        self.assertFalse(self.ns['robotlog_row_allowed'](written[0]))


if __name__ == '__main__':
    unittest.main()
