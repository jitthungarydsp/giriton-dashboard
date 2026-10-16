import ast
import unittest
from pathlib import Path
from typing import Any

from resources.settlement_pdf import build_tig_breakdown


def load_requirements():
    source = (Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8")
    names = {"workflow_invoice_requirements", "workflow_cash_amount_from_financial_breakdown"}
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"Any": Any, "money_int": lambda value: int(float(value or 0))}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), namespace)
    return namespace["workflow_invoice_requirements"]


class WorkflowInvoiceRequirementsTest(unittest.TestCase):
    def setUp(self):
        self.requirements = load_requirements()

    def test_komjati_cash_is_not_subtracted_twice(self):
        tig = build_tig_breakdown(
            {"tig_type": "AAM"},
            {"payable": 1025039, "tip": 237771, "cash": 55644},
        )
        result = self.requirements({"totalPayableHuf": 1025039}, tig)
        self.assertEqual(result["transferGrossHuf"], 1025039)
        self.assertEqual(result["cashGrossHuf"], 55644)
        self.assertEqual(result["totalGrossHuf"], 1080683)
        self.assertTrue(result["requiresCashInvoice"])

    def test_vat_transfer_and_separate_cash(self):
        tig = build_tig_breakdown(
            {"tig_type": "VAT"}, {"payable": 100000, "tip": 0, "cash": 152218},
        )
        result = self.requirements({}, tig)
        self.assertEqual(result["transferGrossHuf"], tig["finalTotalHuf"])
        self.assertEqual(result["totalGrossHuf"], tig["finalTotalHuf"] + 152218)

    def test_no_cash_keeps_same_total(self):
        result = self.requirements({}, {"finalTotalHuf": 402225})
        self.assertEqual(result["transferGrossHuf"], 402225)
        self.assertEqual(result["totalGrossHuf"], 402225)
        self.assertFalse(result["requiresCashInvoice"])

    def test_cash_only_process_has_no_transfer(self):
        result = self.requirements({}, {"processType": "kp_invoice", "finalTotalHuf": 55644, "cashGrossHuf": 55644})
        self.assertEqual(result["transferGrossHuf"], 0)
        self.assertEqual(result["totalGrossHuf"], 55644)
        self.assertTrue(result["cashOnlyInvoice"])
        self.assertFalse(result["requiresCashInvoice"])

    def test_missing_tig_uses_transfer_fallback_without_deducting_cash(self):
        result = self.requirements(
            {"totalPayableHuf": 1025039, "cards": []}, {"cashGrossHuf": 55644},
            expected_tig_gross_huf=1025039,
        )
        self.assertEqual(result["transferGrossHuf"], 1025039)
        self.assertEqual(result["totalGrossHuf"], 1080683)


if __name__ == "__main__":
    unittest.main()
