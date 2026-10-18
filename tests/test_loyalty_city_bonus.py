"""Exercise loyalty calculation without starting the Streamlit application."""
import ast
import json
import re
import unicodedata
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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
            "load_loyalty_advance_booking_days", "_loyalty_booking_pair_key",
            "_booking_user_email_key", "_booking_operation_key", "_is_clean_booking_operation",
            "_is_booking_change_operation", "_booked_in_period", "_parse_booking_timestamp_date",
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
            "load_loyalty_profile_lookup": lambda: {"test courier": {"start_date": "2025-01-01"}},
            "load_courier_profile_lookup": lambda: {},
            "load_advance_booking_cancellation_summary": lambda *args: {"remaining_shift_count": bookings},
        }
        exec(self.code, ns)
        ns["load_loyalty_advance_booking_days"] = lambda *args: pd.DataFrame([{
            "courier_id": "123", "driver_key": "test courier", "advance_booking_days": bookings,
        }])
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

    def test_200_couriers_share_one_monthly_booking_load(self):
        ns = self.namespace()
        batch = pd.DataFrame([
            {"courier_id": str(index), "driver_key": "test courier", "advance_booking_days": 48}
            for index in range(200)
        ])
        ns["load_loyalty_advance_booking_days"] = Mock(return_value=batch)
        ns["load_advance_booking_cancellation_summary"] = Mock(
            side_effect=AssertionError("Unexpected per-courier database lookup")
        )
        data = pd.DataFrame([
            {"Futár": "Test Courier", "Courier ID": str(index), "Normál túrák": 26}
            for index in range(200)
        ])
        result = ns["apply_loyalty_bonus"](data, date(2026, 9, 1), date(2026, 9, 30), "session")
        self.assertEqual(result["Lojalitás"].sum(), 200 * 19000)
        ns["load_loyalty_advance_booking_days"].assert_called_once()
        ns["load_advance_booking_cancellation_summary"].assert_not_called()

    def test_monthly_booking_pages_include_cancellations_after_first_1000_rows(self):
        ns = self.namespace()
        # Restore the real batch loader after namespace() installs its fixture.
        exec(self.code, ns)
        rows = [
            {"courier_id": "123", "courier_name": "Test Courier", "user_email": "test@example.test",
             "operation": "book", "booked_at": "2026-08-20", "shift_date": "2026-09-01",
             "shift_time": str(index), "warehouse": "BUD1"}
            for index in range(1000)
        ]
        rows.append({**rows[0], "operation": "cancel", "booked_at": "2026-09-01"})
        ranges = []
        query = Mock()
        for method in ("select", "gte", "lte", "order"):
            getattr(query, method).return_value = query
        def select_range(start, end):
            ranges.append((start, end))
            query.execute.return_value = SimpleNamespace(data=rows[start:end + 1])
            return query
        query.range.side_effect = select_range
        db = Mock()
        db.schema.return_value.table.return_value = query
        ns.update({
            "get_db": lambda: db,
            "add_months": lambda *args: date(2026, 8, 1),
            "month_bounds": lambda *args: (date(2026, 8, 1), date(2026, 8, 31)),
        })
        result = ns["load_loyalty_advance_booking_days"](date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(result.iloc[0]["advance_booking_days"], 999)
        self.assertEqual(ranges, [(0, 999), (1000, 1999)])

    def test_explicit_booking_column_overrides_legacy_name(self):
        ns = self.namespace()
        self.assertEqual(ns["loyalty_advance_booking_min_from_rule"](pd.Series({
            "advance_booked_shifts_min": 20, "previous_normal_routes_min": 40,
        })), 20)


if __name__ == "__main__":
    unittest.main()
