import ast
import base64
import re
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock


class InvoiceRecheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8"))
        names = {"latest_monthly_invoice_candidates", "read_latest_monthly_invoices", "admin_recheck_latest_monthly_invoice"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        cls.code = compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec")

    def namespace(self):
        class Error(Exception):
            def __init__(self, status_code, detail):
                self.status_code = status_code
                self.detail = detail
        records = [
            {"id": "old", "document_type": "invoice", "title": "Invoice", "uploaded_at": "2026-10-17T09:00:00Z"},
            {"id": "latest", "document_type": "invoice", "title": "Invoice", "uploaded_at": "2026-10-18T09:00:00Z", "file_name": "latest.pdf"},
            {"id": "cash", "document_type": "invoice", "title": "KP számla", "uploaded_at": "2026-10-18T10:00:00Z", "file_name": "cash.pdf"},
        ]
        def rest(method, table, *, params, **kwargs):
            self.assertEqual(method, "GET")
            self.assertEqual(params["courier_id"], "eq.7147")
            self.assertEqual(params["document_month"], "eq.2026-09-01")
            if "id" not in params:
                return list(reversed(records))
            key = params["id"][3:]
            return [{"id": key, "file_name": f"{key}.pdf", "file_content_base64": base64.b64encode(key.encode()).decode()}]
        ns = {
            "date": date, "datetime": datetime, "timezone": timezone, "Any": Any,
            "base64": base64, "re": re, "MAX_INVOICE_BYTES": 10000,
            "DashboardInvoiceRecheckRequest": Any, "Cookie": lambda **kwargs: None,
            "HTTPException": Error, "require_user": lambda *args: {"username": "admin"},
            "require_settlement_dashboard_admin": lambda value: value,
            "parse_month": lambda value: date(2026, 9, 1),
            "read_courier_display_name": lambda cid: "Courier",
            "document_belongs_to_process": lambda doc, process: not doc.get("extra_process"),
            "build_financial_breakdown": Mock(return_value={"available": True}),
            "build_workflow_tig_breakdown": Mock(return_value={"available": True}),
            "workflow_invoice_requirements": Mock(return_value={"requiresCashInvoice": False, "transferGrossHuf": 923602, "cashGrossHuf": 2000}),
            "read_billing_profile": lambda user: {"company_name": "Seller", "tax_number": "123", "company_address": "Address"},
            "validate_invoice": Mock(return_value={"ok": True, "checks": []}),
            "read_workflow_rows": lambda *args: ([], [], []),
            "status_map": lambda *args: {}, "workflow_done": lambda *args: False,
            "money_int": lambda value: int(value or 0),
            "upsert_workflow_status": Mock(), "supabase_rest": Mock(side_effect=rest),
        }
        exec(self.code, ns)
        return ns, records, Error

    def run_check(self, ns):
        return ns["admin_recheck_latest_monthly_invoice"](SimpleNamespace(month="2026-09", courierId="7147"), None)

    def test_uses_latest_transfer_even_if_cash_uploaded_later(self):
        ns, records, _ = self.namespace()
        result = self.run_check(ns)
        self.assertEqual(result["documents"][0]["id"], "latest")
        kwargs = ns["validate_invoice"].call_args.kwargs
        self.assertEqual(kwargs["content"], b"latest")
        self.assertEqual(kwargs["expected_gross_amount"], 923602)
        self.assertEqual(kwargs["expected_seller_tax_number"], "123")
        self.assertEqual(ns["upsert_workflow_status"].call_args.args[3], "done")
        # A newer upload is selected on the next run, without a browser ID.
        records.append({"id": "newest", "document_type": "invoice", "uploaded_at": "2026-10-18T11:00:00Z"})
        self.assertEqual(self.run_check(ns)["documents"][0]["id"], "newest")

    def test_extra_process_invoice_cannot_replace_monthly_invoice(self):
        ns, records, _ = self.namespace()
        records.append({"id": "extra", "document_type": "invoice", "extra_process": True,
                        "uploaded_at": "2026-10-18T12:00:00Z"})
        self.assertEqual(self.run_check(ns)["documents"][0]["id"], "latest")

    def test_transfer_note_mentioning_cash_does_not_turn_it_into_cash_invoice(self):
        ns, records, _ = self.namespace()
        records[1]["note"] = "Fizetési mód: Átutalás; Külön KP számla is feltöltve."
        self.assertEqual(self.run_check(ns)["documents"][0]["id"], "latest")

    def test_cash_requirement_checks_both_latest_documents(self):
        ns, _, _ = self.namespace()
        ns["workflow_invoice_requirements"].return_value["requiresCashInvoice"] = True
        result = self.run_check(ns)
        self.assertEqual([doc["id"] for doc in result["documents"]], ["latest", "cash"])
        self.assertEqual([call.kwargs["expected_gross_amount"] for call in ns["validate_invoice"].call_args_list], [923602, 2000])

    def test_missing_required_cash_invoice_fails_validation(self):
        ns, records, _ = self.namespace()
        records[:] = [row for row in records if row["id"] != "cash"]
        ns["workflow_invoice_requirements"].return_value["requiresCashInvoice"] = True
        result = self.run_check(ns)
        self.assertFalse(result["validation"]["ok"])
        self.assertEqual(ns["upsert_workflow_status"].call_args.args[3], "open")

    def test_closed_payment_is_checked_without_reopening(self):
        ns, _, _ = self.namespace()
        ns["workflow_done"] = lambda *args: True
        result = self.run_check(ns)
        self.assertTrue(result["paymentClosed"])
        ns["validate_invoice"].assert_called_once()
        ns["upsert_workflow_status"].assert_not_called()

    def test_invoice_failure_does_not_create_duplicate_complaints(self):
        ns, _, _ = self.namespace()
        ns["validate_invoice"].return_value = {"ok": False, "checks": [{"status": "error", "title": "Amount", "detail": "Mismatch"}]}
        result = self.run_check(ns)
        self.assertFalse(result["validation"]["ok"])
        self.assertEqual(ns["upsert_workflow_status"].call_args.args[3], "open")
        self.assertTrue(all(call.args[0] == "GET" for call in ns["supabase_rest"].call_args_list))

    def test_admin_permission_required(self):
        ns, _, Error = self.namespace()
        ns["require_settlement_dashboard_admin"] = Mock(side_effect=Error(403, "Denied"))
        with self.assertRaises(Error):
            self.run_check(ns)
        ns["supabase_rest"].assert_not_called()

    def test_missing_invoice_does_not_change_workflow(self):
        ns, records, Error = self.namespace()
        records.clear()
        with self.assertRaises(Error) as caught:
            self.run_check(ns)
        self.assertEqual(caught.exception.status_code, 404)
        ns["upsert_workflow_status"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
