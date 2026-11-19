"""Reconcile imported Google adjustment rows with the published settlement."""

from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any, Iterable

import requests

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


SNAPSHOT_SCHEMA = "settlement"
MANUAL_SOURCE_KEY = "manual_adjustments"
GOOGLE_PREFIX = "google_bonus_malus:"
REVIEW_REASONS = {
    "no_snapshot": "Nincs alapelszámolás",
    "no_adjustments_source": "A mentés tételforrása hiányzik",
    "inconsistent_base": "Az alapelszámolás összetevői nem egyeznek",
    "invoiced": "A számlázott elszámolást a pénzügynek kell egyeztetnie",
    "issued_tig": "A már kiállított Teljesítés-összesítő egyeztetésre vár",
    "closed": "Lezárt vagy kifizetett elszámolás",
    "closed_source_change": "Új Google Sheet-eltérés egy lezárt hónapban",
    "closed_reserve": "A havi céltartalék már lezárt",
    "reserve_recalculation": "A céltartalék miatt teljes Pénzügy-újraszámítás szükséges",
}


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


def _write(table, payload, *, method="POST", params=None, prefer="return=minimal"):
    response = requests.request(method, _url(table), headers=_headers(prefer),
                                params=params, json=payload, timeout=60)
    raise_for_supabase_error(response)
    return response.json() if response.content else None


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
    return next((index for index, item in enumerate(items)
                 if item.get("section") == "finance" and item.get("item_key") == item_key), None)


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
        if item.get("section") != "finance" or (
            item.get("item_key") not in {"bonus_malus", "manual_bonus", "manual_malus"}
            and not str(item.get("item_key") or "").startswith(("jitt_bonus_", "jitt_malus_"))
        )
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
    financial_items = [
        {
            "section": str(item.get("section") or ""),
            "item_key": str(item.get("item_key") or ""),
            "amount_huf": _number(item.get("amount_value")),
        }
        for item in items
        if str(item.get("amount_kind") or "huf").strip().casefold() == "huf"
    ]
    payload = {
        "format": "financial-items-v2",
        "period_start": snapshot["period_start"],
        "courier_id": str(snapshot["courier_id"]),
        "items": sorted(financial_items, key=lambda item: (item["section"], item["item_key"])),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _google_row_signature(row):
    return (
        str(row.get("id") or ""), str(row.get("adjustment_type") or ""),
        _number(row.get("amount_huf")), str(row.get("valid_from") or ""),
        str(row.get("valid_to") or ""), str(row.get("note") or ""),
    )


def _review(courier_id, month, reason, old=None, proposed=None, delta=None):
    _write("google_adjustment_review", {
        "courier_id": courier_id, "period_start": month.isoformat(), "reason": reason,
        "previous_payable_huf": old, "proposed_payable_huf": proposed, "google_delta_huf": delta,
    }, params={"on_conflict": "courier_id,period_start"}, prefer="resolution=merge-duplicates,return=minimal")
    return "review", REVIEW_REASONS[reason]


def _clear_review(courier_id, month):
    _write("google_adjustment_review", None, method="DELETE",
           params={"courier_id": f"eq.{courier_id}", "period_start": f"eq.{month.isoformat()}"})


def check_reconciliation_schema():
    _rows("google_adjustment_review", {"select": "courier_id", "limit": "1"})


def report_closed_sheet_change(courier_id, month):
    _review(courier_id, month, "closed_source_change")


def _rebuild_tig(items, sources, old_payable, payable):
    from resources.settlement_pdf import build_tig_breakdown

    source = next((row for row in sources if row["source_key"] == "tig_breakdown"), None)
    if not source or not isinstance(source["payload"], dict):
        raise ValueError("Hiányzik a mentett Teljesítés-összesítő bontás.")
    old = source["payload"]
    document = old.get("documentMeta") or {}
    tax_mode = old.get("taxMode")
    if tax_mode not in {"aam", "vat"} or not {"originalTipHuf", "cashGrossHuf"} <= old.keys():
        raise ValueError("A mentett Teljesítés-összesítő adózási adatai hiányosak.")
    profile = {"tig_type": tax_mode, "document_month": document.get("periodStart")}
    inputs = {"tip": old["originalTipHuf"], "cash": old["cashGrossHuf"]}
    baseline = build_tig_breakdown(profile, {**inputs, "payable": old_payable})
    if any(baseline[key] != old.get(key) for key in ("finalTotalHuf", "transferServiceHuf", "tipHuf", "cashGrossHuf")):
        raise ValueError("A korábbi Teljesítés-összesítő eltér a számítási alaptól.")
    tig = build_tig_breakdown(profile, {**inputs, "payable": payable})
    old_rows = {row["key"]: row for row in old.get("rows", [])}
    tig["rows"] = [
        {**old_rows.get(row["key"], row), **{key: row[key] for key in ("netHuf", "vatHuf", "grossHuf")}}
        for row in tig["rows"]
    ]
    for key in ("documentMeta", "cashDocumentMeta"):
        if key in old:
            tig[key] = old[key]
    source.update(payload={**old, **tig}, row_count=len(tig["rows"]))
    old_items = {item["item_key"]: item for item in items if item["section"] == "tig"}
    items[:] = [item for item in items if item["section"] != "tig"]
    rows = [("tig_" + row["key"], row["label"], row["grossHuf"], row.get("note", "")) for row in tig["rows"]]
    rows.append(("tig_final_total", "Teljesítés-összesítő végösszeg", tig["finalTotalHuf"], ""))
    for index, (key, label, amount, note) in enumerate(rows, 1):
        items.append({"section": "tig", "item_key": key, "item_label": label, "amount_kind": "huf",
                      "note": note, "display_order": index, **old_items.get(key, {}), "amount_value": amount})
    return tig["finalTotalHuf"]


def _refresh_sources(sources, items, metadata):
    amounts = {item["item_key"]: item for item in items if item["section"] == "finance"}
    source_map = {row["source_key"]: row["payload"] for row in sources}
    working = source_map.get("working_row")
    if isinstance(working, dict):
        working.update({
            "JITT bónusz": amounts["manual_bonus"]["amount_value"],
            "JITT malus": -amounts["manual_malus"]["amount_value"],
            "Korrekció": metadata["correction_total"], "Kifizetendő": metadata["payable_total"],
        })
        # This older key can carry a different balance; move it by the same delta.
        if isinstance(working.get("Kifizetendő kifizetésre"), (int, float)):
            working["Kifizetendő kifizetésre"] += metadata["google_delta_huf"] - metadata["google_reserve_delta_huf"]
    drilldowns = source_map.get("card_drilldowns")
    if isinstance(drilldowns, dict):
        from resources.finance_adjustment_details import snapshot_manual_adjustment_details

        snapshot = {"sources": sources, "items": items}
        drilldowns["JITT bónusz / malus"] = snapshot_manual_adjustment_details(snapshot, "JITT bónusz / malus")
        if metadata["google_correction_delta"]:
            drilldowns["Korrekció"] = snapshot_manual_adjustment_details(snapshot, "Korrekció")
        if isinstance(drilldowns.get("Mobilon látható értékek"), list):
            drilldowns["Mobilon látható értékek"] = items
        next(row for row in sources if row["source_key"] == "card_drilldowns")["row_count"] = sum(
            len(rows) for rows in drilldowns.values() if isinstance(rows, list)
        )


def _reserve_delta(sources, items, month, net_delta):
    """Check the saved reserve formula before rebasing a payable amount."""
    if not net_delta:
        return 0
    source = next((row["payload"] for row in sources if row["source_key"] == "target_reserve_month"), {})
    if not isinstance(source, dict):
        return None
    values = {row["item_key"]: _number(row["amount_value"]) for row in items if row["section"] == "finance"}
    if not source.get("insurance_active_before") and not values.get("insurance_fee") and not values.get("reserve"):
        return 0
    if not source.get("insurance_fee_huf") and not values.get("insurance_fee") and not values.get("reserve"):
        # Insurance was inactive for the month, including backdated cancellations.
        return 0
    if not {"payable_before_insurance_huf", "reserve_before_huf", "reserve_addition_huf"} <= source.keys():
        return None
    rules = _rows("cfg_jitt_reserve_insurance_rules", {
        "is_active": "eq.true", "deleted_at": "is.null", "valid_from": f"lte.{month.isoformat()}",
        "or": f"(valid_to.is.null,valid_to.gte.{month.isoformat()})", "order": "priority.asc,valid_from.desc,id.asc",
        "limit": "1",
    })
    rule = rules[0] if rules else {}
    cap = _number(rule.get("reserve_target_huf", 50000))
    target = _number(rule.get("base_insurance_total_huf", 350000))
    rate = float(rule["deduction_percent"]) / 100 if rule else 0.1
    opening = _number(source["reserve_before_huf"])
    limit = min(max(cap, 0), max(target - opening, 0))
    baseline = float(source["payable_before_insurance_huf"])
    old_topup = min(round(max(baseline, 0) * rate), limit)
    new_topup = min(round(max(baseline + net_delta, 0) * rate), limit)
    return new_topup - old_topup


def refresh_finance_snapshot(courier_id: str, period_start: date) -> tuple[str, str]:
    """Publish one consistent version, or keep the discrepancy visible for review."""
    month = period_start.replace(day=1)
    day = month.isoformat()
    end = _month_end(month)
    adjustments = _rows("courier_settlement_adjustment", {
        "select": "id,courier_id,adjustment_type,amount_huf,effective_date,valid_from,valid_to,note,source_key,created_by,is_active,deleted_at",
        "courier_id": f"eq.{courier_id}", "source_key": f"like.{GOOGLE_PREFIX}*",
        "valid_from": f"lte.{end.isoformat()}", "valid_to": f"gte.{day}", "order": "effective_date.asc,id.asc",
    })
    google_ids = {str(row["id"]) for row in adjustments}
    current = [{k: v for k, v in row.items() if k not in {"is_active", "deleted_at"}}
               for row in adjustments if row.get("is_active") and not row.get("deleted_at")]
    def is_google(row):
        return str(row.get("id") or "") in google_ids or str(row.get("source_key") or "").startswith(GOOGLE_PREFIX)

    latest = _rows("courier_finance_snapshot", {
        "select": "*", "courier_id": f"eq.{courier_id}", "period_start": f"eq.{day}",
        "version": "gt.0", "order": "version.desc", "limit": "1",
    })
    if not latest:
        if current:
            return _review(courier_id, month, "no_snapshot")
        return "unchanged", ""
    previous = dict(latest[0])
    previous_id = previous["id"]
    sources = _rows("courier_finance_snapshot_source", {
        "select": "source_key,source_table,payload,row_count", "snapshot_id": f"eq.{previous_id}",
        "order": "source_key.asc", "limit": "200",
    })
    manual_source = next((source for source in sources if source.get("source_key") == MANUAL_SOURCE_KEY), None)
    old_adjustments = (manual_source or {}).get("payload")
    if not isinstance(old_adjustments, list):
        return _review(courier_id, month, "no_adjustments_source")
    old_google = [row for row in old_adjustments if is_google(row)]
    if sorted(map(_google_row_signature, old_google)) == sorted(map(_google_row_signature, current)):
        return "unchanged", ""
    adjustments = [row for row in old_adjustments if not is_google(row)] + current
    old_totals = _adjustment_totals(old_google)
    new_totals = _adjustment_totals(current)
    delta_bonus = new_totals["bonus"] - old_totals["bonus"]
    delta_malus = new_totals["malus"] - old_totals["malus"]
    delta_income = new_totals["correction_income"] - old_totals["correction_income"]
    delta_deduction = new_totals["correction_deduction"] - old_totals["correction_deduction"]
    net_delta = delta_bonus - delta_malus + delta_income - delta_deduction
    items = _rows("courier_finance_snapshot_item", {
        "select": "section,item_key,item_label,amount_value,amount_kind,note,display_order",
        "snapshot_id": f"eq.{previous_id}", "order": "section.asc,display_order.asc", "limit": "700",
    })
    amounts = {item["item_key"]: _number(item["amount_value"]) for item in items if item["section"] == "finance"}
    old_payable = amounts.get("payable")
    old_manual = _adjustment_totals(old_adjustments)
    if (old_payable is None or not {"income", "deductions", "correction"} <= amounts.keys()
        or amounts.get("manual_bonus", 0) != old_manual["bonus"]
        or amounts.get("manual_malus", 0) != -old_manual["malus"]
        or amounts["income"] + amounts["deductions"] + amounts["correction"] != old_payable):
        return _review(courier_id, month, "inconsistent_base", old_payable, None, net_delta)
    proposed = old_payable + net_delta
    reserve_delta = _reserve_delta(sources, items, month, net_delta)
    if reserve_delta is None:
        return _review(courier_id, month, "inconsistent_base", old_payable, None, net_delta)
    proposed -= reserve_delta
    rebuilt_items = _rebuild_manual_items(items, adjustments)
    for key, change, label in (
        ("income", delta_bonus, "Jóváírások összesen"),
        ("deductions", -delta_malus - reserve_delta, "Levonások összesen"),
        ("payable", net_delta - reserve_delta, "Kifizetendő"),
        ("correction", delta_income - delta_deduction, "Korrekció"),
        ("correction_income", delta_income, "Korrekció +"),
        ("correction_deduction", -delta_deduction, "Korrekció -"),
    ):
        _set_item_amount(rebuilt_items, key, amounts.get(key, 0) + change, label)
    if reserve_delta:
        if not {"reserve", "target_reserve_close"} <= amounts.keys():
            return _review(courier_id, month, "reserve_recalculation", old_payable, proposed, net_delta)
        _set_item_amount(rebuilt_items, "reserve", amounts["reserve"] - reserve_delta, "Céltartalék")
        _set_item_amount(rebuilt_items, "target_reserve_close", amounts["target_reserve_close"] + reserve_delta,
                         "Záró céltartalék")
    metadata = dict(previous.get("metadata") or {})
    metadata["income_total"] = amounts["income"] + delta_bonus
    metadata["deduction_total"] = amounts["deductions"] - delta_malus - reserve_delta
    metadata["payable_total"] = proposed
    metadata["correction_total"] = amounts["correction"] + delta_income - delta_deduction
    metadata["source"] = "google_bonus_malus_snapshot_refresh"
    metadata["google_delta_huf"] = net_delta
    metadata["google_reserve_delta_huf"] = reserve_delta
    metadata["google_correction_delta"] = bool(delta_income or delta_deduction)
    metadata["google_adjustment_refreshed_at"] = datetime.now(timezone.utc).isoformat()
    manual_source.update(payload=adjustments, row_count=len(adjustments))
    reserve_source = next((row["payload"] for row in sources if row["source_key"] == "target_reserve_month"), None)
    if isinstance(reserve_source, dict):
        for key, change in (("payable_before_insurance_huf", net_delta),
                            ("payable_after_insurance_huf", net_delta - reserve_delta),
                            ("reserve_addition_huf", reserve_delta), ("reserve_after_huf", reserve_delta)):
            if isinstance(reserve_source.get(key), (int, float)):
                reserve_source[key] += change
    try:
        if net_delta:
            metadata["tig_final_total"] = _rebuild_tig(rebuilt_items, sources, old_payable, proposed)
    except ValueError:
        return _review(courier_id, month, "inconsistent_base", old_payable, None, net_delta)
    _refresh_sources(sources, rebuilt_items, metadata)
    result = _write("rpc/publish_google_adjustment_snapshot", {
        "p_courier_id": courier_id, "p_period_start": day, "p_base_id": previous_id,
        "p_fingerprint": _snapshot_fingerprint(previous, rebuilt_items, sources),
        "p_metadata": metadata, "p_items": rebuilt_items, "p_sources": sources,
    }, prefer="return=representation")
    if result in REVIEW_REASONS:
        return _review(courier_id, month, result, old_payable, proposed, net_delta)
    if result != "saved":
        raise RuntimeError("A pénzügyi mentés időközben megváltozott; a következő futás újrapróbálja.")
    return "saved", ""


def refresh_finance_snapshots(changed_periods: Iterable[tuple[str, date]]) -> dict[str, Any]:
    result: dict[str, Any] = {"saved": 0, "unchanged": 0, "review": 0, "failed": 0, "errors": [], "reviews": []}
    periods = sorted(set(changed_periods), key=lambda item: (item[1], item[0]))
    if not periods:
        return result
    pending = {(str(row["courier_id"]), row["period_start"]) for row in _rows("google_adjustment_review", {
        "select": "courier_id,period_start", "order": "period_start.asc,courier_id.asc", "limit": "1000",
    })}

    def refresh(period):
        courier_id, period_start = period
        try:
            outcome, message = refresh_finance_snapshot(str(courier_id), period_start)
            if outcome == "unchanged" and (str(courier_id), period_start.isoformat()) in pending:
                _clear_review(str(courier_id), period_start)
            return outcome, f"{courier_id} {period_start}: {message}"
        except Exception as exc:
            return "failed", f"{courier_id} {period_start}: {type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=6) as executor:
        for outcome, message in executor.map(refresh, periods):
            result[outcome] += 1
            if outcome == "review":
                result["reviews"].append(message)
            elif outcome == "failed":
                result["errors"].append(message)
    return result
