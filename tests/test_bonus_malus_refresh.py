from copy import deepcopy
from datetime import date
import unittest
from unittest.mock import patch

from resources.bonus_malus_snapshot_refresh import prepare_bonus_malus_refresh, monthly_rows
from scripts import import_google_bonus_malus_adjustments as importer
from scripts import refresh_bonus_malus_snapshots as worker


def adjustment(amount=12371, kind="bonus", row_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", **kwargs):
    return {"id": row_id, "courier_id": "7440", "adjustment_type": kind, "amount_huf": amount,
            "note": "Extra kör | Tranzakcio: TEST-1", "effective_date": "2026-09-30",
            "valid_from": "2026-09-30", "valid_to": "2026-09-30", "is_active": True,
            "created_at": "2026-10-20T00:47:19Z", **kwargs}


def snapshot():
    amounts = {"base": 221850, "tip": 139675, "delay_bonus": 124333, "compliance_bonus": 124333,
               "customer_rating": 12600, "monthly_bonus": 19950, "manual_bonus": 0, "manual_malus": 0,
               "bonus_malus": 0, "income": 642741, "deductions": 0, "correction": 20450,
               "correction_income": 20450, "payable": 663191, "reserve": 0}
    return {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "courier_id": "7440", "courier_name": "Jamal Wasil",
            "period_start": "2026-09-01", "version": 16,
            "metadata": {"payable_total": 663191, "income_total": 642741, "deduction_total": 0,
                         "correction_total": 20450, "tig_final_total": 663191},
            "items": [{"section": "finance", "item_key": k, "item_label": k, "amount_value": v,
                       "amount_kind": "huf", "display_order": n} for n, (k, v) in enumerate(amounts.items())],
            "sources": [{"source_key": k, "source_table": "test", "payload": v, "row_count": 1} for k, v in {
                "manual_adjustments": [], "courier_profile": {"tig_type": "AAM"},
                "tig_breakdown": {"cashGrossHuf": 0, "documentMeta": {"performanceDate": "2026-10-27"}},
                "card_drilldowns": {}, "working_row": {}, "route_detail": [{"Route ID": "unchanged"}],
                "target_reserve_month": {"reserve_after_huf": 123000, "payable_after_insurance_huf": 663191},
            }.items()]}


def reopened(original, result):
    return {**original, **result["prepared"], "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "version": 17}


class CalculationTests(unittest.TestCase):
    def test_jamal_reproduction_and_idempotency(self):
        saved = snapshot(); before = deepcopy(saved)
        result = prepare_bonus_malus_refresh(saved, [adjustment()])
        self.assertEqual(result["prepared"]["metadata"]["payable_total"], 675562)
        self.assertEqual(result["prepared"]["metadata"]["tig_final_total"], 675562)
        self.assertEqual(saved, before)
        self.assertIsNone(prepare_bonus_malus_refresh(reopened(saved, result), [adjustment(updated_at="later")]))
        old_items = {r["item_key"]: r["amount_value"] for r in saved["items"]}
        new_items = {r["item_key"]: r["amount_value"] for r in result["prepared"]["items"] if r["section"] == "finance"}
        for key in ["base", "tip", "delay_bonus", "compliance_bonus", "customer_rating", "correction", "reserve"]:
            self.assertEqual(old_items[key], new_items[key])

    def test_update_delete_malus_and_note_only(self):
        first = prepare_bonus_malus_refresh(snapshot(), [adjustment()])
        saved = reopened(snapshot(), first)
        changed = prepare_bonus_malus_refresh(saved, [adjustment(15000)])
        self.assertEqual(changed["prepared"]["metadata"]["payable_total"], 678191)
        deleted = prepare_bonus_malus_refresh(saved, [])
        self.assertEqual(deleted["prepared"]["metadata"]["payable_total"], 663191)
        malus = prepare_bonus_malus_refresh(snapshot(), [adjustment(10000, "malus")])
        self.assertEqual(malus["prepared"]["metadata"]["payable_total"], 653191)
        self.assertEqual(malus["prepared"]["metadata"]["deduction_total"], -10000)
        note = prepare_bonus_malus_refresh(saved, [adjustment(note="Új megjegyzés")])
        self.assertEqual(note["prepared"]["metadata"]["payable_total"], 675562)

    def test_period_courier_active_and_dedup_scope(self):
        rows = [adjustment(), adjustment(100, courier_id="another"), adjustment(100, valid_from="2026-10-01"),
                adjustment(100, is_active=False), adjustment(100, deleted_at="2026-10-20")]
        self.assertEqual(len(monthly_rows(rows, "7440", "2026-09-01")), 1)
        newest = adjustment(15000, created_at="2026-10-21", id="new-id")
        self.assertEqual(monthly_rows([adjustment(), newest], "7440", "2026-09-01")[0]["amount_huf"], 15000)

    def test_preserves_pwa_manual_amounts_and_all_other_sources(self):
        saved = snapshot()
        for item in saved["items"]:
            if item["item_key"] in {"manual_bonus", "bonus_malus", "income", "payable"}:
                item["amount_value"] += 1000
        for key in ["income_total", "payable_total", "tig_final_total"]:
            saved["metadata"][key] += 1000
        result = prepare_bonus_malus_refresh(saved, [adjustment()])
        values = {i["item_key"]: i["amount_value"] for i in result["prepared"]["items"]}
        self.assertEqual(values["manual_bonus"], 13371)
        sources = {s["source_key"]: s["payload"] for s in result["prepared"]["sources"]}
        self.assertEqual(sources["route_detail"], [{"Route ID": "unchanged"}])
        self.assertEqual(sources["target_reserve_month"]["reserve_after_huf"], 123000)
        self.assertEqual(sources["tig_breakdown"]["documentMeta"], {"performanceDate": "2026-10-27"})

    def test_vat_uses_shared_tig_calculator(self):
        saved = snapshot()
        next(s for s in saved["sources"] if s["source_key"] == "courier_profile")["payload"] = {"tig_type": "VAT"}
        result = prepare_bonus_malus_refresh(saved, [adjustment()])
        tig = next(s for s in result["prepared"]["sources"] if s["source_key"] == "tig_breakdown")["payload"]
        self.assertEqual(tig["taxMode"], "vat")
        self.assertGreater(tig["finalTotalHuf"], result["prepared"]["metadata"]["payable_total"])


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.row = {"row_number": 2, "transaction_id": "TEST-1", "courier_name": "Jamal Wasil",
                    "effective_date": date(2026, 9, 30), "adjustment_type": "bonus", "amount_huf": 12371,
                    "note": "Extra kör", "raw_type": "BONUSZ"}
        self.key = importer.source_key("sheet", 1, self.row)
        self.payload = importer.adjustment_payload(self.row, {"courier_id": "7440"}, self.key)
        self.current = {**self.payload, "id": "old", "updated_at": "old-time"}

    def reconcile(self, prepared, existing, **kwargs):
        return importer.reconcile_sheet_payloads(prepared, existing, kwargs.pop("closed", set()),
            sheet_id="sheet", gid=1, eligible_ids={"7440"}, apply=True, **kwargs)

    def test_identical_import_does_not_write(self):
        with patch.object(importer, "insert_adjustment") as insert, patch.object(importer, "update_adjustment") as update, patch.object(importer, "deactivate_adjustment") as delete:
            stats = self.reconcile([(self.key, self.payload)], {self.key: self.current})
            self.assertEqual(stats["updated"], 0); insert.assert_not_called(); update.assert_not_called(); delete.assert_not_called()

    def test_changed_amount_replaces_old_record_and_only_target(self):
        new_row = {**self.row, "amount_huf": 15000}
        key = importer.source_key("sheet", 1, new_row)
        payload = importer.adjustment_payload(new_row, {"courier_id": "7440"}, key)
        with patch.object(importer, "insert_adjustment") as insert, patch.object(importer, "deactivate_adjustment") as delete:
            stats = self.reconcile([(key, payload)], {self.key: self.current, "google_bonus_malus:sheet:1:other": {**self.current, "id": "other", "courier_id": "another"}})
            self.assertEqual((stats["inserted"], stats["deactivated"]), (1, 1)); delete.assert_called_once_with("old"); insert.assert_called_once_with(payload)

    def test_removed_row_closed_month_and_admin_deleted_protection(self):
        with patch.object(importer, "deactivate_adjustment") as delete:
            self.reconcile([], {self.key: self.current}); delete.assert_called_once_with("old")
        with patch.object(importer, "deactivate_adjustment") as delete, patch.object(importer, "insert_adjustment") as insert, patch.object(importer, "update_adjustment") as update:
            self.reconcile([], {self.key: self.current}, closed={("7440", "2026-09-01")})
            self.reconcile([(self.key, self.payload)], {self.key: {**self.current, "deleted_at": "yesterday"}})
            delete.assert_not_called(); insert.assert_not_called(); update.assert_not_called()

    def test_dry_run_has_no_writes(self):
        with patch.object(importer, "insert_adjustment") as insert, patch.object(importer, "deactivate_adjustment") as delete:
            importer.reconcile_sheet_payloads([(self.key, self.payload)], {}, set(), sheet_id="sheet", gid=1, eligible_ids={"7440"}, apply=False)
            insert.assert_not_called(); delete.assert_not_called()


class WorkerTests(unittest.TestCase):
    def test_failed_publish_remains_retryable_and_revision_scoped(self):
        job = {"courier_id": "7440", "period_start": "2026-09-01", "revision": 2}
        with patch.object(worker, "rest", side_effect=[[job], []]) as rest, patch.object(worker, "refresh_one", side_effect=RuntimeError("network failed")):
            with self.assertRaisesRegex(RuntimeError, "7440"):
                worker.refresh_pending()
            self.assertEqual(rest.call_args.kwargs["params"]["revision"], "eq.2")
            self.assertEqual(rest.call_args.kwargs["payload"]["state"], "error")


if __name__ == "__main__":
    unittest.main()
