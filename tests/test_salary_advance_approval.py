"""Exercise the PWA approval handler without starting the API or contacting the DB."""
import ast
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


class SalaryAdvanceApprovalTest(unittest.TestCase):
    def handler(self, status="requested", paid_at=None):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "admin_approve_salary_advance_request")
        node.decorator_list = []
        node.args.defaults = [ast.Constant(None), ast.Constant(None)]
        row = {"id": "request-1", "courier_id": "6686", "courier_name": "Magyar Csilla",
               "start_date": "2026-10-01", "requested_amount_huf": 100000,
               "status": status, "process_id": "advance-1", "paid_at": paid_at}
        db = Mock(side_effect=[[row], None, [row]])
        workflow = Mock()
        ns = {"date": date, "datetime": datetime, "timezone": timezone,
              "HTTPException": HTTPError, "Cookie": lambda **kw: None,
              "require_user": lambda session: {"username": "admin"},
              "can_preview_couriers": lambda user: True,
              "normalize_process_id": lambda value: value,
              "clean_text": lambda value, **kw: value,
              "supabase_rest": db, "upsert_workflow_status": workflow,
              "normalize_salary_advance_request": lambda row: row}
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), "pwa_api.py", "exec"), ns)
        return ns[node.name], db, workflow

    def test_approval_requires_invoice_and_does_not_complete_check_or_payment(self):
        handler, db, workflow = self.handler()
        result = handler("request-1")
        self.assertTrue(result["ok"])
        states = {call.args[2]: call.args[3] for call in workflow.call_args_list}
        self.assertEqual(states, {"settlement": "done", "tig": "done", "invoice_submit": "open"})
        self.assertTrue(all(call.args[-1] == "advance-1" for call in workflow.call_args_list))
        saved = db.call_args_list[1].kwargs["payload"]
        self.assertEqual(saved["approved_by"], "admin")
        self.assertTrue(saved["approved_at"])

    def test_repeat_approval_cannot_reset_existing_invoice_or_payment(self):
        for status, paid_at in [("approved", None), ("paid", None), ("closed", None), ("requested", "2026-11-01")]:
            with self.subTest(status=status, paid_at=paid_at):
                handler, db, workflow = self.handler(status, paid_at)
                with self.assertRaises(HTTPError) as caught:
                    handler("request-1")
                self.assertEqual(caught.exception.status_code, 409)
                self.assertEqual(db.call_count, 1)
                workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
