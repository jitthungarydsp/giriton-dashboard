import ast
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any


class QualityShiftTimesTest(unittest.TestCase):
    def enrich(self, details, records, logins):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "pwa_api.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"quality_shift_clock", "attach_quality_shift_times"}]
        ns = {"Any": Any, "re": re, "normalize_time": lambda v: str(v or "")[:5],
              "local_datetime": lambda v: datetime.fromisoformat(v) if v else None}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pwa_api.py", "exec"), ns)
        summary = {"details": {"lateShift": details}}
        ns["attach_quality_shift_times"](summary, records, logins)
        return details

    def test_matches_shift_and_keeps_login_separate_from_earliest_queue(self):
        details = [{"date": "2026-10-13", "label": "08:45-13:15", "note": "late"}]
        records = [{"work_date": "2026-10-13", "shift_start_at": f"2026-10-13T{shift}:00+02:00",
                    "queue_started_at": f"2026-10-13T{queue}:00+02:00"}
                   for shift, queue in [("14:00", "14:02"), ("08:45", "10:00"), ("08:45", "09:01")]]
        row = self.enrich(details, records, {"2026-10-13": {"checkin_start": "08:39"}})[0]
        self.assertEqual(row["giritonLoginAt"], "08:39")
        self.assertIn("T09:01:00", row["queueStartedAt"])
        self.assertEqual(row["note"], "late")

    def test_does_not_borrow_another_day_or_shift(self):
        details = [{"date": "2026-10-13", "label": "08:45-13:15"}]
        records = [{"work_date": "2026-10-13", "shift_start_at": "2026-10-13T14:00:00",
                    "queue_started_at": "2026-10-13T14:01:00"}]
        row = self.enrich(details, records, {"2026-10-12": {"checkin_start": "08:30"}})[0]
        self.assertEqual(row["giritonLoginAt"], "")
        self.assertEqual(row["queueStartedAt"], "")


if __name__ == "__main__":
    unittest.main()
