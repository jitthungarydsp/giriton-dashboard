import calendar
from datetime import date

import pandas as pd
import streamlit as st

from page.invoice_summary import filter_by_worksheet
from page.monthly_invoice_tasks import _latest_document_amount
from resources.invoice_summary import (
    build_driver_invoice_summary,
    normalize_person_key,
    read_invoice_data,
)
from resources.peopleforce_documents import read_peopleforce_documents_for_month


def build_current_invoice_summary(data, selected_sheet, month_start):
    """Build the same payable_total_huf used by the invoice summary page."""
    final_df = filter_by_worksheet(data.get("final", pd.DataFrame()), selected_sheet)
    return build_driver_invoice_summary(
        final_df,
        bonus_df=data.get("bonus", pd.DataFrame()),
        penalty_df=data.get("penalties", pd.DataFrame()),
        manual_df=data.get("manual", pd.DataFrame()),
        day_rates_df=data.get("day_rates", pd.DataFrame()),
        raw_route_df=data.get("routes", pd.DataFrame()),
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=data.get("atm_balance", pd.DataFrame()),
        customer_rating_df=data.get("customer_rating", pd.DataFrame()),
        monthly_adjustment_df=data.get("monthly_adjustments", pd.DataFrame()),
        period_start=month_start,
    )


def tig_courier_lookup(document_month):
    documents = read_peopleforce_documents_for_month(document_month, document_type="tig")
    by_name = {}
    if documents.empty:
        return by_name
    for _, row in documents.iterrows():
        name = str(row.get("courier_name") or "").strip()
        courier_id = str(row.get("courier_id") or "").strip()
        key = normalize_person_key(name)
        if key and key not in by_name:
            by_name[key] = {"courier_id": courier_id, "courier_name": name}
    return by_name


def _clean_text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _summarize_by_courier(driver_summary):
    """Return one monthly invoice-summary total per courier, across warehouses."""
    if driver_summary is None or driver_summary.empty:
        return pd.DataFrame()

    summary = driver_summary.copy()
    summary["driver_name"] = summary.get("driver_name", "").map(_clean_text)
    summary["_name_key"] = summary["driver_name"].map(normalize_person_key)
    summary["payable_total_huf"] = pd.to_numeric(
        summary.get("payable_total_huf", 0), errors="coerce"
    ).fillna(0)
    if "courier_id" not in summary.columns:
        summary["courier_id"] = ""
    summary["courier_id"] = summary["courier_id"].map(_clean_text)

    rows = []
    for name_key, group in summary.groupby("_name_key", dropna=False, sort=False):
        courier_ids = [value for value in group["courier_id"] if value]
        rows.append(
            {
                "_name_key": name_key,
                "driver_name": next(
                    (value for value in group["driver_name"] if value), "Ismeretlen"
                ),
                "courier_id": courier_ids[0] if courier_ids else "",
                "payable_total_huf": int(round(group["payable_total_huf"].sum())),
            }
        )
    return pd.DataFrame(rows)


def build_invoice_tig_comparison_rows(
    driver_summary, document_month, tig_by_name, amount_loader
):
    rows = []
    monthly_summary = _summarize_by_courier(driver_summary)
    if monthly_summary.empty:
        return pd.DataFrame()

    for _, summary in monthly_summary.iterrows():
        courier_name = _clean_text(summary.get("driver_name"))
        name_key = _clean_text(summary.get("_name_key"))
        tig_courier = tig_by_name.get(name_key, {})
        courier_id = _clean_text(summary.get("courier_id")) or _clean_text(
            tig_courier.get("courier_id")
        )
        invoice_amount = int(summary.get("payable_total_huf", 0))

        if courier_id:
            try:
                tig_amount, tig_file = amount_loader(courier_id, document_month, "tig")
            except Exception as exc:
                tig_amount, tig_file = 0, f"TIG hiba: {exc}"
        else:
            tig_amount, tig_file = 0, "Nincs Courier ID / TIG"

        tig_amount = int(tig_amount or 0)
        tig_found = bool(tig_amount)
        difference = invoice_amount - tig_amount if tig_found else 0
        rows.append(
            {
                "Futár": courier_name or tig_courier.get("courier_name") or "Ismeretlen",
                "Courier ID": courier_id or "-",
                "Invoice summary végösszeg": invoice_amount,
                "TIG PDF végösszeg": tig_amount,
                "Eltérés (invoice summary − TIG)": difference,
                "Ellenőrzés": (
                    "Egyezik"
                    if tig_found and difference == 0
                    else "Eltérés"
                    if tig_found
                    else "Hiányzó TIG/összeg"
                ),
                "TIG dokumentum": tig_file,
                "_tig_found": tig_found,
                "_matches": tig_found and difference == 0,
            }
        )
    return pd.DataFrame(rows)


def show_amount_reconciliation_page():
    st.title("Invoice summary–TIG ellenőrzés")
    st.caption(
        "A resources/invoice_summary.py payable_total_huf végösszegét hasonlítja "
        "össze a feltöltött TIG PDF végösszegével. Más adatforrást nem használ."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    selected_date = col1.date_input(
        "Hónap", value=today.replace(day=1), key="invoice_tig_comparison_month"
    )
    selected_sheet = col2.selectbox(
        "Raktár", ["Mind", "BUD1_JIT", "BUD2_JIT"], key="invoice_tig_comparison_sheet"
    )
    month_start = selected_date.replace(day=1)
    month_end = selected_date.replace(
        day=calendar.monthrange(selected_date.year, selected_date.month)[1]
    )
    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    if not st.button(
        "Invoice summary és TIG összehasonlítása",
        type="primary",
        use_container_width=True,
        key=f"run_invoice_tig_comparison_{month_start}_{selected_sheet}",
    ):
        st.info("Válaszd ki a hónapot, majd indítsd el az összehasonlítást.")
        return

    with st.spinner("Invoice summary végösszegek és TIG PDF-ek ellenőrzése..."):
        try:
            data = read_invoice_data(month_start, month_end)
            driver_summary = build_current_invoice_summary(
                data, selected_sheet, month_start
            )
            tig_by_name = tig_courier_lookup(month_start)
            result = build_invoice_tig_comparison_rows(
                driver_summary, month_start, tig_by_name, _latest_document_amount
            )
        except Exception as exc:
            st.error(f"Az összehasonlítás nem futtatható: {exc}")
            return

    if result.empty:
        st.info("A kiválasztott hónaphoz nincs invoice summary adat.")
        return

    tig_found = result["_tig_found"].astype(bool)
    matches = result["_matches"].astype(bool)
    mismatches = tig_found & ~matches
    missing = ~tig_found
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Futár", len(result))
    m2.metric("Egyezik", int(matches.sum()))
    m3.metric("Eltérés", int(mismatches.sum()))
    m4.metric("Hiányzó TIG/összeg", int(missing.sum()))

    view_filter = st.radio(
        "Megjelenítés",
        ["Mindenki", "Csak eltérés", "Csak hiányzó TIG/összeg"],
        horizontal=True,
        key="invoice_tig_comparison_filter",
    )
    visible = result.copy()
    if view_filter == "Csak eltérés":
        visible = visible[visible["_tig_found"] & ~visible["_matches"]]
    elif view_filter == "Csak hiányzó TIG/összeg":
        visible = visible[~visible["_tig_found"]]

    def style_row(row):
        if row.get("Ellenőrzés") == "Egyezik":
            style = "background-color: #dcfce7; color: #14532d;"
        elif row.get("Ellenőrzés") == "Eltérés":
            style = "background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"
        else:
            style = "background-color: #fef9c3; color: #713f12;"
        return [style] * len(row)

    display = visible.drop(columns=["_tig_found", "_matches"], errors="ignore")
    st.dataframe(
        display.style.apply(style_row, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Invoice summary végösszeg": st.column_config.NumberColumn(format="%d Ft"),
            "TIG PDF végösszeg": st.column_config.NumberColumn(format="%d Ft"),
            "Eltérés (invoice summary − TIG)": st.column_config.NumberColumn(
                format="%d Ft"
            ),
        },
    )
