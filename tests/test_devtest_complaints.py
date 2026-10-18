import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class DevtestComplaintsTest(unittest.TestCase):
    def reader(self, get):
        tree = ast.parse((ROOT / "resources/peopleforce_documents.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "read_peopleforce_complaints_for_month")
        node.decorator_list = []
        ns = dict(pd=pd, requests=SimpleNamespace(get=get), require_supabase=lambda: "https://db.test",
                  supabase_headers=lambda: {}, format_month=lambda value: value.isoformat(),
                  COMPLAINT_COLUMNS=["id", "courier_id", "document_type", "admin_response"],
                  raise_for_supabase_error=lambda response: response.raise_for_status())
        exec(compile(ast.Module(body=[node], type_ignores=[]), "complaints", "exec"), ns)
        return ns[node.name]

    def test_pages_keep_older_complaints_and_answers(self):
        rows = [dict(id=str(i), courier_id="6498", document_type="invoice_check", admin_response="Válasz") for i in range(1050)]
        calls = []
        def get(url, **kwargs):
            params = kwargs["params"]
            calls.append(params.copy())
            start = int(params["offset"])
            page = rows[start:start + int(params["limit"])]
            return SimpleNamespace(status_code=200, json=lambda: page, raise_for_status=lambda: None)
        result = self.reader(get)(date(2026, 9, 1), courier_id="6498")
        self.assertEqual(len(result), 1050)
        self.assertEqual(result.iloc[-1]["admin_response"], "Válasz")
        self.assertEqual([c["offset"] for c in calls], ["0", "500", "1000", "1050"])
        self.assertTrue(all(c["courier_id"] == "eq.6498" and c["status"] == "neq.deleted" for c in calls))

    def test_page_failure_does_not_return_incomplete_list(self):
        def get(url, **kwargs):
            def fail():
                raise RuntimeError("DB unavailable")
            offset = kwargs["params"]["offset"]
            return SimpleNamespace(status_code=200 if offset == "0" else 500,
                                   json=lambda: [{"id": "1"}],
                                   raise_for_status=(lambda: None) if offset == "0" else fail)
        with self.assertRaisesRegex(RuntimeError, "DB unavailable"):
            self.reader(get)(date(2026, 9, 1))

    def test_empty_courier_does_not_query_all_couriers(self):
        def get(*args, **kwargs):
            self.fail("An empty courier must not query the entire month")
        self.assertTrue(self.reader(get)(date(2026, 9, 1), courier_id="").empty)

    def test_ui_uses_real_monthly_records_without_hiding_invoice_checks(self):
        source = (ROOT / "devtest.py").read_text(encoding="utf-8")
        tab = source[source.index('    if selected_menu == "Reklamációk":'):source.index('    if selected_menu == "E-mail küldése":')]
        self.assertIn("courier_id=_courier_id_key(courier_id)", tab)
        self.assertNotIn('base_action_key(value) == "invoice_check"', tab)
        dialog = source[source.index("def show_reports_dialog("):source.index('@st.dialog("Bejelentés részletei"')]
        self.assertNotIn("get_demo_complaints()", dialog)
        self.assertIn("read_peopleforce_complaints_for_month(report_month)", dialog)
        self.assertIn('st.rerun(scope="app")', dialog)


if __name__ == "__main__":
    unittest.main()
