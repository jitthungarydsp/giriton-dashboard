import ast
from datetime import date
from pathlib import Path
from typing import Any
import unittest


class ReserveCardSnapshotTest(unittest.TestCase):
    def setUp(self):
        source = (Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8")
        names = {"build_financial_breakdown_from_snapshot", "snapshot_item_map",
                 "snapshot_items_by_section", "snapshot_signed_item", "signed_item"}
        nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.ns = {"Any": Any, "date": date, "money_int": lambda v: int(v or 0),
                   "courier_identity": lambda u: ("6686", "Magyar Csilla"),
                   "annotate_quality_financial_cards": lambda cards, notes: cards,
                   "snapshot_card_detail_items": lambda snapshot, label, card: [
                       {"key": "old_net_movement", "label": "Céltartalék feltöltés", "amountHuf": 325295}]
                   if card == "insurance" else []}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), self.ns)

    def breakdown(self, amounts):
        snapshot = {"version": 17, "items": [
            {"section": "finance", "item_key": key, "amount_value": amount}
            for key, amount in amounts.items()]}
        return self.ns["build_financial_breakdown_from_snapshot"](
            {}, date(2026, 9, 1), snapshot, include_quality_notes=False)

    def test_stale_net_drilldown_cannot_replace_booked_topup(self):
        result = self.breakdown({"reserve": -24705, "insurance_fee": -10000,
                                 "target_reserve_open": 350000, "target_reserve_close": 24705,
                                 "reserve_deduction_credit": 350000, "payable": 562345})
        cards = {card["key"]: card for card in result["cards"]}
        insurance = cards["insurance"]
        self.assertEqual(insurance["amountHuf"], -34705)
        rows = {row["key"]: row for row in insurance["items"]}
        self.assertEqual(rows["reserve"]["amountHuf"], -24705)
        self.assertEqual(rows["reserve"]["label"], "Céltartalék feltöltés")
        self.assertEqual(rows["insurance_fee"]["amountHuf"], -10000)
        self.assertEqual(rows["target_reserve_close"]["label"], "Új nyitó egyenleg")
        self.assertEqual(rows["target_reserve_close"]["amountHuf"], 24705)
        self.assertTrue(rows["target_reserve_close"]["excludeFromTotal"])
        self.assertEqual(sum(row["amountHuf"] for row in rows.values()
                             if not row.get("excludeFromTotal")), insurance["amountHuf"])
        self.assertEqual(cards["reserve_release"]["amountHuf"], 350000)
        options = {v["key"] for v in result["complaintOptions"]}
        self.assertNotIn("target_reserve_open", options)
        self.assertNotIn("target_reserve_close", options)
        self.assertNotIn("old_net_movement", options)

    def test_month_without_release_shows_topup_and_insurance(self):
        result = self.breakdown({"reserve": -50000, "insurance_fee": -10000,
                                 "target_reserve_open": 300000, "target_reserve_close": 350000})
        insurance = next(card for card in result["cards"] if card["key"] == "insurance")
        self.assertEqual(insurance["amountHuf"], -60000)
        self.assertEqual(insurance["items"][0]["amountHuf"], -50000)


if __name__ == "__main__":
    unittest.main()
