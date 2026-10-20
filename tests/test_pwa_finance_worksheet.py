import ast
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from resources.pwa_finance_worksheet import prepare_worksheet, require_pilot, worksheet_state


def snapshot():
    values = {"base": 100000, "tip": 20000, "monthly_bonus": 1000, "monthly_malus": -500,
              "manual_bonus": 1000, "manual_malus": 0, "customer_rating": 5000,
              "correction_income": 10000, "correction_deduction": -1000,
              "payable": 135500, "income": 127000, "deductions": -500, "correction": 9000,
              "kiflis_bonus_malus": 500, "bonus_malus": 1000,
              "base_detail_1": 100000, "kiflis_bonus_1": 1000, "target_reserve_open": 350000,
              "target_reserve_close": 350000}
    return {"id": "base-id", "version": 10, "courier_id": "12345", "period_start": "2026-09-01",
            "courier_name": "Bagoly Zoltán", "metadata": {"payable_total": 135500, "tig_final_total": 135500},
            "items": [{"section": "finance", "item_key": k, "item_label": k, "amount_value": v, "amount_kind": "huf"}
                      for k, v in values.items()], "sources": [{"source_key": "courier_profile", "payload": {"tig_type": "AAM"}, "row_count": 1}]}


def manual(row_id="test", kind="bonus", amount=2500):
    return {"id": row_id, "type": kind, "amountHuf": amount, "note": "Teszt tétel", "validFrom": "2026-09-01", "validTo": "2026-09-30"}


class WorksheetCalculationTest(unittest.TestCase):
    def test_no_double_count_of_aggregates_details_or_reserve_balances(self):
        saved = snapshot()
        before = deepcopy(saved)
        state = worksheet_state(saved)
        self.assertNotIn("base_detail_1", [r["key"] for r in state["rows"]])
        result = prepare_worksheet(saved, [], [], "Egyeztetés")
        self.assertEqual(result["totals"]["payable_total"], 135500)
        self.assertEqual(result["tig"]["finalTotalHuf"], 135500)
        self.assertEqual(saved, before)

    def test_edit_and_manual_rows_match_shared_devtest_keys(self):
        result = prepare_worksheet(snapshot(), [{"key": "base", "amountHuf": 110000}],
                                   [manual(), manual("deduct", "malus", 1000), manual("corr", "correction_income", 500)], "Javítás")
        self.assertEqual(result["totals"]["payable_total"], 147500)
        values = {r["item_key"]: r["amount_value"] for r in result["prepared"]["items"] if r["section"] == "finance"}
        self.assertEqual(values["manual_bonus"], 3500)
        self.assertEqual(values["manual_malus"], -1000)
        self.assertEqual(values["correction_income"], 10500)
        self.assertEqual(values["target_reserve_close"], 350000)
        self.assertEqual(values["payable"], result["tig"]["finalTotalHuf"])

    def test_reopening_does_not_add_manual_amounts_again_and_one_delete_is_local(self):
        result = prepare_worksheet(snapshot(), [], [manual(), manual("other", "bonus", 1000)], "Első")
        reopened = {**snapshot(), **result["prepared"], "id": "new-id", "version": 11}
        state = worksheet_state(reopened)
        again = prepare_worksheet(reopened, state["rows"], state["manualRows"], "Második")
        self.assertEqual(again["totals"], result["totals"])
        deleted_one = prepare_worksheet(reopened, state["rows"], state["manualRows"][1:], "Egy sor törlése")
        self.assertEqual(deleted_one["totals"]["payable_total"], result["totals"]["payable_total"] - 2500)

    def test_all_couriers_and_months_use_the_selected_scope(self):
        for courier, month in [("7767", "2026-09"), ("7725", "2026-10"), ("12345", "2028-02")]:
            with self.subTest(courier=courier, month=month):
                saved = {**snapshot(), "courier_id": courier, "period_start": month + "-01"}
                result = prepare_worksheet(saved, [], [], "Módosítás")
                self.assertEqual(result["prepared"]["metadata"]["worksheet_courier_id"], courier)
                self.assertEqual(result["tig"]["documentMeta"]["periodStart"], month + "-01")
                self.assertEqual(result["tig"]["documentMeta"]["note"], "Futár ID: " + courier)

    def test_manual_dates_follow_selected_month_and_leap_year(self):
        saved = {**snapshot(), "courier_id": "7767", "period_start": "2028-02-01"}
        entry = {**manual(), "validFrom": "2028-02-01", "validTo": "2028-02-29"}
        self.assertEqual(prepare_worksheet(saved, [], [entry], "Teszt")["delta"], 2500)
        with self.assertRaises(ValueError):
            prepare_worksheet(saved, [], [manual()], "Másik hónap")

    def test_invalid_target_is_rejected(self):
        for courier, month in [("", "2026-09"), (None, "2026-09"), ("7767", "2026-13"), ("7767", "2026-09-02")]:
            with self.subTest(courier=courier, month=month), self.assertRaises(ValueError):
                require_pilot(courier, month)

    def test_invalid_input_cannot_be_saved(self):
        for rows, manual_rows, note in [
            ([{"key": "base_detail_1", "amountHuf": 1}], [], "Indok"),
            ([{"key": "manual_malus", "amountHuf": 5}], [], "Indok"),
            ([], [manual(), manual()], "Indok"), ([], [], ""),
            ([], [{**manual(), "validFrom": "2026-08-01"}], "Indok"),
        ]:
            with self.subTest(rows=rows, manual_rows=manual_rows), self.assertRaises(ValueError):
                prepare_worksheet(snapshot(), rows, manual_rows, note)


class WorksheetEndpointTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8"))
        names = {"prepare_pilot_request", "admin_worksheet_pilot_preview", "admin_worksheet_pilot_commit"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for n in nodes:
            n.decorator_list = []
        self.rest = Mock(return_value=[])
        self.read = Mock(return_value=snapshot())
        self.ns = {"WorksheetPilotRequest": object, "Any": object, "Cookie": lambda **kw: None,
                   "HTTPException": HTTPException, "parse_month": lambda m: date.fromisoformat(m + "-01"),
                   "read_latest_courier_finance_snapshot": self.read, "supabase_rest": self.rest,
                   "require_user": lambda _: {"username": "admin"}, "require_settlement_dashboard_admin": lambda u: u}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), self.ns)
        self.payload = SimpleNamespace(courierId="12345", month="2026-09", snapshotId="base-id", rows=[], manualRows=[], note="Teszt", previewHash="")

    def test_preview_is_read_only(self):
        result = self.ns["admin_worksheet_pilot_preview"](self.payload)
        self.assertEqual(result["totals"]["payable_total"], 135500)
        self.assertTrue(all(c.args[0] == "GET" for c in self.rest.call_args_list))

    def test_missing_target_is_rejected_before_database_access(self):
        self.payload.courierId = ""
        with self.assertRaises(HTTPException) as caught:
            self.ns["admin_worksheet_pilot_preview"](self.payload)
        self.assertEqual(caught.exception.status_code, 403)
        self.read.assert_not_called()
        self.rest.assert_not_called()

    def test_other_courier_and_month_scope_all_reads_and_writes(self):
        self.payload.courierId, self.payload.month = "7767", "2026-10"
        self.read.return_value = {**snapshot(), "courier_id": "7767", "period_start": "2026-10-01"}
        preview = self.ns["admin_worksheet_pilot_preview"](self.payload)
        self.read.assert_called_with("7767", date(2026, 10, 1), include_sources=True)
        for call in self.rest.call_args_list:
            self.assertEqual(call.kwargs["params"]["courier_id"], "eq.7767")
            key = "period_start" if call.args[1] == "courier_monthly_closure" else "document_month"
            self.assertEqual(call.kwargs["params"][key], "eq.2026-10-01")
        self.payload.previewHash = preview["previewHash"]
        self.rest.side_effect = lambda method, *a, **kw: {"ok": True, "version": 11} if method == "POST" else []
        self.ns["admin_worksheet_pilot_commit"](self.payload)
        post = next(c for c in self.rest.call_args_list if c.args[0] == "POST")
        self.assertEqual(post.kwargs["payload"]["p_courier_id"], "7767")
        self.assertEqual(post.kwargs["payload"]["p_period_start"], "2026-10-01")

    def test_mismatched_snapshot_courier_or_month_cannot_be_edited(self):
        for changed in [{"courier_id": "7767"}, {"period_start": "2026-10-01"}]:
            self.read.return_value = {**snapshot(), **changed}
            with self.assertRaises(HTTPException) as caught:
                self.ns["admin_worksheet_pilot_preview"](self.payload)
            self.assertEqual(caught.exception.status_code, 409)

    def test_stale_version_and_closed_payment_block_preview(self):
        self.payload.snapshotId = "old-id"
        with self.assertRaises(HTTPException):
            self.ns["admin_worksheet_pilot_preview"](self.payload)
        self.payload.snapshotId = "base-id"
        self.rest.return_value = [{"status": "done"}]
        with self.assertRaises(HTTPException):
            self.ns["admin_worksheet_pilot_preview"](self.payload)

    def test_save_requires_current_preview_and_calls_one_scoped_transaction(self):
        with self.assertRaises(HTTPException):
            self.ns["admin_worksheet_pilot_commit"](self.payload)
        preview = self.ns["admin_worksheet_pilot_preview"](self.payload)
        self.payload.previewHash = preview["previewHash"]
        self.rest.side_effect = lambda method, *a, **kw: {"ok": True, "version": 11} if method == "POST" else []
        result = self.ns["admin_worksheet_pilot_commit"](self.payload)
        self.assertEqual(result["version"], 11)
        posts = [c for c in self.rest.call_args_list if c.args[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].args[1], "rpc/pwa_commit_worksheet_pilot")
        self.assertEqual(posts[0].kwargs["payload"]["p_courier_id"], "12345")


class DevtestSharedSnapshotTest(unittest.TestCase):
    def test_saved_effective_amounts_are_visible_in_devtest_without_recalculation(self):
        result = prepare_worksheet(snapshot(), [{"key": "base", "amountHuf": 110000}],
                                   [manual(), manual("deduct", "correction_deduction", 500)], "PWA módosítás")
        shared = {**snapshot(), **result["prepared"]}
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        names = {"_snapshot_amount", "finance_snapshot_display_row"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        ns = {"parse_huf_value": lambda v: float(v or 0)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), ns)
        visible = ns["finance_snapshot_display_row"]({}, shared)
        self.assertEqual(visible["Alapdíj"], 110000)
        self.assertEqual(visible["JITT bónusz"], 3500)
        self.assertEqual(visible["Korrekció"], 8500)
        self.assertEqual(visible["Kifizetendő"], result["totals"]["payable_total"])

    def test_explicit_zero_pwa_snapshot_is_not_replaced_by_previous_version(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "load_reliable_devtest_finance_snapshot")
        empty_pilot = {"id": "new", "previous_snapshot_id": "old", "metadata": {"source": "pwa_worksheet_pilot"}}
        previous = Mock(side_effect=AssertionError("Explicit zero version must remain authoritative"))
        ns = {"date": date, "load_latest_devtest_finance_snapshot": lambda *a: empty_pilot,
              "_snapshot_has_core_finance_data": lambda s: False, "load_devtest_finance_snapshot_by_id": previous}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        self.assertEqual(ns[node.name]("12345", date(2026, 9, 1)), empty_pilot)
        previous.assert_not_called()


if __name__ == "__main__":
    unittest.main()
