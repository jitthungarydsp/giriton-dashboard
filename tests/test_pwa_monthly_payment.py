import ast
import copy
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote
import re

ROOT = Path(__file__).resolve().parents[1]


def load(name, ns):
    tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), "pwa_api.py", "exec"), ns)
    return ns[name]


class MonthlyPaymentTest(unittest.TestCase):
    def test_read_uses_saved_zero_and_only_monthly_invoices_without_writing(self):
        calls = []
        snapshot = {"id": "saved", "version": 9, "courier_name": "Futár"}
        def get(method, table, **kwargs):
            calls.append((method, table))
            return []
        ns = {"Any": Any, "date": date, "ThreadPoolExecutor": ThreadPoolExecutor, "quote": quote,
              "supabase_rest": get, "read_latest_courier_finance_snapshot": lambda *a, **k: snapshot,
              "read_billing_profile": lambda *a: {"courier_name": "Futár", "bank_account_number": "123", "company_name": "Cég"},
              "read_workflow_rows": lambda *a: ([
                  {"id": "monthly", "document_type": "invoice", "title": "Számla 2026-25", "note": ""},
                  {"id": "advance", "document_type": "invoice", "title": "Előleg", "note": "advance"},
              ], [], []),
              "status_map": lambda *a: {"invoice_check": {"status": "done"}},
              "snapshot_item_map": lambda *a: {"payable": {"amount_value": 0, "item_label": "Kifizetendő"}},
              "snapshot_source_payload": lambda *a: {"rows": []},
              "workflow_done": lambda states, action: states.get(action, {}).get("status") == "done",
              "workflow_open": lambda *a: False,
              "money_int": lambda v: int(v or 0), "base_action_key": str,
              "document_belongs_to_process": lambda doc, process: doc.get("note") != "advance"}
        before = copy.deepcopy(snapshot)
        payment = load("build_admin_monthly_payment", ns)("7644", date(2026, 9, 1))
        self.assertEqual(payment["amountHuf"], 0)
        self.assertEqual(payment["invoiceNumber"], "2026-25")
        self.assertEqual(len(payment["invoices"]), 1)
        self.assertTrue(payment["canClose"])
        self.assertEqual(calls, [("GET", "courier_monthly_closure")])
        self.assertEqual(snapshot, before)

    def close_namespace(self):
        class Error(Exception):
            def __init__(self, **kwargs): self.status_code = kwargs["status_code"]
        ns = {"MonthlyPaymentCloseRequest": Any, "Cookie": lambda **k: None,
              "require_user": lambda token: {"username": "admin"},
              "require_settlement_dashboard_admin": lambda user: user,
              "parse_month": lambda v: date.fromisoformat(v + "-01"), "re": re,
              "HTTPException": Error,
              "build_admin_monthly_payment": lambda *a: {"closed": False, "snapshotId": "saved",
                    "canClose": True, "blockingReason": "", "amountHuf": 402225}}
        ns["error_type"] = Error
        return ns

    def test_close_checks_snapshot_approval_note_and_only_calls_transaction_rpc(self):
        ns = self.close_namespace()
        calls = []
        ns["supabase_rest"] = lambda *a, **k: calls.append((a, k)) or {"ok": True}
        fn = load("admin_close_monthly_payment", ns)
        payload = SimpleNamespace(courierId="7644", month="2026-09", snapshotId="saved",
                                  invoiceNumber="2026-25", note="Kifizetve: 402 225 Ft", adminNote="")
        result = fn(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(calls[0][0], ("POST", "rpc/pwa_close_monthly_payment"))
        self.assertEqual(calls[0][1]["payload"]["p_actor"], "admin")
        self.assertNotIn("amountHuf", calls[0][1]["payload"])
        calls.clear()
        payload.snapshotId = "old"
        with self.assertRaises(ns["error_type"]): fn(payload)
        payload.snapshotId = "saved"
        payload.note = "Kész"
        with self.assertRaises(ns["error_type"]): fn(payload)
        self.assertEqual(calls, [])
        ns["build_admin_monthly_payment"] = lambda *a: {"closed": True}
        self.assertTrue(fn(payload)["alreadyClosed"])
        self.assertEqual(calls, [])

    def test_unauthorized_close_never_reads_or_writes_payment(self):
        ns = self.close_namespace()
        def denied(user): raise ns["error_type"](status_code=403)
        ns["require_settlement_dashboard_admin"] = denied
        ns["build_admin_monthly_payment"] = lambda *a: self.fail("Unauthorized read")
        ns["supabase_rest"] = lambda *a, **k: self.fail("Unauthorized write")
        with self.assertRaises(ns["error_type"]):
            load("admin_close_monthly_payment", ns)(SimpleNamespace())

    def test_reopen_requires_reason_and_email_is_sent_only_when_selected(self):
        ns = self.close_namespace()
        writes = []
        emails = []
        ns["supabase_rest"] = lambda *a, **k: writes.append((a, k)) or {"ok": True}
        ns["build_admin_monthly_payment"] = lambda *a: {"courierName": "Futár", "amountHuf": 402225}
        ns["format_email_huf"] = str
        ns["send_courier_template_email"] = lambda **kwargs: emails.append(kwargs)
        ns["run_pwa_background"] = lambda label, fn: fn()
        fn = load("admin_reopen_monthly_payment", ns)
        payload = SimpleNamespace(courierId="7644", month="2026-09", note="", notifyCourier=False)
        with self.assertRaises(ns["error_type"]): fn(payload)
        self.assertEqual(writes, [])
        payload.note = "Hibás számla"
        fn(payload)
        self.assertEqual(writes[0][0], ("POST", "rpc/pwa_reopen_monthly_payment"))
        self.assertEqual(emails, [])
        payload.notifyCourier = True
        fn(payload)
        self.assertEqual(emails[0]["courier_id"], "7644")
        self.assertEqual(emails[0]["template_key"], "payment_rejected")

    def test_ui_shows_invoice_payment_and_disabled_closed_action(self):
        source = (ROOT / "pwa/app.js").read_text(encoding="utf-8")
        function = source[source.index("function settlementDashboardPaymentPanel("):
                          source.index("async function loadSettlementDashboardMonthlyPayment(")]
        script = "const assert = require('assert');\n"
        script += "const state={settlementDashboardMonth:'2026-09', settlementDashboardPayment:{courierId:'7644',month:'2026-09',loading:false,error:'',data:{snapshotVersion:9,recipientName:'Cég',bankAccount:'123',amountHuf:402225,closed:true,canClose:false,invoices:[{id:'invoice'}],invoiceCheck:{status:'done'},breakdown:[],tigBreakdown:{rows:[]}}}};\n"
        script += "const escapeHtml=String; const formatHuf=v=>`${v} Ft`; const formatMonthLabel=String; const documentPreviewList=docs=>docs.map(d=>d.id).join(''); const previousLocalMonth=()=> '2026-09';\n"
        script += function
        script += "const html=settlementDashboardPaymentPanel({courierId:'7644'}); assert(html.includes('invoice'));assert(html.includes('402225 Ft'));assert(html.includes('data-close-monthly-payment disabled')); assert(html.includes('banki utalást nem indít'));\n"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
