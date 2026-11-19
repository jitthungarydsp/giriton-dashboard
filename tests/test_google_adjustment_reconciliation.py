import ast
from datetime import date
import importlib.util
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
stub = ModuleType("resources.supabase_raw")
stub.get_supabase_config = lambda: ("", "")
stub.raise_for_supabase_error = lambda response: response.raise_for_status()
spec = importlib.util.spec_from_file_location(
    "google_adjustment_reconciliation", ROOT / "scripts/refresh_google_adjustment_snapshots.py"
)
refresh = importlib.util.module_from_spec(spec)
with patch.dict("sys.modules", {"resources.supabase_raw": stub}):
    spec.loader.exec_module(refresh)

MONTH = date(2026, 10, 1)


def google_row(row_id, amount, note="", *, kind="malus", active=True):
    return {
        "id": row_id, "courier_id": "7644", "adjustment_type": kind, "amount_huf": amount,
        "valid_from": "2026-10-10", "valid_to": "2026-10-31", "note": note,
        "source_key": f"google_bonus_malus:sheet:tab:{row_id}", "is_active": active,
    }


class GoogleAdjustmentReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.active = [google_row("new", 15000)]
        self.old = []
        self.base = {"id": "base", "courier_id": "7644", "period_start": str(MONTH), "metadata": {}}
        self.original = [
            {"section": "finance", "item_key": key, "amount_value": amount,
             "amount_kind": "huf", "display_order": index}
            for index, (key, amount) in enumerate({
                "income": 350000, "deductions": -200000, "correction": 10000,
                "correction_income": 10000, "payable": 160000, "salary_advance": -200000,
            }.items())
        ]
        self.calls = []

    def rows(self, table, params):
        if table == "courier_settlement_adjustment":
            return self.active
        if table == "courier_finance_snapshot":
            return [self.base] if self.base else []
        if table == "courier_finance_snapshot_source":
            return [
                {"source_key": "manual_adjustments", "source_table": "adjustment", "row_count": len(self.old), "payload": self.old},
                {"source_key": "working_row", "source_table": "finance", "row_count": 1, "payload": {"Kifizetendő": 160000}},
            ]
        if table == "courier_finance_snapshot_item":
            return self.original
        raise AssertionError(table)

    def reconcile(self, result="saved"):
        def write(table, payload, **_options):
            self.calls.append((table, payload))
            return result

        with patch.object(refresh, "_rows", side_effect=self.rows), patch.object(refresh, "_write", side_effect=write), \
                patch.object(refresh, "_rebuild_tig", side_effect=lambda _items, _sources, _old, payable: payable):
            return refresh.refresh_finance_snapshot("7644", MONTH)

    def test_retries_already_imported_row_and_keeps_unrelated_deduction(self):
        self.assertEqual(self.reconcile(), ("saved", ""))
        table, params = self.calls[0]
        self.assertEqual(table, "rpc/publish_google_adjustment_snapshot")
        self.assertEqual(params["p_base_id"], "base")
        values = {row["item_key"]: row["amount_value"] for row in params["p_items"]}
        self.assertEqual(values["salary_advance"], -200000)
        self.assertEqual(values["manual_malus"], -15000)
        self.assertEqual(values["payable"], 145000)
        self.assertEqual(params["p_metadata"]["tig_final_total"], 145000)
        self.assertEqual(params["p_sources"][1]["payload"]["Kifizetendő"], 145000)

    def test_same_sum_with_changed_row_is_reconciled_and_next_run_is_unchanged(self):
        self.active.append(google_row("old", 15000, active=False))
        self.old = [google_row("old", 15000)]
        for item in self.original:
            if item["item_key"] in {"deductions", "payable"}:
                item["amount_value"] -= 15000
        self.original.append({"section": "finance", "item_key": "manual_malus", "amount_value": -15000})
        self.assertEqual(self.reconcile(), ("saved", ""))
        self.old = self.calls[0][1]["p_sources"][0]["payload"]
        self.calls.clear()
        self.assertEqual(self.reconcile(), ("unchanged", ""))
        self.assertFalse(self.calls)

    def test_correction_delta_is_counted_once(self):
        self.active = [google_row("corr", 15000, kind="correction_deduction")]
        self.reconcile()
        params = self.calls[0][1]
        values = {row["item_key"]: row["amount_value"] for row in params["p_items"]}
        self.assertEqual((values["deductions"], values["correction"], values["payable"]), (-200000, -5000, 145000))

    def test_invoice_protection_logs_the_calculated_difference_for_admin(self):
        outcome, _message = self.reconcile("invoiced")
        self.assertEqual(outcome, "review")
        table, row = self.calls[-1]
        self.assertEqual(table, "google_adjustment_review")
        self.assertEqual((row["reason"], row["previous_payable_huf"], row["proposed_payable_huf"]),
                         ("invoiced", 160000, 145000))

    def test_missing_base_remains_visible(self):
        self.base = None
        self.assertEqual(self.reconcile()[0], "review")
        self.assertEqual(self.calls[0][1]["reason"], "no_snapshot")

    def test_candidate_months_include_inactive_rows_and_respect_date_bounds(self):
        tree = ast.parse((ROOT / "scripts/import_google_bonus_malus_adjustments.py").read_text(encoding="utf-8"))
        func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "reconciliation_periods")
        namespace = {"date": date}
        exec(compile(ast.Module(body=[func], type_ignores=[]), "<reconciliation periods>", "exec"), namespace)
        old = {"google:old": {"valid_from": "2026-10-03", "courier_id": "1", "is_active": False},
               "google:other": {"valid_from": "2026-09-02", "courier_id": "2"}}
        prepared = [("google:new", {"valid_from": "2026-10-20", "courier_id": "3"})]
        result = namespace[func.name](prepared, old, "google:", MONTH, date(2026, 10, 31))
        self.assertEqual(result, {("1", MONTH), ("3", MONTH)})
