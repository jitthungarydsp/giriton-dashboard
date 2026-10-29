import ast
import unittest
from datetime import date, timedelta
from pathlib import Path


class MonthRangeTest(unittest.TestCase):
    def test_full_month_boundaries_and_legacy_range(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'pwa_api.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'shifts')
        node.decorator_list = []
        calls = []
        ns = dict(date=date, timedelta=timedelta,
                  Query=lambda **kwargs: kwargs.get('default'), Cookie=lambda **kwargs: None,
                  require_user=lambda _: {}, workflow_view_user=lambda user, _: (user, False),
                  read_shifts=lambda *args: calls.append(args))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'month_range', 'exec'), ns)
        for month, days in [('2026-11', 30), ('2026-12', 31), ('2028-02', 29), ('2027-02', 28)]:
            ns['shifts'](month=month)
            self.assertEqual(calls[-1][1:], (days, date.fromisoformat(month + '-01')))
        ns['shifts'](days=5)
        self.assertEqual(calls[-1], ({}, 5))


if __name__ == '__main__':
    unittest.main()
