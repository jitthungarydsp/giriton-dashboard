from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.giriton_attendance_db import read_giriton_attendance_raw


def show_giriton_attendance_db_page():
    st.title("Giriton Attendance DB")
    st.caption(
        "Forras: Supabase giriton_attendance_raw. Ez az Attendance robot DB-s ellenorzo oldala."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdo datum",
        value=today - timedelta(days=7),
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today,
    )

    try:
        df = read_giriton_attendance_raw(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        st.error(
            f"Giriton Attendance DB olvasasi hiba: {exc}"
        )
        st.info(
            "Ha meg nincs tabla, futtasd a docs/supabase_giriton_attendance_raw.sql fajlt a Supabase SQL Editorban."
        )
        return

    if df.empty:
        st.warning(
            "Meg nincs adat a giriton_attendance_raw tablaban erre az idoszakra."
        )
        return

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Sor",
        len(df),
    )
    col2.metric(
        "Futar",
        df["courier_name"].nunique() if "courier_name" in df.columns else 0,
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
        "courier_name",
        "shift_text",
        "activity_status",
        "checkin_start",
        "checkin_end",
        "raw_details",
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
                "courier_name": "Futar",
                "shift_text": "Muszak",
                "activity_status": "Statusz",
                "checkin_start": "Bejelentkezes kezdete",
                "checkin_end": "Bejelentkezes vege",
                "raw_details": "Nyers reszlet",
                "fetched_at": "DB frissites",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
