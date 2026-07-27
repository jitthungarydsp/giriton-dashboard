from __future__ import annotations

from datetime import date
import unittest

from resources.settlement_parameters import (
    parameter_status,
    validate_base_rate,
    validate_customer_rating_rule,
    validate_day_definition,
    validate_life_insurance_rule,
    validate_loyalty_bonus_rule,
    validate_performance_rule,
    validate_periodic_fee,
    validate_reserve_insurance_rule,
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
                "excel_source_field": "Delay Bonus",
                "valid_from": date(2026, 6, 1),
                "valid_to": None,
            }
        )
        self.assertEqual(row["threshold_max"], 1.5)
        self.assertEqual(row["duration_max_hours"], 2.0)
        self.assertEqual(row["calculation_mode"], "api")
        self.assertEqual(row["excel_source_field"], "Delay Bonus")

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

    def test_insurance_and_loyalty_rules_are_versioned(self) -> None:
        common = {"valid_from": date(2026, 6, 1), "valid_to": None}
        reserve = validate_reserve_insurance_rule({"insurance_fee_huf": 1200, "base_insurance_total_huf": 10000, "deduction_percent": 12.5, **common})
        loyalty = validate_loyalty_bonus_rule({"loyalty_start_date": date(2026, 1, 1), "bonus_amount_huf": 5000, **common})
        life = validate_life_insurance_rule({"life_insurance_amount_huf": 3500, **common})
        self.assertEqual(reserve["deduction_percent"], 12.5)
        self.assertEqual(loyalty["loyalty_start_date"], "2026-01-01")
        self.assertEqual(life["life_insurance_amount_huf"], 3500)

    def test_customer_rating_rule_has_percent_band_and_courier_amount(self) -> None:
        row = validate_customer_rating_rule({
            "level_code": "Kiemelkedő értékelés",
            "rating_min": 95,
            "rating_max": 100,
            "courier_amount_huf": 5000,
            "valid_from": date(2026, 6, 1),
            "valid_to": None,
        })
        self.assertEqual(row["rating_min_percent"], 95)
        self.assertEqual(row["courier_amount_huf"], 5000)


if __name__ == "__main__":
    unittest.main()
