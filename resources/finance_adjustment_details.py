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
        adjustments = []
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
    if label == "Korrekció":
        # Periodic bonuses are separate snapshot items, not manual adjustments.
        # Preserve their original rule name and calculation before any remainder.
        periodic_items = [item for item in snapshot.get("items", [])
                          if item.get("section") == "finance"
                          and str(item.get("item_key") or "").startswith("correction_periodic_")]
        drilldowns = next((source.get("payload") for source in snapshot.get("sources", [])
                          if source.get("source_key") == "card_drilldowns"), {})
        if isinstance(drilldowns, dict) and not periodic_items:
            # Older snapshots may keep the same named entries in source payloads
            # rather than in the normalized snapshot items table.
            periodic_items = [item for item in drilldowns.get("Mobilon látható értékek", [])
                              if str(item.get("item_key") or "").startswith("correction_periodic_")]
            if not periodic_items:
                for detail in drilldowns.get("Korrekció", []):
                    # Periodic rule rows have their calculation/days recorded;
                    # manual +/- aggregate rows do not, so do not duplicate them.
                    if not (detail.get("Napok") or detail.get("Feltétel")):
                        continue
                    periodic_items.append({
                        "item_label": detail.get("Tétel"), "amount_value": detail.get("Összeg"),
                        "note": " | ".join(str(detail.get(key) or "") for key in
                                           ("Napok", "Túratípus", "Feltétel", "Számítás") if detail.get(key)),
                    })
        for item in periodic_items:
            amount = float(item.get("amount_value") or 0)
            if amount:
                rows.append({"Tétel": str(item.get("item_label") or "Időszakos bónusz"),
                             "Összeg": amount, "Megjegyzés": str(item.get("note") or ""),
                             "Érvényesség": ""})
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
