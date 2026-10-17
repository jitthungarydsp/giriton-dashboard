import ast
import copy
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def functions(names, namespace):
    tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), namespace)
    return namespace


class DashboardLatestSnapshotsTest(unittest.TestCase):
    def namespace(self):
        return {"Any": Any, "date": date, "datetime": datetime, "timezone": timezone}

    def test_latest_only_request_is_get_and_does_not_load_history(self):
        calls = []
        latest = [{"courier_id": "7817", "version": 9, "metadata": {"payable_total": -17668}}]
        def get(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return latest
        ns = self.namespace() | {"supabase_rest": get,
                                "optional_supabase_rows_paged": lambda *a, **k: self.fail("Unexpected history read")}
        functions({"read_dashboard_latest_finance_snapshots"}, ns)
        result = ns["read_dashboard_latest_finance_snapshots"](date(2026, 9, 17))
        self.assertEqual(result, latest)
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[0][2]["params"]["p_period_start"], "2026-09-01")

    def test_uninstalled_view_uses_unchanged_legacy_query(self):
        calls = []
        def missing(*args, **kwargs):
            raise RuntimeError("RPC not installed")
        def legacy(table, **kwargs):
            calls.append((table, kwargs))
            return [{"courier_id": "1", "version": 7}, {"courier_id": "1", "version": 6}]
        ns = self.namespace() | {"supabase_rest": missing, "optional_supabase_rows_paged": legacy}
        functions({"read_dashboard_latest_finance_snapshots"}, ns)
        rows = ns["read_dashboard_latest_finance_snapshots"](date(2026, 9, 1))
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls[0][0], "courier_finance_snapshot")
        self.assertEqual(calls[0][1]["params"]["order"], "courier_id.asc,version.desc,created_at.desc")

    def test_failed_second_page_discards_partial_data(self):
        calls = []
        def get(method, path, **kwargs):
            calls.append(kwargs["params"]["offset"])
            if len(calls) == 1:
                return [{"courier_id": str(i)} for i in range(1000)]
            raise RuntimeError("Failed page")
        ns = self.namespace() | {"supabase_rest": get,
                                "optional_supabase_rows_paged": lambda *a, **k: [{"courier_id": "fallback"}]}
        functions({"read_dashboard_latest_finance_snapshots"}, ns)
        self.assertEqual(ns["read_dashboard_latest_finance_snapshots"](date(2026, 9, 1)),
                         [{"courier_id": "fallback"}])
        self.assertEqual(calls, ["0", "1000"])

    def test_fast_and_legacy_reads_produce_same_saved_totals(self):
        latest = [{"courier_id": "1", "courier_name": "A", "warehouse_label": "BUD2",
                   "version": 7, "metadata": {"payable_total": 0}, "created_at": "2026-10-17"},
                  {"courier_id": "2", "courier_name": "B", "version": 8,
                   "metadata": {"payable_total": -17668}, "created_at": "2026-10-17"}]
        history = [latest[0], {**latest[0], "version": 6, "metadata": {"payable_total": 99999}}, latest[1]]
        ns = self.namespace() | {
            "dashboard_courier_id_key": lambda v: str(v or ""),
            "dashboard_courier_name_key": lambda v: str(v or ""),
            "normalize_person_match_text": lambda v: str(v or ""),
            "money_int": lambda v: int(v or 0),
            "dashboard_month_courier_roster": lambda *a: {},
            "dashboard_monthly_flags_by_courier": lambda *a: {},
            "read_dashboard_latest_finance_snapshots": lambda *a: copy.deepcopy(latest),
        }
        functions({"build_admin_settlement_totals"}, ns)
        fast = ns["build_admin_settlement_totals"](date(2026, 9, 1))
        ns["read_dashboard_latest_finance_snapshots"] = lambda *a: copy.deepcopy(history)
        legacy = ns["build_admin_settlement_totals"](date(2026, 9, 1))
        self.assertEqual(fast["rows"], legacy["rows"])
        self.assertEqual(fast["summary"], legacy["summary"])
        self.assertEqual(fast["summary"]["totalPayableHuf"], -17668)


if __name__ == "__main__":
    unittest.main()
