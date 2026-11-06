import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


# These tests exercise only the Sheets writer, without a Streamlit/DB runtime.
db_stub = types.ModuleType("resources.supabase_raw")
db_stub.get_supabase_config = Mock()
db_stub.raise_for_supabase_error = Mock()
spec = importlib.util.spec_from_file_location(
    "capacity_sheet_export_under_test",
    Path(__file__).resolve().parents[1] / "scripts/export_courier_hub_shift_block_capacity_sheet.py",
)
export = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"resources.supabase_raw": db_stub}):
    spec.loader.exec_module(export)


class CapacitySheetExportTest(unittest.TestCase):
    def setUp(self):
        self.sheet = Mock(id=30983345, row_count=6, col_count=26)
        self.book = Mock()

    def row(self, key):
        return export.row_to_sheet_row({"block_key": key, "muszakpro_booking": None}, "now")

    def written_rows(self):
        requests = self.book.batch_update.call_args.args[0]["requests"]
        return requests[-1]["updateCells"]

    def test_values_follow_block_keys_when_order_changes_and_new_rows_arrive(self):
        self.sheet.batch_get.return_value = [
            [["block-a"], ["block-b"], ["removed"]],
            [["D9070"], ["D9413"], ["D0001"]],
        ]
        export.write_capacity_rows(self.book, self.sheet, [export.HEADER,
            self.row("block-b"), self.row("new"), self.row("block-a")])
        update = self.written_rows()
        self.assertEqual(update["rows"][1]["values"][17], {"userEnteredValue": {"stringValue": "D9413"}})
        self.assertEqual(update["rows"][2]["values"][17], {})
        self.assertEqual(update["rows"][3]["values"][17], {"userEnteredValue": {"stringValue": "D9070"}})
        # Old A:S rows are cleared in the same request; T:Z and formatting survive.
        self.assertEqual(update["range"]["endRowIndex"], 6)
        self.assertEqual(update["range"]["endColumnIndex"], 19)
        self.assertEqual(update["fields"], "userEnteredValue")
        self.sheet.clear.assert_not_called()

    def test_blank_zero_and_formula_values_survive_without_hub_fallback(self):
        self.sheet.batch_get.return_value = [
            [["blank"], ["zero"], ["formula"]], [[], [0], ['=IF(1=1,"D9070","")']],
        ]
        rows = [export.HEADER, self.row("blank"), self.row("zero"), self.row("formula")]
        rows[1][17] = "stale DB value"
        export.write_capacity_rows(self.book, self.sheet, rows)
        values = [r["values"][17] for r in self.written_rows()["rows"][1:]]
        self.assertEqual(values, [{}, {"userEnteredValue": {"numberValue": 0}},
            {"userEnteredValue": {"formulaValue": '=IF(1=1,"D9070","")'}}])

    def test_failed_read_never_erases_existing_sheet(self):
        self.sheet.batch_get.side_effect = RuntimeError("Sheets unavailable")
        with self.assertRaises(RuntimeError):
            export.write_capacity_rows(self.book, self.sheet, [export.HEADER, self.row("a")])
        self.book.batch_update.assert_not_called()
        self.sheet.clear.assert_not_called()

    def test_duplicate_keys_abort_before_write(self):
        for existing, outgoing in [([["a"], ["a"]], ["a"]), ([["a"]], ["a", "a"])]:
            with self.subTest(existing=existing, outgoing=outgoing):
                self.sheet.batch_get.return_value = [existing, [["D9070"]]]
                with self.assertRaises(RuntimeError):
                    export.write_capacity_rows(self.book, self.sheet,
                        [export.HEADER, *[self.row(k) for k in outgoing]])
                self.book.batch_update.assert_not_called()

    def test_expansion_and_update_are_one_atomic_request(self):
        self.sheet.row_count = 1
        export.write_capacity_rows(self.book, self.sheet, [export.HEADER, self.row("new")])
        requests = self.book.batch_update.call_args.args[0]["requests"]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["updateSheetProperties"]["properties"]["gridProperties"]["rowCount"], 2)
        self.book.batch_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
