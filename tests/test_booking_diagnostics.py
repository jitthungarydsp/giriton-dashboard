import ast
import collections
import re
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class BookingDiagnosticsTest(unittest.TestCase):
    def build(self, mp, hub=(), failures=(), logs=()):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'scripts/export_booking_diagnostics_sheet.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'clock', 'stamp', 'identity', 'key', 'build_diagnostics', 'sheet_values'}]
        data = {'bookings': mp, 'courier_hub_shift_bookings_raw': list(hub), 'hub_autobooking_failures': list(failures), 'ops_giriton_auto_booking_log': list(logs)}
        ns = {'re': re, 'datetime': datetime, 'ZoneInfo': ZoneInfo, 'collections': collections,
              'read': lambda table, *args: data[table]}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'diagnostics.py', 'exec'), ns)
        return ns['build_diagnostics'](date(2026, 11, 2), date(2026, 11, 5))

    def mp(self, **kwargs):
        return {'work_date': '2026-11-02', 'warehouse': 'BUD1', 'courier_id': 9311,
                'courier_name': 'Futár', 'shift_text': 'BUD1_14:45', 'status': 'ACTIVE', **kwargs}

    def test_overlap_is_a_failure_even_after_later_candidate_selection(self):
        common = {'work_date': '2026-11-02', 'warehouse': 'BUD1', 'courier_id': 9311, 'shift_start': '14:45'}
        logs = [common | {'status': 'HUB_API_REJECTED_OVERLAP', 'message': 'Hub API rejected booking: overlap', 'created_at': '2026-10-28T13:00:00+00:00'},
                common | {'status': 'CANDIDATE_SELECTED_EXACT', 'message': 'selected', 'created_at': '2026-10-28T14:00:00+00:00'}]
        result = self.build([self.mp()], logs=logs)
        self.assertEqual(result['rows'][0][7], 'Átfedés – Hub elutasította')
        self.assertEqual(result['rows'][0][11], 'HUB_API_REJECTED_OVERLAP')

    def test_daily_capacity_failure_is_not_attributed_to_the_wrong_slot(self):
        failure = {'work_date': '2026-11-02', 'warehouse': 'BUD1', 'courier_id': 9311,
                   'muszakpro_shift_start': '14:45', 'reason': 'no_free_slot 2026-11-02:246:12:30:47', 'run_at': '2026-10-28T13:00:00+00:00'}
        row = self.build([self.mp()], failures=[failure])['rows'][0]
        self.assertEqual(row[7], 'Napi foglalás másik műszakon elakadt')
        self.assertIn('12:30', row[8])

    def test_existing_exact_booking_is_not_reported_from_an_old_failure(self):
        hub = {'work_date': '2026-11-02', 'warehouse_code': 'BUD1', 'courier_id': 9311, 'slot_from': '14:45:00'}
        self.assertEqual(self.build([self.mp()], hub=[hub])['rows'], [])

    def test_empty_report_keeps_a_visible_result_below_the_frozen_header(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts/export_booking_diagnostics_sheet.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        ns = {}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sheet_values'], type_ignores=[]), 'diagnostics.py', 'exec'), ns)
        payload = self.build([])
        values = ns['sheet_values'](payload, date(2026, 11, 2), date(2026, 11, 5))
        self.assertEqual(len(values), 5)
        self.assertTrue(all(len(row) == 16 for row in values))
        self.assertIn('Nincs eltérés', values[-1][0])

    def test_unknown_identity_is_not_labelled_missing_and_hub_only_is_included(self):
        hub = {'work_date': '2026-11-02', 'warehouse_code': 'BUD1', 'courier_id': 7440, 'slot_from': '18:30'}
        rows = self.build([self.mp(courier_id=None, email='unknown@example.com')], hub=[hub])['rows']
        self.assertEqual({r[7] for r in rows}, {'MP-futárazonosító hiányzik', 'Csak Hubon szereplő kezdés'})


if __name__ == '__main__':
    unittest.main()
