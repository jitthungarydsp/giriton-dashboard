import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "resources" / "shift_operation_results.py"
SPEC = importlib.util.spec_from_file_location("shift_operation_results", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
shift_operation_results = MODULE.shift_operation_results


class ShiftOperationResultsTests(unittest.TestCase):
    def test_external_deletions_resolve_names_and_separate_warehouses(self):
        def read(table, params):
            if table == "courier_hub_courier_identity_raw":
                self.assertEqual(params["dsp_id"], "eq.8")
                return [{"email": "courier@example.invalid", "name_without_identifier": "Futár Minta"}]
            self.assertEqual(table, "external_shift_deletion_requests")
            self.assertEqual(params["warehouse"], "in.(BUD1,BUD2)")
            self.assertIn("processed_at.lt.2026-11-30T23:00:00+00:00", params["and"])
            return [
                {"warehouse": "BUD1", "deletion_status": "deleted"},
                {"warehouse": "BUD1", "deletion_status": "pending"},
                {"warehouse": "BUD2", "deletion_status": "error", "email": "Courier@example.invalid",
                 "message": "HTTP 409: Past shift blocks are read-only."},
                {"warehouse": "BUD3", "deletion_status": "error"},
            ]

        bud1, bud2 = shift_operation_results(
            read, "deletion", ["BUD1", "BUD2"],
            "2026-10-31T23:00:00+00:00", "2026-11-30T23:00:00+00:00", 8,
        )
        self.assertEqual((bud1["succeeded"], bud1["failed"]), (1, 0))
        self.assertEqual((bud2["succeeded"], bud2["failed"]), (0, 1))
        failure = bud2["failures"][0]
        self.assertEqual(failure["courierName"], "Futár Minta")
        self.assertIn("műszak elmúlt", failure["reason"])
        self.assertNotIn("example.invalid", str(failure))

    def test_booking_counts_live_attempts_and_paginates(self):
        def read(table, params):
            self.assertEqual(table, "ops_giriton_auto_booking_log")
            self.assertEqual(params["warehouse"], "in.(BUD2)")
            self.assertEqual(params["response_json->>booking_engine"], "eq.hub_api")
            if params["offset"] == "0":
                return [{"warehouse": "BUD2", "status": "COURIER_ADDED"}] * 1000
            self.assertEqual(params["offset"], "1000")
            return [
                {"warehouse": "BUD2", "status": "HUB_AUTOBOOK_DRY_RUN_OK"},
                {"warehouse": "BUD2", "status": "ALREADY_BOOKED"},
                {"warehouse": "BUD2", "status": "HUB_API_REJECTED_OVERLAP", "courier_name": "Futár Minta"},
            ]

        [bud2] = shift_operation_results(read, "booking", ["BUD2"], "start", "end", 8)
        self.assertEqual((bud2["succeeded"], bud2["failed"]), (1000, 1))
        self.assertIn("Átfedés", bud2["failures"][0]["reason"])
