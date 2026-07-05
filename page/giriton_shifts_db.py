from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.giriton_shifts_db import read_giriton_shifts_raw


def show_giriton_shifts_db_page():
    st.title("Giriton muszakok DB")
    st.caption(
        "Forras: Supabase giriton_shifts_raw. Ez a Shift Subscription robot DB-s ellenorzo oldala."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdo datum",
        value=today,
        key="giriton_shifts_db_start",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today + timedelta(days=10),
        key="giriton_shifts_db_end",
    )

    try:
        df = read_giriton_shifts_raw(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        st.error(
            f"Giriton muszak DB olvasasi hiba: {exc}"
        )
        st.info(
            "Ha meg nincs tabla, futtasd a docs/supabase_giriton_shifts_raw.sql fajlt a Supabase SQL Editorban."
        )
        return

    if df.empty:
        st.warning(
            "Meg nincs adat a giriton_shifts_raw tablaban erre az idoszakra."
        )
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sor", len(df))
    col2.metric(
        "Futar",
        df["courier_id"].dropna().nunique() if "courier_id" in df.columns else 0,
    )
    col3.metric(
        "Nap",
        df["work_date"].nunique() if "work_date" in df.columns else 0,
    )
    col4.metric(
        "Giriton OK",
        int((df["status"].astype(str) == "GIRITON_OK").sum())
        if "status" in df.columns
        else 0,
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
        "start_time",
        "end_time",
        "warehouse",
        "occupancy",
        "booked",
        "maximum",
        "courier_name",
        "email",
        "courier_id",
        "serial",
        "status",
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
                "start_time": "Kezdes",
                "end_time": "Vege",
                "warehouse": "Raktar",
                "occupancy": "Foglaltsag",
                "booked": "Foglalt",
                "maximum": "Maximum",
                "courier_name": "Futar",
                "email": "E-mail",
                "courier_id": "Courier ID",
                "serial": "Sorszam",
                "status": "Statusz",
                "fetched_at": "DB frissites",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
