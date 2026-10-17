import ast
import json
import re
import subprocess
import unittest
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(names, ns):
    tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes: node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), ns)
    return ns


class QualityDetailsTest(unittest.TestCase):
    def namespace(self):
        return {"Any": Any, "date": date, "re": re, "json": json,
                "safe_int": lambda value: int(value or 0),
                "normalize_text": lambda value: str(value or "").lower()}

    def test_compliance_read_is_filtered_and_times_are_readable(self):
        calls = []
        def read(method, table, **kwargs):
            calls.append((method, table, kwargs))
            return [{"response_json": {"lateLoginShifts": 1, "noShowShifts": 1, "totalShifts": 3,
                     "shifts": [
                         {"date": "2026-09-07", "evaluation": "late", "plannedStart": "2026-09-07T08:30:00",
                          "plannedEnd": "2026-09-07T13:00:00", "actualStart": "2026-09-07T08:42:00"},
                         {"date": "2026-09-18", "evaluation": "no_show", "plannedStart": "13:30", "plannedEnd": "18:00"},
                         {"date": "2026-08-20", "evaluation": "late"},
                     ]}}]
        ns = self.namespace() | {"supabase_rest": read}
        load({"quality_shift_clock", "parse_shift_overview_quality_rows", "read_settlement_quality_details"}, ns)
        result = ns["read_settlement_quality_details"]("6498", date(2026, 9, 1), "compliance_bonus")
        late, absent = result["groups"]
        self.assertEqual(late["count"], 1)
        self.assertEqual(late["rows"][0]["label"], "08:30-13:00")
        self.assertIn("08:42", late["rows"][0]["note"])
        self.assertEqual(absent["rows"][0]["date"], "2026-09-18")
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[0][2]["params"]["courier_id"], "eq.6498")
        self.assertEqual(calls[0][2]["params"]["month"], "eq.9")

    def test_delay_read_keeps_cleaned_and_uncleaned_days_separate(self):
        calls = []
        def read(method, table, **kwargs):
            calls.append((method, table, kwargs))
            return [{"delivery_date": "2026-09-12", "route_id": "route1", "uncleaned_delay_count": 2,
                     "uncleaned_delay_minutes": 11, "cleaned_delay_count": 1,
                     "cleaned_delay_minutes": 9, "cleaned_reasons": ["Forgalom"]}]
        ns = self.namespace() | {"supabase_rest": read, "month_end": lambda month: date(2026, 9, 30)}
        load({"read_settlement_quality_details"}, ns)
        result = ns["read_settlement_quality_details"]("6498", date(2026, 9, 1), "delay_bonus")
        uncleaned, cleaned = result["groups"]
        self.assertEqual(uncleaned["count"], 2)
        self.assertIn("11 perc", uncleaned["rows"][0]["note"])
        self.assertEqual(cleaned["count"], 1)
        self.assertIn("Forgalom", cleaned["rows"][0]["note"])
        self.assertIn("delivery_date.lte.2026-09-30", calls[0][2]["params"]["and"])

    def test_courier_can_read_own_days_but_other_courier_still_needs_preview_rights(self):
        def denied(*args): raise PermissionError("Other courier")
        ns = self.namespace() | {"Cookie": lambda **k: None, "Query": lambda **k: "",
              "require_user": lambda *a: {"courierId": "6498"},
              "courier_identity": lambda user: (user["courierId"], "Name"),
              "dashboard_courier_id_key": str, "workflow_view_user": denied,
              "parse_month": lambda value: date(2026, 9, 1),
              "require_workflow_month_allowed": lambda *a, **k: None,
              "read_settlement_quality_details": lambda cid, month, card: {"courierId": cid}}
        load({"settlement_quality_details"}, ns)
        self.assertEqual(ns["settlement_quality_details"]("2026-09", "6498", "compliance_bonus"), {"courierId": "6498"})
        with self.assertRaises(PermissionError):
            ns["settlement_quality_details"]("2026-09", "8185", "compliance_bonus")

    def test_frontend_reuses_cache_and_refresh_forces_only_quality_read(self):
        source = (ROOT / "pwa/app.js").read_text(encoding="utf-8")
        start = source.index("async function loadSettlementQualityDetails(")
        end = source.index('\ndocument.addEventListener("click"', start)
        script = "const assert=require('assert');const state={user:{username:'admin'},settlementQualityDetailsCache:{}};const calls=[];const target={isConnected:true,innerHTML:''};const details={dataset:{qualityCard:'compliance_bonus',qualityCourier:'6498',qualityMonth:'2026-09'},querySelector:()=>target};const renderSettlementQualityDetails=()=> 'days';const escapeHtml=String;const api=async(path,options)=>{calls.push(path);return {groups:[]}};\n"
        script += source[start:end]
        script += "\n(async()=>{await loadSettlementQualityDetails(details);await loadSettlementQualityDetails(details);assert.equal(calls.length,1);await loadSettlementQualityDetails(details,true);assert.equal(calls.length,2);assert(calls[0].startsWith('/api/workflow/quality-details?'));assert(calls[0].includes('courier=6498'));assert.equal(target.innerHTML,'days');})().catch(e=>{console.error(e);process.exit(1)});"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
