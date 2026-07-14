from datetime import date

import pandas as pd
import streamlit as st

from resources.invoice_summary import (
    MANUAL_ITEM_TYPES,
    build_display_base_rate_matrix,
    build_display_driver_summary,
    build_display_manual_items,
    build_display_routes,
    build_display_summary,
    build_driver_invoice_summary,
    build_invoice_pdf_bytes,
    create_manual_invoice_item,
    format_huf,
    read_invoice_data,
)


def slugify_filename(value):
    text = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    safe = []
    for char in text:
        if char.isalnum():
            safe.append(char)
        elif char in [" ", "-", "_", "."]:
            safe.append("_")
    return "".join(safe).strip("_") or "osszes"


def filter_by_worksheet(df, selected_sheet):
    if df.empty or selected_sheet == "Mind":
        return df

    return df[
        df["worksheet_name"].astype(str) == selected_sheet
    ].copy()


def filter_by_driver(df, selected_driver):
    if df.empty or selected_driver == "Mind":
        return df

    return df[
        df["driver_name"].astype(str) == selected_driver
    ].copy()


def show_invoice_summary_page():
    st.title("Elszamolas")
    st.caption(
        "Forras: JITT invoice workbook. A BUD1_JIT es BUD2_JIT fulek 23. sortol indulnak, "
        "ezekbol keszul a futar szintu osszesito."
    )

    today = date.today()
    default_start = today.replace(day=1)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.5])
    start_date = col1.date_input(
        "Kezdo datum",
        value=default_start,
        key="invoice_start_date",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today,
        key="invoice_end_date",
    )
    selected_sheet = col3.selectbox(
        "Raktar ful",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="invoice_sheet_filter",
    )

    try:
        data = read_invoice_data(
            start_date,
            end_date,
        )
    except Exception as exc:
        st.error(
            f"Elszamolas DB olvasasi hiba: {exc}"
        )
        return

    final_df = data["final"]
    summary_df = data["summary"]
    bonus_df = data["bonus"]
    penalty_df = data["penalties"]
    manual_df = data["manual"]
    day_rates_df = data.get("day_rates", pd.DataFrame())

    final_df = filter_by_worksheet(
        final_df,
        selected_sheet,
    )

    drivers = sorted(
        value
        for value in final_df.get("driver_name", pd.Series(dtype=str)).dropna().astype(str).unique()
        if value.strip()
    )
    selected_driver = col4.selectbox(
        "Futar",
        ["Mind"] + drivers,
        key="invoice_driver_filter",
    )
    final_df = filter_by_driver(
        final_df,
        selected_driver,
    )

    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df,
        penalty_df,
        manual_df,
        day_rates_df,
    )

    if driver_summary.empty:
        st.warning(
            "Nincs elszamolasi route adat erre a szuresre."
        )
        return

    total_orders = int(pd.to_numeric(driver_summary["orders"], errors="coerce").fillna(0).sum())
    total_routes_source = (
        "route_count" if "route_count" in driver_summary.columns else "routes"
    )
    total_routes = int(
        pd.to_numeric(
            driver_summary[total_routes_source],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )
    total_delay = pd.to_numeric(driver_summary["delay_bonus_huf"], errors="coerce").fillna(0).sum()
    total_compliance = pd.to_numeric(driver_summary["compliance_bonus_huf"], errors="coerce").fillna(0).sum()
    total_adjustment = pd.to_numeric(driver_summary["adjustment_huf"], errors="coerce").fillna(0).sum()
    total_manual = pd.to_numeric(driver_summary.get("manual_payable_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_payable = pd.to_numeric(driver_summary["payable_total_huf"], errors="coerce").fillna(0).sum()

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Rendeles", total_orders)
    m2.metric("Kor", total_routes)
    m3.metric("Kesedelmi dij", format_huf(total_delay))
    m4.metric("Turamegfeleles", format_huf(total_compliance))
    m5.metric("Levonas / plusz", format_huf(total_adjustment))
    m6.metric("Manualis", format_huf(total_manual))
    m7.metric("Fizetendo", format_huf(total_payable))

    st.subheader("Futar osszesito")
    display_summary = build_display_driver_summary(driver_summary)
    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True,
    )

    pdf_title = (
        f"JITT elszamolas {start_date.isoformat()} - {end_date.isoformat()}"
    )
    try:
        filename_driver = "osszes"
        if selected_driver != "Mind" and not driver_summary.empty:
            selected_row = driver_summary.iloc[0]
            courier_id = str(selected_row.get("courier_id", "") or "").strip()
            driver_slug = slugify_filename(selected_driver)
            filename_driver = (
                f"{courier_id}_{driver_slug}" if courier_id else driver_slug
            )
        pdf_bytes = build_invoice_pdf_bytes(
            driver_summary,
            final_df,
            pdf_title,
        )
        st.download_button(
            "PDF generalasa",
            data=pdf_bytes,
            file_name=f"jitt_elszamolas_{filename_driver}_{start_date.isoformat()}_{end_date.isoformat()}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as exc:
        st.info(
            f"PDF generalas nem elerheto: {exc}"
        )

    with st.expander("Manualis elszamolasi tetelek", expanded=False):
        st.caption(
            "Ide kerulnek azok az osszegek, amelyek meg nincsenek a DB-ben automatikus forrasbol: "
            "celtartalek, uzemanyag, karokozas, KP vagy egyeb plusz/levonas."
        )
        form_col1, form_col2, form_col3 = st.columns([1, 1, 1])
        manual_date = form_col1.date_input(
            "Tetel datuma",
            value=end_date,
            key="invoice_manual_date",
        )
        manual_sheet = form_col2.selectbox(
            "Raktar ful",
            ["BUD1_JIT", "BUD2_JIT"],
            key="invoice_manual_sheet",
        )
        manual_driver_options = drivers or sorted(
            value
            for value in final_df.get("driver_name", pd.Series(dtype=str)).dropna().astype(str).unique()
            if value.strip()
        )
        manual_driver = form_col3.selectbox(
            "Futar",
            manual_driver_options,
            key="invoice_manual_driver",
        )
        form_col4, form_col5 = st.columns([1, 1])
        manual_type = form_col4.selectbox(
            "Tetel tipusa",
            list(MANUAL_ITEM_TYPES.keys()),
            format_func=lambda value: MANUAL_ITEM_TYPES[value],
            key="invoice_manual_type",
        )
        manual_amount = form_col5.number_input(
            "Osszeg Ft",
            value=0,
            step=500,
            key="invoice_manual_amount",
        )
        manual_note = st.text_input(
            "Megjegyzes",
            key="invoice_manual_note",
        )
        if st.button("Manualis tetel mentese", use_container_width=True):
            if not manual_driver:
                st.warning("Valassz futart a manualis tetelhez.")
            else:
                try:
                    table_name = create_manual_invoice_item(
                        manual_date,
                        manual_sheet,
                        manual_driver,
                        manual_type,
                        manual_amount,
                        manual_note,
                        created_by=str(st.session_state.get("username", "admin")),
                    )
                    st.cache_data.clear()
                    st.success(f"Manualis tetel mentve: {table_name}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Manualis tetel mentese sikertelen: {exc}")

        st.dataframe(
            build_display_manual_items(manual_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Alapdij matrix"):
        st.dataframe(
            build_display_base_rate_matrix(),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Felso osszesito tabla"):
        st.dataframe(
            build_display_summary(summary_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Route reszletek - nyers ellenorzes"):
        st.caption("A PDF-be ezt mar nem generaljuk, csak oldali ellenorzesre marad.")
        st.dataframe(
            build_display_routes(final_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Bonusz es penalty forras"):
        c1, c2 = st.columns(2)
        c1.write("Bonus routes")
        c1.dataframe(
            bonus_df,
            use_container_width=True,
            hide_index=True,
        )
        c2.write("Penalties")
        c2.dataframe(
            penalty_df,
            use_container_width=True,
            hide_index=True,
        )
