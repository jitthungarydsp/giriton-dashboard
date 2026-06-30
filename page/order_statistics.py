from datetime import date

import pandas as pd
import streamlit as st

from resources.google_auth import get_client


SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"


@st.cache_data(show_spinner=False, ttl=300)
def read_worksheet_records(sheet_name):
    worksheet = get_client().open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    values = worksheet.get_all_values()

    if not values:
        return pd.DataFrame()

    header = values[0]
    return pd.DataFrame(
        [
            {
                column: row[index] if index < len(row) else ""
                for index, column in enumerate(header)
            }
            for row in values[1:]
        ]
    )


def normalize_id(value):
    text = str(value or "").strip()

    if text.endswith(".0"):
        return text[:-2]

    return text


def load_order_statistics_source():
    customers = read_worksheet_records("DSP_Order_Customers")
    orders = read_worksheet_records("DSP_Orders")

    if customers.empty:
        return customers

    customers = customers.copy()

    if "routeId" not in customers.columns:
        customers["routeId"] = ""

    customers["routeId"] = customers["routeId"].apply(normalize_id)

    for column in ["date", "deliverSince", "deliverTill", "plannedArrivalTime", "realArrivalTime"]:
        if column not in customers.columns:
            customers[column] = ""

        customers[f"{column}_dt"] = pd.to_datetime(
            customers[column],
            errors="coerce",
        )

    if not orders.empty and "routeId" in orders.columns:
        orders = orders.copy()
        orders["routeId"] = orders["routeId"].apply(normalize_id)

        warehouse_by_route = (
            orders[["routeId", "warehouseName"]]
            .dropna()
            .drop_duplicates("routeId")
            if "warehouseName" in orders.columns
            else pd.DataFrame(columns=["routeId", "warehouseName"])
        )

        customers = customers.merge(
            warehouse_by_route,
            on="routeId",
            how="left",
        )
    else:
        customers["warehouseName"] = ""

    customers["work_date"] = customers["date_dt"].dt.date
    customers["time_bucket"] = customers["deliverSince_dt"].dt.floor("15min")
    customers["time_bucket_label"] = customers["time_bucket"].dt.strftime("%H:%M")

    return customers


def build_bucket_table(customers, selected_date):
    full_buckets = pd.DataFrame({
        "Idosav": pd.date_range(
            start=pd.Timestamp(selected_date),
            periods=96,
            freq="15min",
        ).strftime("%H:%M")
    })

    if customers.empty:
        full_buckets["Megrendelesek"] = 0
        full_buckets["Route-ok"] = 0
        full_buckets["Futarok"] = 0
        return full_buckets

    grouped = (
        customers
        .dropna(subset=["time_bucket"])
        .groupby("time_bucket_label", as_index=False)
        .agg(
            megrendelesek=("id", "count"),
            routeok=("routeId", "nunique"),
            futarok=("courierId", "nunique"),
        )
        .sort_values("time_bucket_label")
    )

    return grouped.rename(
        columns={
            "time_bucket_label": "Idosav",
            "megrendelesek": "Megrendelesek",
            "routeok": "Route-ok",
            "futarok": "Futarok",
        }
    )

    return full_buckets.merge(
        grouped,
        on="Idosav",
        how="left",
    ).fillna(0)


def show_order_statistics_page():
    st.title("Megrendeles statisztika")
    st.caption(
        "Forras: Google Sheet DSP_Order_Customers. A 15 perces bontas a deliverSince idoablak kezdete alapjan keszul."
    )

    customers = load_order_statistics_source()

    if customers.empty:
        st.warning("Nincs olvashato DSP_Order_Customers adat.")
        return

    available_dates = sorted(
        value
        for value in customers["work_date"].dropna().unique()
        if isinstance(value, date)
    )

    if not available_dates:
        st.warning("Nincs ervenyes datum a megrendeles adatokban.")
        return

    latest_date = available_dates[-1]

    col1, col2 = st.columns([1, 1])

    selected_date = col1.date_input(
        "Datum",
        value=latest_date,
        min_value=available_dates[0],
        max_value=available_dates[-1],
    )

    warehouses = sorted(
        value
        for value in customers.get("warehouseName", pd.Series(dtype=str)).fillna("").unique()
        if str(value).strip()
    )
    selected_warehouses = col2.multiselect(
        "Raktar",
        options=warehouses,
        default=warehouses,
    )

    filtered = customers[
        customers["work_date"] == selected_date
    ].copy()

    if selected_warehouses:
        filtered = filtered[
            filtered["warehouseName"].isin(selected_warehouses)
        ]

    bucket_table = build_bucket_table(
        filtered,
        selected_date,
    )

    total_orders = len(filtered)
    total_routes = filtered["routeId"].nunique() if "routeId" in filtered.columns else 0
    busiest = (
        bucket_table.sort_values("Megrendelesek", ascending=False).iloc[0]
        if not bucket_table.empty and bucket_table["Megrendelesek"].sum() > 0
        else None
    )

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Osszes megrendeles", total_orders)
    metric2.metric("Route-ok", total_routes)
    metric3.metric(
        "Legterheltebb idosav",
        f"{busiest['Idosav']} ({int(busiest['Megrendelesek'])})"
        if busiest is not None
        else "-",
    )

    if bucket_table["Megrendelesek"].sum() == 0:
        st.info("A valasztott napra nincs 15 perces bontasban megjelenitheto adat.")
        return

    chart_data = bucket_table.set_index("Idosav")["Megrendelesek"]
    st.bar_chart(chart_data, use_container_width=True)

    st.dataframe(
        bucket_table,
        use_container_width=True,
        hide_index=True,
    )
