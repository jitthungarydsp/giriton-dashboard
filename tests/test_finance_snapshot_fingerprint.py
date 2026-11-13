import ast
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_function(path: Path, function_name: str, namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[function_name]


class FinanceSnapshotFingerprintTest(unittest.TestCase):
    def setUp(self):
        self.devtest_fingerprint = load_function(
            ROOT / "devtest.py",
            "_finance_snapshot_financial_fingerprint",
            {
                "hashlib": hashlib,
                "json": json,
                "Any": Any,
                "parse_huf_value": lambda value: float(value or 0),
                "_courier_id_key": lambda value: str(value or "").strip(),
            },
        )
        self.pwa_fingerprint = load_function(
            ROOT / "pwa_api.py",
            "finance_snapshot_financial_fingerprint",
            {"hashlib": hashlib, "json": json, "Any": Any, "money_int": lambda value: int(value or 0)},
        )

    def test_only_money_bearing_rows_change_the_fingerprint(self):
        before = [
            {"section": "finance", "item_key": "payable", "amount_value": 100000, "amount_kind": "huf", "note": "régi"},
            {"section": "finance", "item_key": "orders", "amount_value": 10, "amount_kind": "count"},
        ]
        volatile_only = [
            {"section": "finance", "item_key": "payable", "amount_value": 100000, "amount_kind": "huf", "note": "új reklamációs szöveg"},
            {"section": "finance", "item_key": "orders", "amount_value": 99, "amount_kind": "count"},
        ]
        changed_money = [
            {"section": "finance", "item_key": "payable", "amount_value": 100001, "amount_kind": "huf"},
        ]
        for fingerprint in (self.devtest_fingerprint, self.pwa_fingerprint):
            with self.subTest(fingerprint=fingerprint.__name__):
                initial = fingerprint("2026-10-01", "2875", before)
                self.assertEqual(initial, fingerprint("2026-10-01", "2875", volatile_only))
                self.assertNotEqual(initial, fingerprint("2026-10-01", "2875", changed_money))


if __name__ == "__main__":
    unittest.main()
