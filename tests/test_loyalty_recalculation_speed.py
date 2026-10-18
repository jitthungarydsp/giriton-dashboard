import ast
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd


class SummaryDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0
        self.writes = []

    def schema(self, name):
        return self

    def table(self, name):
        if name != "courier_settlement_summary":
            raise AssertionError(f"Unexpected full-finance access: {name}")
        self.amount = None
        self.ids = None
        self.bounds = (0, 999)
        return self

    def select(self, columns):
        return self

    def eq(self, column, value):
        self.session = value
        return self

    def order(self, column):
        return self

    def range(self, start, end):
        self.bounds = (start, end)
        return self

    def update(self, payload):
        self.amount = payload["loyalty_bonus_huf"]
        return self

    def in_(self, column, values):
        self.ids = values
        return self

    def execute(self):
        selected = [row for row in self.rows if row["session_id"] == self.session]
        if self.amount is None:
            self.reads += 1
            start, end = self.bounds
            return SimpleNamespace(data=[dict(row) for row in selected[start:end + 1]])
        self.writes.append((self.amount, self.ids))
        for row in selected:
            if row["id"] in self.ids:
                row["loyalty_bonus_huf"] = self.amount
        return SimpleNamespace(data=[])


class LoyaltyRecalculationSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        names = {"persist_loyalty_summary_changes", "store_loyalty_recalculation_for_session"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        cls.code = compile(ast.Module(body=nodes, type_ignores=[]), "devtest.py", "exec")

    def namespace(self, db):
        ns = {
            "pd": pd, "date": date, "get_db": lambda: db,
            "_courier_id_key": lambda value: str(value or ""),
            "_courier_match_key": lambda value: str(value or "").lower(),
            "parse_huf_value": lambda value: float(value or 0),
            "st": SimpleNamespace(session_state={}),
            "apply_loyalty_bonus": lambda data, *args: data.copy(),
            "settlement_loyalty_cache_key": lambda *args: "loyalty_cache",
            "clear_settlement_overview_data_cache": Mock(),
            "load_courier_settlement_summary": SimpleNamespace(clear=Mock()),
            "load_courier_settlement_summary_row": SimpleNamespace(clear=Mock()),
            "save_devtest_finance_snapshots_for_rows": Mock(side_effect=AssertionError("Full recalculation")),
        }
        exec(self.code, ns)
        return ns

    def rows(self, count, amount=0):
        return [{"id": str(index), "courier_id": str(index), "driver_name": f"Courier {index}",
                 "session_id": "month", "loyalty_bonus_huf": amount, "payable_huf": 500000}
                for index in range(count)]

    def data(self, count, amount=19000):
        return pd.DataFrame([{"Courier ID": str(index), "Futár": f"Courier {index}",
                              "Lojalitás": amount, "Lojalitás aktuális normál kör": 19,
                              "Lojalitás előre foglalt nap": 48} for index in range(count)])

    def test_250_couriers_use_one_read_three_writes_and_no_full_financial_save(self):
        db = SummaryDatabase(self.rows(250))
        ns = self.namespace(db)
        progress = Mock()
        count = ns["store_loyalty_recalculation_for_session"](
            self.data(250), period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            session_id="month", calculation_mode="Excel", progress_callback=progress,
        )
        self.assertEqual(count, 250)
        self.assertEqual(db.reads, 1)
        self.assertEqual(len(db.writes), 3)
        self.assertTrue(all(row["payable_huf"] == 500000 for row in db.rows))
        self.assertTrue(all(row["loyalty_bonus_huf"] == 19000 for row in db.rows))
        ns["save_devtest_finance_snapshots_for_rows"].assert_not_called()
        self.assertTrue(ns["st"].session_state["loyalty_cache_pending_publication"])
        self.assertEqual(ns["st"].session_state["loyalty_cache"]["id:249"]["Lojalitás előre foglalt nap"], 48)
        self.assertEqual(progress.call_args.args, ("Mentés", 250, 250))

    def test_unchanged_amounts_do_not_write(self):
        db = SummaryDatabase(self.rows(250, amount=19000))
        ns = self.namespace(db)
        self.assertEqual(ns["persist_loyalty_summary_changes"](self.data(250), "month"), 0)
        self.assertEqual(db.reads, 1)
        self.assertEqual(db.writes, [])

    def test_other_sessions_and_couriers_are_untouched(self):
        rows = self.rows(3)
        rows.append({**rows[0], "id": "other-month", "session_id": "other"})
        db = SummaryDatabase(rows)
        ns = self.namespace(db)
        data = self.data(1)
        ns["persist_loyalty_summary_changes"](data, "month")
        self.assertEqual([row["loyalty_bonus_huf"] for row in rows], [19000, 0, 0, 0])

    def test_pagination_includes_last_courier(self):
        db = SummaryDatabase(self.rows(1001))
        ns = self.namespace(db)
        ns["persist_loyalty_summary_changes"](self.data(1001).tail(1), "month")
        self.assertEqual(db.reads, 2)
        self.assertEqual(db.writes, [(19000, ["1000"])])

    def test_save_failure_is_reported_instead_of_success(self):
        db = Mock()
        db.schema.side_effect = RuntimeError("Connection failed")
        ns = self.namespace(db)
        with self.assertRaisesRegex(RuntimeError, "Connection failed"):
            ns["store_loyalty_recalculation_for_session"](
                self.data(1), period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                session_id="month", calculation_mode="Excel",
            )
        self.assertEqual(ns["st"].session_state, {})

    def test_missing_column_identifies_required_migration_and_does_not_cache_success(self):
        db = SummaryDatabase(self.rows(1))
        db.execute = Mock(side_effect=RuntimeError({
            "message": "column courier_settlement_summary.loyalty_bonus_huf does not exist",
            "code": "42703",
        }))
        ns = self.namespace(db)
        with self.assertRaisesRegex(RuntimeError, "settlement_add_loyalty_summary_amount.sql"):
            ns["store_loyalty_recalculation_for_session"](
                self.data(1), period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                session_id="month", calculation_mode="Excel",
            )
        self.assertEqual(ns["st"].session_state, {})
        self.assertEqual(db.writes, [])


if __name__ == "__main__":
    unittest.main()
