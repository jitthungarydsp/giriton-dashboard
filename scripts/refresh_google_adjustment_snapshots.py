"""Create a fresh finance-snapshot version after a Google bonus/malus change.

The Google importer owns only bonus/malus adjustment rows.  Re-running the
whole Streamlit settlement page from a scheduled GitHub Action is unreliable,
so this module safely rebases just those adjustment components on the latest
immutable finance snapshot.
"""

from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Iterable

import requests

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


SNAPSHOT_SCHEMA = "settlement"
MANUAL_SOURCE_KEY = "manual_adjustments"
GOOGLE_ACTOR = "google-bonus-malus-sync"


def _headers(prefer: str = "") -> dict[str, str]:
    _url, key = get_supabase_config()
    key = str(key or "").strip()
    if not key:
        raise RuntimeError("Hiányzik a SUPABASE_SERVICE_ROLE_KEY beállítás.")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Profile": SNAPSHOT_SCHEMA,
        "Content-Profile": SNAPSHOT_SCHEMA,
    }
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _url(table: str) -> str:
    base_url, _key = get_supabase_config()
    base_url = str(base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("Hiányzik a SUPABASE_URL beállítás.")
    return f"{base_url}/rest/v1/{table}"


def _rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = requests.get(_url(table), headers=_headers(), params=params, timeout=60)
    raise_for_supabase_error(response)
    return response.json() or []


def _number(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _month_end(month: date) -> date:
    return date(month.year, month.month, monthrange(month.year, month.month)[1])


def _adjustment_totals(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    result = {"bonus": 0, "malus": 0, "correction_income": 0, "correction_deduction": 0}
    for row in rows:
        adjustment_type = str(row.get("adjustment_type") or "").strip()
        if adjustment_type in result:
            result[adjustment_type] += abs(_number(row.get("amount_huf")))
    return result


def _item_index(items: list[dict[str, Any]], item_key: str) -> int | None:
    return next((index for index, item in enumerate(items) if item.get("item_key") == item_key), None)


def _set_item_amount(items: list[dict[str, Any]], item_key: str, amount: int, label: str) -> None:
    index = _item_index(items, item_key)
    if index is not None:
        items[index]["amount_value"] = int(amount)
        return
    display_order = max((_number(item.get("display_order")) for item in items), default=0) + 1
    items.append({
        "section": "finance",
        "item_key": item_key,
        "item_label": label,
        "amount_value": int(amount),
        "amount_kind": "huf",
        "note": "Google bónusz/malus automatikus szinkron",
        "display_order": display_order,
    })


def _adjustment_note(row: dict[str, Any]) -> str:
    return str(row.get("note") or "Google Sheet tétel").strip()


def _rebuild_manual_items(items: list[dict[str, Any]], adjustments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [
        dict(item) for item in items
        if item.get("item_key") not in {"bonus_malus", "manual_bonus", "manual_malus"}
        and not str(item.get("item_key") or "").startswith(("jitt_bonus_", "jitt_malus_"))
    ]
    totals = _adjustment_totals(adjustments)
    bonus_note = " | ".join(
        f"{_number(row.get('amount_huf')):,.0f} Ft - {_adjustment_note(row)}".replace(",", " ")
        for row in adjustments if row.get("adjustment_type") == "bonus"
    )
    malus_note = " | ".join(
        f"{_number(row.get('amount_huf')):,.0f} Ft - {_adjustment_note(row)}".replace(",", " ")
        for row in adjustments if row.get("adjustment_type") == "malus"
    )
    _set_item_amount(kept, "bonus_malus", totals["bonus"] - totals["malus"], "JITT bónusz / malus")
    _set_item_amount(kept, "manual_bonus", totals["bonus"], "JITT bónusz")
    _set_item_amount(kept, "manual_malus", -totals["malus"], "JITT malus")
    for key, note in (("bonus_malus", " ; ".join(part for part in (bonus_note, malus_note) if part)),
                      ("manual_bonus", bonus_note), ("manual_malus", malus_note)):
        index = _item_index(kept, key)
        if index is not None:
            kept[index]["note"] = note or "Sheet/DB tételek"
    order = max((_number(item.get("display_order")) for item in kept), default=0)
    for index, row in enumerate((row for row in adjustments if row.get("adjustment_type") in {"bonus", "malus"}), start=1):
        adjustment_type = str(row["adjustment_type"])
        order += 1
        kept.append({
            "section": "finance",
            "item_key": f"jitt_{adjustment_type}_{index}",
            "item_label": "JITT bónusz" if adjustment_type == "bonus" else "JITT malus",
            "amount_value": _number(row.get("amount_huf")) if adjustment_type == "bonus" else -_number(row.get("amount_huf")),
            "amount_kind": "huf",
            "note": _adjustment_note(row),
            "display_order": order,
        })
    return kept


def _snapshot_fingerprint(snapshot: dict[str, Any], items: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    payload = {
        "period_start": snapshot["period_start"],
        "courier_id": str(snapshot["courier_id"]),
        "calculation_mode": snapshot.get("calculation_mode") or "",
        "warehouse_label": snapshot.get("warehouse_label") or "",
        "session_id": snapshot.get("session_id") or "",
        "metadata": snapshot.get("metadata") or {},
        "items": sorted(items, key=lambda item: (str(item.get("section")), _number(item.get("display_order")), str(item.get("item_key")))),
        "sources": sorted(sources, key=lambda source: str(source.get("source_key") or "")),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def refresh_finance_snapshot(courier_id: str, period_start: date) -> str:
    """Rebase a single existing snapshot. Returns saved/unchanged/skipped."""
    month = period_start.replace(day=1)
    latest = _rows("courier_finance_snapshot", {
        "select": "*", "courier_id": f"eq.{courier_id}", "period_start": f"eq.{month.isoformat()}",
        "order": "version.desc", "limit": "1",
    })
    if not latest:
        return "skipped"
    previous = dict(latest[0])
    previous_id = str(previous.get("id") or "")
    if not previous_id:
        return "skipped"
    items = _rows("courier_finance_snapshot_item", {
        "select": "section,item_key,item_label,amount_value,amount_kind,note,display_order",
        "snapshot_id": f"eq.{previous_id}", "order": "section.asc,display_order.asc", "limit": "700",
    })
    sources = _rows("courier_finance_snapshot_source", {
        "select": "source_key,source_table,payload,row_count", "snapshot_id": f"eq.{previous_id}",
        "order": "source_key.asc", "limit": "200",
    })
    manual_source = next((source for source in sources if source.get("source_key") == MANUAL_SOURCE_KEY), None)
    old_adjustments = (manual_source or {}).get("payload")
    if not isinstance(old_adjustments, list):
        return "skipped"
    end = _month_end(month)
    adjustments = _rows("courier_settlement_adjustment", {
        "select": "id,courier_id,adjustment_type,amount_huf,effective_date,valid_from,valid_to,note,source_key,created_by",
        "courier_id": f"eq.{courier_id}", "is_active": "eq.true", "deleted_at": "is.null",
        "valid_from": f"lte.{end.isoformat()}", "valid_to": f"gte.{month.isoformat()}", "order": "effective_date.asc,id.asc", "limit": "1000",
    })
    old_totals = _adjustment_totals(old_adjustments)
    new_totals = _adjustment_totals(adjustments)
    if old_totals == new_totals:
        return "unchanged"

    rebuilt_items = _rebuild_manual_items(items, adjustments)
    delta_bonus = new_totals["bonus"] - old_totals["bonus"]
    delta_malus = new_totals["malus"] - old_totals["malus"]
    delta_income = new_totals["correction_income"] - old_totals["correction_income"]
    delta_deduction = new_totals["correction_deduction"] - old_totals["correction_deduction"]
    net_delta = delta_bonus - delta_malus + delta_income - delta_deduction
    _set_item_amount(rebuilt_items, "income", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "income"), 0)) + delta_bonus + delta_income, "Jóváírások összesen")
    _set_item_amount(rebuilt_items, "deductions", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "deductions"), 0)) - delta_malus - delta_deduction, "Levonások összesen")
    _set_item_amount(rebuilt_items, "payable", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "payable"), 0)) + net_delta, "Kifizetendő")
    _set_item_amount(rebuilt_items, "correction", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "correction"), 0)) + delta_income - delta_deduction, "Korrekció")
    _set_item_amount(rebuilt_items, "correction_income", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "correction_income"), 0)) + delta_income, "Korrekció +")
    _set_item_amount(rebuilt_items, "correction_deduction", _number(next((item.get("amount_value") for item in items if item.get("item_key") == "correction_deduction"), 0)) - delta_deduction, "Korrekció -")

    metadata = dict(previous.get("metadata") or {})
    metadata["income_total"] = _number(metadata.get("income_total")) + delta_bonus + delta_income
    metadata["deduction_total"] = _number(metadata.get("deduction_total")) - delta_malus - delta_deduction
    metadata["payable_total"] = _number(metadata.get("payable_total")) + net_delta
    metadata["correction_total"] = _number(metadata.get("correction_total")) + delta_income - delta_deduction
    metadata["source"] = "google_bonus_malus_snapshot_refresh"
    metadata["google_adjustment_refreshed_at"] = datetime.utcnow().isoformat()
    source_rows = [dict(source) for source in sources]
    for source in source_rows:
        if source.get("source_key") == MANUAL_SOURCE_KEY:
            source["payload"] = adjustments
            source["row_count"] = len(adjustments)
    snapshot = {
        "period_start": month.isoformat(), "courier_id": str(courier_id),
        "courier_name": previous.get("courier_name") or "", "version": _number(previous.get("version")) + 1,
        "source": "devtest_finance", "calculation_mode": previous.get("calculation_mode") or "Excel",
        "warehouse_label": previous.get("warehouse_label") or "", "session_id": previous.get("session_id") or "",
        "metadata": metadata, "previous_snapshot_id": previous_id,
        "previous_fingerprint": previous.get("fingerprint") or "", "changed_from_previous": True,
        "created_by": GOOGLE_ACTOR,
    }
    snapshot["fingerprint"] = _snapshot_fingerprint(snapshot, rebuilt_items, source_rows)
    inserted = requests.post(_url("courier_finance_snapshot"), headers=_headers("return=representation"), json=snapshot, timeout=60)
    raise_for_supabase_error(inserted)
    created = (inserted.json() or [{}])[0]
    snapshot_id = str(created.get("id") or "")
    if not snapshot_id:
        raise RuntimeError("A pénzügyi snapshot mentése nem adott azonosítót.")
    item_payloads = [{"snapshot_id": snapshot_id, **item} for item in rebuilt_items]
    source_payloads = [{"snapshot_id": snapshot_id, **source} for source in source_rows]
    for table, payloads in (("courier_finance_snapshot_item", item_payloads), ("courier_finance_snapshot_source", source_payloads)):
        if not payloads:
            continue
        response = requests.post(_url(table), headers=_headers("return=minimal"), json=payloads, timeout=60)
        raise_for_supabase_error(response)
    return "saved"


def refresh_finance_snapshots(changed_periods: Iterable[tuple[str, date]]) -> dict[str, Any]:
    result: dict[str, Any] = {"saved": 0, "unchanged": 0, "skipped": 0, "failed": 0, "errors": []}
    for courier_id, period_start in sorted(set(changed_periods), key=lambda item: (item[1], item[0])):
        try:
            outcome = refresh_finance_snapshot(str(courier_id), period_start)
            result[outcome] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{courier_id} {period_start}: {type(exc).__name__}: {exc}")
    return result
