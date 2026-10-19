"""Snapshot-based worksheet pilot. No database access or source refreshes."""
from copy import deepcopy
from datetime import date
import hashlib
import json

from resources.settlement_pdf import build_tig_breakdown

PILOT_COURIER = "12345"
PILOT_MONTH = "2026-09"
MONEY_KEYS = {
    "base", "tip", "delay_bonus", "compliance_bonus", "address_bonus_kifli",
    "loyalty_bonus", "customer_rating", "monthly_bonus", "monthly_malus",
    "manual_bonus", "manual_malus", "atm_effect", "salary_advance", "reserve",
    "insurance_fee", "other_expense", "reserve_payment_credit", "reserve_deduction_credit",
    "correction_income", "correction_deduction",
}
NEGATIVE_KEYS = {"monthly_malus", "manual_malus", "salary_advance", "reserve", "insurance_fee", "other_expense", "correction_deduction"}
MANUAL_TYPES = {
    "bonus": ("Bónusz", 1), "malus": ("Malus", -1),
    "correction_income": ("Korrekció +", 1), "correction_deduction": ("Korrekció −", -1),
    "customer_rating": ("Ügyfélértékelés", 1), "atm_deduction": ("ATM levonás", -1),
    "other_expense": ("Egyéb kiadás", -1),
}


def require_pilot(courier_id, month):
    if str(courier_id) != PILOT_COURIER or str(month)[:7] != PILOT_MONTH:
        raise ValueError("A munkalap tesztje csak Bagoly Zoltán (#12345), 2026. szeptember hónapjára engedélyezett.")


def source_payload(snapshot, key):
    return next((s.get("payload") for s in snapshot.get("sources", []) if s.get("source_key") == key), None)


def worksheet_state(snapshot):
    """Expose canonical editable rows, never summary/detail aliases as inputs."""
    finance = [i for i in snapshot.get("items", []) if i.get("section") == "finance"]
    keys = {i["item_key"] for i in finance}
    allowed = set(MONEY_KEYS)
    for aggregate, components in (
        ("kiflis_bonus_malus", {"monthly_bonus", "monthly_malus"}),
        ("bonus_malus", {"manual_bonus", "manual_malus"}),
        ("correction", {"correction_income", "correction_deduction"}),
    ):
        if not keys.intersection(components):
            allowed.add(aggregate)
    rows = [{"key": i["item_key"], "label": i["item_label"],
             "amountHuf": int(i.get("amount_value") or 0),
             "amountKind": i.get("amount_kind") or "huf", "note": i.get("note") or ""}
            for i in finance if (i["item_key"] in allowed or i.get("amount_kind") == "count")
            and not (i["item_key"] == "performance" and "orders" in keys)]
    previous_edit = source_payload(snapshot, "pwa_worksheet_audit")
    if isinstance(previous_edit, dict) and isinstance(previous_edit.get("rows"), list):
        rows = deepcopy(previous_edit["rows"])
    return {
        "snapshotId": str(snapshot["id"]), "version": snapshot["version"], "rows": rows,
        "manualRows": source_payload(snapshot, "pwa_worksheet_manual_rows") or [],
        "savedTotal": int(next((i["amount_value"] for i in finance if i["item_key"] == "payable"), 0)),
        "tigTotal": (snapshot.get("metadata") or {}).get("tig_final_total"),
        "existingManualRows": source_payload(snapshot, "manual_adjustments") or [],
    }


def prepare_worksheet(snapshot, rows, manual_rows, note):
    require_pilot(snapshot.get("courier_id"), snapshot.get("period_start"))
    if not str(note or "").strip():
        raise ValueError("A módosítás indoka kötelező.")
    baseline = worksheet_state(snapshot)
    original = {r["key"]: r for r in baseline["rows"]}
    edited = {}
    for row in rows:
        key = row["key"]
        if key not in original or key in edited:
            raise ValueError("Ismeretlen vagy ismétlődő pénzügyi sor.")
        amount = row.get("amountHuf", 0)
        if isinstance(amount, bool) or not isinstance(amount, int) or abs(amount) > 1_000_000_000:
            raise ValueError("Az összeg egész forint legyen, legfeljebb 1 milliárd.")
        if key in NEGATIVE_KEYS and amount > 0:
            raise ValueError("A levonás típusú pénzügyi sor előjele negatív legyen.")
        edited[key] = {**original[key], "amountHuf": amount}
    # An omitted base row is never interpreted as deletion.
    base = [{**r, **edited.get(r["key"], {})} for r in baseline["rows"]]
    used_ids = set()
    clean_manual = []
    extra = []
    for row in manual_rows:
        row_id = str(row.get("id") or "")
        kind = str(row.get("type") or "")
        amount = row.get("amountHuf", 0)
        if not row_id or len(row_id) > 80 or row_id in used_ids or kind not in MANUAL_TYPES:
            raise ValueError("Hiányzó/ismétlődő kézi tételazonosító vagy ismeretlen típus.")
        used_ids.add(row_id)
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 1_000_000_000:
            raise ValueError("A kézi tétel összege 0 és 1 milliárd közötti egész forint legyen.")
        start = date.fromisoformat(str(row.get("validFrom") or ""))
        end = date.fromisoformat(str(row.get("validTo") or ""))
        if start > end or start.strftime("%Y-%m") != PILOT_MONTH or end.strftime("%Y-%m") != PILOT_MONTH:
            raise ValueError("A kézi tétel érvényessége a teszt hónapján belül legyen.")
        if not str(row.get("note") or "").strip():
            raise ValueError("Minden kézi tételhez megjegyzés szükséges.")
        label, sign = MANUAL_TYPES[kind]
        clean_manual.append({"id": row_id, "type": kind, "amountHuf": amount,
                             "validFrom": start.isoformat(), "validTo": end.isoformat(), "note": row["note"].strip()})
        extra.append({"key": "worksheet_manual_" + row_id, "label": label, "amountHuf": sign * amount,
                      "amountKind": "huf", "note": row["note"].strip(), "correction": kind.startswith("correction_")})
    income = deductions = correction = 0
    for row in base + extra:
        if row["amountKind"] != "huf":
            continue
        amount = row["amountHuf"]
        if row["key"] in {"correction", "correction_income", "correction_deduction"} or row.get("correction"):
            correction += amount
        elif amount >= 0:
            income += amount
        else:
            deductions += amount
    total = income + deductions + correction
    if total < 0:
        raise ValueError("Negatív kifizetendő összeghez ebben a tesztben nem készíthető TIG.")
    totals = {"income_total": income, "deduction_total": deductions, "correction_total": correction, "payable_total": total}
    by_key = {r["key"]: r["amountHuf"] for r in base}
    # Preserve the current profile as input; never refetch imports or run a batch.
    profile = deepcopy(source_payload(snapshot, "courier_profile") or {})
    cash = abs(by_key.get("atm_effect", 0) - sum(r["amountHuf"] for r in clean_manual if r["type"] == "atm_deduction"))
    tig = build_tig_breakdown({**profile, "id": PILOT_COURIER, "name": snapshot.get("courier_name"),
                               "document_month": date(2026, 9, 1)},
                              {"payable": total, "tip": by_key.get("tip", 0), "cash": cash})
    tig_total = int(tig["finalTotalHuf"])
    # These identities are checked again inside the transactional DB function.
    all_rows = base + extra + [{"key": key, "label": label, "amountHuf": value, "amountKind": "huf", "note": note}
                             for key, label, value in (("income", "Jóváírások", income), ("deductions", "Levonások", deductions),
                                                       ("correction", "Korrekciók", correction), ("payable", "Teljes összeg", total))]
    # A legacy net correction is an input and an aggregate: retain it only once.
    unique_rows = {r["key"]: r for r in all_rows}
    if "orders" in unique_rows:
        unique_rows["performance"] = {**unique_rows["orders"], "key": "performance", "label": "Teljesítmény"}
    # Store effective component amounts under the existing shared keys, so
    # devtest.py and PWA display the same values. Audit retains the editable
    # base amounts separately; opening/saving again must not re-add deltas.
    destinations = {"bonus": "manual_bonus", "malus": "manual_malus", "customer_rating": "customer_rating",
                    "correction_income": "correction_income", "correction_deduction": "correction_deduction",
                    "atm_deduction": "atm_effect", "other_expense": "other_expense"}
    for manual, detail in zip(clean_manual, extra):
        key = destinations[manual["type"]]
        if key not in unique_rows:
            unique_rows[key] = {"key": key, "label": detail["label"], "amountHuf": 0, "amountKind": "huf", "note": "PWA munkalap"}
        unique_rows[key] = {**unique_rows[key], "amountHuf": unique_rows[key]["amountHuf"] + detail["amountHuf"]}
    if "correction" in by_key:
        for key, amount in (("correction_income", max(by_key["correction"], 0)), ("correction_deduction", min(by_key["correction"], 0))):
            current = unique_rows.get(key, {"key": key, "label": key, "amountHuf": 0, "amountKind": "huf", "note": "PWA munkalap"})
            unique_rows[key] = {**current, "amountHuf": current["amountHuf"] + amount}
    # Individual manual entries are in the audited source, not additional
    # financial amounts (which would cause a second count in other readers).
    unique_rows = {key: row for key, row in unique_rows.items() if not key.startswith("worksheet_manual_")}
    for item in snapshot.get("items", []):
        if item.get("section") == "finance" and item["item_key"] in {"target_reserve_open", "target_reserve_close", "previous_excel_balance"}:
            unique_rows[item["item_key"]] = {"key": item["item_key"], "label": item["item_label"], "amountHuf": int(item["amount_value"]), "amountKind": "huf", "note": item.get("note", "")}
    items = [{"section": "finance", "item_key": r["key"], "item_label": r["label"],
              "amount_value": r["amountHuf"], "amount_kind": r["amountKind"],
              "note": r.get("note", ""), "display_order": n}
             for n, r in enumerate(unique_rows.values(), 1)]
    for row in tig["rows"]:
        items.append({"section": "tig", "item_key": "tig_" + row["key"], "item_label": row["label"],
                      "amount_value": row["grossHuf"], "amount_kind": "huf", "note": row.get("note", ""), "display_order": len(items) + 1})
    items.append({"section": "tig", "item_key": "tig_final_total", "item_label": "TIG végösszeg", "amount_value": tig_total,
                  "amount_kind": "huf", "note": note, "display_order": len(items) + 1})
    # Refresh aggregate aliases for existing PWA cards without counting them twice.
    for key, components, label in (("kiflis_bonus_malus", ["monthly_bonus", "monthly_malus"], "Kiflis levonások / bónuszok"),
                                    ("bonus_malus", ["manual_bonus", "manual_malus"], "JITT bónusz / malus")):
        if any(k in unique_rows for k in components):
            items.append({"section": "finance", "item_key": key, "item_label": label, "amount_value": sum(unique_rows.get(k, {}).get("amountHuf", 0) for k in components),
                          "amount_kind": "huf", "note": "Összesítő, nem külön tétel", "display_order": len(items) + 1})
    sources = [{k: deepcopy(s.get(k)) for k in ("source_key", "source_table", "payload", "row_count")}
               for s in snapshot.get("sources", []) if s.get("source_key") not in {
                   "card_drilldowns", "tig_breakdown", "pwa_worksheet_manual_rows", "pwa_worksheet_audit"}]
    sources += [
        {"source_key": "tig_breakdown", "payload": tig, "row_count": len(tig["rows"]), "source_table": "pwa_finance_worksheet"},
        {"source_key": "pwa_worksheet_manual_rows", "payload": clean_manual, "row_count": len(clean_manual), "source_table": "pwa_finance_worksheet"},
        {"source_key": "pwa_worksheet_audit", "payload": {"baseSnapshotId": baseline["snapshotId"], "note": note.strip(), "rows": base}, "row_count": len(base), "source_table": "pwa_finance_worksheet"},
    ]
    # Existing PWA card groups must include newly entered manual lines.
    labels = {"base": "Alapdíj", "tip": "Borravaló", "delay_bonus": "Késedelmi díj", "compliance_bonus": "Túramegfelelés",
              "address_bonus_kifli": "Cím bónusz (Kifli)", "loyalty_bonus": "Lojalitás", "customer_rating": "Ügyfélértékelési bónusz"}
    drilldowns = {label: [{"Tétel": label, "Összeg": unique_rows.get(key, {}).get("amountHuf", 0)}] for key, label in labels.items()}
    drilldowns["Korrekció"] = [{"Tétel": r["label"], "Összeg": r["amountHuf"], "Megjegyzés": r.get("note", "")}
                              for r in base + extra if r["key"] in {"correction", "correction_income", "correction_deduction"} or r.get("correction")]
    sources.append({"source_key": "card_drilldowns", "payload": drilldowns, "row_count": len(drilldowns), "source_table": "pwa_finance_worksheet"})
    metadata = {**(snapshot.get("metadata") or {}), **totals, "tig_final_total": tig_total,
                "order_count": by_key.get("orders", by_key.get("performance", 0)), "route_count": by_key.get("routes", 0),
                "source": "pwa_worksheet_pilot", "worksheet_base_snapshot_id": baseline["snapshotId"], "worksheet_note": note.strip()}
    changes = [{"key": r["key"], "label": r["label"], "before": original[r["key"]]["amountHuf"], "after": r["amountHuf"]}
               for r in base if original[r["key"]]["amountHuf"] != r["amountHuf"]]
    prepared = {"items": items, "sources": sources, "metadata": metadata}
    digest = hashlib.sha256(json.dumps(prepared, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return {"prepared": prepared, "previewHash": digest, "totals": totals, "tig": tig, "changes": changes,
            "previousTotal": baseline["savedTotal"], "delta": total - baseline["savedTotal"], "manualRows": clean_manual}
