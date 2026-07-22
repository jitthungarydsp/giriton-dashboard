import inspect
import unittest
from datetime import date

import pandas as pd

from resources.invoice_summary import (
    build_driver_invoice_summary,
    build_invoice_pdf_bytes,
    build_invoice_regeneration_candidates,
)


def route_row(warehouse, route_id, tip_huf, courier_id="42"):
    return {
        "courier_id": courier_id,
        "worksheet_name": warehouse,
        "row_number": 1,
        "driver_name": "Teszt Futár",
        "route_unique_id": route_id,
        "route_type": "City",
        "work_date": "2026-06-10",
        "orders": 10,
        "routes": 1,
        "fixed_rate_huf": 0,
        "fuel_bonus_huf": 0,
        "car_fridge_bonus_huf": 0,
        "branding_huf": 0,
        "delay_bonus_huf": 0,
        "compliance_bonus_huf": 0,
        "fill_rate_bonus_huf": 0,
        "bonus_total_huf": 0,
        "tip_huf": tip_huf,
        "route_total_without_tip_huf": 0,
        "route_total_huf": tip_huf,
    }


class MultiWarehouseInvoiceTest(unittest.TestCase):
    def test_summary_returns_one_row_and_does_not_duplicate_courier_sources(self):
        final_df = pd.DataFrame(
            [
                route_row("BUD1_JIT", "route-1", 100),
                route_row("BUD2_JIT", "route-2", 200),
            ]
        )
        atm_df = pd.DataFrame(
            [
                {"courier_id": "42", "driver_name": "Teszt Futár", "balance_huf": 500},
                {"courier_id": "42", "driver_name": "Teszt Futár", "balance_huf": 500},
            ]
        )
        monthly_df = pd.DataFrame(
            [
                {"courier_id": "42", "driver_name": "Teszt Futár", "bonus_huf": 1000},
                {"courier_id": "42", "driver_name": "Teszt Futár", "bonus_huf": 1000},
            ]
        )
        manual_df = pd.DataFrame(
            [
                {
                    "worksheet_name": "BUD1_JIT",
                    "driver_name": "Teszt Futár",
                    "item_type": "fuel_huf",
                    "amount_huf": 300,
                },
                {
                    "worksheet_name": "BUD2_JIT",
                    "driver_name": "Teszt Futár",
                    "item_type": "fuel_huf",
                    "amount_huf": 700,
                },
            ]
        )
        reserve_df = pd.DataFrame([{"courier_id": "42"}])

        result = build_driver_invoice_summary(
            final_df,
            manual_df=manual_df,
            atm_balance_df=atm_df,
            monthly_adjustment_df=monthly_df,
            target_reserve_df=reserve_df,
            period_start=date(2026, 6, 1),
        )

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["courier_id"], "42")
        self.assertEqual(row["warehouse_count"], 2)
        self.assertEqual(row["route_count"], 2)
        self.assertEqual(row["orders"], 20)
        self.assertEqual(row["tip_huf"], 300)
        self.assertEqual(row["fuel_huf"], 1000)
        self.assertEqual(row["atm_balance_huf"], 500)
        self.assertEqual(row["monthly_bonus_huf"], 1000)
        self.assertEqual(row["insurance_deduction_huf"], 10_000)
        self.assertEqual(
            row["reserve_deduction_huf"],
            min(max(row["payable_before_reserve_huf"], 0) * 0.10, 50_000),
        )

    def test_regeneration_candidates_use_driver_key_without_courier_id(self):
        routes = pd.DataFrame(
            [
                route_row("BUD1_JIT", "route-1", 0, courier_id=""),
                route_row("BUD2_JIT", "route-2", 0, courier_id=""),
            ]
        )
        documents = pd.DataFrame(
            [
                {"courier_id": "", "courier_name": "Teszt Futár"},
                {"courier_id": "", "courier_name": "Teszt Futár"},
            ]
        )

        result = build_invoice_regeneration_candidates(routes, documents)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["warehouse_count"], 2)
        self.assertEqual(result.iloc[0]["current_invoice_count"], 2)
        self.assertTrue(bool(result.iloc[0]["needs_regeneration"]))

    def test_pdf_builder_contains_no_summary_groupby(self):
        source = inspect.getsource(build_invoice_pdf_bytes)
        self.assertNotIn(".groupby(", source)


if __name__ == "__main__":
    unittest.main()
