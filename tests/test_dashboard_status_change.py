import ast
import subprocess
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class DashboardStatusChangeTest(unittest.TestCase):
    def endpoint(self):
        class Error(Exception):
            def __init__(self, **kwargs): self.status_code = kwargs["status_code"]
        calls = []
        ns = {"DashboardStatusChangeRequest": Any, "Cookie": lambda **k: None,
              "require_user": lambda token: {"username": "admin"},
              "require_settlement_dashboard_admin": lambda user: user,
              "parse_month": lambda value: date.fromisoformat(value + "-01"),
              "HTTPException": Error, "courier_has_efo_assignment": lambda *a: False,
              "supabase_rest": lambda *a, **k: calls.append((a, k)) or {"ok": True}}
        tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "admin_change_dashboard_status")
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), "pwa_api.py", "exec"), ns)
        return ns, calls, Error

    def test_only_explicit_valid_change_invokes_workflow_transaction(self):
        ns, calls, Error = self.endpoint()
        fn = ns["admin_change_dashboard_status"]
        payload = SimpleNamespace(month="2026-09", courierId="7056", target="invoice_check", note="Számla újraellenőrzése")
        fn(payload)
        self.assertEqual(calls[0][0], ("POST", "rpc/pwa_change_monthly_status"))
        self.assertEqual(calls[0][1]["payload"]["p_courier_id"], "7056")
        self.assertEqual(calls[0][1]["payload"]["p_period_start"], "2026-09-01")
        calls.clear()
        payload.note = ""
        with self.assertRaises(Error): fn(payload)
        payload.note = "Ok"
        payload.target = "paid"
        with self.assertRaises(Error): fn(payload)
        self.assertEqual(calls, [])

    def test_courier_cannot_change_admin_status_and_efo_is_not_overridden(self):
        ns, calls, Error = self.endpoint()
        payload = SimpleNamespace(month="2026-09", courierId="7056", target="settlement_wait", note="Újraellenőrzés")
        ns["courier_has_efo_assignment"] = lambda *a: True
        with self.assertRaises(Error): ns["admin_change_dashboard_status"](payload)
        ns["courier_has_efo_assignment"] = lambda *a: False
        def deny(user): raise Error(status_code=403)
        ns["require_settlement_dashboard_admin"] = deny
        with self.assertRaises(Error): ns["admin_change_dashboard_status"](payload)
        self.assertEqual(calls, [])

    def test_badge_keeps_style_and_has_distinct_click_target(self):
        source = (ROOT / "pwa/app.js").read_text(encoding="utf-8")
        start = source.index("function renderSettlementDashboardStatus(")
        end = source.index("function openSettlementDashboardStatusEditor(", start)
        script = "const assert=require('assert');const escapeHtml=String;\n" + source[start:end]
        script += "\nconst badge=renderSettlementDashboardStatus({label:'TIG elfogadásra vár',tone:'waiting'},'7056');assert(badge.includes('settlement-dashboard-status waiting'));assert(badge.includes('data-dashboard-change-status=\"7056\"'));assert(badge.includes('<button'));assert(renderSettlementDashboardStatus({label:'Kifizetve'}).startsWith('<span'));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
