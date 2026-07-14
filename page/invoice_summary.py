from datetime import date

import pandas as pd
import streamlit as st

from resources.courier_master_db import read_courier_master
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
from resources.peopleforce_documents import (
    decode_document_content,
    delete_peopleforce_document,
    read_peopleforce_complaints,
    read_peopleforce_documents_for_courier,
    read_peopleforce_document_content,
    respond_to_peopleforce_complaint,
    update_peopleforce_document,
    update_peopleforce_complaint_status,
    upload_peopleforce_document_bytes,
    upsert_peopleforce_card_status,
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


def normalize_name(value):
    return " ".join(str(value or "").strip().casefold().split())


def resolve_courier_identity(selected_row, selected_driver):
    courier_id = str(selected_row.get("courier_id", "") or "").strip()
    courier_name = str(
        selected_row.get("driver_name", selected_driver) or selected_driver
    ).strip()

    if courier_id:
        return courier_id, courier_name

    try:
        master = read_courier_master()
    except Exception:
        master = pd.DataFrame()

    if master.empty or "courier_name" not in master.columns:
        return courier_id, courier_name

    target_name = normalize_name(courier_name)
    matches = master[
        master["courier_name"].astype(str).map(normalize_name) == target_name
    ].copy()

    if matches.empty:
        return courier_id, courier_name

    match = matches.iloc[0]
    courier_id = str(match.get("courier_id", "") or "").strip()
    courier_name = str(match.get("courier_name", courier_name) or courier_name).strip()
    return courier_id, courier_name


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


def month_start_from_date(value):
    return value.replace(day=1)


def render_admin_document_manager(courier_id, courier_name):
    with st.expander("A futárnak feltöltött dokumentumok kezelése", expanded=False):
        try:
            documents = read_peopleforce_documents_for_courier(courier_id)
        except Exception as exc:
            st.error(f"A dokumentumlista nem tölthető be: {exc}")
            return
        if documents.empty:
            st.info("Ehhez a futárhoz még nincs feltöltött dokumentum.")
            return
        type_labels = {
            "settlement": "Elszámolás", "tig": "TIG", "invoice": "Számla",
            "complaint_response": "Reklamációs válasz",
        }
        st.caption(f"{len(documents)} feltöltött dokumentum – {courier_name}")
        overview = documents.copy()
        overview["Típus"] = overview["document_type"].map(
            lambda value: type_labels.get(str(value), str(value))
        )
        overview["Hónap"] = overview["document_month"].astype(str).str[:7]
        st.dataframe(
            overview[["Hónap", "Típus", "title", "file_name", "uploaded_at"]].rename(
                columns={"title": "Megnevezés", "file_name": "Fájl", "uploaded_at": "Feltöltve"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        rows_by_id = {
            str(row.get("id")): row for _, row in documents.iterrows()
        }
        selected_id = st.selectbox(
            "Kezelendő dokumentum",
            list(rows_by_id),
            format_func=lambda value: (
                f"{str(rows_by_id[value].get('document_month', ''))[:7]} | "
                f"{type_labels.get(str(rows_by_id[value].get('document_type', '')), str(rows_by_id[value].get('document_type', '')))} | "
                f"{rows_by_id[value].get('title') or rows_by_id[value].get('file_name')}"
            ),
        )
        document = rows_by_id[selected_id]
        file_name = str(document.get("file_name") or "dokumentum")
        title = str(document.get("title") or file_name)
        note = str(document.get("note") or "")
        try:
            content = read_peopleforce_document_content(selected_id)
            file_bytes = decode_document_content(content.get("file_content_base64"))
        except Exception:
            file_bytes = b""
        if file_bytes:
            st.download_button(
                "Kiválasztott dokumentum letöltése",
                data=file_bytes,
                file_name=file_name,
                mime=str(document.get("mime_type") or "application/octet-stream"),
            )
        with st.form(f"admin_document_edit_{selected_id}"):
            edited_title = st.text_input("Megnevezés", value=title)
            edited_note = st.text_area("Megjegyzés", value=note, height=70)
            if st.form_submit_button("Adatok mentése"):
                update_peopleforce_document(selected_id, title=edited_title, note=edited_note)
                st.success("A dokumentum adatai frissültek.")
                st.rerun()
        confirm_delete = st.checkbox(
            "Törlés megerősítése",
            key=f"admin_document_delete_confirm_{selected_id}",
        )
        if st.button("Dokumentum törlése", disabled=not confirm_delete):
            delete_peopleforce_document(selected_id)
            st.success("A dokumentum törölve.")
            st.rerun()


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
    raw_route_df = data.get("routes", pd.DataFrame())

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
        raw_route_df,
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        period_start=start_date,
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
    total_loyalty = pd.to_numeric(driver_summary.get("loyalty_bonus_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_instructor = pd.to_numeric(driver_summary.get("instructor_fee_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_payable = pd.to_numeric(driver_summary["payable_total_huf"], errors="coerce").fillna(0).sum()

    m1, m2, m3, m4, m5, m6, m7, m8, m9 = st.columns(9)
    m1.metric("Rendeles", total_orders)
    m2.metric("Kor", total_routes)
    m3.metric("Kesedelmi dij", format_huf(total_delay))
    m4.metric("Turamegfeleles", format_huf(total_compliance))
    m5.metric("Levonas / plusz", format_huf(total_adjustment))
    m6.metric("Lojalitás", format_huf(total_loyalty))
    m7.metric("Oktatói Díj", format_huf(total_instructor))
    m8.metric("Manuális", format_huf(total_manual - total_loyalty - total_instructor))
    m9.metric("Fizetendő", format_huf(total_payable))

    st.subheader("Futar osszesito")
    display_summary = build_display_driver_summary(driver_summary)
    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True,
    )
    if data.get("loyalty_error"):
        st.warning(
            "A lojalitási Google-törzsadat jelenleg nem olvasható. "
            "A Google service-account kulcsot frissíteni kell; ez a Túramegfelelés számítását nem érinti."
        )
    with st.expander("Lojalitási bónusz ellenőrzése", expanded=False):
        loyalty_columns = [
            "driver_name", "loyalty_previous_normal_routes", "loyalty_current_normal_routes",
            "loyalty_rate_huf", "loyalty_bonus_huf", "loyalty_status",
        ]
        st.dataframe(
            driver_summary[[column for column in loyalty_columns if column in driver_summary.columns]],
            use_container_width=True,
            hide_index=True,
        )

    if selected_driver != "Mind" and not driver_summary.empty:
        selected_row = driver_summary.iloc[0]
        courier_id, courier_name = resolve_courier_identity(selected_row, selected_driver)
        if courier_id:
            try:
                complaints = read_peopleforce_complaints(
                    courier_id,
                    month_start_from_date(start_date),
                    "settlement",
                )
            except Exception:
                complaints = pd.DataFrame()
            open_complaints = complaints[
                complaints.get("status", pd.Series(dtype=str)).astype(str).str.lower() != "resolved"
            ] if not complaints.empty else complaints
            if not open_complaints.empty:
                st.error("A futár reklamációt küldött ehhez az elszámoláshoz. Az elszámolás visszanyitva.")
                for _, complaint in open_complaints.iterrows():
                    with st.container(border=True):
                        st.write(complaint.get("message", ""))
                        st.caption(f"Beküldte: {complaint.get('created_by', courier_name)} | {complaint.get('created_at', '')}")
                        complaint_id = complaint.get("id")
                        with st.form(f"reply_invoice_complaint_{complaint_id}"):
                            response_message = st.text_area(
                                "Válasz a futárnak",
                                placeholder="Írd le, mit javítottál vagy miért helyes az elszámolás.",
                                height=100,
                            )
                            send_response = st.form_submit_button(
                                "Válasz küldése és reklamáció lezárása"
                            )
                        if send_response:
                            if not str(response_message or "").strip():
                                st.warning("Írj választ a futárnak.")
                            else:
                                respond_to_peopleforce_complaint(
                                    complaint_id,
                                    response_message,
                                    str(st.session_state.get("username", "admin")),
                                    courier_id=courier_id,
                                    courier_name=courier_name,
                                    document_type="settlement",
                                    document_month=month_start_from_date(start_date),
                                )
                                st.success("A választ elküldtük a futárnak, a reklamáció lezárva.")
                                st.rerun()
                        if st.button(
                            "Lezárás válasz nélkül",
                            key=f"resolve_invoice_complaint_{complaint_id}",
                        ):
                            update_peopleforce_complaint_status(complaint_id, "resolved")
                            st.success("A reklamáció lezárva.")
                            st.rerun()
            render_admin_document_manager(courier_id, courier_name)

    pdf_title = (
        f"JITT elszamolas {start_date.isoformat()} - {end_date.isoformat()}"
    )
    try:
        filename_driver = "osszes"
        if selected_driver != "Mind" and not driver_summary.empty:
            selected_row = driver_summary.iloc[0]
            courier_id, _courier_name = resolve_courier_identity(
                selected_row,
                selected_driver,
            )
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
        if selected_driver != "Mind" and st.button(
            "Feltöltés a futár profiljába",
            use_container_width=True,
            key="invoice_send_to_courier_card",
        ):
            selected_row = driver_summary.iloc[0]
            courier_id, courier_name = resolve_courier_identity(
                selected_row,
                selected_driver,
            )

            if not courier_id:
                st.warning("Ehhez a futárhoz nincs courier ID, így nem tudom a Kifli kártyára küldeni.")
            else:
                document_month = month_start_from_date(start_date)
                file_name = (
                    f"jitt_elszamolas_{courier_id}_{slugify_filename(courier_name)}_"
                    f"{start_date.isoformat()}_{end_date.isoformat()}.pdf"
                )
                upload_peopleforce_document_bytes(
                    courier_id=courier_id,
                    courier_name=courier_name,
                    document_type="settlement",
                    document_month=document_month,
                    title=f"Elszamolas - {start_date.isoformat()} - {end_date.isoformat()}",
                    note="Admin által kártyára küldött elszámolás.",
                    file_name=file_name,
                    mime_type="application/pdf",
                    file_bytes=pdf_bytes,
                    uploaded_by=str(st.session_state.get("username", "admin")),
                )
                upsert_peopleforce_card_status(
                    courier_id=courier_id,
                    courier_name=courier_name,
                    action_key="settlement",
                    document_month=document_month,
                    status="open",
                    status_note="Elszámolás kártyára küldve, futár visszajelzésre vár.",
                    updated_by=str(st.session_state.get("username", "admin")),
                )
                st.cache_data.clear()
                st.success("Az elszámolás bekerült a futár profiljába.")
                st.rerun()
        elif selected_driver == "Mind":
            st.caption("Profilba feltöltéshez válassz ki egy konkrét futárt.")
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
