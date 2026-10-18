"""Exercise loyalty calculation without starting the Streamlit application."""
import ast
import json
import re
import unicodedata
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


class LoyaltyCityBonusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        names = {
            "_normalized_field_key", "normalize_loyalty_route_type",
            "_loyalty_count_record", "_loyalty_route_counts_from_settlement_rows",
            "completed_months_between", "_loyalty_rule_bool",
            "loyalty_advance_booking_min_from_rule", "apply_loyalty_bonus", "payable_bonus_total",
        }
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        cls.code = compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec")

    def namespace(self, bookings=48, route_types=None, rules=None):
        route_types = route_types if route_types is not None else ["city"] * 19 + ["regional"] * 4 + ["express"] * 3
        ns = {
            "pd": pd, "date": date, "timedelta": timedelta,
            "json": json, "re": re, "unicodedata": unicodedata,
            "parse_huf_value": lambda value: 0.0 if value is None or pd.isna(value) else float(value),
            "_courier_match_key": lambda value: str(value or "").strip().casefold(),
            "_courier_id_key": lambda value: str(value or ""),
            "_numeric_series": lambda frame, key: pd.to_numeric(frame.get(key, pd.Series(0, index=frame.index))),
            "load_loyalty_bonus_rules_for_month": lambda *args: pd.DataFrame(rules or [
                {"previous_normal_routes_min": 0, "bonus_amount_huf": 500, "priority": 1},
                {"previous_normal_routes_min": 40, "bonus_amount_huf": 1000, "priority": 100},
            ]),
            "load_loyalty_route_counts_for_period": lambda *args: pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"]),
            "load_loyalty_advance_booking_days": lambda *args: pd.DataFrame(),
            "load_loyalty_profile_lookup": lambda: {"test courier": {"start_date": "2025-01-01"}},
            "load_courier_profile_lookup": lambda: {},
            "load_advance_booking_cancellation_summary": lambda *args: {"remaining_shift_count": bookings},
        }
        exec(self.code, ns)
        records = [ns["_loyalty_count_record"]({"Driver": "Test Courier", "Route Type": kind, "Orders": 10}) for kind in route_types]
        counts = pd.DataFrame(records, columns=["driver_key", "route_type", "routes", "orders"])
        ns["load_loyalty_route_counts"] = lambda *args: counts
        return ns

    def calculate(self, ns, **values):
        row = {"Futár": "Test Courier", "Courier ID": "123", "Kör": 26,
               "Normál túrák": 26, "Nettó bevétel": 100000, "Bónusz": 0, **values}
        return ns["apply_loyalty_bonus"](pd.DataFrame([row]), date(2026, 9, 1), date(2026, 9, 30), "session").iloc[0]

    def test_48_bookings_selects_higher_band_without_previous_month_routes(self):
        row = self.calculate(self.namespace())
        self.assertEqual(row["Lojalitás Ft/kör"], 1000)
        self.assertEqual(row["Lojalitás"], 19000)
        self.assertEqual(row["Lojalitás aktuális normál kör"], 19)
        self.assertEqual(row["Lojalitás előre foglalt nap"], 48)
        self.assertEqual(row["Lojalitás státusz"], "Jogosult")

    def test_booking_threshold_is_inclusive(self):
        for bookings, rate in [(39, 500), (40, 1000)]:
            with self.subTest(bookings=bookings):
                row = self.calculate(self.namespace(bookings=bookings))
                self.assertEqual(row["Lojalitás Ft/kör"], rate)

    def test_non_city_and_unknown_routes_never_receive_bonus(self):
        for route_types in [["regional", "express"], ["", "unexpected"], []]:
            with self.subTest(route_types=route_types):
                row = self.calculate(self.namespace(route_types=route_types), **{"Normál túrák": 0})
                self.assertEqual(row["Lojalitás"], 0)
                self.assertEqual(row["Lojalitás aktuális normál kör"], 0)

    def test_any_rule_is_still_limited_to_city(self):
        row = self.calculate(self.namespace(rules=[{
            "route_type": "any", "bonus_amount_huf": 500, "priority": 1,
        }]))
        self.assertEqual(row["Lojalitás"], 19 * 500)

    def test_per_order_rule_counts_only_city_orders(self):
        row = self.calculate(self.namespace(rules=[{
            "calculation_unit": "per_order", "bonus_amount_huf": 100, "priority": 1,
        }]))
        self.assertEqual(row["Lojalitás"], 19 * 10 * 100)

    def test_aggregate_fallback_excludes_express_and_regional(self):
        ns = self.namespace(route_types=[])
        row = self.calculate(ns, **{"Normál túrák": 26, "Express normál": 3, "regional_route_count": 4})
        self.assertEqual(row["Lojalitás aktuális normál kör"], 19)
        self.assertEqual(row["Lojalitás"], 19000)

    def test_explicit_city_count_zero_does_not_fall_back_to_all_routes(self):
        row = self.calculate(self.namespace(route_types=[]), normal_route_count=0)
        self.assertEqual(row["Lojalitás"], 0)

    def test_unclassified_day_totals_are_not_assumed_to_be_city(self):
        row = self.calculate(self.namespace(route_types=[]))
        self.assertEqual(row["Lojalitás"], 0)

    def test_non_city_rule_cannot_award_bonus_for_city_routes(self):
        row = self.calculate(self.namespace(rules=[{
            "route_type": "regional", "bonus_amount_huf": 1000, "priority": 1,
        }]))
        self.assertEqual(row["Lojalitás"], 0)

    def test_explicit_booking_column_overrides_legacy_name(self):
        ns = self.namespace()
        self.assertEqual(ns["loyalty_advance_booking_min_from_rule"](pd.Series({
            "advance_booked_shifts_min": 20, "previous_normal_routes_min": 40,
        })), 20)


if __name__ == "__main__":
    unittest.main()
