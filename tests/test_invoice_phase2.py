import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("resources")
package.__path__ = [str(ROOT / "resources")]
# Avoid application startup from resources/__init__.py in this isolated unit test.
sys.modules.setdefault("resources", package)
from resources.pwa_invoice_phase2 import compare_sheet, compare_workbooks, get_working, select_working, RawImportError
from resources.pwa_invoice_phase2 import COMPARISON_SLOT


class SheetClient:
    def __init__(self, sources):
        self.sources = sources; self.fields = []; self.filters = {}
    def schema(self, _): return self
    def table(self, _): self.filters = {}; return self
    def select(self, fields): self.current = fields; self.fields.append(fields); return self
    def eq(self, field, value): self.filters[field] = value; return self
    def is_(self, *args): return self
    def in_(self, field, values): self.filters[field] = values; return self
    def limit(self, _): return self
    def execute(self):
        rows = self.sources
        selected = self.filters.get('id')
        if selected: rows = [row for row in rows if row['id'] in selected] if isinstance(selected,list) else [row for row in rows if row['id']==selected]
        result = []
        for source in rows:
            entry = {'id':source['id']}
            for field in self.current.split(','):
                if ':raw_data->sheets->' in field:
                    alias, expression = field.split(':',1); index = int(expression.split('->')[2])
                    sheet = source['raw_data']['sheets'][index] if index < len(source['raw_data']['sheets']) else None
                    entry[alias] = sheet.get('name') if sheet and expression.endswith('->name') else sheet
                elif field=='sheet_count': entry[field] = len(source['raw_data']['sheets'])
                elif field in source: entry[field] = source[field]
            result.append(entry)
        return SimpleNamespace(data=result)


def row(number, *values):
    return {"id": str(uuid4()), "sourceRowNo": number, "cells": [
        {"column": i, "type": "n" if isinstance(value, (float, int)) else "s", "value": value}
        for i, value in enumerate(values, 1)]}


class ComparisonTests(unittest.TestCase):
    def test_inserted_rows_do_not_shift_all_later_rows(self):
        a = {"rows": [row(1, "ID", "Amount"), row(2, "a", 100), row(3, "b", 200)]}
        b = {"rows": [row(1, "ID", "Amount"), row(2, "new", 50), row(3, "a", 100), row(4, "b", 200)]}
        result = compare_sheet(a, b, include_details=True)
        self.assertEqual((result["identicalRows"], result["changedRows"], result["addedRows"], result["movedRows"]), (3, 0, 1, 2))
        self.assertEqual(result["changes"][0]["afterRow"], 2)

    def test_unique_composite_key_pairs_changed_values_after_insertion(self):
        a = {"rows": [row(2, "courier", "route1", 100), row(3, "courier", "route2", 200)]}
        b = {"rows": [row(2, "new", "route3", 50), row(3, "courier", "route2", 250), row(4, "courier", "route1", 100)]}
        result = compare_sheet(a, b, [1, 2], include_details=True)
        self.assertEqual((result["changedRows"], result["addedRows"]), (1, 1))
        self.assertEqual(result["changes"][0]["cells"][0]["delta"], "50")
        self.assertEqual(result["changes"][0]["match"], "key")

    def test_duplicate_key_never_silently_pairs_unrelated_rows(self):
        a = {"rows": [row(2, "same", 100), row(3, "same", 200)]}
        b = {"rows": [row(2, "same", 150), row(3, "same", 250)]}
        result = compare_sheet(a, b, [1], include_details=True)
        self.assertEqual((result["changedRows"], result["removedRows"], result["addedRows"]), (0, 2, 2))
        self.assertIn("nem egyedi", result["warning"])

    def test_duplicate_identical_rows_are_counted_not_discarded(self):
        result = compare_sheet({"rows": [row(1, "a"), row(2, "a")]}, {"rows": [row(1, "a")]})
        self.assertEqual((result["identicalRows"], result["removedRows"]), (1, 1))

    def test_no_key_value_changes_are_labelled_suggestions_and_paginated(self):
        a = {"rows": [row(i, i) for i in range(1, 120)]}
        b = {"rows": [row(i, i + 1000) for i in range(1, 120)]}
        result = compare_sheet(a, b, offset=50, limit=20, include_details=True)
        self.assertEqual((result["total"], len(result["changes"]), result["hasMore"]), (119, 20, True))
        self.assertEqual(result["changes"][0]["beforeRow"], 51)
        self.assertEqual(result["changes"][0]["match"], "suggested")

    def test_formula_and_cached_values_preserved_in_cell_diff(self):
        a = row(2, "=1+1"); b = row(2, "=1+1")
        a["cells"][0].update(type="f", cachedValue=2)
        b["cells"][0].update(type="f", cachedValue=3)
        result = compare_sheet({"rows": [a]}, {"rows": [b]}, include_details=True)
        cell = result["changes"][0]["cells"][0]
        self.assertEqual((cell["before"]["cachedValue"], cell["after"]["cachedValue"]), (2, 3))

    def test_numeric_serialization_is_not_a_change_but_boolean_is(self):
        same = compare_sheet({"rows": [row(2, 1)]}, {"rows": [row(2, 1.0)]}, include_details=True)
        self.assertEqual(same["identicalRows"], 1)
        left, right = row(2, "=TRUE"), row(2, "=TRUE")
        left["cells"][0].update(type="f", cachedValue=True)
        right["cells"][0].update(type="f", cachedValue=1)
        diff = compare_sheet({"rows": [left]}, {"rows": [right]}, include_details=True)
        self.assertEqual(len(diff["changes"][0]["cells"]), 1)

    def test_sources_must_all_belong_to_selected_month_and_not_be_deleted(self):
        client = Mock(); query = client.schema.return_value.table.return_value
        query.select.return_value.eq.return_value.is_.return_value.in_.return_value.execute.return_value.data = []
        first, second = uuid4(), uuid4()
        with self.assertRaises(RawImportError):
            compare_workbooks(client, "2026-09", [first, second], first)
        query.select.return_value.eq.assert_called_once_with("settlement_month", "2026-09-01")
        query.select.return_value.eq.return_value.is_.assert_called_once_with("deleted_at", "null")

    def test_multi_file_comparison_covers_added_and_empty_sheets_and_exact_detail_target(self):
        ids = [str(uuid4()) for _ in range(3)]
        sources = [{"id": id, "source_file_name": f"file{i}.xlsx", "raw_data": {"sheets": [
            {"name": "Adatok-JITT", "index": 1, "rows": [row(2, "ID", i * 100)]},
            {"name": "Üres-KIFLI" if i==0 else "Új-KIFLI", "index": 2, "rows": []},
        ]}} for i, id in enumerate(ids)]
        client = SheetClient(sources)
        result = compare_workbooks(client, "2026-09", ids, ids[0])
        self.assertEqual(len(result["comparisons"]), 2)
        self.assertEqual([s["status"] for s in result["comparisons"][0]["sheets"]], ["changed", "removed", "added"])
        detail = compare_workbooks(client, "2026-09", ids, ids[0], {"Adatok-JITT": [1]}, ids[2], "Adatok-JITT")
        changes = next(c["sheets"] for c in detail["comparisons"] if c["uploadId"]==ids[2])[0]["changes"]
        self.assertEqual(changes[0]["cells"][0]["delta"], "200")
        self.assertFalse(any('raw_data' in fields.split(',') for fields in client.fields))
        self.assertTrue(any('sheet:raw_data->sheets->' in fields for fields in client.fields))

    def test_one_comparison_at_a_time_and_slot_released_after_failure(self):
        COMPARISON_SLOT.acquire()
        try:
            with self.assertRaises(RawImportError) as error:
                compare_workbooks(Mock(), '2026-09', [uuid4(),uuid4()],uuid4())
            self.assertEqual(error.exception.status,429)
        finally: COMPARISON_SLOT.release()
        with self.assertRaises(RawImportError):
            compare_workbooks(Mock(), '2026-09', [uuid4(),uuid4()],uuid4())
        self.assertTrue(COMPARISON_SLOT.acquire(blocking=False))
        COMPARISON_SLOT.release()

    def test_old_working_id_rejected_instead_of_loading_current_month_copy(self):
        client = Mock(); query = client.schema.return_value.table.return_value
        query.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        with self.assertRaises(RawImportError) as error:
            get_working(client, "2026-09", uuid4())
        self.assertEqual(error.exception.status, 409)

    def test_replacement_conflict_does_not_report_success(self):
        client = Mock()
        client.schema.return_value.rpc.return_value.execute.return_value.data = {"conflict": True}
        with self.assertRaises(RawImportError) as error:
            select_working(client, "2026-09", uuid4(), uuid4(), uuid4(), "admin")
        self.assertEqual(error.exception.status, 409)

    def test_all_four_endpoints_check_admin_before_accessing_storage(self):
        names = {"admin_compare_invoice_raw", "admin_delete_invoice_raw", "admin_get_invoice_working", "admin_select_invoice_working"}
        tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(nodes), 4)
        for node in nodes: node.decorator_list = []
        class Forbidden(Exception): pass
        guard = Mock(side_effect=Forbidden)
        client = Mock()
        ns = dict(InvoiceCompareRequest=object, InvoiceWorkingRequest=object, InvoiceDeleteRequest=object,
                  Cookie=lambda **kw: None, Query=lambda **kw: None, UUID=UUID, require_user=lambda _: {},
                  require_settlement_dashboard_admin=guard, settlement_supabase_client=client)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "endpoints", "exec"), ns)
        for name in names:
            with self.assertRaises(Forbidden): ns[name]("2026-09" if name=="admin_get_invoice_working" else SimpleNamespace())
        client.assert_not_called()


if __name__ == "__main__": unittest.main()
