"""Candidate selection without importing browser/DB dependencies."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any


class CandidatesTest(unittest.TestCase):
    def read(self, rows):
        source = Path(__file__).resolve().parents[1] / 'scripts/run_giriton_overlap_fallback.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {'clean', 'read_candidates'}]
        scope = {'json': json, 'Path': Path, 'Any': Any}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'failures.json'
            path.write_text(json.dumps(rows), encoding='utf-8')
            return scope['read_candidates'](path)

    def row(self, reason, **changes):
        return dict(work_date='2026-11-18', warehouse='BUD1', courier_id=9458,
                    muszakpro_shift_start='07:45:00', hub_slot_from='07:45:00',
                    match_diff_minutes=0, reason=reason, **changes)

    def test_routes_requested_rejections_and_api_errors(self):
        for reason in ['hub_api_rejected_overlap', 'hub_api_rejected_already_assigned',
                       'api_booking_failed HTTPError: 400 Client Error: Bad Request']:
            with self.subTest(reason=reason):
                result = self.read([self.row(reason)])
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['reason'], reason)
                self.assertEqual(result[0]['shift_start'], '07:45:00')

    def test_capacity_skips_and_other_rejections_are_not_routed(self):
        for reason in ['no_free_slot block', 'hub_block_not_open block', 'already_booked',
                       'hub_api_rejected_unknown', 'missing_exact_hub_block BUD1 07:45:00']:
            self.assertEqual(self.read([self.row(reason)]), [])

    def test_preserves_exact_match_and_duplicate_guards(self):
        row = self.row('hub_api_rejected_already_assigned')
        self.assertEqual(len(self.read([row, row])), 1)
        self.assertEqual(self.read([{**row, 'hub_slot_from': '08:00:00'}]), [])
        self.assertEqual(self.read([{**row, 'match_diff_minutes': 15}]), [])
        self.assertEqual(self.read([{**row, 'courier_id': ''}]), [])


if __name__ == '__main__':
    unittest.main()
