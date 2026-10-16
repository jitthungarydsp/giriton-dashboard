"""Status of the monthly workflow, shared by the admin list and PWA."""


def settlement_dashboard_status(
    *, settlement_ready, settlement_done, tig_ready, tig_done,
    invoice_submit_open=False, invoice_submit_done=False,
    invoice_check_open=False, invoice_check_done=False,
    invoice_payment_open=False, invoice_payment_done=False, open_complaints=0,
):
    def status(label, detail, tone, sort):
        return {"label": label, "detail": detail, "tone": tone, "sort": sort}

    if open_complaints:
        return status("Reklamáció", f"{open_complaints} nyitott reklamáció", "attention", 20)
    # A prepared TIG or reopened downstream action is not settlement acceptance.
    if settlement_ready and not settlement_done:
        return status("Elszámolás elfogadásra vár", "Futár teendő", "waiting", 40)
    if invoice_payment_done:
        return status("Kifizetve", "Folyamat lezárva", "done", 90)
    if invoice_payment_open or (invoice_check_done and not invoice_check_open and not invoice_submit_open):
        return status("Kifizetésre vár", "Admin kifizetésre vár", "waiting", 80)
    if invoice_check_open or (invoice_submit_done and not invoice_check_done):
        return status("Számla ellenőrzésre vár", "Számla beérkezett", "warning", 70)
    if invoice_submit_open or (tig_done and not invoice_submit_done):
        return status("Számlafeltöltésre vár", "Futár teendő", "waiting", 60)
    if settlement_done and not tig_ready and not tig_done:
        return status("TIG-re vár", "TIG elkészülésére vár", "waiting", 45)
    if settlement_done and tig_ready and not tig_done:
        return status("TIG elfogadásra vár", "Futár teendő", "waiting", 50)
    if settlement_ready:
        return status("Elszámolás", "Folyamatban", "active", 30)
    return status("Elszámolás készül", "Várakozás", "muted", 10)


def settlement_dashboard_status_from_row(row):
    """Recompute labels from flags, including rows returned by an older SQL view."""
    return settlement_dashboard_status(
        settlement_ready=bool(row.get("has_settlement_document") or row.get("settlement_started") or row.get("session_id")),
        settlement_done=bool(row.get("settlement_done")),
        tig_ready=bool(row.get("has_tig_document")),
        tig_done=bool(row.get("tig_done")),
        # Older deployed views omit this flag, but already calculate its label.
        # Use that label only until the flag is included in the view response.
        invoice_payment_open=bool(row.get(
            "invoice_payment_open", row.get("dashboard_status_label") == "Kifizetésre vár",
        )),
        **{key: bool(row.get(key)) for key in (
            "invoice_submit_open", "invoice_submit_done", "invoice_check_open",
            "invoice_check_done", "invoice_payment_done",
        )},
        open_complaints=int(row.get("open_complaints") or 0),
    )
