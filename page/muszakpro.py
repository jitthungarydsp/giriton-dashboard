from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.foglalasok_db import (
    read_foglalasok_raw,
    read_muszakpro_events,
)


def _format_dataframe(df, columns, labels):
    visible_columns = [
        column
        for column in columns
        if column in df.columns
    ]

    if not visible_columns:
        return pd.DataFrame()

    return df[visible_columns].rename(
        columns=labels
    )


def _render_setup_box():
    with st.expander(
        "DB atvezetes beallitasa",
        expanded=False,
    ):
        st.markdown(
            """
1. Supabase SQL Editorban futtasd: `docs/supabase_muszakpro_live.sql`
2. Apps Scriptben add hozza a `muszakpro/supabase_bridge_gs.txt` tartalmat `SupabaseBridge.gs` fajlkent.
3. Apps Script Project Settings / Script properties:

```text
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
MUSZAKPRO_DB_ENABLED=TRUE
MUSZAKPRO_DB_TABLE=raw_muszakpro_bookings
MUSZAKPRO_DB_EVENT_TABLE=ops_muszakpro_events
```

Biztonsagi elv: a regi Google Sheet iras megmarad, a DB iras mellekerul.
"""
        )


def show_muszakpro_page():
    st.title("MuszakPro")
    st.caption(
        "Sajat rendszerre kotott MuszakPro foglalasok es esemenyek."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdo datum",
        value=today,
        key="muszakpro_start",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today + timedelta(days=10),
        key="muszakpro_end",
    )

    _render_setup_box()

    try:
        bookings = read_foglalasok_raw(
            start_date=start_date,
            end_date=end_date,
            limit=20000,
        )
    except Exception as exc:
        st.error(
            f"MuszakPro foglalas olvasasi hiba: {exc}"
        )
        st.info(
            "Ha meg nincs tabla, futtasd a docs/supabase_muszakpro_live.sql fajlt."
        )
        return

    try:
        events = read_muszakpro_events(
            start_date=start_date,
            end_date=end_date,
            limit=2000,
        )
    except Exception as exc:
        st.warning(
            f"MuszakPro esemenynaplo nem olvashato: {exc}"
        )
        events = pd.DataFrame()

    if bookings.empty:
        st.warning(
            "Meg nincs aktiv MuszakPro foglalas ebben az idoszakban."
        )
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Aktiv foglalas",
            len(bookings),
        )
        col2.metric(
            "Futar",
            bookings["courier_id"].dropna().nunique()
            if "courier_id" in bookings.columns
            else 0,
        )
        col3.metric(
            "Nap",
            bookings["work_date"].nunique()
            if "work_date" in bookings.columns
            else 0,
        )
        col4.metric(
            "Raktar",
            bookings["warehouse"].dropna().nunique()
            if "warehouse" in bookings.columns
            else 0,
        )

    tab_bookings, tab_events, tab_debug = st.tabs(
        [
            "Foglalasok",
            "Esemenynaplo",
            "Ellenorzes",
        ]
    )

    with tab_bookings:
        if bookings.empty:
            st.info(
                "Nincs megjelenitheto foglalas."
            )
        else:
            names = sorted(
                name
                for name in bookings.get(
                    "courier_name",
                    pd.Series(dtype=str),
                ).dropna().unique()
                if str(name).strip()
            )
            warehouses = sorted(
                warehouse
                for warehouse in bookings.get(
                    "warehouse",
                    pd.Series(dtype=str),
                ).dropna().unique()
                if str(warehouse).strip()
            )

            filter_col1, filter_col2 = st.columns(2)
            selected_name = filter_col1.selectbox(
                "Futar",
                options=["Mind"] + names,
                key="muszakpro_name_filter",
            )
            selected_warehouse = filter_col2.selectbox(
                "Raktar",
                options=["Mind"] + warehouses,
                key="muszakpro_warehouse_filter",
            )

            visible_df = bookings.copy()

            if selected_name != "Mind":
                visible_df = visible_df[
                    visible_df["courier_name"] == selected_name
                ]

            if selected_warehouse != "Mind":
                visible_df = visible_df[
                    visible_df["warehouse"] == selected_warehouse
                ]

            st.dataframe(
                _format_dataframe(
                    visible_df,
                    [
                        "work_date",
                        "shift_text",
                        "warehouse",
                        "courier_name",
                        "courier_id",
                        "email",
                        "booking_code",
                        "serial",
                        "fetched_at",
                    ],
                    {
                        "work_date": "Datum",
                        "shift_text": "Muszak",
                        "warehouse": "Raktar",
                        "courier_name": "Futar",
                        "courier_id": "Courier ID",
                        "email": "E-mail",
                        "booking_code": "Foglalasi kod",
                        "serial": "Sorszam",
                        "fetched_at": "DB frissites",
                    },
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab_events:
        if events.empty:
            st.info(
                "Meg nincs MuszakPro DB esemeny vagy az esemenytabla nincs letrehozva."
            )
        else:
            st.dataframe(
                _format_dataframe(
                    events,
                    [
                        "created_at",
                        "action_type",
                        "work_date",
                        "shift_text",
                        "warehouse",
                        "email",
                        "actor_email",
                        "booking_code",
                    ],
                    {
                        "created_at": "Idopont",
                        "action_type": "Muvelet",
                        "work_date": "Datum",
                        "shift_text": "Muszak",
                        "warehouse": "Raktar",
                        "email": "Futar e-mail",
                        "actor_email": "Muvelet vegzoje",
                        "booking_code": "Foglalasi kod",
                    },
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab_debug:
        st.subheader("Gyors ellenorzes")
        st.markdown(
            """
- Az aktiv foglalasok forrasa: `raw_muszakpro_bookings`
- Regi fallback: `foglalasok_raw`
- A torolt sorok DB-ben `status = CANCELLED` allapotot kapnak.
- A regi Google Sheet iras egyelore megmarad, ezert az eles MuszakPro nem ezen az oldalon mulik.
"""
        )

        if not bookings.empty:
            missing_id_count = (
                bookings["courier_id"].isna().sum()
                if "courier_id" in bookings.columns
                else 0
            )
            st.metric(
                "Hianyzo Courier ID",
                int(missing_id_count),
            )
