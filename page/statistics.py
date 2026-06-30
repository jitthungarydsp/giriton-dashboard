from datetime import date

import pandas as pd
import streamlit as st

from resources.dsp_dashboard_statistics import (
    build_company_kpis,
    build_statistics,
    normalize_id,
)


def format_number(value, decimals=1):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "0"


def format_minutes(value):
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return "0 perc"

    return f"{minutes:.1f} perc"


def display_company_kpis(summary_df, title):
    kpis = build_company_kpis(summary_df)

    st.subheader(title)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Futárok", kpis["couriers"])
    c2.metric("Kivitt címek", kpis["delivered_orders"])
    c3.metric("Kivitt körök", kpis["routes"])
    c4.metric("Dolgozott napok", kpis["worked_days"])
    c5.metric("Késéses műszak", kpis["late_shift_count"])

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Átlag cím/kör", format_number(kpis["avg_orders_per_route"]))
    c7.metric("Átlag kör/nap", format_number(kpis["avg_routes_per_workday"]))
    c8.metric("Átlag várakozás", format_minutes(kpis["avg_wait_minutes"]))
    c9.metric("Átlag túra hossz", format_minutes(kpis["avg_route_minutes"]))
    c10.metric("Átlag bepakolás", format_minutes(kpis["avg_loading_minutes"]))

    c11, c12 = st.columns(2)
    c11.metric("Korai cím időablakon kívül", kpis["early_address_count"])
    c12.metric("Késő cím időablakon kívül", kpis["late_address_count"])


def build_summary_table(summary_df):
    table = summary_df.copy()

    table = table.rename(
        columns={
            "courier_id": "Futár ID",
            "name": "Futár",
            "warehouse": "Raktár",
            "delivered_orders": "Kivitt címek",
            "routes": "Kivitt körök",
            "worked_days": "Dolgozott napok",
            "avg_orders_per_route": "Átlag cím/kör",
            "avg_routes_per_workday": "Átlag kör/nap",
            "avg_wait_minutes": "Átlag várakozás (perc)",
            "late_shift_count": "Késéses műszak",
            "early_address_count": "Korai cím",
            "late_address_count": "Késő cím",
            "avg_route_minutes": "Átlag túra hossz (perc)",
            "avg_loading_minutes": "Átlag bepakolás (perc)",
        }
    )

    columns = [
        "Futár ID",
        "Futár",
        "Raktár",
        "Kivitt címek",
        "Kivitt körök",
        "Dolgozott napok",
        "Átlag cím/kör",
        "Átlag kör/nap",
        "Átlag várakozás (perc)",
        "Késéses műszak",
        "Korai cím",
        "Késő cím",
        "Átlag túra hossz (perc)",
        "Átlag bepakolás (perc)",
    ]

    for column in columns:
        if column not in table.columns:
            table[column] = ""

    numeric_columns = [
        "Átlag cím/kör",
        "Átlag kör/nap",
        "Átlag várakozás (perc)",
        "Átlag túra hossz (perc)",
        "Átlag bepakolás (perc)",
    ]

    for column in numeric_columns:
        table[column] = pd.to_numeric(
            table[column],
            errors="coerce",
        ).fillna(0).round(1)

    return table[columns]


def show_driver_metrics(row):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kivitt címek", int(row["delivered_orders"]))
    c2.metric("Kivitt körök", int(row["routes"]))
    c3.metric("Dolgozott napok", int(row["worked_days"]))
    c4.metric("Átlag cím/kör", format_number(row["avg_orders_per_route"]))
    c5.metric("Késéses műszak", int(row["late_shift_count"]))

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Átlag kör/nap", format_number(row["avg_routes_per_workday"]))
    c7.metric("Átlag várakozás", format_minutes(row["avg_wait_minutes"]))
    c8.metric("Átlag túra hossz", format_minutes(row["avg_route_minutes"]))
    c9.metric("Átlag bepakolás", format_minutes(row["avg_loading_minutes"]))
    c10.metric(
        "Korai / késő cím",
        f"{int(row['early_address_count'])} / {int(row['late_address_count'])}",
    )


def filter_driver_rows(details, row):
    courier_id = normalize_id(row.get("courier_id", ""))
    name = str(row.get("name", "")).strip()
    result = {}

    orders = details.get("orders", pd.DataFrame())
    if not orders.empty and "courierId" in orders.columns:
        result["orders"] = orders[
            orders["courierId"].apply(normalize_id) == courier_id
        ].copy()
    else:
        result["orders"] = pd.DataFrame()

    attendance_routes = details.get("attendance_routes", pd.DataFrame())
    if not attendance_routes.empty and "courierId" in attendance_routes.columns:
        result["attendance_routes"] = attendance_routes[
            attendance_routes["courierId"].apply(normalize_id) == courier_id
        ].copy()
    else:
        result["attendance_routes"] = pd.DataFrame()

    giriton_login = details.get("giriton_login", pd.DataFrame())
    if not giriton_login.empty and "futar_nev" in giriton_login.columns:
        result["giriton_login"] = giriton_login[
            giriton_login["futar_nev"].astype(str).str.strip() == name
        ].copy()
    else:
        result["giriton_login"] = pd.DataFrame()

    customers = details.get("customers", pd.DataFrame())
    if not customers.empty and "courierId" in customers.columns:
        result["customers"] = customers[
            customers["courierId"].apply(normalize_id) == courier_id
        ].copy()
    else:
        result["customers"] = pd.DataFrame()

    return result


def show_driver_details(row, details):
    driver_details = filter_driver_rows(details, row)

    orders = driver_details["orders"]
    attendance_routes = driver_details["attendance_routes"]
    giriton_login = driver_details["giriton_login"]
    customers = driver_details["customers"]

    if not orders.empty:
        route_columns = [
            "date",
            "routeId",
            "warehouseName",
            "numDeliveredOrders",
            "numTotalOrders",
            "loadingTime",
            "realDeparture",
            "realReturn",
            "loading_minutes_calc",
            "real_tour_minutes_calc",
        ]
        visible = [
            column
            for column in route_columns
            if column in orders.columns
        ]

        route_table = orders[visible].rename(
            columns={
                "date": "Dátum",
                "routeId": "Route ID",
                "warehouseName": "Raktár",
                "numDeliveredOrders": "Kivitt cím",
                "numTotalOrders": "Össz. cím",
                "loadingTime": "Pakolás kezdete",
                "realDeparture": "Indulás",
                "realReturn": "Visszaérkezés",
                "loading_minutes_calc": "Bepakolás perc",
                "real_tour_minutes_calc": "Túra perc",
            }
        )
        st.dataframe(
            route_table,
            use_container_width=True,
            hide_index=True,
        )

    if not attendance_routes.empty:
        attendance_columns = [
            "date",
            "routeId",
            "shiftName",
            "availableForShiftSince",
            "courierRegisteredAt",
            "assignedAt",
            "wait_minutes",
            "departure_diff_minutes",
            "return_diff_minutes",
            "match_source",
        ]
        visible = [
            column
            for column in attendance_columns
            if column in attendance_routes.columns
        ]
        attendance_table = attendance_routes[visible].rename(
            columns={
                "date": "Dátum",
                "routeId": "Route ID",
                "shiftName": "Műszak",
                "availableForShiftSince": "Sorba állt",
                "courierRegisteredAt": "Regisztrált",
                "assignedAt": "Túrát kapott",
                "wait_minutes": "Várakozás perc",
                "departure_diff_minutes": "Indulás eltérés",
                "return_diff_minutes": "Vissza eltérés",
                "match_source": "Párosítás",
            }
        )
        st.caption("Várakozás és eltérések")
        st.dataframe(
            attendance_table,
            use_container_width=True,
            hide_index=True,
        )

    if not customers.empty:
        address_columns = [
            "date",
            "routeId",
            "orderId",
            "position",
            "address",
            "deliverSince",
            "deliverTill",
            "realArrivalTime",
            "arrival_status",
            "arrival_diff_minutes",
        ]
        visible = [
            column
            for column in address_columns
            if column in customers.columns
        ]
        address_table = customers[
            customers["arrival_status_normalized"].isin(["EARLY", "LATE"])
        ][visible].rename(
            columns={
                "date": "Dátum",
                "routeId": "Route ID",
                "orderId": "Rendelés",
                "position": "Poz",
                "address": "Cím",
                "deliverSince": "Időablak kezdete",
                "deliverTill": "Időablak vége",
                "realArrivalTime": "Valós érkezés",
                "arrival_status": "Státusz",
                "arrival_diff_minutes": "Eltérés perc",
            }
        )

        st.caption("Időablakon kívüli címek")
        st.dataframe(
            address_table,
            use_container_width=True,
            hide_index=True,
        )

    if not giriton_login.empty:
        login_columns = [
            "datum",
            "futar_nev",
            "planned_shift_count",
            "bejelentkezes_kezdete",
            "bejelentkezes_vege",
            "worked_hours",
            "attendance_statusz",
            "attendance_muszak",
            "shift_late_minutes",
        ]
        visible = [
            column
            for column in login_columns
            if column in giriton_login.columns
        ]
        login_table = giriton_login[visible].rename(
            columns={
                "datum": "Dátum",
                "futar_nev": "Futár",
                "planned_shift_count": "Tervezett műszak",
                "bejelentkezes_kezdete": "Bejelentkezés",
                "bejelentkezes_vege": "Kijelentkezés",
                "worked_hours": "Ledolgozott óra",
                "attendance_statusz": "Giriton státusz",
                "attendance_muszak": "Giriton műszak",
                "shift_late_minutes": "Műszak késés perc",
            }
        )
        st.caption("Giriton bejelentkezés")
        st.dataframe(
            login_table,
            use_container_width=True,
            hide_index=True,
        )


def show_statistics_page():
    st.title("DSP statisztika")

    user = st.session_state["user"]

    today = date.today()
    default_start = today.replace(day=1)

    left, right = st.columns(2)
    start_date = left.date_input(
        "Kezdő dátum",
        value=default_start,
    )
    end_date = right.date_input(
        "Záró dátum",
        value=today,
    )

    if start_date > end_date:
        st.error("A kezdő dátum nem lehet későbbi, mint a záró dátum.")
        return

    try:
        summary_df, details = build_statistics(
            start_date=start_date,
            end_date=end_date,
            user=user,
        )
    except Exception as exc:
        st.error(f"Nem sikerült beolvasni a DSP statisztikát: {exc}")
        return

    if summary_df.empty:
        st.warning("Még nincs megjeleníthető DSP statisztikai adat.")
        return

    if user["role"] == "admin":
        title = "Céges KPI"
    elif user["role"] == "trainer":
        title = "Csapat KPI"
    else:
        title = "Saját KPI"

    display_company_kpis(summary_df, title)

    st.divider()

    st.subheader("Futárok összesítve")
    st.dataframe(
        build_summary_table(summary_df),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Futár részletek")

    for _, row in summary_df.iterrows():
        label = (
            f"{row['name']} "
            f"#{row['courier_id']} | "
            f"{int(row['delivered_orders'])} cím | "
            f"{int(row['routes'])} kör"
        )

        with st.expander(label):
            show_driver_metrics(row)
            show_driver_details(row, details)
