"""Book reserve withdrawals against an existing settlement without recalculation."""
from copy import deepcopy
from math import isfinite


def split_net_reserve_rows(rows, totals):
    """Expose manual releases separately when rebuilding a net reserve calculation."""
    rows = deepcopy(rows)
    by_key = {r["item_key"]: r for r in rows}
    if "reserve_payment_credit" in by_key or "reserve_deduction_credit" in by_key:
        return rows
    released = sum(float(totals.get(kind) or 0) for kind in ("payment", "deduction"))
    if not released:
        return rows
    by_key["reserve"]["amount_value"] -= released
    by_key["income"]["amount_value"] += released
    by_key["deductions"]["amount_value"] -= released
    for kind, label in (("payment", "Céltartalék kifizetés"),
                        ("deduction", "Céltartalék levonás jóváírása")):
        rows.append({"item_key": f"reserve_{kind}_credit", "item_label": label,
                     "amount_kind": "huf", "amount_value": float(totals.get(kind) or 0)})
    return rows


def prepare_reserve_release(snapshot, totals):
    finance = [deepcopy(item) for item in snapshot.get("items", []) if item.get("section") == "finance"]
    by_key = {item["item_key"]: item for item in finance}
    keys = {"payment": "reserve_payment_credit", "deduction": "reserve_deduction_credit"}
    amounts = {kind: float(totals.get(kind) or 0) for kind in keys}
    prior = {kind: float(by_key.get(key, {}).get("amount_value") or 0) for kind, key in keys.items()}
    delta = sum(amounts.values()) - sum(prior.values())
    if not delta and amounts == prior:
        return {"changed": False}
    if any(not isfinite(value) or value < 0 for value in amounts.values()):
        raise ValueError("A céltartalék műveleti összeg nem lehet negatív.")
    required = {"payable", "income", "target_reserve_close", "reserve"}
    if not required.issubset(by_key):
        raise ValueError("Hiányos elszámolás: a céltartalék művelet nem könyvelhető.")
    def amount(key):
        return float(by_key.get(key, {}).get("amount_value") or 0)
    closing = amount("target_reserve_close") - delta
    if closing < 0:
        raise ValueError("A műveletek összege nagyobb a rendelkezésre álló céltartaléknál.")
    for key in ("payable", "income"):
        by_key[key]["amount_value"] = amount(key) + delta
    by_key["target_reserve_close"]["amount_value"] = closing
    for kind, key in keys.items():
        if key not in by_key:
            item = {"section": "finance", "item_key": key, "amount_kind": "huf",
                    "item_label": "Céltartalék kifizetés" if kind == "payment" else "Céltartalék levonás jóváírása",
                    "note": "Céltartalékból felszabadított összeg; növeli az elszámolást."}
            finance.append(item)
            by_key[key] = item
        by_key[key]["amount_value"] = amounts[kind]
    sources = deepcopy(snapshot.get("sources") or [])
    for source in sources:
        for field in ("id", "snapshot_id", "created_at"):
            source.pop(field, None)
    source_by_key = {s["source_key"]: s for s in sources}
    original_monthly = source_by_key.get("target_reserve_month", {}).get("payload")
    if not isinstance(original_monthly, dict) or "reserve_addition_huf" not in original_monthly:
        raise ValueError("Hiányzik a mentett havi céltartalék számítás.")
    monthly = deepcopy(original_monthly)
    monthly["reserve_addition_huf"] = float(monthly["reserve_addition_huf"]) - delta
    monthly["reserve_after_huf"] = closing
    monthly["payable_after_insurance_huf"] = amount("payable")
    source_by_key["target_reserve_month"]["payload"] = monthly
    drill = source_by_key.get("card_drilldowns", {}).get("payload")
    if isinstance(drill, dict):
        drill["Céltartalék 10%"] = [
            {"Tétel": "Céltartalék feltöltés", "Összeg": amount("reserve")},
            *[{"Tétel": by_key[key]["item_label"], "Összeg": amounts[kind]} for kind, key in keys.items() if amounts[kind]],
            {"Tétel": "Nyitó céltartalék", "Összeg": amount("target_reserve_open")},
            {"Tétel": "Záró céltartalék", "Összeg": closing},
        ]
        drill["Mobilon látható értékek"] = deepcopy(finance)
    return {"changed": True, "finance_rows": finance, "sources": sources,
            "monthly": monthly, "payable": amount("payable"), "closing": closing,
            "metadata": {"reserve_release_booked": True, "reserve_release_totals": amounts,
                         "payable_total": amount("payable"), "income_total": amount("income")}}
