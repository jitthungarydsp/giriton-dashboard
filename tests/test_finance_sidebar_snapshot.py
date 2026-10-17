import ast
import unittest
from io import BytesIO
from pathlib import Path
from datetime import date
from types import SimpleNamespace
import html
import pandas as pd


class FinanceSidebarSnapshotTest(unittest.TestCase):
    def test_refresh_keeps_rating_and_restores_advance_without_double_deduction(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        names = {"resolve_courier_salary_advance_amount", "refresh_courier_salary_advance_row"}
        nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
        def load(start, end, include_closed=False):
            self.assertTrue(include_closed)
            return pd.DataFrame([
                {"courier_id": "7817", "amount_huf": 250000, "status": "done"},
                {"courier_id": "other", "amount_huf": 90000, "status": "open"},
            ])
        ns = {"pd": pd, "date": date, "_courier_id_key": str,
              "parse_huf_value": lambda value: float(value or 0),
              "load_salary_advance_installments_for_month": load}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), ns)
        original = {"Ügyfélértékelés": 7500, "Fizetés előleg": 0,
                    "Kifizetendő": 232332, "Levonás": 335233}
        refresh = ns["refresh_courier_salary_advance_row"]
        result = refresh(original, "7817", date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(result["Ügyfélértékelés"], 7500)
        self.assertEqual(result["Fizetés előleg"], 250000)
        self.assertEqual(result["Kifizetendő"], -17668)
        self.assertEqual(result["Levonás"], 585233)
        self.assertEqual(refresh(result, "7817", date(2026, 9, 1), date(2026, 9, 30)), result)
        self.assertEqual(original["Fizetés előleg"], 0)

    def test_failed_advance_query_cannot_be_published_as_zero(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                    and node.name == "load_salary_advance_installments_for_month")
        node.decorator_list = []
        def failed_db():
            raise ConnectionError("unavailable")
        ns = {"pd": pd, "date": date, "get_db": failed_db}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        with self.assertRaises(RuntimeError):
            ns[node.name](date(2026, 9, 1), date(2026, 9, 30), include_closed=True)

    def setUp(self):
        source = (Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8")
        self.tree = ast.parse(source)
        names = {"finance_snapshot_display_row", "_snapshot_amount", "_snapshot_source_payload"}
        nodes = [node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.ns = {"parse_huf_value": lambda value: float(value or 0)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), self.ns)

    def test_saved_version_overrides_stale_amount_and_components(self):
        snapshot = {"items": [
            {"section": "finance", "item_key": key, "amount_value": value}
            for key, value in {"payable": 498602, "base": 214450, "tip": 160228,
                               "delay_bonus": 97637, "monthly_bonus": 26400,
                               "atm_effect": -113}.items()
        ]}
        row = {"Kifizetendő": 526677, "Alapdíj": 1, "Státusz": "Számlaellenőrzésre vár"}
        result = self.ns["finance_snapshot_display_row"](row, snapshot)
        self.assertEqual(result["Kifizetendő"], 498602)
        total = (result["Alapdíj"] + result["Borravaló"] + result["Késedelmi díj"]
                 + result["Importált bónusz"] - abs(result["Importált ATM levonás"]))
        self.assertEqual(total, result["Kifizetendő"])
        self.assertEqual(result["Státusz"], row["Státusz"])
        self.assertEqual(row["Kifizetendő"], 526677)

    def test_saved_zero_does_not_revert_to_previous_amount(self):
        snapshot = {"items": [{"section": "finance", "item_key": "payable", "amount_value": 0}]}
        result = self.ns["finance_snapshot_display_row"]({"Kifizetendő": 526677, "Nettó bevétel": 214450}, snapshot)
        self.assertEqual(result["Kifizetendő"], 0)
        self.assertEqual(result["Nettó bevétel"], 0)

    def test_detail_render_saves_only_in_explicit_action_branches(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "render_courier_detail_page")
        calls = []
        def visit(current, conditions):
            if isinstance(current, ast.Call) and isinstance(current.func, ast.Name) \
                    and current.func.id == "save_current_finance_snapshot":
                calls.append((ast.literal_eval(current.args[0]), conditions))
            for field, value in ast.iter_fields(current):
                children = value if isinstance(value, list) else [value]
                for child in children:
                    if isinstance(child, ast.AST):
                        tests = conditions
                        if isinstance(current, ast.If) and field == "body":
                            tests = conditions + [ast.unparse(current.test)]
                        visit(child, tests)
        visit(node, [])
        self.assertEqual(len(calls), 3)
        for source, conditions in calls:
            if source.endswith(".preflight"):
                self.assertIn("finance_preflight_active", conditions)
            elif source.endswith(".batch"):
                self.assertTrue(any("batch_period == period_start.isoformat()" in test for test in conditions))
                self.assertTrue(any("batch_ids[batch_index]" in test for test in conditions))
            elif source.endswith(".manual"):
                self.assertTrue(any("st.button(" in test for test in conditions))
            else:
                self.fail(f"Unexpected publication path: {source}")

    def test_successful_edit_queues_one_refresh_for_affected_courier(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "request_courier_finance_refresh")
        state = {"courier_menu_7817": "Fizetés előleg"}
        ns = {"st": SimpleNamespace(session_state=state), "_courier_id_key": lambda value: str(value or "").strip()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        ns[node.name]("7817")
        ns[node.name]("7817")
        ns[node.name]("")
        self.assertEqual(state.pop("courier_rebuild_request_7817"), {"target_menu": "Fizetés előleg"})
        self.assertEqual(state, {"courier_menu_7817": "Fizetés előleg"})

    def test_rating_uses_route_alias_when_kor_is_zero(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "apply_customer_rating_bonus")
        ratings = pd.DataFrame([dict(courier_id="7817", driver_name="Roland",
                                    completed_routes=1, bonus_per_route_huf=150, bonus_total_huf=150)])
        seen = []
        def resolve(courier_id, name, routes, *args):
            seen.append(routes)
            return routes * 150
        ns = {"pd": pd, "date": date, "parse_huf_value": lambda v: float(v or 0),
              "load_customer_rating_bonus_rows": lambda *args: ratings.copy(),
              "_courier_id_key": str, "_courier_match_key": str,
              "_customer_rating_dashboard_routes": lambda *args: (pd.Series(dtype=float), pd.Series(dtype=float)),
              "resolve_customer_rating_bonus_total": resolve,
              "_numeric_series": lambda df, key: df.get(key, pd.Series(0, index=df.index)),
              "payable_bonus_total": lambda df: df["Bónusz"]}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        result = ns[node.name](pd.DataFrame([{"Courier ID": "7817", "Futár": "Roland",
                                            "Kör": 0, "Útvonalak": 50}]), date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(seen, [50])
        self.assertEqual(result.iloc[0]["Ügyfélértékelés"], 7500)

    def test_single_rating_source_replaces_placeholder_route_count(self):
        names = {"recalculate_customer_rating_source_rows", "recalculate_customer_rating_rows"}
        nodes = [node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        ns = {"pd": pd, "date": date, "parse_huf_value": lambda value: float(value or 0),
              "customer_rating_rule_amount": lambda *args: 150}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec"), ns)
        rows = pd.DataFrame([dict(completed_routes=1, bonus_per_route_huf=150,
                                 bonus_total_huf=150, average_rating=4.75, rating_count=129,
                                 source_spreadsheet_id="legacy_monthly_upload", row_data={})])
        from resources.profile_route_metrics import resolve_profile_route_metrics
        routes = resolve_profile_route_metrics(pd.DataFrame(), {"route_count": 0}, {"Kör": 50})["route_total"]
        result = ns["recalculate_customer_rating_source_rows"](
            rows, routes, date(2026, 9, 1), date(2026, 9, 30), pd.DataFrame())
        self.assertEqual(result["completed_routes"].sum(), 50)
        self.assertEqual(result["bonus_total_huf"].sum(), 7500)
        # Multiple independent sources retain their own period counts.
        other = rows.copy()
        other["source_spreadsheet_id"] = "another_period"
        combined = ns["recalculate_customer_rating_source_rows"](
            pd.concat([rows, other], ignore_index=True), 50,
            date(2026, 9, 1), date(2026, 9, 30), pd.DataFrame())
        self.assertEqual(combined["bonus_total_huf"].sum(), 300)

    def test_refresh_from_other_tab_calculates_finance_before_returning(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "render_courier_detail_page")
        preflight = next(child for child in node.body if isinstance(child, ast.If)
                         and ast.unparse(child.test) == "finance_preflight_active")
        ns = {"st": SimpleNamespace(session_state={"tab": "Fizetés előleg"}),
              "finance_preflight_active": True, "finance_preflight_key": "pending",
              "finance_preflight_target_key": "target", "menu_key": "tab"}
        exec(compile(ast.Module(body=[preflight], type_ignores=[]), "devtest.py", "exec"), ns)
        self.assertEqual(ns["st"].session_state["tab"], "Pénzügy")

    def test_snapshot_counts_accept_overview_column_names(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "mobile_breakdown_rows_from_settlement_row")
        ns = {"parse_huf_value": lambda value: float(value or 0)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        rows = ns[node.name]({"Kör": 50, "Rendelés": 700})
        amounts = {row["item_key"]: row["amount_value"] for row in rows}
        self.assertEqual(amounts["routes"], 50)
        self.assertEqual(amounts["orders"], 700)

    def test_closed_advance_remains_in_monthly_calculation(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "apply_salary_advance_deduction")
        def load(start, end, include_closed=False):
            self.assertTrue(include_closed)
            return pd.DataFrame([{"courier_id": "7817", "amount_huf": 250000, "status": "done"}])
        ns = {"pd": pd, "date": date, "_courier_id_key": str,
              "load_salary_advance_installments_for_month": load}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        result = ns[node.name](pd.DataFrame([{"Courier ID": "7817", "Levonás": 100,
                                            "Kifizetendő": 300000}]), date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(result.iloc[0]["Fizetés előleg"], 250000)
        self.assertEqual(result.iloc[0]["Levonás"], 250100)
        self.assertEqual(result.iloc[0]["Kifizetendő"], 50000)

    def test_advance_loader_keeps_workflow_open_only_and_excludes_cancelled(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "load_salary_advance_installments_for_month")
        node.decorator_list = []
        captured = []
        class Query:
            def schema(self, *args): return self
            def table(self, *args): return self
            def select(self, *args): return self
            def in_(self, column, statuses): captured.append(statuses); return self
            def gte(self, *args): return self
            def lte(self, *args): return self
            def execute(self): return SimpleNamespace(data=[])
        ns = {"pd": pd, "date": date, "get_db": Query}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        ns[node.name](date(2026, 9, 1), date(2026, 9, 30))
        ns[node.name](date(2026, 9, 1), date(2026, 9, 30), include_closed=True)
        self.assertEqual(captured, [["open"], ["open", "done"]])

    def test_sidebar_uses_same_snapshot_for_tig_and_ledger(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_empty_right_menu")
        code = ast.unparse(node)
        self.assertIn("finance_snapshot_display_row(row, panel_snapshot)", code)
        self.assertIn("_snapshot_source_payload(panel_snapshot, 'tig_breakdown')", code)
        self.assertNotIn("transfer_uploaded or transfer_expected", code)

    def test_empty_sidebar_html_is_not_markdown_code(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_empty_right_menu")
        rendered = []
        ns = {"pd": pd, "date": date, "html": html,
              "parse_huf_value": lambda value: float(value or 0),
              "format_huf": lambda value: f"{int(value)} Ft",
              "format_bank_account_4": lambda value: str(value or ""),
              "st": SimpleNamespace(markdown=lambda text, **kwargs: rendered.append(text))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        ns["render_empty_right_menu"]()
        self.assertEqual(len(rendered), 1)
        self.assertTrue(rendered[0].startswith('<div class="right-empty-menu">'))
        self.assertNotIn("\n\n", rendered[0])
        self.assertTrue(all(not line.startswith(" ") for line in rendered[0].splitlines()))

    def test_initial_empty_sidebar_is_skipped_for_selected_courier(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "show_new_settlement_page")
        prefix = ast.Module(body=[ast.FunctionDef(
            name="render_initial_sidebar", args=node.args, body=node.body[:2],
            decorator_list=[], returns=None,
        )], type_ignores=[])
        calls = []
        ns = {"apply_design": lambda: None, "render_empty_right_menu": lambda: calls.append("empty"),
              "st": SimpleNamespace(session_state={"selected_courier_id": "7665"})}
        exec(compile(ast.fix_missing_locations(prefix), "devtest.py", "exec"), ns)
        ns["render_initial_sidebar"]()
        self.assertEqual(calls, [])
        ns["st"].session_state.clear()
        ns["render_initial_sidebar"]()
        self.assertEqual(calls, ["empty"])

    def test_tig_pdf_requests_cash_invoice_only_above_1000(self):
        from resources.settlement_pdf import build_tig_pdf
        from pypdf import PdfReader
        for cash in (122, 1000, 1001):
            with self.subTest(cash=cash):
                pdf = build_tig_pdf(
                    {"name": "Teszt Futár", "id": "7665", "tig_type": "AAM"},
                    {"payable": 498602, "tip": 160228, "cash": cash},
                )
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
                self.assertEqual("ELADÓ - KP SZÁMLA" in text, cash > 1000)


if __name__ == "__main__":
    unittest.main()
