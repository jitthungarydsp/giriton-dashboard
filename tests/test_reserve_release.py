import ast
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from resources.reserve_release import prepare_reserve_release, split_net_reserve_rows


def fixture():
    amounts = {"payable": 212345, "income": 553250, "deductions": -34705,
               "reserve": -24705, "insurance_fee": -10000,
               "target_reserve_open": 350000, "target_reserve_close": 374705,
               "correction": -306200, "loyalty_bonus": 20000}
    return {"items": [{"section": "finance", "item_key": k, "amount_value": v}
                      for k, v in amounts.items()],
            "sources": [{"source_key": "target_reserve_month", "payload": {
                "reserve_before_huf": 350000, "reserve_addition_huf": 24705,
                "reserve_after_huf": 374705, "payable_after_insurance_huf": 212345,
                "insurance_fee_huf": 10000}},
                {"source_key": "card_drilldowns", "payload": {}}]}


class ReserveReleaseTest(unittest.TestCase):
    def test_reloaded_snapshot_without_release_metadata_keeps_booked_month(self):
        prepared = prepare_reserve_release(fixture(), {"deduction": 350000})
        snapshot = {"items": prepared["finance_rows"], "sources": prepared["sources"], "metadata": {"source": "preflight"}}
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "resolve_target_reserve_month")
        save = Mock()
        namespace = {
            "date": date, "parse_huf_value": lambda v: float(v or 0),
            "load_latest_devtest_finance_snapshot": lambda *a: snapshot,
            "load_target_reserve_monthly": lambda *a: {"reserve_after_huf": 50000},
            "load_target_reserve_event_totals": lambda *a: {"deduction": 350000},
            "_snapshot_amount": lambda s, k: next((v["amount_value"] for v in s["items"] if v["item_key"] == k), 0),
            "_snapshot_source_payload": lambda s, k: next(v["payload"] for v in s["sources"] if v["source_key"] == k),
            "save_target_reserve_monthly": save,
            "calculate_target_reserve_month": Mock(side_effect=AssertionError("Must use booked month")),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), namespace)
        result = namespace["resolve_target_reserve_month"](
            "session", "6686", date(2026, 9, 1), date(2026, 9, 30), {}, 547250)
        self.assertEqual(result["reserve_after_huf"], 24705)
        self.assertEqual(result["payable_after_insurance_huf"], 562345)
        save.assert_called_once()

    def test_retry_of_saved_release_writes_bigint_and_does_not_book_again(self):
        prepared = prepare_reserve_release(fixture(), {"deduction": 350000})
        snapshot = {"items": prepared["finance_rows"], "sources": prepared["sources"], "session_id": "session"}
        writes = []

        class Query:
            def schema(self, schema):
                return self

            def table(self, table):
                self.table_name = table
                return self

            def upsert(self, payload, **kwargs):
                self.payload = payload
                return self

            def update(self, payload):
                self.payload = payload
                return self

            def eq(self, key, value):
                self.assert_scope = (key, value)
                return self

            def execute(self):
                if self.table_name == "courier_target_reserve":
                    # PostgREST rejects JSON 24705.0 for this bigint column.
                    if type(self.payload["current_reserve_huf"]) is not int:
                        raise ValueError("invalid input syntax for type bigint")
                    if self.assert_scope != ("courier_ID", "6686"):
                        raise AssertionError("Wrong courier")
                writes.append((self.table_name, self.payload))

        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "save_target_reserve_snapshot_after_event")
        namespace = {
            "date": date, "get_db": Query, "parse_huf_value": lambda v: float(v or 0),
            "pd": SimpleNamespace(Timestamp=SimpleNamespace(utcnow=lambda: date(2026, 10, 19))),
            "month_bounds": lambda d: (d, date(2026, 9, 30)),
            "load_latest_devtest_finance_snapshot": lambda *a: snapshot,
            "load_target_reserve_event_totals": lambda *a: {"deduction": 350000},
            "_snapshot_source_payload": lambda s, key: next(v["payload"] for v in s["sources"] if v["source_key"] == key),
            "_snapshot_amount": lambda s, key: float(next(v["amount_value"] for v in s["items"] if v["item_key"] == key)),
            "load_target_reserve_monthly": Mock(return_value={"status": "in_progress"}),
            "load_target_reserve_status": Mock(), "load_target_reserve_rows_bulk": Mock(),
            "clear_devtest_finance_snapshot_cache": Mock(), "clear_settlement_overview_data_cache": Mock(),
            "save_devtest_finance_snapshot_version": Mock(side_effect=AssertionError("Already booked")),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), namespace)
        for _ in range(2):
            result = namespace["save_target_reserve_snapshot_after_event"](
                courier_id="6686", period_start=date(2026, 9, 1), calculation_mode="Excel",
                warehouse_label=None, updated_by="admin")
            self.assertEqual(result["new_versions"], 0)
        master = [payload for table, payload in writes if table == "courier_target_reserve"]
        self.assertEqual([v["current_reserve_huf"] for v in master], [24705, 24705])
        self.assertTrue(all(v["CT_Z_FT"] == "24705" for v in master))
        namespace["save_devtest_finance_snapshot_version"].assert_not_called()

    def test_mobile_recalculation_counts_releases_as_income(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        names = {"recalculate_mobile_breakdown_totals", "_mobile_breakdown_amount", "_set_mobile_breakdown_row_amount"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        namespace = {"parse_huf_value": lambda v: float(v or 0)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), namespace)
        for values in ({"base": 247050, "reserve": -24705, "insurance_fee": -10000,
                        "reserve_payment_credit": 100000, "reserve_deduction_credit": 50000},
                       {"base": 247050, "reserve": 125295, "insurance_fee": -10000}):
            rows = namespace["recalculate_mobile_breakdown_totals"](
                [{"item_key": k, "amount_value": v} for k, v in values.items()])
            amounts = {r["item_key"]: r["amount_value"] for r in rows}
            self.assertEqual(amounts["payable"], 362345)

    def test_rebuilding_net_calculation_keeps_positive_credit_items(self):
        rows = [{"item_key": key, "amount_value": value} for key, value in
                {"reserve": 75295, "income": 553250, "deductions": 65295,
                 "payable": 312345}.items()]
        split = split_net_reserve_rows(rows, {"payment": 100000})
        values = {r["item_key"]: r["amount_value"] for r in split}
        self.assertEqual(values["reserve"], -24705)
        self.assertEqual(values["reserve_payment_credit"], 100000)
        self.assertEqual(values["payable"], 312345)
        self.assertEqual(values["deductions"], -34705)
        self.assertEqual(split_net_reserve_rows(split, {"payment": 100000}), split)

    def test_both_operation_types_credit_settlement_and_reduce_reserve(self):
        for kind, key in [("payment", "reserve_payment_credit"),
                          ("deduction", "reserve_deduction_credit")]:
            with self.subTest(kind=kind):
                snapshot = fixture()
                original = deepcopy(snapshot)
                result = prepare_reserve_release(snapshot, {kind: 100000})
                values = {r["item_key"]: r["amount_value"] for r in result["finance_rows"]}
                self.assertEqual(result["payable"], 312345)
                self.assertEqual(result["closing"], 274705)
                self.assertEqual(values[key], 100000)
                self.assertEqual(values["reserve"], -24705)
                self.assertEqual(values["insurance_fee"], -10000)
                self.assertEqual(values["correction"], -306200)
                self.assertEqual(result["monthly"]["reserve_addition_huf"], -75295)
                self.assertEqual(snapshot, original)

    def test_repeat_is_idempotent_and_next_event_only_books_difference(self):
        result = prepare_reserve_release(fixture(), {"payment": 100000})
        saved = {"items": result["finance_rows"], "sources": result["sources"]}
        self.assertFalse(prepare_reserve_release(saved, {"payment": 100000})["changed"])
        second = prepare_reserve_release(saved, {"payment": 100000, "deduction": 50000})
        self.assertEqual(second["payable"], 362345)
        self.assertEqual(second["closing"], 224705)
        self.assertEqual(second["monthly"]["reserve_addition_huf"], -125295)
        keys = [r["item_key"] for r in second["finance_rows"]]
        self.assertEqual(keys.count("reserve_payment_credit"), 1)

    def test_full_release_leaves_zero_reserve(self):
        result = prepare_reserve_release(fixture(), {"payment": 374705})
        self.assertEqual(result["closing"], 0)
        self.assertEqual(result["payable"], 587050)

    def test_overdraw_and_invalid_amounts_are_rejected(self):
        for totals in ({"payment": 374706}, {"payment": 200000, "deduction": 200000},
                       {"deduction": -1}, {"payment": float("nan")}):
            with self.subTest(totals=totals), self.assertRaises(ValueError):
                prepare_reserve_release(fixture(), totals)

    def test_missing_monthly_source_is_rejected(self):
        snapshot = fixture()
        snapshot["sources"] = []
        with self.assertRaises(ValueError):
            prepare_reserve_release(snapshot, {"payment": 1})

    def test_removed_event_reverses_only_its_credit(self):
        result = prepare_reserve_release(fixture(), {"payment": 100000})
        reversed_result = prepare_reserve_release(
            {"items": result["finance_rows"], "sources": result["sources"]}, {})
        self.assertEqual(reversed_result["payable"], 212345)
        self.assertEqual(reversed_result["closing"], 374705)

    def test_regular_calculation_subtracts_both_event_types(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "calculate_target_reserve_month")
        namespace = {"date": date, "parse_huf_value": lambda v: float(v or 0),
                     "load_active_reserve_insurance_rule": lambda *a: {},
                     "RESERVE_TARGET_HUF": 50000, "RESERVE_RATE": .1,
                     "INSURANCE_FEE_HUF": 10000,
                     "resolve_target_reserve_opening_balance": lambda *a: 350000}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), namespace)
        result = namespace["calculate_target_reserve_month"](
            {"insurance_active": True}, 247050,
            manual_events={"payment": 100000, "deduction": 50000})
        self.assertEqual(result["reserve_after_huf"], 224705)
        self.assertEqual(result["payable_after_insurance_huf"], 362345)


if __name__ == "__main__":
    unittest.main()
