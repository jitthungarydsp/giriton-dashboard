from datetime import date

import pandas as pd
import streamlit as st

from page.monthly_invoice_tasks import _latest_document_amount
from resources.peopleforce_documents import read_peopleforce_documents_for_month


def document_couriers(document_month):
    documents = read_peopleforce_documents_for_month(document_month)
    if documents.empty:
        return []
    document_type = documents.get(
        "document_type", pd.Series("", index=documents.index)
    ).astype(str).str.strip().str.lower()
    documents = documents[document_type.isin(["settlement", "tig"])].copy()
    couriers = {}
    for _, row in documents.iterrows():
        courier_id = str(row.get("courier_id") or "").strip()
        courier_name = str(row.get("courier_name") or "").strip()
        key = courier_id or courier_name.casefold()
        if not key:
            continue
        current = couriers.setdefault(
            key,
            {
                "courier_id": courier_id,
                "courier_name": courier_name,
                "document_types": set(),
            },
        )
        current["document_types"].add(
            str(row.get("document_type") or "").strip().lower()
        )
    return sorted(
        couriers.values(),
        key=lambda row: str(row.get("courier_name") or "").casefold(),
    )


def build_pdf_comparison_rows(couriers, document_month, amount_loader):
    rows = []
    for courier in couriers:
        courier_id = str(courier.get("courier_id") or "").strip()
        courier_name = str(courier.get("courier_name") or "").strip()
        try:
            settlement_amount, settlement_file = amount_loader(
                courier_id, document_month, "settlement"
            )
        except Exception as exc:
            settlement_amount, settlement_file = 0, f"Elszámolás hiba: {exc}"
        try:
            tig_amount, tig_file = amount_loader(courier_id, document_month, "tig")
        except Exception as exc:
            tig_amount, tig_file = 0, f"TIG hiba: {exc}"

        both_found = bool(settlement_amount) and bool(tig_amount)
        difference = settlement_amount - tig_amount if both_found else 0
        rows.append(
            {
                "Futár": courier_name or "Ismeretlen",
                "Courier ID": courier_id or "-",
                "Elszámolás PDF végösszeg": int(settlement_amount or 0),
                "TIG PDF végösszeg": int(tig_amount or 0),
                "Eltérés (elszámolás − TIG)": int(difference),
                "Ellenőrzés": (
                    "Egyezik"
                    if both_found and difference == 0
                    else "Eltérés"
                    if both_found
                    else "Hiányzó PDF/összeg"
                ),
                "Elszámolás dokumentum": settlement_file,
                "TIG dokumentum": tig_file,
                "_both_found": both_found,
                "_matches": both_found and difference == 0,
            }
        )
    return pd.DataFrame(rows)


def show_amount_reconciliation_page():
    st.title("TIG–elszámolás ellenőrzés")
    st.caption(
        "Nincs újraszámolás: kizárólag a feltöltött elszámolás PDF és a "
        "feltöltött TIG PDF végösszegét hasonlítja össze."
    )

    selected_date = st.date_input(
        "Hónap",
        value=date.today().replace(day=1),
        key="pdf_amount_comparison_month",
    )
    document_month = selected_date.replace(day=1)
    if not st.button(
        "PDF-összegek összehasonlítása",
        type="primary",
        use_container_width=True,
        key=f"run_pdf_amount_comparison_{document_month}",
    ):
        st.info("Válaszd ki a hónapot, majd indítsd el az összehasonlítást.")
        return

    with st.spinner("A feltöltött PDF-ek végösszegének kiolvasása..."):
        try:
            couriers = document_couriers(document_month)
            result = build_pdf_comparison_rows(
                couriers, document_month, _latest_document_amount
            )
        except Exception as exc:
            st.error(f"A PDF-összehasonlítás nem futtatható: {exc}")
            return

    if result.empty:
        st.info("A kiválasztott hónapban nincs feltöltött TIG vagy elszámolás PDF.")
        return

    both_found = result["_both_found"].astype(bool)
    matches = result["_matches"].astype(bool)
    mismatches = both_found & ~matches
    missing = ~both_found
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Futár", len(result))
    m2.metric("Egyezik", int(matches.sum()))
    m3.metric("Eltérés", int(mismatches.sum()))
    m4.metric("Hiányzó PDF/összeg", int(missing.sum()))

    view_filter = st.radio(
        "Megjelenítés",
        ["Mindenki", "Csak eltérés", "Csak hiányzó PDF/összeg"],
        horizontal=True,
        key="pdf_amount_comparison_filter",
    )
    visible = result.copy()
    if view_filter == "Csak eltérés":
        visible = visible[visible["_both_found"] & ~visible["_matches"]]
    elif view_filter == "Csak hiányzó PDF/összeg":
        visible = visible[~visible["_both_found"]]

    def style_row(row):
        if row.get("Ellenőrzés") == "Egyezik":
            style = "background-color: #dcfce7; color: #14532d;"
        elif row.get("Ellenőrzés") == "Eltérés":
            style = "background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"
        else:
            style = "background-color: #fef9c3; color: #713f12;"
        return [style] * len(row)

    display = visible.drop(columns=["_both_found", "_matches"], errors="ignore")
    st.dataframe(
        display.style.apply(style_row, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Elszámolás PDF végösszeg": st.column_config.NumberColumn(format="%d Ft"),
            "TIG PDF végösszeg": st.column_config.NumberColumn(format="%d Ft"),
            "Eltérés (elszámolás − TIG)": st.column_config.NumberColumn(format="%d Ft"),
        },
    )
