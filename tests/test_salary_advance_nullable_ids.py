import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

import pandas as pd

from resources.salary_advance_validation import salary_advance_optional_text, salary_advance_uuid


REQUEST_ID = "67de4106-b31d-4be1-a0d4-88a79226cfbe"
PLAN_ID = "221e64d9-892f-49c9-ad7e-141870b6d8b1"


class AdvanceNullableIdsTest(unittest.TestCase):
    def handlers(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        names = {"mark_salary_advance_request_paid", "update_salary_advance_schedule", "cancel_salary_advance_plan_for_request"}
        nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
        db = Mock()
        ns = {"pd": pd, "date": date, "st": SimpleNamespace(session_state={"user": {"username": "admin"}}),
              "salary_advance_optional_text": salary_advance_optional_text, "salary_advance_uuid": salary_advance_uuid,
              "get_db": lambda: db, "create_salary_advance_plan": Mock(return_value=PLAN_ID),
              "upsert_peopleforce_card_status": Mock(), "parse_huf_value": lambda value: float(value or 0),
              "salary_advance_process_id": lambda *args: "eloleg-generated",
              "month_bounds": lambda d: (d.replace(day=1), date(2026, 9, 30)),
              "salary_advance_installment_amounts": lambda total, months: [int(total / months)] * months,
              "format_huf": str, "request_courier_finance_refresh": Mock()}
        for key in ["load_courier_salary_advance_requests", "load_salary_advance_requests_for_month",
                    "load_salary_advance_installments_for_month", "load_courier_salary_advance_history"]:
            ns[key] = Mock()
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), ns)
        return ns, db

    def row(self, **changes):
        result = dict(id=REQUEST_ID, courier_id="8264", start_date="2026-09-01", requested_amount_huf=500000,
                      installment_months=5, process_id="eloleg-8264-202610-67de4106", plan_id=float("nan"), note="")
        result.update(changes)
        return result

    def test_nullable_plan_ids_create_a_plan_then_close_with_real_uuid(self):
        for missing in [None, float("nan"), pd.NA, pd.NaT, "nan", "None", "", " null "]:
            with self.subTest(missing=repr(missing)):
                ns, db = self.handlers()
                result = ns["mark_salary_advance_request_paid"](self.row(plan_id=missing), "Rusvai Marcell")
                self.assertEqual(result, PLAN_ID)
                ns["create_salary_advance_plan"].assert_called_once()
                saved = db.schema.return_value.table.return_value.update.call_args.args[0]
                self.assertEqual(saved["plan_id"], PLAN_ID)
                self.assertEqual(saved["status"], "closed")
                self.assertEqual(saved["process_id"], "eloleg-8264-202610-67de4106")

    def test_existing_plan_is_reused_without_duplicate_plan(self):
        ns, db = self.handlers()
        ns["mark_salary_advance_request_paid"](self.row(plan_id=PLAN_ID), "Rusvai Marcell")
        ns["create_salary_advance_plan"].assert_not_called()

    def test_invalid_uuid_or_missing_required_id_blocks_before_any_write(self):
        for changes in [dict(plan_id="not-a-uuid"), dict(id=float("nan")), dict(start_date="bad date")]:
            with self.subTest(changes=changes):
                ns, db = self.handlers()
                with self.assertRaises(ValueError):
                    ns["mark_salary_advance_request_paid"](self.row(**changes), "Rusvai Marcell")
                ns["create_salary_advance_plan"].assert_not_called()
                ns["upsert_peopleforce_card_status"].assert_not_called()
                db.assert_not_called()
                self.assertEqual(db.mock_calls, [])

    def test_missing_process_id_gets_real_process_name(self):
        ns, db = self.handlers()
        ns["mark_salary_advance_request_paid"](self.row(process_id=pd.NA), "Rusvai Marcell")
        saved = db.schema.return_value.table.return_value.update.call_args.args[0]
        self.assertEqual(saved["process_id"], "eloleg-generated")

    def test_schedule_without_plan_does_not_query_nan_uuid(self):
        ns, db = self.handlers()
        message = ns["update_salary_advance_schedule"](self.row(), "Rusvai Marcell", 500000, date(2026, 9, 1), 5)
        self.assertIn("Részlet-terv még nem jött létre", message)
        self.assertEqual(db.schema.return_value.table.call_count, 1)
        self.assertEqual(db.schema.return_value.table.call_args.args[0], "courier_salary_advance_request")

    def test_cancelling_missing_plan_is_noop(self):
        ns, db = self.handlers()
        self.assertEqual(ns["cancel_salary_advance_plan_for_request"](self.row()), 0)
        self.assertEqual(db.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
