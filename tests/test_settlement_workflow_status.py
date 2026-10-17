import ast
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from resources.settlement_workflow_status import (
    settlement_dashboard_status,
    settlement_dashboard_status_from_row,
)


ROOT = Path(__file__).resolve().parents[1]


def load_functions(filename, names, namespace):
    """Exercise UI functions without starting Streamlit or the API server."""
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class SettlementWorkflowStatusTest(unittest.TestCase):
    def test_snapshot_dashboard_reads_workflow_without_changing_amounts(self):
        import copy
        data = {
            "peopleforce_documents": [
                {"courier_id": "2", "document_type": "tig"},
                {"courier_id": "3", "document_type": "tig"},
            ],
            "peopleforce_card_statuses": [
                {"courier_id": "2", "action_key": "settlement", "status": "done", "updated_at": "2026-10-02"},
                {"courier_id": "2", "action_key": "settlement", "status": "open", "updated_at": "2026-10-01"},
                {"courier_id": "3", "action_key": "settlement", "status": "done"},
                {"courier_id": "3", "action_key": "tig", "status": "done"},
                {"courier_id": "3", "action_key": "invoice_payment", "status": "done"},
                {"courier_id": "1", "action_key": "settlement:advance", "status": "done"},
            ],
            "peopleforce_complaints": [
                {"courier_id": "4", "document_type": "settlement", "status": "open"},
                {"courier_id": "5", "document_type": "settlement", "status": "open", "admin_response": "Answered"},
            ],
        }
        calls = []
        def read(table, month, fields):
            calls.append((table, month))
            return data[table]
        ns = {"Any": Any, "date": date, "_workflow_month_rows": read,
              "dashboard_courier_id_key": str, "money_int": lambda v: int(v or 0),
              "base_action_key": lambda a: str(a).split(":")[0],
              "process_id_from_action_key": lambda a: str(a).partition(":")[2],
              "settlement_dashboard_status": settlement_dashboard_status}
        load_functions("pwa_api.py", {"attach_readonly_dashboard_statuses", "_dashboard_status_from_bulk",
                                     "workflow_done", "workflow_open", "workflow_status", "workflow_action_visible"}, ns)
        original = {"rows": [dict(courierId=str(i), snapshotVersion=7, totalPayableHuf=100*i,
                                 status={"label": "Devtest összesítés"}) for i in range(1, 6)],
                    "summary": {"couriers": 5, "totalPayableHuf": 1500}}
        before = copy.deepcopy(original)
        result = ns["attach_readonly_dashboard_statuses"](date(2026, 9, 1), original)
        self.assertEqual(original, before)
        self.assertEqual([r["totalPayableHuf"] for r in result["rows"]], [100, 200, 300, 400, 500])
        self.assertEqual([r["status"]["label"] for r in result["rows"]], [
            "Elszámolás elfogadásra vár", "TIG elfogadásra vár", "Kifizetve",
            "Reklamáció", "Elszámolás elfogadásra vár",
        ])
        self.assertEqual(result["summary"]["statusCounts"]["Elszámolás elfogadásra vár"], 2)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(month == "2026-09-01" for table, month in calls))

    def test_prepared_tig_cannot_skip_settlement_acceptance(self):
        for later in ({}, {"tig_done": True}, {"invoice_submit_open": True},
                      {"invoice_check_open": True}, {"invoice_payment_open": True}):
            with self.subTest(later=later):
                flags = dict(settlement_ready=True, settlement_done=False, tig_ready=True, tig_done=False)
                flags.update(later)
                self.assertEqual(settlement_dashboard_status(**flags)["label"], "Elszámolás elfogadásra vár")

    def test_tig_requires_acceptance_and_a_document(self):
        for ready, expected in ((False, "TIG-re vár"), (True, "TIG elfogadásra vár")):
            self.assertEqual(settlement_dashboard_status(
                settlement_ready=True, settlement_done=True, tig_ready=ready, tig_done=False,
            )["label"], expected)

    def test_old_database_label_and_open_tig_are_not_authoritative(self):
        row = dict(session_id="monthly", settlement_done=False, has_tig_document=True,
                   dashboard_status_label="TIG elfogadásra vár")
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "Elszámolás elfogadásra vár")
        row.update(settlement_done=True, has_tig_document=False, tig_started=True)
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "TIG-re vár")

    def test_complaints_and_completed_payment(self):
        flags = dict(settlement_ready=True, settlement_done=True, tig_ready=True, tig_done=True)
        self.assertEqual(settlement_dashboard_status(**flags, open_complaints=2)["label"], "Reklamáció")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_payment_done=True)["label"], "Kifizetve")

    def test_payment_waiting_survives_older_view_without_payment_flag(self):
        row = dict(session_id="monthly", settlement_done=True, has_tig_document=True,
                   tig_done=True, invoice_submit_done=False,
                   dashboard_status_label="Kifizetésre vár")
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "Kifizetésre vár")
        row["invoice_payment_open"] = False
        self.assertNotEqual(settlement_dashboard_status_from_row(row)["label"], "Kifizetésre vár")
        row["invoice_payment_open"] = True
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "Kifizetésre vár")
        row["settlement_done"] = False
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "Elszámolás elfogadásra vár")

    def test_old_payment_label_cannot_hide_pending_invoice_review(self):
        row = dict(session_id="monthly", settlement_done=True, tig_done=True,
                   invoice_submit_done=True, invoice_check_open=True,
                   dashboard_status_label="Kifizetésre vár")
        self.assertEqual(settlement_dashboard_status_from_row(row)["label"], "Számla ellenőrzésre vár")

    def test_approved_invoice_waits_for_payment_without_separate_payment_action(self):
        flags = dict(settlement_ready=True, settlement_done=True, tig_ready=True,
                     tig_done=True, invoice_submit_done=True, invoice_check_done=True)
        self.assertEqual(settlement_dashboard_status(**flags)["label"], "Kifizetésre vár")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_payment_done=True)["label"], "Kifizetve")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_check_open=True)["label"], "Számla ellenőrzésre vár")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_submit_open=True)["label"], "Számlafeltöltésre vár")

    def test_pwa_full_and_bulk_follow_same_prerequisite(self):
        ns = load_functions("pwa_api.py", {
            "workflow_status", "workflow_done", "workflow_open", "workflow_action_visible",
            "workflow_dashboard_open_complaints", "workflow_dashboard_status", "_dashboard_status_from_bulk",
            "base_action_key",
        }, {"Any": Any, "re": __import__("re"), "settlement_dashboard_status": settlement_dashboard_status})
        states = {"settlement": {"status": "open"}, "tig": {"status": "open"},
                  "invoice_payment": {"status": "open"}}
        workflow = {"states": states, "steps": [
            {"key": "settlement_document", "done": True}, {"key": "settlement", "done": False},
            {"key": "tig_document", "done": True}, {"key": "tig", "done": False},
        ]}
        full = ns["workflow_dashboard_status"](workflow)
        bulk = ns["_dashboard_status_from_bulk"](
            has_summary=True, has_settlement_document=True, has_tig_document=True,
            states=states, open_complaints=0,
        )
        self.assertEqual(full, bulk)
        self.assertEqual(full["label"], "Elszámolás elfogadásra vár")
        workflow["steps"][1]["done"] = True
        workflow["steps"][3]["done"] = True
        workflow["steps"].append({"key": "invoice_submit", "done": True})
        workflow["complaints"] = {"invoice_check": [
            {"document_type": "invoice_check", "status": "new", "message": "Automatikus hiba"},
        ]}
        self.assertEqual(ns["workflow_dashboard_status"](workflow)["label"], "Számla ellenőrzésre vár")

    def test_streamlit_fast_list_recomputes_stale_database_label(self):
        row = dict(courier_id="7688", courier_name="Teszt Futár", payable_huf=100,
                   session_id="monthly", settlement_done=False, has_tig_document=True,
                   dashboard_status_label="TIG elfogadásra vár")
        ns = {
            "pd": pd, "date": date, "settlement_dashboard_status_from_row": settlement_dashboard_status_from_row,
            "load_fast_admin_settlement_dashboard_rows": lambda *_: [row.copy()],
            "_courier_id_key": lambda value: str(value or ""),
            "parse_huf_value": lambda value: float(value or 0),
            "load_courier_master": lambda *_: pd.DataFrame(),
            "augment_settlement_courier_master": lambda value, *_: value,
            "timedelta": timedelta,
            "settlement_dashboard_status": settlement_dashboard_status,
            "read_peopleforce_documents_for_month": lambda *_: pd.DataFrame(),
            "read_peopleforce_card_statuses_for_month": lambda *_: pd.DataFrame(),
            "read_peopleforce_complaints_for_month": lambda *_: pd.DataFrame(),
        }
        for name in ("apply_loyalty_bonus", "apply_settlement_attention_flags", "apply_monthly_closure_status",
                     "apply_salary_advance_request_status", "apply_expense_request_status", "apply_effective_payment_total_column"):
            ns[name] = lambda value, *_: value
        load_functions("devtest.py", {"build_fast_settlement_overview_data", "_streamlit_status_from_dashboard_label", "apply_peopleforce_workflow_status"}, ns)
        result = ns["build_fast_settlement_overview_data"](None, date(2026, 9, 1), date(2026, 9, 30), None)
        self.assertEqual(result.iloc[0]["Státusz"], "Elszámolás elfogadásra vár")

    def test_pending_invoice_check_is_not_payment_waiting(self):
        flags = dict(settlement_ready=True, settlement_done=True, tig_ready=True,
                     tig_done=True, invoice_submit_done=True, invoice_payment_open=True)
        self.assertEqual(settlement_dashboard_status(**flags, invoice_check_open=True)["label"], "Számla ellenőrzésre vár")
        self.assertEqual(settlement_dashboard_status(**flags)["label"], "Számla ellenőrzésre vár")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_check_done=True)["label"], "Kifizetésre vár")
        self.assertEqual(settlement_dashboard_status(**flags, invoice_submit_open=True)["label"], "Számlafeltöltésre vár")

    def test_monthly_admin_distinguishes_invoice_check_from_complaints(self):
        statuses = pd.DataFrame([
            dict(courier_id="8185", action_key=action, status=value,
                 document_month="2026-09-01", updated_at="2026-10-16")
            for action, value in [("settlement", "done"), ("tig", "done"),
                                  ("invoice_submit", "done"), ("invoice_check", "open"),
                                  ("invoice_payment", "open")]
        ])
        ns = {
            "pd": pd, "date": date, "timedelta": timedelta,
            "settlement_dashboard_status": settlement_dashboard_status,
            "_courier_id_key": lambda value: str(value or ""),
            "read_peopleforce_documents_for_month": lambda *_: pd.DataFrame(),
            "read_peopleforce_card_statuses_for_month": lambda month: statuses if month.month == 9 else pd.DataFrame(),
            "read_peopleforce_complaints_for_month": lambda *_: pd.DataFrame([
                dict(courier_id="8185", document_type="invoice_check", status="new", message="Automatikus hiba"),
                dict(courier_id="8185", document_type="process:advance:settlement", status="new", message="Előleg reklamáció"),
            ]),
            "process_id_from_action_key": lambda value: str(value or "").split(":")[1] if str(value or "").startswith("process:") else "",
            "base_action_key": lambda value: str(value or "").split(":")[-1],
            "complaint_status_meta": lambda *_: ("Új", "complaint-status-new", "led-orange"),
            "SETTLEMENT_ATTENTION_ACTION_KEY": "settlement_attention",
        }
        load_functions("devtest.py", {"apply_peopleforce_workflow_status", "_streamlit_status_from_dashboard_label"}, ns)
        data = pd.DataFrame([{"Courier ID": "8185", "Státusz": "Bejelentések", "_settlement_ready": True}])
        result = ns["apply_peopleforce_workflow_status"](data, date(2026, 9, 1))
        self.assertEqual(result.iloc[0]["Státusz"], "Számlaellenőrzésre vár")
        self.assertTrue(result.iloc[0]["Számlaellenőrzés reklamáció"])
        self.assertEqual(result.iloc[0]["Bejelentés státusz"], "Nincs bejelentés")
        ns["read_peopleforce_complaints_for_month"] = lambda *_: pd.DataFrame([
            dict(courier_id="8185", document_type="settlement", status="new", message="Valódi reklamáció"),
        ])
        result = ns["apply_peopleforce_workflow_status"](data, date(2026, 9, 1))
        self.assertEqual(result.iloc[0]["Státusz"], "Bejelentések")

    def test_sql_view_checks_settlement_before_downstream_actions(self):
        sql = (ROOT / "sql/settlement_admin_dashboard_fast_view.sql").read_text(encoding="utf-8")
        self.assertIn("end as dashboard_status_sort,", sql)
        self.assertIn("    invoice_payment_open\nfrom dashboard_rows", sql)
        for block in sql.split("    case\n")[1:]:
            self.assertLess(block.index("and not settlement_done then"), block.index("when invoice_payment_done"))
            self.assertNotIn("has_tig_document or tig_started", block)


if __name__ == "__main__":
    unittest.main()
