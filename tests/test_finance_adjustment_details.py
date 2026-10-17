import ast
import re
import unittest
from pathlib import Path
from typing import Any
from resources.finance_adjustment_details import snapshot_manual_adjustment_details


class FinanceAdjustmentDetailsTest(unittest.TestCase):
    def snapshot(self):
        entries = [
            ("malus", 10000, "Tartalékos kör (leadás)"),
            ("malus", 65000, "Megbízó szabályainak megszegése\nMásodik sor"),
            ("manual_correction", 21000, "Ügyfélértékelés kézi korrekció"),
            ("manual_correction_deduction", 500000, "Levonás | SIW-944, FÁVAL ÜTKÖZÉS"),
            ("manual_correction_deduction", 65000, "Büntetés | Nem jelenik meg teljesítésre"),
            ("manual_correction_deduction", 409900, "Levonás | SED-126 felütés"),
        ]
        return {"sources": [{"source_key": "manual_adjustments", "payload": [
            dict(adjustment_type=kind, amount_huf=amount, note=note, valid_from="2026-09-01", valid_to="2026-09-30")
            for kind, amount, note in entries]}], "items": [
                dict(section="finance", item_key="bonus_malus", amount_value=-75000),
                dict(section="finance", item_key="correction", amount_value=-933900),
            ]}

    def test_each_correction_and_malus_has_its_own_note(self):
        snapshot = self.snapshot()
        rows = snapshot_manual_adjustment_details(snapshot, "Korrekció")
        self.assertEqual(len(rows), 5)  # Four manual rows plus the saved nonmanual remainder.
        self.assertEqual([row["Összeg"] for row in rows[:4]], [21000, -500000, -65000, -409900])
        self.assertIn("SIW-944", rows[1]["Megjegyzés"])
        self.assertEqual(sum(row["Összeg"] for row in rows), -933900)
        malus = snapshot_manual_adjustment_details(snapshot, "JITT bónusz / malus")
        self.assertEqual(len(malus), 2)
        self.assertIn("\n", malus[1]["Megjegyzés"])
        self.assertEqual(sum(row["Összeg"] for row in malus), -75000)

    def test_pwa_does_not_merge_equal_amounts_with_different_notes(self):
        source = (Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8")
        names = {"compact_snapshot_detail_items", "snapshot_detail_item", "amount_from_snapshot_detail_row"}
        nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
        ns = {"Any": Any, "money_int": lambda value: int(float(value or 0)), "re": re}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), ns)
        rows = [{"Tétel": "Malus", "Összeg": -10000, "Megjegyzés": note, "Érvényesség": "2026-09"}
                for note in ("Első indok", "Második indok")]
        items = ns["compact_snapshot_detail_items"]("bonus_malus", "JITT bónusz / malus", rows)
        self.assertEqual(len(items), 2)
        self.assertIn("Első indok", items[0]["note"])
        self.assertIn("Második indok", items[1]["note"])
        self.assertIn("2026-09", items[1]["note"])


if __name__ == "__main__":
    unittest.main()
