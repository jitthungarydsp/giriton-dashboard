from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.giriton_shift_admin import (
    filter_booked_shift_rows,
    next_days_window,
    read_admin_action_log,
    read_next_giriton_shifts,
)


def _load_uploaded_table(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame()

    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    return pd.DataFrame()


def _metric_card(label, value, helper=""):
    st.markdown(
        f"""
        <div class="jitt-metric">
            <div class="jitt-metric-label">{label}</div>
            <div class="jitt-metric-value">{value}</div>
            <div class="jitt-metric-helper">{helper}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _display_shift_table(df):
    if df.empty:
        st.info("Meg nincs megjelenitheto muszak ebben a nezetben.")
        return

    columns = [
        "work_date",
        "warehouse",
        "start_time",
        "end_time",
        "occupancy",
        "booked",
        "maximum",
        "courier_id",
        "courier_name",
        "email",
        "serial",
        "status",
        "fetched_at",
    ]
    columns = [column for column in columns if column in df.columns]
    st.dataframe(
        df[columns].rename(
            columns={
                "work_date": "Datum",
                "warehouse": "Raktar",
                "start_time": "Kezdes",
                "end_time": "Vege",
                "occupancy": "Foglaltsag",
                "booked": "Foglalt",
                "maximum": "Maximum",
                "courier_id": "Courier ID",
                "courier_name": "Futar",
                "email": "E-mail",
                "serial": "Serial",
                "status": "Statusz",
                "fetched_at": "DB frissites",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=420,
    )


def _render_styles():
    st.markdown(
        """
        <style>
        .jitt-shell {
            border: 1px solid #d8dee8;
            border-radius: 8px;
            padding: 18px 20px;
            background: #ffffff;
        }
        .jitt-title-row {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 12px;
        }
        .jitt-kicker {
            font-size: 12px;
            color: #667085;
            text-transform: uppercase;
            letter-spacing: 0;
            font-weight: 700;
        }
        .jitt-page-title {
            font-size: 28px;
            line-height: 1.15;
            margin: 2px 0 6px 0;
            font-weight: 750;
            color: #182230;
        }
        .jitt-page-copy {
            color: #475467;
            font-size: 14px;
            margin: 0;
        }
        .jitt-status-pill {
            border: 1px solid #b9c6d8;
            border-radius: 999px;
            padding: 7px 12px;
            color: #344054;
            background: #f8fafc;
            font-size: 13px;
            white-space: nowrap;
        }
        .jitt-metric {
            border: 1px solid #d8dee8;
            border-radius: 8px;
            padding: 14px 16px;
            background: #fbfcfe;
            min-height: 96px;
        }
        .jitt-metric-label {
            font-size: 12px;
            color: #667085;
            font-weight: 700;
        }
        .jitt-metric-value {
            color: #182230;
            font-size: 26px;
            line-height: 1.1;
            font-weight: 760;
            margin-top: 6px;
        }
        .jitt-metric-helper {
            color: #667085;
            font-size: 12px;
            margin-top: 6px;
        }
        .jitt-step {
            border-left: 3px solid #2563eb;
            padding: 10px 12px;
            background: #f8fafc;
            margin-bottom: 8px;
            border-radius: 0 8px 8px 0;
        }
        .jitt-step strong {
            display: block;
            color: #182230;
            font-size: 14px;
            margin-bottom: 2px;
        }
        .jitt-step span {
            color: #667085;
            font-size: 13px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _preview_actions(selected_count, key_prefix):
    left, middle, right = st.columns(3)
    left.button(
        "Kovetkezo 10 nap betoltese",
        type="primary",
        use_container_width=True,
        disabled=True,
        key=f"{key_prefix}_load_next_10",
        help="Design fazis: kovetkezo korben kotjuk ra a raw export robotra.",
    )
    middle.button(
        f"Kijelolt torlese ({selected_count})",
        use_container_width=True,
        disabled=True,
        key=f"{key_prefix}_delete_selected",
        help="Design fazis: itt indul majd a tomeges Giriton torles.",
    )
    right.button(
        "GitHub job inditasa",
        use_container_width=True,
        disabled=True,
        key=f"{key_prefix}_github_job",
        help="Design fazis: kesobb innen indithato lesz a workflow.",
    )


def show_jitt_muszak_page():
    _render_styles()

    start_date, end_date = next_days_window(10)

    st.markdown(
        f"""
        <div class="jitt-shell">
            <div class="jitt-title-row">
                <div>
                    <div class="jitt-kicker">JITT HUB admin</div>
                    <div class="jitt-page-title">JITT muszakkezelo</div>
                    <p class="jitt-page-copy">
                        Kulon felulet a kovetkezo 10 nap Giriton muszakainak betoltesere,
                        ellenorzesere es torlesi elokeszitesere.
                    </p>
                </div>
                <div class="jitt-status-pill">Design nezet | {start_date} - {end_date}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    try:
        shifts = read_next_giriton_shifts(days=10)
    except Exception as exc:
        shifts = pd.DataFrame()
        st.warning(f"A Giriton raw adat most nem olvashato: {exc}")

    booked = filter_booked_shift_rows(shifts)
    free_count = max(len(shifts) - len(booked), 0)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _metric_card("Osszes raw sor", len(shifts), "giriton_shifts_raw")
    with m2:
        _metric_card("Foglalt sor", len(booked), "torleshez relevans")
    with m3:
        _metric_card("Ures sor", free_count, "csak ellenorzes")
    with m4:
        _metric_card("Idoszak", "10 nap", f"{start_date} - {end_date}")

    tabs = st.tabs(
        [
            "Betoltes",
            "Muszakok",
            "Torles",
            "Jog es log",
        ]
    )

    with tabs[0]:
        st.subheader("Betoltesi kozpont")
        st.caption(
            "Itt lesz egy helyen a DB-bol olvasas, file feltoltes es kesobb a robotos frissites inditasa."
        )

        upload_col, plan_col = st.columns([1.1, 0.9])
        with upload_col:
            uploaded_file = st.file_uploader(
                "Muszak lista feltoltese",
                type=["xlsx", "xls", "csv"],
                help="Design fazisban csak elonezetet keszitunk, DB-be meg nem ir.",
            )
            uploaded_df = _load_uploaded_table(uploaded_file)
            if uploaded_file is not None and uploaded_df.empty:
                st.error("Ezt a fajltipust vagy tartalmat most nem tudtam beolvasni.")
            elif not uploaded_df.empty:
                st.success(f"Fajl beolvasva: {len(uploaded_df)} sor")
                st.dataframe(uploaded_df.head(100), use_container_width=True, hide_index=True)
            else:
                st.info("Tolts fel xlsx/csv fajlt, es itt jelenik meg az elonezet.")

        with plan_col:
            st.markdown(
                """
                <div class="jitt-step">
                    <strong>1. Betoltes</strong>
                    <span>Giriton raw export vagy feltoltott xlsx/csv.</span>
                </div>
                <div class="jitt-step">
                    <strong>2. Ellenorzes</strong>
                    <span>Datum, raktar, kezdes, futar ID es serial validalas.</span>
                </div>
                <div class="jitt-step">
                    <strong>3. Muvelet</strong>
                    <span>Tomeges vagy egyedi torles, majd audit log.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            _preview_actions(0, "jitt_muszak_load_tab")

    with tabs[1]:
        st.subheader("Kovetkezo 10 nap muszakai")
        f1, f2, f3, f4 = st.columns([1, 1, 1, 1.4])
        mode = f1.segmented_control(
            "Nezet",
            ["Osszes", "Foglalt", "Ures"],
            default="Foglalt",
            key="jitt_muszak_mode",
        )
        warehouse = f2.selectbox(
            "Raktar",
            ["Mind", "BUD1", "BUD2"],
            key="jitt_muszak_warehouse",
        )
        day = f3.date_input(
            "Datum",
            value=date.today(),
            min_value=date.today() - timedelta(days=30),
            max_value=date.today() + timedelta(days=60),
            key="jitt_muszak_date",
        )
        search = f4.text_input(
            "Futar / ID / serial",
            key="jitt_muszak_search",
        )

        visible = shifts.copy()
        if mode == "Foglalt":
            visible = booked.copy()
        elif mode == "Ures":
            visible = shifts.drop(booked.index, errors="ignore") if not shifts.empty else shifts

        if not visible.empty and warehouse != "Mind" and "warehouse" in visible.columns:
            visible = visible[visible["warehouse"].astype(str) == warehouse]
        if not visible.empty and "work_date" in visible.columns:
            visible = visible[visible["work_date"].astype(str).str[:10] == day.isoformat()]
        if not visible.empty and search.strip():
            needle = search.strip().casefold()
            visible = visible[
                visible.get("courier_name", pd.Series("", index=visible.index))
                .astype(str)
                .str.casefold()
                .str.contains(needle, na=False)
                | visible.get("courier_id", pd.Series("", index=visible.index))
                .astype(str)
                .str.contains(needle, na=False)
                | visible.get("serial", pd.Series("", index=visible.index))
                .astype(str)
                .str.casefold()
                .str.contains(needle, na=False)
            ]

        _display_shift_table(visible)

    with tabs[2]:
        st.subheader("Torlesi munkapad")
        st.caption(
            "Most design nezet: itt fogjuk kivalasztani, hogy egyedi ID, serial vagy tomeges kijeloles alapjan torlunk."
        )

        delete_source = booked.copy()
        if not delete_source.empty:
            delete_source.insert(0, "Torles", False)
            delete_columns = [
                "Torles",
                "work_date",
                "warehouse",
                "start_time",
                "courier_id",
                "courier_name",
                "serial",
                "occupancy",
            ]
            delete_columns = [column for column in delete_columns if column in delete_source.columns]
            edited = st.data_editor(
                delete_source[delete_columns].rename(
                    columns={
                        "work_date": "Datum",
                        "warehouse": "Raktar",
                        "start_time": "Kezdes",
                        "courier_id": "Courier ID",
                        "courier_name": "Futar",
                        "serial": "Serial",
                        "occupancy": "Foglaltsag",
                    }
                ),
                use_container_width=True,
                hide_index=True,
                disabled=[
                    column
                    for column in [
                        "Datum",
                        "Raktar",
                        "Kezdes",
                        "Courier ID",
                        "Futar",
                        "Serial",
                        "Foglaltsag",
                    ]
                ],
                key="jitt_muszak_delete_design_editor",
                height=360,
            )
            selected_count = int(edited["Torles"].sum()) if "Torles" in edited.columns else 0
        else:
            selected_count = 0
            st.info("Nincs foglalt muszak a torlesi munkapadhoz.")

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.text_input("Serial", placeholder="08/03_7814_BUD1_10:00")
        c2.text_input("Courier ID", placeholder="7814")
        c3.selectbox("Raktar", ["BUD1", "BUD2"])
        c4.text_input("Kezdes", placeholder="10:00")
        st.text_input("Megeroses", placeholder="Eles torleshez majd TORLES szoveg kell")
        _preview_actions(selected_count, "jitt_muszak_delete_tab")

    with tabs[3]:
        st.subheader("Jogosultsag es audit")
        st.caption(
            "Az oldal admin menuben van, a robot muveletek pedig kulon log tablaba kerulnek."
        )

        a1, a2 = st.columns([0.9, 1.1])
        with a1:
            st.info(
                "Kovetkezo korben itt lesz a vegleges jogosultsagi matrix: ki kerhet le, ki torolhet, ki indithat GitHub jobot."
            )
            st.toggle("Lekerdezes engedelyezve", value=True, disabled=True)
            st.toggle("Tomeges torles engedelyezve", value=False, disabled=True)
            st.toggle("GitHub workflow inditas engedelyezve", value=False, disabled=True)

        with a2:
            try:
                log_df = read_admin_action_log(limit=100)
            except Exception as exc:
                log_df = pd.DataFrame()
                st.warning(f"Admin log most nem olvashato: {exc}")

            if log_df.empty:
                st.info("Meg nincs admin log adat, vagy a log tabla nincs letrehozva.")
            else:
                st.dataframe(log_df, use_container_width=True, hide_index=True, height=360)
