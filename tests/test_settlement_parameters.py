from __future__ import annotations

from datetime import date
import unittest

from resources.settlement_parameters import (
    parameter_status,
    validate_base_rate,
    validate_day_definition,
    validate_performance_rule,
    validate_periodic_fee,
)


class SettlementParameterValidationTests(unittest.TestCase):
    def test_highlighted_day_definition_is_versioned(self) -> None:
        row = validate_day_definition(
            {
                "day_type": "highlighted",
                "weekdays": [1, 4, 5, 6],
                "valid_from": date(2026, 6, 1),
                "valid_to": None,
            }
        )
        self.assertEqual(row["weekdays"], [1, 4, 5, 6])
        self.assertIsNone(row["valid_to"])

    def test_base_rate_supports_day_and_route_type(self) -> None:
        row = validate_base_rate(
            {
                "day_type": "normal",
                "route_type": "regional",
                "company_amount_huf": 6300,
                "courier_amount_huf": 7300,
                "calculation_unit": "per_route",
                "valid_from": date(2026, 6, 1),
                "valid_to": None,
            }
        )
        self.assertEqual(row["route_type"], "regional")
        self.assertEqual(row["courier_amount_huf"], 7300)

    def test_delay_or_compliance_rule_supports_one_sided_ranges(self) -> None:
        row = validate_performance_rule(
            {
                "level_code": "Szint 1",
                "day_type": "any",
                "route_type": "express",
                "threshold_min": None,
                "threshold_max": 1.5,
                "duration_min": None,
                "duration_max": 2.0,
                "company_amount_huf": 1333,
                "courier_amount_huf": 1333,
                "calculation_unit": "per_route",
                "calculation_mode": "api",
                "valid_from": date(2026, 6, 1),
                "valid_to": None,
            }
        )
        self.assertEqual(row["threshold_max"], 1.5)
        self.assertEqual(row["duration_max_hours"], 2.0)
        self.assertEqual(row["calculation_mode"], "api")

    def test_periodic_fee_supports_twelve_order_route_condition(self) -> None:
        row = validate_periodic_fee(
            {
                "fee_name": "12 címes túrabónusz",
                "day_type": "any",
                "route_type": "any",
                "condition_metric": "orders_per_route",
                "condition_min": 12,
                "company_amount_huf": 0,
                "courier_amount_huf": 1000,
                "calculation_unit": "per_route",
                "valid_from": date(2026, 6, 7),
                "valid_to": date(2026, 6, 9),
            }
        )
        self.assertEqual(row["condition_min"], 12)
        self.assertEqual(row["valid_to"], "2026-06-09")

    def test_end_date_is_inclusive(self) -> None:
        self.assertEqual(parameter_status("2026-06-07", "2026-06-09", True, date(2026, 6, 9)), "Aktív")
        self.assertEqual(parameter_status("2026-06-07", "2026-06-09", True, date(2026, 6, 10)), "Lejárt")


if __name__ == "__main__":
    unittest.main()
