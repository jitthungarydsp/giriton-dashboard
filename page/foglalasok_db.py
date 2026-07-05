from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.foglalasok_db import read_foglalasok_raw


def show_foglalasok_db_page():
    st.title("Foglalasok DB")
    st.caption(
        "Forras: MuszakPRO Foglalasok Google Sheet -> Supabase foglalasok_raw."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdo datum",
        value=today,
        key="foglalasok_db_start",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today + timedelta(days=10),
        key="foglalasok_db_end",
    )

    try:
        df = read_foglalasok_raw(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        st.error(
            f"Foglalasok DB olvasasi hiba: {exc}"
        )
        st.info(
            "Ha meg nincs tabla, futtasd a docs/supabase_foglalasok_raw.sql fajlt a Supabase SQL Editorban."
        )
        return

    if df.empty:
        st.warning(
            "Meg nincs adat a foglalasok_raw tablaban erre az idoszakra."
        )
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Sor", len(df))
    col2.metric(
        "Futar",
        df["courier_id"].dropna().nunique() if "courier_id" in df.columns else 0,
    )
    col3.metric(
        "Nap",
        df["work_date"].nunique() if "work_date" in df.columns else 0,
    )

    names = sorted(
        name
        for name in df.get("courier_name", pd.Series(dtype=str)).dropna().unique()
        if str(name).strip()
    )
    selected_name = st.selectbox(
        "Futar szures",
        options=["Mind"] + names,
    )
    visible_df = df.copy()

    if selected_name != "Mind":
        visible_df = visible_df[
            visible_df["courier_name"] == selected_name
        ]

    display_columns = [
        "work_date",
        "shift_text",
        "warehouse",
        "email",
        "courier_name",
        "courier_id",
        "booking_code",
        "serial",
        "fetched_at",
    ]
    display_columns = [
        column
        for column in display_columns
        if column in visible_df.columns
    ]

    st.dataframe(
        visible_df[display_columns].rename(
            columns={
                "work_date": "Datum",
                "shift_text": "Muszak",
                "warehouse": "Raktar",
                "email": "E-mail",
                "courier_name": "Futar",
                "courier_id": "Courier ID",
                "booking_code": "Foglalasi kod",
                "serial": "Sorszam",
                "fetched_at": "DB frissites",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
