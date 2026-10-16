import ast
import unittest
from pathlib import Path
from typing import Any
import re

from resources.settlement_pdf import build_tig_breakdown


def load_requirements():
    source = (Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8")
    names = {"workflow_invoice_requirements", "workflow_cash_amount_from_financial_breakdown", "combine_invoice_validation_results"}
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"Any": Any, "re": re, "KP_INVOICE_THRESHOLD_HUF": 1000, "money_int": lambda value: int(float(value or 0))}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), namespace)
    return namespace


class WorkflowInvoiceRequirementsTest(unittest.TestCase):
    def setUp(self):
        self.functions = load_requirements()
        self.requirements = self.functions["workflow_invoice_requirements"]

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

    def test_cash_invoice_required_only_above_1000(self):
        for cash in (0, 113, 122, 999, 1000, 1001):
            with self.subTest(cash=cash):
                result = self.requirements({}, {"finalTotalHuf": 498602, "cashGrossHuf": cash})
                self.assertEqual(result["requiresCashInvoice"], cash > 1000)
                self.assertEqual(result["transferGrossHuf"], 498602)

    def test_two_documents_are_validated_separately(self):
        results = [
            ("Átutalásos számla", {"parsed": {"invoiceNumber": "ABC-1", "grossTotal": 498602}, "checks": []}),
            ("KP számla", {"parsed": {"invoiceNumber": "ABC-2", "grossTotal": 55644}, "checks": []}),
        ]
        combine = self.functions["combine_invoice_validation_results"]
        result = combine(results, declared_gross_amount=498602, invoice_number="ABC-1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["parsed"]["grossTotal"], 498602)
        self.assertEqual(result["parsed"]["combinedGrossTotal"], 554246)
        wrong_total = combine(results, declared_gross_amount=554246, invoice_number="ABC-1")
        self.assertFalse(wrong_total["ok"])
        results[1][1]["checks"] = [{"status": "error", "title": "TIG szerinti végösszeg", "detail": "KP összegeltérés"}]
        self.assertFalse(combine(results, declared_gross_amount=498602, invoice_number="ABC-1")["ok"])


if __name__ == "__main__":
    unittest.main()
