from __future__ import annotations

from datetime import date
import unittest

from resources.settlement_parameters import (
    parameter_status,
    validate_periodic_bonus,
    validate_rate_parameter,
)


class SettlementParameterValidationTests(unittest.TestCase):
    def test_open_ended_rate_parameter_is_supported(self) -> None:
        payload = validate_rate_parameter(
            {
                "parameter_name": "Delay Szint 1 Expressz",
                "parameter_kind": "delay_bonus",
                "level_code": "Szint 1",
                "day_type": "highlighted",
                "weekdays": [1, 4, 5, 6],
                "route_type": "express",
                "threshold_min": None,
                "threshold_max": 1.5,
                "threshold_max_inclusive": True,
                "planned_duration_min_hours": None,
                "planned_duration_max_hours": 2.0,
                "company_amount_huf": 1333,
                "courier_amount_huf": 1333,
                "calculation_unit": "per_route",
                "valid_from": date(2026, 6, 1),
                "valid_to": None,
            }
        )

        self.assertIsNone(payload["valid_to"])
        self.assertEqual(payload["weekdays"], [1, 4, 5, 6])
        self.assertEqual(payload["threshold_max"], 1.5)
        self.assertEqual(payload["planned_duration_max_hours"], 2.0)

    def test_only_delay_and_compliance_rate_kinds_are_allowed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Ismeretlen díjparaméter"):
            validate_rate_parameter(
                {
                    "parameter_name": "Alapdíj",
                    "parameter_kind": "base_rate",
                    "day_type": "any",
                    "weekdays": [],
                    "route_type": "normal",
                    "company_amount_huf": 6500,
                    "courier_amount_huf": 7500,
                    "calculation_unit": "per_route",
                    "valid_from": date(2026, 6, 1),
                    "valid_to": None,
                }
            )

    def test_periodic_route_bonus_supports_minimum_orders(self) -> None:
        payload = validate_periodic_bonus(
            {
                "bonus_name": "12 címes időszakos túrabónusz",
                "day_type": "any",
                "weekdays": [],
                "route_type": "any",
                "condition_metric": "orders_per_route",
                "condition_min": 12,
                "condition_max": None,
                "company_amount_huf": 0,
                "courier_amount_huf": 1000,
                "calculation_unit": "per_route",
                "valid_from": date(2026, 6, 7),
                "valid_to": date(2026, 6, 9),
            }
        )

        self.assertEqual(payload["condition_min"], 12)
        self.assertEqual(payload["courier_amount_huf"], 1000)
        self.assertEqual(payload["valid_to"], "2026-06-09")

    def test_invalid_period_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "záró dátum"):
            validate_periodic_bonus(
                {
                    "bonus_name": "Hibás időszak",
                    "day_type": "any",
                    "route_type": "any",
                    "condition_metric": "none",
                    "company_amount_huf": 0,
                    "courier_amount_huf": 1000,
                    "calculation_unit": "per_route",
                    "valid_from": date(2026, 6, 10),
                    "valid_to": date(2026, 6, 9),
                }
            )

    def test_highlighted_day_requires_explicit_weekdays(self) -> None:
        with self.assertRaisesRegex(ValueError, "legalább egy napot"):
            validate_rate_parameter(
                {
                    "parameter_name": "Kiemelt napi Delay bónusz",
                    "parameter_kind": "delay_bonus",
                    "day_type": "highlighted",
                    "weekdays": [],
                    "route_type": "normal",
                    "company_amount_huf": 6500,
                    "courier_amount_huf": 7500,
                    "calculation_unit": "per_route",
                    "valid_from": date(2026, 6, 1),
                    "valid_to": None,
                }
            )

    def test_status_uses_inclusive_end_date(self) -> None:
        self.assertEqual(
            parameter_status(
                "2026-06-07",
                "2026-06-09",
                True,
                today=date(2026, 6, 9),
            ),
            "Aktív",
        )
        self.assertEqual(
            parameter_status(
                "2026-06-07",
                "2026-06-09",
                True,
                today=date(2026, 6, 10),
            ),
            "Lejárt",
        )

    def test_separate_invoice_line_requires_note(self) -> None:
        with self.assertRaisesRegex(ValueError, "számlasor"):
            validate_periodic_bonus(
                {
                    "bonus_name": "Külön számlasor",
                    "day_type": "any",
                    "route_type": "any",
                    "condition_metric": "none",
                    "company_amount_huf": 0,
                    "courier_amount_huf": 1000,
                    "calculation_unit": "per_route",
                    "valid_from": date(2026, 6, 7),
                    "valid_to": None,
                    "show_as_separate_invoice_line": True,
                    "invoice_line_note": "",
                }
            )


if __name__ == "__main__":
    unittest.main()
