import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd

from resources.efo_deduction import calculate_efo_adjustments, EfoCalculationError
from resources.finance_adjustment_details import snapshot_manual_adjustment_details, snapshot_correction_amounts


START, END = date(2026, 10, 1), date(2026, 10, 31)


def rule(**changes):
    return dict(id="r1", courier_id="8264", valid_from="2026-10-01", valid_to=None,
                daily_deduction_huf=5490, is_active=True, **changes)


def functions(*names, **dependencies):
    source = Path(__file__).resolve().parents[1] / "devtest.py"
    nodes = [item for item in ast.parse(source.read_text(encoding="utf-8")).body
             if isinstance(item, ast.FunctionDef) and item.name in names]
    for node in nodes:
        node.decorator_list = []
    namespace = {"pd": pd, "date": date, "st": SimpleNamespace(session_state={}),
                 "parse_huf_value": lambda value: 0 if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)) else float(value or 0),
                 "_courier_id_key": lambda value: str(value or "").removesuffix(".0"),
                 "calculate_efo_adjustments": calculate_efo_adjustments, "EfoCalculationError": EfoCalculationError,
                 **dependencies}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class EfoTest(unittest.TestCase):
    def calculate(self, days, rules=None, manual=()):
        return calculate_efo_adjustments("8264", days, rules if rules is not None else [rule()], START, END, manual)

    def test_distinct_dates_not_tours_and_only_requested_month(self):
        items = self.calculate(["2026-10-01", "2026-10-01", "2026-10-02", "2026-11-01"])
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(row["amount_huf"] for row in items), 10980)
        self.assertIn("1 nap × 5 490 Ft", items[0]["note"])

    def test_period_boundaries_and_rate_change(self):
        first = rule()
        first.update(valid_from="2026-10-02", valid_to="2026-10-15")
        second = dict(first, id="r2", valid_from="2026-10-16", valid_to="2026-10-30", daily_deduction_huf=6000)
        result = self.calculate(["2026-10-01", "2026-10-02", "2026-10-15", "2026-10-16", "2026-10-30", "2026-10-31"], [first, second])
        self.assertEqual([row["amount_huf"] for row in result], [5490, 5490, 6000, 6000])

    def test_inactive_deleted_and_other_courier_not_charged(self):
        self.assertEqual(self.calculate(["2026-10-02"], [dict(rule(), is_active=False), dict(rule(), deleted_at="2026-10-01"), dict(rule(), courier_id="7724")]), [])

    def test_invalid_rate_date_and_overlapping_rules_block(self):
        for rules, days in [([dict(rule(), daily_deduction_huf=-1)], ["2026-10-02"]),
                            ([rule(), dict(rule(), id="r2")], ["2026-10-02"]),
                            ([rule()], [None])]:
            with self.subTest(rules=rules, days=days), self.assertRaises(EfoCalculationError):
                self.calculate(days, rules)

    def test_existing_manual_efo_blocks_instead_of_deducting_twice(self):
        for kind in ["malus", "correction_deduction", "manual_correction_deduction", "other_expense"]:
            with self.subTest(kind=kind), self.assertRaisesRegex(EfoCalculationError, "dupla levonás"):
                self.calculate(["2026-10-02"], manual=[dict(id="m1", adjustment_type=kind, amount_huf=69300, note="Adók, EFO")])
        self.assertEqual(len(self.calculate(["2026-10-02"], manual=[dict(adjustment_type="malus", amount_huf=1000, note="CASCO")])), 1)

    def test_same_amount_in_two_warehouses_is_one_day(self):
        days = [date(2026, 10, 2), date(2026, 10, 2)]
        self.assertEqual(sum(row["amount_huf"] for row in self.calculate(days)), 5490)

    def test_saved_snapshot_correction_minus_keeps_each_date_and_rate(self):
        entries = self.calculate(["2026-10-02", "2026-10-03"])
        snapshot = {"sources": [{"source_key": "manual_adjustments", "payload": entries + [
            dict(adjustment_type="manual_correction", amount_huf=20000, note="Plusz")]}]}
        detail = snapshot_manual_adjustment_details(snapshot, "Korrekció -")
        self.assertEqual(len(detail), 2)
        self.assertEqual(sum(row["Összeg"] for row in detail), -10980)
        self.assertEqual(detail[0]["Tétel"], "EFO napi levonás")
        self.assertIn("2026-10-02", detail[0]["Megjegyzés"])
        self.assertEqual(len(snapshot_manual_adjustment_details(snapshot, "Korrekció +")), 1)

    def test_overview_rebuild_is_idempotent_and_keeps_manual_deductions(self):
        entries = self.calculate(["2026-10-02", "2026-10-03"])
        manual = pd.DataFrame([dict(adjustment_type="manual_correction", amount_huf=20000),
                               dict(adjustment_type="correction_deduction", amount_huf=3000)])
        ns = functions("apply_efo_deductions", load_efo_assignments_for_month=lambda *a: [rule()],
                       efo_adjustments_for_calculation=lambda *a: entries,
                       load_courier_adjustments=lambda *a, **kw: manual)
        data = pd.DataFrame([{"Courier ID": "8264", "Futár": "Rusvai Marcell", "Korrekció": 17000, "Kifizetendő": 117000}])
        result = ns["apply_efo_deductions"](data, "session", "Excel", START, END)
        again = ns["apply_efo_deductions"](result, "session", "Excel", START, END)
        self.assertEqual(again.iloc[0]["Korrekció"], 6020)
        self.assertEqual(again.iloc[0]["Kifizetendő"], 106020)
        self.assertEqual(again.iloc[0]["_efo_correction_deduction"], 13980)

    def test_mobile_correction_does_not_net_away_efo_or_count_detail_twice(self):
        ns = functions("append_efo_mobile_rows", "recalculate_mobile_breakdown_totals",
                       "_mobile_breakdown_amount", "_set_mobile_breakdown_row_amount")
        entries = self.calculate(["2026-10-02", "2026-10-03"])
        rows = [dict(item_key="base", amount_value=100000), dict(item_key="correction", amount_value=6020)]
        rows = ns["append_efo_mobile_rows"](rows, entries, 13980)
        rows = ns["append_efo_mobile_rows"](rows, entries, 13980)
        rows = ns["recalculate_mobile_breakdown_totals"](rows)
        amounts = {row["item_key"]: row["amount_value"] for row in rows}
        self.assertEqual(amounts["correction_income"], 20000)
        self.assertEqual(amounts["correction_deduction"], -13980)
        self.assertEqual(amounts["payable"], 106020)
        self.assertEqual(sum(row["item_key"].startswith("efo_daily_") for row in rows), 2)

    def test_missing_route_rows_block_instead_of_undercharging(self):
        ns = functions("efo_adjustments_for_calculation",
                       load_efo_assignments_for_month=lambda *a: [rule()],
                       load_courier_route_detail=lambda *a: pd.DataFrame([{"Excel dátum": "2026-10-02"}]))
        with self.assertRaises(EfoCalculationError):
            ns["efo_adjustments_for_calculation"]("8264", "Rusvai", "s", "Excel", START, END, 2)

    def test_legacy_net_only_snapshot_still_displays_its_saved_deduction(self):
        snapshot = {"items": [dict(section="finance", item_key="correction", amount_value=-69300)]}
        self.assertEqual(snapshot_correction_amounts(snapshot), (0, -69300))
        snapshot["items"] = [dict(section="finance", item_key=key, amount_value=value) for key, value in
                             [("correction", 6020), ("correction_income", 20000), ("correction_deduction", -13980)]]
        self.assertEqual(snapshot_correction_amounts(snapshot), (20000, -13980))


if __name__ == "__main__":
    unittest.main()
