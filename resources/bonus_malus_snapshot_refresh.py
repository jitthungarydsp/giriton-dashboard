"""Refresh only changed bonus/malus components of an existing monthly snapshot.

Route prices, corrections, cash, reserve balances and source parameters are not
reimported. The existing TIG calculator remains the sole VAT/TIG calculator.
Publication is performed by the transactional, version-checked database RPC.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
import re

from resources.settlement_pdf import build_tig_breakdown


def money(value):
    number = Decimal(str(value or 0))
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("A bónusz/malusz összege egész forint legyen.")
    return int(number)


def monthly_rows(rows, courier_id, period):
    start = date.fromisoformat(str(period)[:10]).replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    selected = {}
    for row in sorted(rows, key=lambda r: str(r.get("created_at") or "")):
        if row.get("adjustment_type") not in {"bonus", "malus"}:
            continue
        if row.get("is_active") is False or row.get("deleted_at"):
            continue
        if str(row.get("courier_id", courier_id)) != str(courier_id):
            continue
        first = str(row.get("valid_from") or row.get("effective_date") or "")[:10]
        last = str(row.get("valid_to") or "9999-12-31")[:10]
        if not first or first >= end.isoformat() or last < start.isoformat():
            continue
        note = str(row.get("note") or "")
        transaction = re.search(r"Tranzakci[oó]\s*:\s*([^|;\n]+)", note, re.I)
        key = (row["adjustment_type"], transaction.group(1).strip().lower()) if transaction else (
            row["adjustment_type"], money(row.get("amount_huf")), " ".join(note.lower().split()))
        if money(row.get("amount_huf")) < 0:
            raise ValueError("A forrástétel összege nem lehet negatív.")
        selected[key] = deepcopy(row)
    return sorted(selected.values(), key=lambda r: (str(r.get("id") or ""), str(r.get("note") or "")))


def prepare_bonus_malus_refresh(snapshot, adjustments):
    """Pure preparation, based on the saved source baseline, never double adds."""
    cid, period = str(snapshot["courier_id"]), str(snapshot["period_start"])[:10]
    sources = {s["source_key"]: deepcopy(s) for s in snapshot.get("sources", [])}
    old_source = sources.get("manual_adjustments", {}).get("payload")
    if not isinstance(old_source, list):
        raise ValueError("A korábbi kézi tételek forrása hiányzik; teljes futárfrissítés szükséges.")
    old = monthly_rows(old_source, cid, period)
    new = monthly_rows(adjustments, cid, period)
    fields = ("id", "adjustment_type", "amount_huf", "note", "valid_from", "valid_to", "effective_date")
    stable = lambda rows: [{k: r.get(k) for k in fields} for r in rows]
    if stable(old) == stable(new):
        return None
    totals = lambda rows, kind: sum(money(r.get("amount_huf")) for r in rows if r["adjustment_type"] == kind)
    bonus_delta = totals(new, "bonus") - totals(old, "bonus")
    malus_delta = totals(new, "malus") - totals(old, "malus")
    delta = bonus_delta - malus_delta
    items = [{k: deepcopy(v) for k, v in i.items() if k not in {"id", "snapshot_id", "created_at"}}
             for i in snapshot["items"] if i.get("section") != "tig"
             and not str(i.get("item_key") or "").startswith(("jitt_bonus_", "jitt_malus_"))]
    finance = {i["item_key"]: i for i in items if i["section"] == "finance"}
    required = {"manual_bonus", "manual_malus", "bonus_malus", "income", "deductions", "payable"}
    if not required <= finance.keys():
        raise ValueError("Hiányos pénzügyi mentés; teljes futárfrissítés szükséges.")
    deltas = {"manual_bonus": bonus_delta, "manual_malus": -malus_delta,
              "bonus_malus": delta, "income": bonus_delta, "deductions": -malus_delta, "payable": delta}
    for key, amount in deltas.items():
        finance[key]["amount_value"] = money(finance[key]["amount_value"]) + amount
    meta = deepcopy(snapshot["metadata"])
    for key, amount in (("income_total", bonus_delta), ("deduction_total", -malus_delta), ("payable_total", delta)):
        meta[key] = money(meta[key]) + amount
    if meta["payable_total"] != meta["income_total"] + meta["deduction_total"] + money(meta["correction_total"]):
        raise ValueError("A mentett összesítések nem egyeznek; automatikus frissítés leállítva.")
    if meta["payable_total"] != finance["payable"]["amount_value"]:
        raise ValueError("A mentett kifizetendő és a főösszeg eltér.")
    rows = []
    for n, row in enumerate(new, 1):
        positive = row["adjustment_type"] == "bonus"
        amount = money(row["amount_huf"]) * (1 if positive else -1)
        rows.append({"Tétel": "JITT bónusz" if positive else "JITT malus", "Összeg": amount,
                     "Megjegyzés": row.get("note") or "", "Érvényesség": f"{row.get('valid_from')} - {row.get('valid_to') or ''}"})
        items.append({"section": "finance", "item_key": f"jitt_{'bonus' if positive else 'malus'}_{n}",
                      "item_label": rows[-1]["Tétel"], "amount_value": amount, "amount_kind": "huf",
                      "note": row.get("note") or "", "display_order": 500 + n})
    sources["manual_adjustments"]["payload"] = [r for r in old_source if r.get("adjustment_type") not in {"bonus", "malus"}] + new
    drill = sources.get("card_drilldowns", {}).get("payload")
    if isinstance(drill, dict):
        drill["JITT bónusz / malus"] = rows
        for group in drill.values():
            if isinstance(group, list):
                for row in group:
                    if isinstance(row, dict) and row.get("item_key") in deltas and "amount_value" in row:
                        row["amount_value"] = money(row["amount_value"]) + deltas[row["item_key"]]
    working = sources.get("working_row", {}).get("payload")
    if isinstance(working, dict):
        working["JITT bónusz"] = finance["manual_bonus"]["amount_value"]
        working["JITT malus"] = abs(finance["manual_malus"]["amount_value"])
        working["Kifizetendő"] = meta["payable_total"]
        working["Kifizetendő kifizetésre"] = meta["payable_total"]
    reserve = sources.get("target_reserve_month", {}).get("payload")
    if isinstance(reserve, dict):
        for key in ("payable_before_insurance_huf", "payable_after_insurance_huf"):
            if key in reserve:
                reserve[key] = money(reserve[key]) + delta
    profile = sources.get("courier_profile", {}).get("payload")
    old_tig = sources.get("tig_breakdown", {}).get("payload")
    if not isinstance(profile, dict) or not isinstance(old_tig, dict):
        raise ValueError("A mentett profil vagy TIG-bontás hiányzik.")
    tig = build_tig_breakdown({**profile, "id": cid, "name": snapshot.get("courier_name"),
                               "document_month": date.fromisoformat(period)},
                              {"payable": meta["payable_total"], "tip": money(finance.get("tip", {}).get("amount_value")),
                               "cash": money(old_tig.get("cashGrossHuf"))})
    # Financial edits do not silently change document dates or regenerate PDFs.
    tig["documentMeta"] = deepcopy(old_tig.get("documentMeta") or tig["documentMeta"])
    meta["tig_final_total"] = money(tig["finalTotalHuf"])
    sources["tig_breakdown"]["payload"] = tig
    for n, row in enumerate(tig["rows"]):
        items.append({"section": "tig", "item_key": "tig_" + row["key"], "item_label": row["label"],
                      "amount_value": row["grossHuf"], "amount_kind": "huf", "note": row.get("note") or "", "display_order": n})
    items.append({"section": "tig", "item_key": "tig_final_total", "item_label": "TIG végösszeg",
                  "amount_value": meta["tig_final_total"], "amount_kind": "huf", "note": "", "display_order": 99})
    meta["source"] = "bonus_malus_refresh"
    meta["bonus_malus_base_snapshot_id"] = str(snapshot["id"])
    meta["bonus_malus_delta"] = delta
    sources["bonus_malus_refresh"] = {"source_key": "bonus_malus_refresh", "source_table": "settlement.courier_settlement_adjustment",
        "payload": {"base_snapshot_id": str(snapshot["id"]), "before": stable(old), "after": stable(new),
                    "bonus_delta": bonus_delta, "malus_delta": malus_delta}, "row_count": len(new)}
    # Keep PWA editor baselines consistent when an external adjustment changes.
    worksheet = sources.get("pwa_worksheet_audit", {}).get("payload")
    if isinstance(worksheet, dict):
        for row in worksheet.get("rows", []):
            if row.get("key") in {"manual_bonus", "manual_malus"}:
                row["amountHuf"] = money(row["amountHuf"]) + deltas[row["key"]]
    clean_sources = []
    for source in sources.values():
        clean = {k: v for k, v in source.items() if k in {"source_key", "source_table", "payload", "row_count"}}
        if isinstance(clean.get("payload"), list):
            clean["row_count"] = len(clean["payload"])
        clean_sources.append(clean)
    prepared = {"items": items, "sources": clean_sources, "metadata": meta}
    fingerprint = hashlib.sha256(json.dumps(prepared, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {"prepared": prepared, "fingerprint": fingerprint}
