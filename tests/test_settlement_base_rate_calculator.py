from __future__ import annotations

import unittest

from resources.settlement_base_rate_calculator import calculate_excel_courier_base_rates


class ExcelCourierBaseRateTests(unittest.TestCase):
    def test_calculates_courier_amount_by_day_and_route_type(self) -> None:
        result = calculate_excel_courier_base_rates(
            [
                {"normalized_data": {"Driver": "Anna", "Date": "2026-06-08", "Route Type": "Express", "Location": "BUD1", "Orders": 10}},
                {"normalized_data": {"Driver": "Anna", "Date": "2026-06-09", "Route Type": "Regional", "Location": "BUD1", "Orders": 10}},
            ],
            [
                {"id": "normal", "day_type": "normal", "weekdays": [1, 2, 3, 4, 5], "valid_from": "2026-01-01", "is_active": True},
                {"id": "highlighted", "day_type": "highlighted", "weekdays": [6, 7], "valid_from": "2026-01-01", "is_active": True},
            ],
            [
                {"id": "express", "day_type": "normal", "route_type": "express", "warehouse_code": "BUD1", "company_amount_huf": 4000, "courier_amount_huf": 3000, "calculation_unit": "per_route", "valid_from": "2026-01-01", "is_active": True},
                {"id": "regional", "day_type": "normal", "route_type": "regional", "warehouse_code": "BUD1", "company_amount_huf": 6000, "courier_amount_huf": 5000, "calculation_unit": "per_route", "valid_from": "2026-01-01", "is_active": True},
            ],
        )
        self.assertEqual(result.iloc[0]["Nettó bevétel"], 8000)
        self.assertEqual(result.iloc[0]["Vállalkozói alapdíj"], 10000)
        self.assertEqual(result.iloc[0]["Számolt túrák"], 2)

    def test_does_not_pay_when_day_definition_or_rate_is_missing(self) -> None:
        result = calculate_excel_courier_base_rates(
            [{"normalized_data": {"Driver": "Béla", "Date": "2026-06-08", "Route Type": "Normal"}}],
            [],
            [],
        )
        self.assertEqual(result.iloc[0]["Nettó bevétel"], 0)
        self.assertEqual(result.iloc[0]["Nem számolt túrák"], 1)

    def test_per_order_rule_uses_excel_order_count(self) -> None:
        result = calculate_excel_courier_base_rates(
            [{"normalized_data": {"Driver": "Csilla", "Date": "2026-06-08", "Route Type": "Normal", "Orders": 12}}],
            [{"id": "normal", "day_type": "normal", "weekdays": [1], "valid_from": "2026-01-01", "is_active": True}],
            [{"id": "orders", "day_type": "normal", "route_type": "normal", "courier_amount_huf": 100, "calculation_unit": "per_order", "valid_from": "2026-01-01", "is_active": True}],
        )
        self.assertEqual(result.iloc[0]["Nettó bevétel"], 1200)

    def test_route_id_is_counted_once_across_warehouses_and_keeps_tip(self) -> None:
        result = calculate_excel_courier_base_rates(
            [
                {"normalized_data": {"Driver": "Dani", "Route Unique ID": "route-42", "Date": "2026-06-08", "Route Type": "Normal", "Location": "BUD1", "Tip": 500}},
                {"normalized_data": {"Driver": "Dani", "Route Unique ID": "route-42", "Date": "2026-06-08", "Route Type": "Normal", "Location": "BUD2", "Tip": 500}},
            ],
            [{"id": "normal", "day_type": "normal", "weekdays": [1], "valid_from": "2026-01-01", "is_active": True}],
            [{"id": "normal", "day_type": "normal", "route_type": "normal", "courier_amount_huf": 3000, "calculation_unit": "per_route", "valid_from": "2026-01-01", "is_active": True}],
        )
        self.assertEqual(result.iloc[0]["Nettó bevétel"], 3000)
        self.assertEqual(result.iloc[0]["Borravaló"], 500)
        self.assertEqual(result.iloc[0]["Normál túrák"], 1)
