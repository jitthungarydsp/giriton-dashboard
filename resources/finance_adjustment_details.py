"""Itemized manual entries from the same published finance snapshot."""


def snapshot_manual_adjustment_details(snapshot, label):
    groups = {
        "Korrekció": ({"correction", "manual_correction", "correction_income",
                        "correction_deduction", "manual_correction_deduction", "other_expense"}, "correction"),
        "JITT bónusz / malus": ({"bonus", "malus"}, "bonus_malus"),
    }
    if label not in groups:
        return []
    types, total_key = groups[label]
    adjustments = next((source.get("payload") for source in snapshot.get("sources", [])
                        if source.get("source_key") == "manual_adjustments"), [])
    if not isinstance(adjustments, list):
        return []
    names = {"bonus": "Bónusz", "malus": "Malus", "manual_correction": "Kézi korrekció +",
             "correction_income": "Korrekció +", "correction": "Korrekció",
             "correction_deduction": "Korrekció -", "manual_correction_deduction": "Kézi korrekció -",
             "other_expense": "Egyéb kiadás"}
    negative = {"malus", "correction_deduction", "manual_correction_deduction", "other_expense"}
    rows = []
    for item in adjustments:
        kind = str(item.get("adjustment_type") or "")
        if kind not in types:
            continue
        amount = float(item.get("amount_huf") or 0)
        if kind in negative:
            amount = -abs(amount)
        if not amount:
            continue
        period = " – ".join(str(item.get(key) or "") for key in ("valid_from", "valid_to")).strip(" –")
        rows.append({"Tétel": names[kind], "Összeg": amount,
                     "Megjegyzés": str(item.get("note") or ""), "Érvényesség": period})
    if not rows:
        return []
    total_item = next((item for item in snapshot.get("items", [])
                       if item.get("section") == "finance" and item.get("item_key") == total_key), None)
    if total_item is not None:
        remainder = float(total_item.get("amount_value") or 0) - sum(row["Összeg"] for row in rows)
        if abs(remainder) > 0.5:
            rows.append({"Tétel": "További mentett tételek", "Összeg": remainder,
                         "Megjegyzés": "A mentett összesítés fennmaradó része; ehhez a verzióhoz nincs kézi tételmegjegyzés.",
                         "Érvényesség": ""})
    return rows
