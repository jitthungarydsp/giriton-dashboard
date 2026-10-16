import ast
import unittest
from io import BytesIO
from pathlib import Path


class FinanceSidebarSnapshotTest(unittest.TestCase):
    def setUp(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        self.tree = ast.parse(source)
        names = {"finance_snapshot_display_row", "_snapshot_amount", "_snapshot_source_payload"}
        nodes = [node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.ns = {"parse_huf_value": lambda value: float(value or 0)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), self.ns)

    def test_saved_version_overrides_stale_amount_and_components(self):
        snapshot = {"items": [
            {"section": "finance", "item_key": key, "amount_value": value}
            for key, value in {"payable": 498602, "base": 214450, "tip": 160228,
                               "delay_bonus": 97637, "monthly_bonus": 26400,
                               "atm_effect": -113}.items()
        ]}
        row = {"Kifizetendő": 526677, "Alapdíj": 1, "Státusz": "Számlaellenőrzésre vár"}
        result = self.ns["finance_snapshot_display_row"](row, snapshot)
        self.assertEqual(result["Kifizetendő"], 498602)
        total = (result["Alapdíj"] + result["Borravaló"] + result["Késedelmi díj"]
                 + result["Importált bónusz"] - abs(result["Importált ATM levonás"]))
        self.assertEqual(total, result["Kifizetendő"])
        self.assertEqual(result["Státusz"], row["Státusz"])
        self.assertEqual(row["Kifizetendő"], 526677)

    def test_saved_zero_does_not_revert_to_previous_amount(self):
        snapshot = {"items": [{"section": "finance", "item_key": "payable", "amount_value": 0}]}
        result = self.ns["finance_snapshot_display_row"]({"Kifizetendő": 526677, "Nettó bevétel": 214450}, snapshot)
        self.assertEqual(result["Kifizetendő"], 0)
        self.assertEqual(result["Nettó bevétel"], 0)

    def test_sidebar_uses_same_snapshot_for_tig_and_ledger(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_empty_right_menu")
        code = ast.unparse(node)
        self.assertIn("finance_snapshot_display_row(row, panel_snapshot)", code)
        self.assertIn("_snapshot_source_payload(panel_snapshot, 'tig_breakdown')", code)
        self.assertNotIn("transfer_uploaded or transfer_expected", code)

    def test_tig_pdf_requests_cash_invoice_only_above_1000(self):
        from resources.settlement_pdf import build_tig_pdf
        from pypdf import PdfReader
        for cash in (122, 1000, 1001):
            with self.subTest(cash=cash):
                pdf = build_tig_pdf(
                    {"name": "Teszt Futár", "id": "7665", "tig_type": "AAM"},
                    {"payable": 498602, "tip": 160228, "cash": cash},
                )
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
                self.assertEqual("ELADÓ - KP SZÁMLA" in text, cash > 1000)


if __name__ == "__main__":
    unittest.main()
