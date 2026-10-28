import ast
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def functions(file, names, namespace):
    tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(file), 'exec', flags=0x1000000), namespace)
    return namespace


class Rejected(Exception):
    def __init__(self, reason, payload=None):
        self.reason = reason


class ExactRowBookingTest(unittest.TestCase):
    def row(self, start, courier=7440):
        return SimpleNamespace(work_date='2026-11-03', warehouse='BUD1', courier_id=courier,
                               shift_start=start, timestamp_text='2026-10-25', source_row=1)

    def block(self, start, free=1):
        return SimpleNamespace(slot_from=start, status='OPEN', free_slots=free, block_key=start, shift_template_id=1)

    def run_rows(self, rows, blocks, book=None, dry_run=False, existing=()):
        calls = []
        def booking(row, block, **kw):
            calls.append((row.shift_start, block.slot_from, kw))
            return book(row, block) if book else True
        def failures(rows, reason, matches):
            return [{'reason': reason, 'courier_id': rows[0].courier_id,
                     'work_date': rows[0].work_date, 'warehouse': rows[0].warehouse,
                     'muszakpro_shift_start': rows[0].shift_start,
                     'hub_slot_from': matches[0][1].slot_from if matches else '', 'match_diff_minutes': 0}]
        ns = {'defaultdict': defaultdict, 'parse_timestamp': str, 'book_one': booking,
              'HubApiBookingRejected': Rejected, 'failure_records_for_group': failures}
        functions('scripts/hub_job_autobooking.py', {'run_exact_bookings'}, ns)
        keyed = {('2026-11-03', 'BUD1', block.slot_from): block for block in blocks}
        args = SimpleNamespace(max_courier_days=300, base_url='invalid', dsp_id=8)
        with redirect_stdout(io.StringIO()):
            result = ns['run_exact_bookings'](rows, keyed, set(existing), args, dry_run)
        return result, calls

    def test_every_row_including_single_or_middle_shift_is_independent(self):
        starts = ['05:00:00', '09:00:00', '13:00:00']
        result, calls = self.run_rows([self.row(s) for s in starts], [self.block(s) for s in starts])
        self.assertEqual(result['booked_rows'], 3)
        self.assertEqual([c[0] for c in calls], starts)
        single, _ = self.run_rows([self.row(starts[0])], [self.block(starts[0])])
        self.assertEqual(single['booked_rows'], 1)

    def test_nearby_alternative_is_never_selected(self):
        result, calls = self.run_rows([self.row('05:00:00')], [self.block('05:15:00')])
        self.assertEqual(calls, [])
        self.assertTrue(result['failure_records'][0]['reason'].startswith('missing_exact_hub_block'))

    def test_one_full_shift_does_not_block_another_shift(self):
        result, calls = self.run_rows([self.row('05:00:00'), self.row('09:00:00')], [self.block('05:00:00', 0), self.block('09:00:00')])
        self.assertEqual(result['booked_rows'], 1)
        self.assertEqual(calls[0][0], '09:00:00')

    def test_overlap_is_exported_once_and_does_not_become_success(self):
        def overlap(*args):
            raise Rejected('overlap')
        row = self.row('09:30:00')
        result, calls = self.run_rows([row, row], [self.block(row.shift_start)], book=overlap)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['booked_rows'], 0)
        self.assertEqual(result['failed_booking_rows'], 1)
        self.assertEqual(result['failure_records'][0]['reason'], 'hub_api_rejected_overlap')
        ns = {'json': json, 'Path': Path}
        functions('scripts/run_giriton_overlap_fallback.py', {'clean', 'read_candidates'}, ns)
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'failures.json'
            p.write_text(json.dumps(result['failure_records']), encoding='utf-8')
            self.assertEqual(ns['read_candidates'](p)[0]['shift_start'], row.shift_start)

    def test_dry_run_counts_plans_without_reporting_real_bookings(self):
        result, calls = self.run_rows([self.row('05:00:00', 1), self.row('05:00:00', 2)], [self.block('05:00:00')], dry_run=True)
        self.assertEqual(result['booked_rows'], 0)
        self.assertEqual(result['simulated_rows'], 1)
        self.assertEqual(len(calls), 1)

    def test_existing_booking_is_not_rebooked(self):
        result, calls = self.run_rows([self.row('05:00:00')], [self.block('05:00:00')], existing=[('2026-11-03', 7440, 'BUD1', '05:00:00')])
        self.assertEqual(calls, [])
        self.assertEqual(result['booked_rows'], 0)

    def test_execution_guard_rejects_alternative_before_request(self):
        ns = {'re': re, 'clean_text': lambda v: str(v or '')}
        functions('scripts/hub_job_autobooking.py', {'book_one', 'normalize_db_time'}, ns)
        with self.assertRaises(ValueError):
            ns['book_one'](self.row('05:00:00'), self.block('05:15:00'), base_url='invalid', dsp_id=8, dry_run=False, match_kind='alternative', match_diff=15)

    def test_http_200_overlap_is_rejected_without_success_log(self):
        statuses = []
        ns = {'re': re, 'clean_text': lambda v: str(v or ''), 'HubApiBookingRejected': Rejected,
              'args_for_log': lambda *a: None, 'build_assign_url': lambda *a: 'invalid',
              'normalize_warehouse_id': lambda v: 1,
              'hub_request': lambda *a, **kw: SimpleNamespace(ok=True, status_code=200),
              'response_payload': lambda r: {'results': [{'decision': 'REJECTED', 'reason': 'OVERLAP'}]},
              'log_result': lambda args, status, *rest: statuses.append(status)}
        functions('scripts/hub_job_autobooking.py', {'book_one', 'normalize_db_time'}, ns)
        with redirect_stdout(io.StringIO()), self.assertRaises(Rejected) as error:
            ns['book_one'](self.row('05:00:00'), self.block('05:00:00'), base_url='invalid', dsp_id=8, dry_run=False, match_kind='exact', match_diff=0)
        self.assertEqual(error.exception.reason, 'overlap')
        self.assertEqual(statuses, ['HUB_API_REJECTED_OVERLAP'])

    def test_fallback_rejects_non_overlap_and_alternative_records(self):
        ns = {'json': json, 'Path': Path}
        functions('scripts/run_giriton_overlap_fallback.py', {'clean', 'read_candidates'}, ns)
        base = {'work_date': '2026-11-03', 'warehouse': 'BUD1', 'courier_id': 7440, 'muszakpro_shift_start': '05:00', 'hub_slot_from': '05:00', 'reason': 'hub_api_rejected_overlap'}
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'candidates.json'
            p.write_text(json.dumps([base | {'reason': 'no_free_slot'}, base | {'hub_slot_from': '05:15', 'match_diff_minutes': 15}]), encoding='utf-8')
            self.assertEqual(ns['read_candidates'](p), [])

    def test_legacy_alternative_selection_returns_no_candidates(self):
        ns = {}
        functions('scripts/select_shift_auto_booking_candidates.py', {'select_candidates'}, ns)
        with redirect_stdout(io.StringIO()):
            result = ns['select_candidates'](start_date=date(2026, 11, 2), end_date=date(2026, 11, 5), match_kind='alternative', tolerance_minutes=30, limit=100, source_limit=1000)
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
