import ast
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CapacityTest(unittest.TestCase):
    def endpoint(self, allowed=(1, 2), reject=False):
        tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
        names = {"coordinator_schedule_capacity", "schedule_capacity_summary", "schedule_capacity_coverage"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for node in nodes:
            node.decorator_list = []
        calls = []
        rows = [dict(work_date="2026-11-30", warehouse_code="BUD1", opened=10, assigned=8, free_slots=2, capacity_published=True),
                dict(work_date="2026-11-30", warehouse_code="BUD2", opened=20, assigned=15, free_slots=5, capacity_published=True),
                dict(work_date="2026-11-30", warehouse_code="BUD1", opened=100, assigned=100, free_slots=0, capacity_published=False),
                dict(work_date="2026-12-01", warehouse_code="BUD1", opened=10, assigned=10, free_slots=0, capacity_published=True)]
        def read(start, end):
            calls.append((start, end))
            return rows
        def authorize(user):
            if reject:
                raise PermissionError()
            return user
        ns = dict(Any=Any, Cookie=lambda **k: None, datetime=SimpleNamespace(now=lambda _:datetime(2026, 11, 30, 23)),
                  timedelta=timedelta, LOCAL_TIMEZONE=None, require_user=lambda _: {}, require_coordinator=authorize,
                  coordinator_warehouse_ids=lambda _:list(allowed), read_schedule_capacity_rows=read,
                  warehouse_allowed=lambda value, ids: int(str(value).replace("BUD", "")) in ids,
                  normalize_warehouse=str, safe_int=lambda v:int(v or 0), safe_bool=bool)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "capacity", "exec"), ns)
        return ns, calls

    def test_five_days_cross_month_both_warehouses_and_unknown(self):
        ns, calls = self.endpoint()
        payload = ns["coordinator_schedule_capacity"]()
        self.assertEqual(calls, [(date(2026,11,30),date(2026,12,4))])
        self.assertEqual(len(payload["days"]), 5)
        first = payload["days"][0]["warehouses"]
        self.assertEqual([(w["warehouse"],w["coveragePercent"],w["freeSlots"]) for w in first], [("BUD1",80,2),("BUD2",75,5)])
        self.assertEqual(payload["days"][1]["warehouses"][0]["freeSlots"], 0)
        self.assertFalse(payload["days"][-1]["warehouses"][0]["capacityKnown"])
        self.assertIsNone(payload["days"][-1]["warehouses"][0]["freeSlots"])

    def test_warehouse_scope_and_authorization(self):
        ns, _ = self.endpoint((2,))
        payload = ns["coordinator_schedule_capacity"]()
        self.assertTrue(all([w["warehouse"] for w in day["warehouses"]] == ["BUD2"] for day in payload["days"]))
        ns, calls = self.endpoint(reject=True)
        with self.assertRaises(PermissionError):
            ns["coordinator_schedule_capacity"]()
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
