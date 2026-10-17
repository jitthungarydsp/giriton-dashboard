import ast
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_function(name, ns):
    tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), "pwa_api.py", "exec"), ns)
    return ns[name]


class ComplaintResponseTest(unittest.TestCase):
    def test_workflow_load_includes_saved_response_for_admin_and_courier(self):
        row = {"id": "complaint", "admin_response": "Megnéztük a foglalásokat.",
               "responded_by": "admin", "responded_at": "2026-10-17T12:00:00+00:00"}
        def read(method, table, **kwargs):
            self.assertEqual(method, "GET")
            if table == "peopleforce_complaints":
                columns = kwargs["params"]["select"].split(",")
                return [{key: value for key, value in row.items() if key in columns}]
            return []
        ns = {"Any": Any, "date": date, "ThreadPoolExecutor": ThreadPoolExecutor,
              "supabase_rest": read, "courier_identity": lambda user: ("6206", "Hervai Olivér")}
        fn = load_function("read_workflow_rows", ns)
        complaints = fn({}, date(2026, 9, 1))[2]
        self.assertEqual(complaints[0], row)

    def test_admin_save_confirms_written_response_before_reporting_success(self):
        calls = []
        class ApiError(Exception):
            def __init__(self, **kwargs): self.status_code = kwargs["status_code"]
        def read(method, table, **kwargs):
            calls.append((method, table, kwargs))
            if method == "GET":
                return [{"id": "complaint", "courier_id": "6206", "courier_name": "Hervai Olivér",
                         "document_month": "2026-09-01", "document_type": "settlement"}]
            self.assertEqual(kwargs["prefer"], "return=representation")
            return [{"id": "complaint", **kwargs["payload"]}]
        ns = {"date": date, "datetime": datetime, "timezone": timezone,
              "AdminComplaintUpdateRequest": Any, "Cookie": lambda **k: None,
              "HTTPException": ApiError, "require_user": lambda session: {"username": "admin"},
              "require_settlement_dashboard_admin": lambda user: user,
              "supabase_rest": read, "process_id_from_action_key": lambda value: "",
              "build_workflow": lambda *a, **k: {"ok": True}}
        fn = load_function("admin_update_workflow_complaint", ns)
        result = fn("complaint", SimpleNamespace(status="resolved", response="Válasz"))
        self.assertTrue(result["ok"])
        self.assertEqual(calls[1][2]["payload"]["admin_response"], "Válasz")
        self.assertTrue(all(table == "peopleforce_complaints" for _, table, _ in calls))
        ns["supabase_rest"] = lambda method, table, **kwargs: read(method, table, **kwargs) if method == "GET" else []
        with self.assertRaises(ApiError) as error:
            fn("complaint", SimpleNamespace(status="resolved", response="Válasz"))
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
