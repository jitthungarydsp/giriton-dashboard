import ast
from copy import deepcopy
from datetime import date
from pathlib import Path
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
