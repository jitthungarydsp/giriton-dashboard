import pandas as pd
import streamlit as st

from resources.courier_master_db import read_courier_master


def show_couriers_page():
    st.title("Futárok")
    st.caption(
        "Forrás: Supabase courier_master. A tábla a DSP API, DSP_Drivers és Felhasznalok adataiból frissül."
    )

    try:
        df = read_courier_master()
    except Exception as exc:
        st.error(
            f"Futár törzs DB olvasási hiba: {exc}"
        )
        return

    if df.empty:
        st.warning(
            "Még nincs adat a courier_master táblában."
        )
        return

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Futár",
        len(df),
    )
    col2.metric(
        "E-maillel",
        int(df["email"].astype(str).str.contains("@", na=False).sum())
        if "email" in df.columns
        else 0,
    )
    col3.metric(
        "Telefonszámmal",
        int(df["phone_number"].astype(str).str.strip().ne("").sum())
        if "phone_number" in df.columns
        else 0,
    )

    warehouses = sorted(
        value
        for value in df.get("warehouse_name", pd.Series(dtype=str)).dropna().unique()
        if str(value).strip()
    )
    selected_warehouse = st.selectbox(
        "Raktár szűrés",
        options=["Mind"] + warehouses,
    )
    search = st.text_input(
        "Keresés név, ID, e-mail vagy telefonszám alapján"
    ).strip().casefold()
    visible_df = df.copy()

    if selected_warehouse != "Mind":
        visible_df = visible_df[
            visible_df["warehouse_name"].astype(str) == selected_warehouse
        ]

    if search:
        searchable = (
            visible_df.get("courier_id", pd.Series(dtype=str)).astype(str)
            + " "
            + visible_df.get("courier_name", pd.Series(dtype=str)).astype(str)
            + " "
            + visible_df.get("email", pd.Series(dtype=str)).astype(str)
            + " "
            + visible_df.get("phone_number", pd.Series(dtype=str)).astype(str)
        ).str.casefold()
        visible_df = visible_df[
            searchable.str.contains(search, na=False)
        ]

    display_columns = [
        "courier_id",
        "courier_name",
        "phone_number",
        "email",
        "warehouse_name",
        "active",
        "updated_at",
    ]
    display_columns = [
        column
        for column in display_columns
        if column in visible_df.columns
    ]

    st.dataframe(
        visible_df[display_columns].rename(
            columns={
                "courier_id": "Courier ID",
                "courier_name": "Név",
                "phone_number": "Telefonszám",
                "email": "E-mail",
                "warehouse_name": "Raktár",
                "active": "Aktív",
                "updated_at": "Frissítve",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
