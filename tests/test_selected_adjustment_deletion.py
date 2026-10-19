import ast
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd


class SelectedAdjustmentDeletionTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "devtest.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "delete_marked_courier_adjustments")
        self.delete = Mock()
        ns = {"pd": pd, "delete_courier_adjustment": self.delete, "parse_huf_value": float}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "devtest.py", "exec"), ns)
        self.run_delete = ns[node.name]
        self.original = pd.DataFrame([
            {"id": "a", "adjustment_type": "bonus", "amount_huf": 5500, "note": "Original A"},
            {"id": "b", "adjustment_type": "malus", "amount_huf": 60000, "note": "Original B"},
        ])

    def test_only_checked_existing_row_is_deleted(self):
        edited = pd.DataFrame([
            {"id": "a", "Törlés": True}, {"id": "b", "Törlés": False},
            {"id": "foreign", "Törlés": True}, {"id": "a", "Törlés": True},
        ])
        self.assertEqual(self.run_delete(None, "7725", self.original, edited), 1)
        self.delete.assert_called_once_with(None, "7725", "a", "bonus", 5500.0,
                                            "Original A", valid_from=None, valid_to=None)

    def test_empty_missing_or_unchecked_selection_never_deletes_all(self):
        for flag in (False, None, float("nan"), "False", "True"):
            with self.subTest(flag=flag):
                self.assertEqual(self.run_delete(None, "7725", self.original,
                                                pd.DataFrame([{"id": "a", "Törlés": flag}])), 0)
        self.assertEqual(self.run_delete(None, "7725", self.original, pd.DataFrame()), 0)
        self.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
