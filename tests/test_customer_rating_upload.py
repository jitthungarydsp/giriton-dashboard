import ast
from datetime import date, timedelta
import hashlib
from io import BytesIO
from pathlib import Path
import re
import unicodedata
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def upload_functions():
    names = {"_numeric_series", "_courier_match_key", "_courier_id_from_text", "_courier_id_key",
             "_normalized_field_key", "customer_rating_source_id", "_customer_rating_dashboard_routes",
             "_finalize_customer_rating_value_rows", "parse_customer_rating_excel_v2"}
    tree = ast.parse((ROOT / "devtest.py").read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(pd=pd, date=date, timedelta=timedelta, hashlib=hashlib, re=re, unicodedata=unicodedata,
              load_customer_rating_rules_for_month=lambda *args: pd.DataFrame(),
              customer_rating_rule_amount=lambda rating, rules, route_type: 500.0)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "rating_upload", "exec"), ns)
    return ns


class CustomerRatingUploadTest(unittest.TestCase):
    def setUp(self):
        self.ns = upload_functions()
        self.grouped = pd.DataFrame({"courier_id": [2875, 6855], "driver_name": ["A", "B"],
            "rating_count": [136, 10], "average_rating": [4.912, 4.792]}, index=[7, 11])
        self.dashboard = pd.DataFrame({"Courier ID": [2875, 6855], "Futár": ["A", "B"], "Kör": [60, 20]})

    def finalize(self, data, dashboard):
        return self.ns["_finalize_customer_rating_value_rows"](
            data, BytesIO(b"test"), date(2026, 10, 1), "Ratings", dashboard)

    def test_missing_completed_routes_uses_dashboard_and_preserves_decimal_ratings(self):
        result = self.finalize(self.grouped, self.dashboard)
        self.assertEqual(result["completed_routes"].tolist(), [60, 20])
        self.assertEqual(result["average_rating"].tolist(), [4.912, 4.792])
        self.assertEqual(result["bonus_total_huf"].tolist(), [30000, 10000])

    def test_existing_counts_and_explicit_zero_keep_their_row_alignment(self):
        data = self.grouped.assign(completed_routes=[3, 0])
        result = self.finalize(data, pd.DataFrame())
        self.assertEqual(result["completed_routes"].tolist(), [3, 0])
        self.assertEqual(result["bonus_total_huf"].tolist(), [1500, 0])

    def test_missing_dashboard_does_not_invent_route_counts(self):
        result = self.finalize(self.grouped, pd.DataFrame())
        self.assertEqual(result["completed_routes"].tolist(), [0, 0])

    def test_supplied_october_workbook_read_only(self):
        source = Path(r"C:\Users\gbgyu\Downloads\JIT_2026.X.xlsx")
        if not source.exists():
            self.skipTest("Local reference workbook is not available")
        with source.open("rb") as uploaded:
            result = self.ns["parse_customer_rating_excel_v2"](uploaded, date(2026, 10, 1), self.dashboard)
        self.assertEqual(len(result), 93)  # 102 couriers minus 9 without numeric ratings.
        self.assertEqual(set(result["worksheet_name"]), {"JITT_courier_ratings_2026-10"})
        racz = result.loc[result["courier_id"].eq("2875")].iloc[0]
        self.assertEqual(racz["average_rating"], 4.912)
        self.assertEqual(racz["completed_routes"], 60)


if __name__ == "__main__":
    unittest.main()
