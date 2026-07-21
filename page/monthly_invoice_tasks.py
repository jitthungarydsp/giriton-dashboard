import calendar
from datetime import date

import pandas as pd
import streamlit as st

from page.invoice_summary import filter_by_worksheet, render_monthly_invoice_tasks
from resources.invoice_summary import (
    build_driver_invoice_summary,
    format_huf,
    normalize_person_key,
    read_invoice_data,
)
from resources.peopleforce_documents import (
    decode_document_content,
    read_peopleforce_card_statuses_for_month,
    read_peopleforce_documents,
)
from resources.pwa_invoice_validation import extract_expected_amount


def _driver_names(final_df):
    if final_df is None or final_df.empty or "driver_name" not in final_df.columns:
        return []
    names_by_key = {}
    for value in final_df["driver_name"].dropna().astype(str):
        name = value.strip()
        key = normalize_person_key(name)
        if name and key:
            names_by_key[key] = name
    return sorted(names_by_key.values(), key=normalize_person_key)


def _current_amounts_by_name(driver_summary):
    amounts = {}
    if driver_summary is None or driver_summary.empty:
        return amounts
    for _, row in driver_summary.iterrows():
        name = str(row.get("driver_name") or "").strip()
        if not name:
            continue
        try:
            amount = int(round(float(row.get("payable_total_huf", 0) or 0)))
        except (TypeError, ValueError):
            amount = 0
        amounts[normalize_person_key(name)] = amount
    return amounts


def _closed_couriers(document_month):
    statuses = read_peopleforce_card_statuses_for_month(document_month)
    if statuses.empty:
        return []
    closed = statuses[
        statuses["action_key"].astype(str).str.lower().isin(["invoice_payment", "monthly_close"])
        & statuses["status"].astype(str).str.lower().eq("done")
    ].copy()
    result = {}
    for _, row in closed.iterrows():
        courier_id = str(row.get("courier_id") or "").strip()
        courier_name = str(row.get("courier_name") or "").strip()
        key = courier_id or normalize_person_key(courier_name)
        if not key:
            continue
        existing = result.get(key)
        if existing is None or str(row.get("updated_at") or "") > str(existing.get("updated_at") or ""):
            result[key] = row.to_dict()
    return sorted(result.values(), key=lambda row: str(row.get("courier_name") or "").casefold())


def _latest_document_amount(courier_id, document_month, document_type):
    documents = read_peopleforce_documents(courier_id, document_month, document_type)
    if documents.empty:
        return 0, "Nincs feltöltött dokumentum"
    unreadable = []
    for _, document in documents.iterrows():
        file_name = str(document.get("file_name") or document_type)
        content = decode_document_content(document.get("file_content_base64"))
        amount = extract_expected_amount(content)
        if amount:
            return int(amount), file_name
        unreadable.append(file_name)
    return 0, "Nem olvasható: " + ", ".join(unreadable)


def render_closed_payment_audit(document_month, driver_summary):
    st.subheader("Lezárt utalások ellenőrzése")
    st.caption(
        "A már lezárt futárnál összehasonlítja a mostani számítást, az elküldött "
        "elszámolást és a TIG-et."
    )
    try:
        closed_couriers = _closed_couriers(document_month)
    except Exception as exc:
        st.error(f"A lezárt futárok nem tölthetők be: {exc}")
        return
    if not closed_couriers:
        st.info("Ebben a hónapban nincs lezárt vagy kifizetett futár.")
        return

    rows_by_key = {
        str(row.get("courier_id") or normalize_person_key(row.get("courier_name"))): row
        for row in closed_couriers
    }
    selected_key = st.selectbox(
        "Lezárt futár",
        list(rows_by_key),
        format_func=lambda key: (
            f"{rows_by_key[key].get('courier_name') or 'Ismeretlen'} "
            f"({rows_by_key[key].get('courier_id') or '-'})"
        ),
        key=f"closed_payment_audit_courier_{document_month}",
    )
    selected = rows_by_key[selected_key]
    courier_id = str(selected.get("courier_id") or "").strip()
    courier_name = str(selected.get("courier_name") or "").strip()
    st.caption(
        f"Zárási státusz: {selected.get('action_key')} · "
        f"{selected.get('updated_at') or '-'} · {selected.get('status_note') or '-'}"
    )

    if not st.button(
        "A három összeg ellenőrzése",
        type="primary",
        use_container_width=True,
        key=f"closed_payment_audit_run_{document_month}_{courier_id}",
    ):
        return

    current_amount = _current_amounts_by_name(driver_summary).get(
        normalize_person_key(courier_name), 0
    )
    try:
        settlement_amount, settlement_file = _latest_document_amount(
            courier_id, document_month, "settlement"
        )
        tig_amount, tig_file = _latest_document_amount(
            courier_id, document_month, "tig"
        )
    except Exception as exc:
        st.error(f"Az ellenőrzéshez szükséges dokumentumok nem tölthetők be: {exc}")
        return

    comparison_rows = [
        {"Forrás": "Mostani számítás", "Összeg": current_amount, "Dokumentum": "payable_total_huf"},
        {"Forrás": "Elszámolás", "Összeg": settlement_amount, "Dokumentum": settlement_file},
        {"Forrás": "TIG", "Összeg": tig_amount, "Dokumentum": tig_file},
    ]
    display_rows = []
    for row in comparison_rows:
        amount = int(row["Összeg"] or 0)
        display_rows.append(
            {
                "Forrás": row["Forrás"],
                "Összeg": format_huf(amount) if amount else "Nem található",
                "Eltérés a mostani számítástól": (
                    format_huf(amount - current_amount) if amount and current_amount else "-"
                ),
                "Dokumentum / adat": row["Dokumentum"],
            }
        )
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    amounts = [current_amount, settlement_amount, tig_amount]
    if all(amounts) and len(set(amounts)) == 1:
        st.success(
            f"Egyezik: {courier_name} mindhárom ellenőrzési összege {format_huf(current_amount)}."
        )
    else:
        st.error(
            "Eltérés vagy hiányzó adat található. Ellenőrizd az aktuális számítást, "
            "az elszámolást és a TIG-et."
        )


def show_monthly_invoice_tasks_page():
    st.title("Havi feladatok")
    st.caption(
        "A még intézendő futárok, a havi dokumentumfolyamat és a számla–TIG ellenőrzés külön nézete."
    )

    today = date.today()
    selected_date = st.date_input(
        "Hónap",
        value=today.replace(day=1),
        key="monthly_tasks_month",
    )
    selected_sheet = st.selectbox(
        "Raktár fül",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="monthly_tasks_sheet",
    )
    month_start = selected_date.replace(day=1)
    month_end = selected_date.replace(
        day=calendar.monthrange(selected_date.year, selected_date.month)[1]
    )
    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    try:
        data = read_invoice_data(month_start, month_end)
    except Exception as exc:
        st.error(f"A havi elszámolási adatok nem tölthetők be: {exc}")
        return

    all_final_df = data.get("final", pd.DataFrame())
    final_df = filter_by_worksheet(all_final_df, selected_sheet)
    bonus_df = data.get("bonus", pd.DataFrame())
    penalty_df = data.get("penalties", pd.DataFrame())
    manual_df = data.get("manual", pd.DataFrame())
    atm_balance_df = data.get("atm_balance", pd.DataFrame())
    customer_rating_df = data.get("customer_rating", pd.DataFrame())
    monthly_adjustment_df = data.get("monthly_adjustments", pd.DataFrame())

    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df=bonus_df,
        penalty_df=penalty_df,
        manual_df=manual_df,
        day_rates_df=data.get("day_rates", pd.DataFrame()),
        raw_route_df=data.get("routes", pd.DataFrame()),
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=atm_balance_df,
        customer_rating_df=customer_rating_df,
        monthly_adjustment_df=monthly_adjustment_df,
        period_start=month_start,
    )
    audit_driver_summary = driver_summary
    if selected_sheet != "Mind":
        audit_driver_summary = build_driver_invoice_summary(
            all_final_df,
            bonus_df=bonus_df,
            penalty_df=penalty_df,
            manual_df=manual_df,
            day_rates_df=data.get("day_rates", pd.DataFrame()),
            raw_route_df=data.get("routes", pd.DataFrame()),
            previous_routes_df=data.get("previous_routes", pd.DataFrame()),
            loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
            bookings_df=data.get("bookings", pd.DataFrame()),
            loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
            atm_balance_df=atm_balance_df,
            customer_rating_df=customer_rating_df,
            monthly_adjustment_df=monthly_adjustment_df,
            period_start=month_start,
        )

    open_tab, audit_tab = st.tabs(["Nyitott feladatok", "Lezárt utalások ellenőrzése"])
    with open_tab:
        render_monthly_invoice_tasks(
            _driver_names(final_df),
            month_start,
            driver_summary,
        )
    with audit_tab:
        render_closed_payment_audit(month_start, audit_driver_summary)
