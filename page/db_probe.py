from datetime import date

import pandas as pd
import streamlit as st

from resources.supabase_raw import read_driver_detail_raw
from resources.supabase_raw import read_vehicle_assignments
from resources.db_driver_statistics import build_db_statistics
from resources.db_driver_statistics import build_db_company_kpis


def parse_raw_rows(raw_rows):
    route_rows = []
    checkpoint_rows = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        driver_id = raw.get("driver_id") or response_json.get("courier-id")
        work_date = raw.get("work_date")
        warehouse = response_json.get("warehouseName", "")

        for route in response_json.get("routes", []) or []:
            route_id = route.get("id")
            checkpoints = route.get("checkpoints", []) or []

            route_rows.append({
                "work_date": work_date,
                "driver_id": driver_id,
                "warehouse": warehouse,
                "route_id": route_id,
                "assigned_at": route.get("assignedAt"),
                "planned_departure": route.get("plannedDeparture"),
                "real_departure": route.get("realDeparture"),
                "planned_return": route.get("plannedReturn"),
                "real_return": route.get("realReturn"),
                "total_orders": route.get("numTotalOrders", len(checkpoints)),
                "delivered_orders": route.get("numDeliveredOrders"),
                "checkpoint_count": len(checkpoints),
            })

            for checkpoint in checkpoints:
                checkpoint_rows.append({
                    "work_date": work_date,
                    "driver_id": driver_id,
                    "warehouse": warehouse,
                    "route_id": route_id,
                    "checkpoint_id": checkpoint.get("id"),
                    "order_id": checkpoint.get("orderId"),
                    "position": checkpoint.get("position"),
                    "address": checkpoint.get("address"),
                    "deliver_since": checkpoint.get("deliverSince"),
                    "deliver_till": checkpoint.get("deliverTill"),
                    "planned_arrival": checkpoint.get("plannedArrivalTime"),
                    "estimated_arrival": checkpoint.get("estimatedArrivalTime"),
                    "real_arrival": checkpoint.get("realArrivalTime"),
                })

    return (
        pd.DataFrame(route_rows),
        pd.DataFrame(checkpoint_rows),
    )


def to_date_series(series):
    return pd.to_datetime(
        series,
        errors="coerce",
    ).dt.date


def show_db_probe_page():
    st.title("DB proba")
    st.caption(
        "Forras: Supabase dsp_driver_detail_raw. Ez meg csak raw DB ellenorzo oldal."
    )

    try:
        raw_rows = read_driver_detail_raw(
            limit=200,
        )
    except Exception as exc:
        st.error(
            f"Supabase olvasasi hiba: {exc}"
        )
        st.info(
            "Ellenorizd a SUPABASE_URL es SUPABASE_SERVICE_ROLE_KEY beallitasokat."
        )
        return

    if not raw_rows:
        st.warning(
            "A dsp_driver_detail_raw tabla ures."
        )
        return

    raw_df = pd.DataFrame(raw_rows)
    route_df, checkpoint_df = parse_raw_rows(
        raw_rows
    )

    if "work_date" in raw_df.columns:
        raw_df["work_date_date"] = to_date_series(
            raw_df["work_date"]
        )
    else:
        raw_df["work_date_date"] = pd.NaT

    available_dates = sorted(
        value
        for value in raw_df["work_date_date"].dropna().unique()
        if isinstance(value, date)
    )

    if available_dates:
        col1, col2 = st.columns(2)
        start_date = col1.date_input(
            "Kezdo datum",
            value=available_dates[0],
            min_value=available_dates[0],
            max_value=available_dates[-1],
        )
        end_date = col2.date_input(
            "Zaro datum",
            value=available_dates[-1],
            min_value=available_dates[0],
            max_value=available_dates[-1],
        )

        raw_df = raw_df[
            (raw_df["work_date_date"] >= start_date)
            & (raw_df["work_date_date"] <= end_date)
        ]
        route_df = route_df[
            pd.to_datetime(route_df["work_date"], errors="coerce").dt.date.between(
                start_date,
                end_date,
            )
        ] if not route_df.empty else route_df
        checkpoint_df = checkpoint_df[
            pd.to_datetime(checkpoint_df["work_date"], errors="coerce").dt.date.between(
                start_date,
                end_date,
            )
        ] if not checkpoint_df.empty else checkpoint_df
    else:
        start_date = None
        end_date = None

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric(
        "Raw sor",
        len(raw_df),
    )
    metric2.metric(
        "Futar",
        raw_df["driver_id"].nunique() if "driver_id" in raw_df.columns else 0,
    )
    metric3.metric(
        "Route",
        route_df["route_id"].nunique() if not route_df.empty else 0,
    )
    metric4.metric(
        "Megrendeles/checkpoint",
        checkpoint_df["order_id"].nunique() if not checkpoint_df.empty else 0,
    )

    st.subheader("DB alapu statisztika")

    try:
        summary_df, _details = build_db_statistics(
            start_date=start_date,
            end_date=end_date,
            user=None,
        )
    except Exception as exc:
        st.warning(
            f"DB statisztika szamolasi hiba: {exc}"
        )
        summary_df = pd.DataFrame()

    if summary_df.empty:
        st.info(
            "Nincs DB alapu statisztika a kivalasztott idoszakra."
        )
    else:
        kpis = build_db_company_kpis(
            summary_df
        )
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Futar", kpis.get("couriers", 0))
        k2.metric("Kivitt cim", kpis.get("delivered_orders", 0))
        k3.metric("Kor", kpis.get("routes", 0))
        k4.metric(
            "Atlag cim/kor",
            f"{kpis.get('avg_orders_per_route', 0):.1f}",
        )
        k5.metric(
            "Kesoi cim %",
            f"{kpis.get('late_address_rate', 0):.1f}%",
        )

        visible_summary = summary_df[[
            "courier_id",
            "name",
            "warehouse",
            "delivered_orders",
            "routes",
            "worked_days",
            "avg_orders_per_route",
            "avg_wait_minutes",
            "avg_route_minutes",
            "avg_real_loading_minutes",
            "late_address_rate",
            "normal_routes",
            "express_routes",
            "estimated_max_revenue",
        ]].copy()
        st.dataframe(
            visible_summary,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Route-ok")

    if route_df.empty:
        st.info(
            "Nincs route adat a kivalasztott idoszakban."
        )
    else:
        st.dataframe(
            route_df.sort_values(
                ["work_date", "driver_id", "route_id"],
                ascending=True,
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Megrendeles / checkpoint minta")

    if checkpoint_df.empty:
        st.info(
            "Nincs checkpoint adat a kivalasztott idoszakban."
        )
    else:
        st.dataframe(
            checkpoint_df.sort_values(
                ["work_date", "driver_id", "route_id", "position"],
                ascending=True,
            ).head(300),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Autobeosztas")

    try:
        vehicle_rows = read_vehicle_assignments()
    except Exception as exc:
        st.warning(
            f"Vehicle assignments DB olvasasi hiba: {exc}"
        )
        st.caption(
            "Ha meg nincs tabla, futtasd a docs/supabase_phase1_vehicle_assignments.sql fajlt, majd a scripts/load_vehicle_assignments.py feltoltot."
        )
        return

    if not vehicle_rows:
        st.info(
            "Meg nincs autobeosztas adat a dsp_vehicle_assignments tablaban."
        )
        return

    vehicle_df = pd.DataFrame(
        vehicle_rows
    )
    driver_names = sorted(
        name
        for name in vehicle_df["driver_name"].dropna().unique()
        if str(name).strip()
    )

    selected_driver_name = st.selectbox(
        "Melyik futar autobeosztasat nezzuk?",
        options=driver_names,
    )
    selected_vehicle_df = vehicle_df[
        vehicle_df["driver_name"] == selected_driver_name
    ].copy()

    st.dataframe(
        selected_vehicle_df.sort_values(
            ["work_date", "shift_start"],
            ascending=True,
        ),
        use_container_width=True,
        hide_index=True,
    )
