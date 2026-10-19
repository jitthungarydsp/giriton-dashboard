import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Any
import unittest
from unittest.mock import Mock
from urllib.parse import quote


SOURCE = Path(__file__).resolve().parents[1] / "pwa_api.py"


def load_function(name, namespace):
    node = next(n for n in ast.parse(SOURCE.read_text(encoding="utf-8")).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


class DashboardDetailLoadingTest(unittest.TestCase):
    def test_one_snapshot_query_includes_items_and_only_display_sources(self):
        saved = {"id": "latest", "items": [{"item_key": "payable"}], "sources": []}
        rest = Mock(return_value=[saved])
        legacy = Mock(side_effect=AssertionError("No duplicate snapshot read"))
        read = load_function("read_dashboard_detail_snapshot", {
            "Any": Any, "date": date, "supabase_rest": rest,
            "read_latest_courier_finance_snapshot": legacy,
        })
        self.assertEqual(read("8001", date(2026, 9, 12)), saved)
        rest.assert_called_once()
        args = rest.call_args.kwargs
        self.assertEqual(args["schema"], "settlement")
        self.assertEqual(args["params"]["courier_id"], "eq.8001")
        self.assertEqual(args["params"]["period_start"], "eq.2026-09-01")
        self.assertIn("items:courier_finance_snapshot_item", args["params"]["select"])
        self.assertNotIn("route_detail", args["params"]["sources.source_key"])
        legacy.assert_not_called()

    def test_missing_relationship_keeps_legacy_reader(self):
        legacy = Mock(return_value={"id": "old-schema"})
        read = load_function("read_dashboard_detail_snapshot", {
            "Any": Any, "date": date, "supabase_rest": Mock(side_effect=RuntimeError("Relationship missing")),
            "read_latest_courier_finance_snapshot": legacy,
        })
        self.assertEqual(read("8001", date(2026, 9, 1)), {"id": "old-schema"})
        legacy.assert_called_once_with("8001", date(2026, 9, 1), include_sources=True)

    def test_no_saved_snapshot_does_not_repeat_the_empty_query(self):
        legacy = Mock(side_effect=AssertionError("No fallback needed for an empty month"))
        read = load_function("read_dashboard_detail_snapshot", {
            "Any": Any, "date": date, "supabase_rest": Mock(return_value=[]),
            "read_latest_courier_finance_snapshot": legacy,
        })
        self.assertEqual(read("8001", date(2026, 9, 1)), {})
        legacy.assert_not_called()

    def namespace(self):
        return {
            "Any": Any, "date": date, "datetime": datetime, "timezone": timezone,
            "ThreadPoolExecutor": ThreadPoolExecutor, "LOCAL_TIMEZONE": timezone.utc,
            "Query": lambda **kw: kw.get("default"), "Cookie": lambda **kw: kw.get("default"),
            "require_user": Mock(return_value={"role": "admin"}),
            "require_settlement_dashboard_admin": Mock(), "parse_month": lambda v: date.fromisoformat(v + "-01"),
            "read_courier_display_name": Mock(side_effect=AssertionError("Name already in snapshot")),
            "admin_finance_rows_from_snapshot": Mock(return_value=[{"key": "payable"}]),
            "read_dashboard_detail_snapshot": Mock(return_value={"id": "saved", "courier_name": "Lulaj Brendon"}),
            "read_mobile_breakdown_overrides": Mock(return_value={}),
            "read_workflow_rows": Mock(return_value=([], [], [])),
            "build_financial_breakdown_from_snapshot": Mock(return_value={"available": True, "snapshotId": "saved"}),
            "build_financial_breakdown": Mock(side_effect=AssertionError("Do not reload financial data")),
            "build_workflow_tig_breakdown": Mock(return_value={"available": True}),
            "document_belongs_to_process": lambda *a: True,
            "process_id_from_action_key": lambda *a: "", "base_action_key": lambda v: v,
            "WORKFLOW_DOCUMENT_TYPES": ["settlement", "tig", "invoice"], "quote": quote,
            "workflow_process_label": lambda v: "Elszámolás", "public_user": lambda user: dict(user),
            "status_map": lambda *a: {},
        }

    def test_detail_reuses_snapshot_and_starts_independent_reads_together(self):
        ns = self.namespace()
        barrier = Barrier(3, timeout=3)
        def concurrent(result):
            def read(*a):
                barrier.wait()
                return result
            return read
        ns["read_dashboard_detail_snapshot"].side_effect = concurrent({"id": "saved", "courier_name": "Lulaj Brendon"})
        ns["read_mobile_breakdown_overrides"].side_effect = concurrent({})
        ns["read_workflow_rows"].side_effect = concurrent(([], [], []))
        endpoint = load_function("admin_settlement_dashboard_detail", ns)
        result = endpoint(month="2026-09", courier="8001", include_tig=False, giriton_pwa_session="session")
        self.assertEqual(result["financialBreakdown"]["snapshotId"], "saved")
        self.assertEqual(result["viewingAs"]["username"], "Lulaj Brendon")
        ns["read_dashboard_detail_snapshot"].assert_called_once()
        ns["build_financial_breakdown_from_snapshot"].assert_called_once()
        ns["build_financial_breakdown"].assert_not_called()
        ns["build_workflow_tig_breakdown"].assert_not_called()
        ns["require_settlement_dashboard_admin"].assert_called_once()

    def test_missing_snapshot_preserves_full_calculation_fallback(self):
        ns = self.namespace()
        ns["read_dashboard_detail_snapshot"].return_value = {}
        ns["read_courier_display_name"].side_effect = None
        ns["read_courier_display_name"].return_value = "Courier"
        ns["build_financial_breakdown"].side_effect = None
        ns["build_financial_breakdown"].return_value = {"available": True, "legacy": True}
        endpoint = load_function("admin_settlement_dashboard_detail", ns)
        result = endpoint(month="2026-09", courier="8001", include_tig=False)
        self.assertTrue(result["financialBreakdown"]["legacy"])
        ns["build_financial_breakdown_from_snapshot"].assert_not_called()
        ns["build_financial_breakdown"].assert_called_once_with(
            {"courierId": "8001", "username": "Courier"}, date(2026, 9, 1),
            allow_unpublished=True, snapshot_only=False)

    def test_editable_drafts_are_still_previewed_without_another_snapshot_read(self):
        ns = self.namespace()
        ns["read_mobile_breakdown_overrides"].return_value = {"base": {"amount_value": 123}}
        ns["admin_merge_finance_edit_rows"] = Mock(return_value=[{"key": "base", "amountHuf": 123}])
        preview = {"id": "preview"}
        ns["admin_snapshot_dict_from_finance_rows"] = Mock(return_value=(preview, {}))
        ns["build_financial_breakdown_from_snapshot"].side_effect = [
            {"available": True, "snapshotId": "saved"}, {"available": True, "snapshotId": "preview"}]
        endpoint = load_function("admin_settlement_dashboard_detail", ns)
        result = endpoint(month="2026-09", courier="8001", include_tig=False)
        self.assertEqual(result["financialBreakdown"]["snapshotId"], "preview")
        self.assertEqual(result["editableFinanceRows"], [{"key": "base", "amountHuf": 123}])
        ns["read_dashboard_detail_snapshot"].assert_called_once()
        ns["build_financial_breakdown"].assert_not_called()

    def test_tig_is_built_only_when_requested(self):
        ns = self.namespace()
        endpoint = load_function("admin_settlement_dashboard_detail", ns)
        result = endpoint(month="2026-09", courier="8001", include_tig=True)
        self.assertTrue(result["tigLoaded"])
        ns["build_workflow_tig_breakdown"].assert_called_once()


if __name__ == "__main__":
    unittest.main()
