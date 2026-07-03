from datetime import date

import pandas as pd

from resources.supabase_raw import read_driver_detail_raw
from resources.users import load_users


EXPRESS_MAX_FEE = 6516
NORMAL_CITY_MAX_FEE = 13000


def normalize_id(value):
    if value in [None, ""]:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        return text[:-2]

    return text


def parse_datetime(value):
    return pd.to_datetime(
        value,
        errors="coerce",
        utc=True,
    )


def minutes_between(end_value, start_value):
    end = parse_datetime(end_value)
    start = parse_datetime(start_value)

    if pd.isna(end) or pd.isna(start):
        return 0

    minutes = (end - start).total_seconds() / 60
    return max(minutes, 0)


def is_normal_window(deliver_since, deliver_till):
    since = parse_datetime(deliver_since)
    till = parse_datetime(deliver_till)

    if pd.isna(since) or pd.isna(till):
        return True

    minutes = (till - since).total_seconds() / 60
    return round(minutes) in [15, 60]


def build_db_source_frames(raw_rows):
    route_rows = []
    checkpoint_rows = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        driver_id = normalize_id(
            raw.get("driver_id") or response_json.get("courier-id")
        )
        work_date = raw.get("work_date")
        warehouse = response_json.get("warehouseName", "")

        for route in response_json.get("routes", []) or []:
            route_id = normalize_id(
                route.get("id")
            )
            checkpoints = route.get("checkpoints", []) or []
            wait_minutes = minutes_between(
                route.get("assignedAt"),
                route.get("courierRegisteredAt"),
            )
            route_minutes = minutes_between(
                route.get("realReturn"),
                route.get("realDeparture"),
            )
            planned_loading_minutes = minutes_between(
                route.get("loadingTime"),
                route.get("assignedAt"),
            )
            real_loading_minutes = minutes_between(
                route.get("realDeparture"),
                route.get("assignedAt"),
            )

            route_rows.append({
                "date": pd.to_datetime(work_date, errors="coerce"),
                "work_date": work_date,
                "courier_id": driver_id,
                "name": driver_id,
                "warehouse": warehouse,
                "routeId": route_id,
                "route_id": route_id,
                "assignedAt": route.get("assignedAt"),
                "loadingTime": route.get("loadingTime"),
                "plannedDeparture": route.get("plannedDeparture"),
                "realDeparture": route.get("realDeparture"),
                "plannedReturn": route.get("plannedReturn"),
                "realReturn": route.get("realReturn"),
                "numTotalOrders": route.get("numTotalOrders", len(checkpoints)),
                "numDeliveredOrders": route.get("numDeliveredOrders", 0),
                "wait_minutes": wait_minutes,
                "real_route_minutes": route_minutes,
                "avg_route_minutes": route_minutes,
                "planned_loading_minutes": planned_loading_minutes,
                "real_loading_minutes": real_loading_minutes,
            })

            for checkpoint in checkpoints:
                real_arrival = parse_datetime(
                    checkpoint.get("realArrivalTime")
                )
                deliver_since = parse_datetime(
                    checkpoint.get("deliverSince")
                )
                deliver_till = parse_datetime(
                    checkpoint.get("deliverTill")
                )
                is_early = (
                    not pd.isna(real_arrival)
                    and not pd.isna(deliver_since)
                    and real_arrival < deliver_since
                )
                is_late = (
                    not pd.isna(real_arrival)
                    and not pd.isna(deliver_till)
                    and real_arrival > deliver_till
                )
                is_normal = is_normal_window(
                    checkpoint.get("deliverSince"),
                    checkpoint.get("deliverTill"),
                )

                checkpoint_rows.append({
                    "date": pd.to_datetime(work_date, errors="coerce"),
                    "work_date": work_date,
                    "courierId": driver_id,
                    "courier_id": driver_id,
                    "warehouse": warehouse,
                    "routeId": route_id,
                    "route_id": route_id,
                    "id": normalize_id(checkpoint.get("id")),
                    "orderId": normalize_id(checkpoint.get("orderId")),
                    "position": checkpoint.get("position"),
                    "address": checkpoint.get("address", ""),
                    "deliverSince": checkpoint.get("deliverSince"),
                    "deliverTill": checkpoint.get("deliverTill"),
                    "plannedArrivalTime": checkpoint.get("plannedArrivalTime"),
                    "estimatedArrivalTime": checkpoint.get("estimatedArrivalTime"),
                    "realArrivalTime": checkpoint.get("realArrivalTime"),
                    "arrival_status": (
                        "EARLY"
                        if is_early
                        else "LATE"
                        if is_late
                        else "OK"
                    ),
                    "early_address_count": int(is_early),
                    "late_address_count": int(is_late),
                    "normal_address_count": int(is_normal),
                    "express_address_count": int(not is_normal),
                    "normal_late_address_count": int(is_normal and is_late),
                    "express_late_address_count": int((not is_normal) and is_late),
                })

    return (
        pd.DataFrame(route_rows),
        pd.DataFrame(checkpoint_rows),
    )


def filter_period(df, start_date=None, end_date=None):
    if df.empty or "date" not in df.columns:
        return df

    result = df.copy()

    if start_date:
        result = result[
            result["date"].dt.date >= start_date
        ]

    if end_date:
        result = result[
            result["date"].dt.date <= end_date
        ]

    return result


def build_summary(route_df, checkpoint_df):
    if route_df.empty:
        return pd.DataFrame()

    users_data = load_users()
    name_by_id = {
        normalize_id(user.get("courierId")): user.get("username", "")
        for user in users_data.get("users", [])
        if user.get("courierId") not in [None, ""]
    }
    summary = {}

    for courier_id, routes in route_df.groupby("courier_id"):
        checkpoints = (
            checkpoint_df[checkpoint_df["courier_id"] == courier_id]
            if not checkpoint_df.empty
            else pd.DataFrame()
        )
        route_count = routes["route_id"].replace("", pd.NA).nunique()
        delivered_orders = pd.to_numeric(
            routes["numDeliveredOrders"],
            errors="coerce",
        ).fillna(0).sum()
        total_orders = pd.to_numeric(
            routes["numTotalOrders"],
            errors="coerce",
        ).fillna(0).sum()
        worked_days = routes["date"].dt.date.nunique()

        if checkpoints.empty:
            total_addresses = 0
            early_addresses = 0
            late_addresses = 0
            normal_addresses = 0
            express_addresses = 0
            normal_late_addresses = 0
            express_late_addresses = 0
            express_routes = 0
        else:
            total_addresses = len(checkpoints)
            early_addresses = int(checkpoints["early_address_count"].sum())
            late_addresses = int(checkpoints["late_address_count"].sum())
            normal_addresses = int(checkpoints["normal_address_count"].sum())
            express_addresses = int(checkpoints["express_address_count"].sum())
            normal_late_addresses = int(
                checkpoints["normal_late_address_count"].sum()
            )
            express_late_addresses = int(
                checkpoints["express_late_address_count"].sum()
            )
            express_route_ids = checkpoints[
                checkpoints["express_address_count"] > 0
            ]["route_id"].replace("", pd.NA).dropna().unique()
            express_routes = len(express_route_ids)

        normal_routes = max(
            int(route_count) - int(express_routes),
            0,
        )
        estimated_max_revenue = (
            normal_routes * NORMAL_CITY_MAX_FEE
            + express_routes * EXPRESS_MAX_FEE
        )

        summary[courier_id] = {
            "courier_id": courier_id,
            "name": name_by_id.get(courier_id) or courier_id,
            "warehouse": routes["warehouse"].dropna().iloc[-1]
            if not routes["warehouse"].dropna().empty
            else "",
            "delivered_orders": int(delivered_orders),
            "total_orders": int(total_orders),
            "routes": int(route_count),
            "worked_days": int(worked_days),
            "avg_orders_per_route": (
                delivered_orders / route_count
                if route_count
                else 0
            ),
            "avg_routes_per_workday": (
                route_count / worked_days
                if worked_days
                else 0
            ),
            "avg_wait_minutes": routes["wait_minutes"].mean(),
            "late_shift_count": 0,
            "planned_shift_count": 0,
            "avg_route_minutes": routes["real_route_minutes"].mean(),
            "avg_loading_minutes": routes["real_loading_minutes"].mean(),
            "avg_planned_loading_minutes": routes[
                "planned_loading_minutes"
            ].mean(),
            "avg_real_loading_minutes": routes["real_loading_minutes"].mean(),
            "total_address_count": int(total_addresses),
            "early_address_count": int(early_addresses),
            "late_address_count": int(late_addresses),
            "early_address_rate": (
                early_addresses / total_addresses * 100
                if total_addresses
                else 0
            ),
            "late_address_rate": (
                late_addresses / total_addresses * 100
                if total_addresses
                else 0
            ),
            "normal_address_count": int(normal_addresses),
            "express_address_count": int(express_addresses),
            "normal_address_rate": (
                normal_addresses / total_addresses * 100
                if total_addresses
                else 0
            ),
            "express_address_rate": (
                express_addresses / total_addresses * 100
                if total_addresses
                else 0
            ),
            "normal_early_address_count": 0,
            "normal_late_address_count": int(normal_late_addresses),
            "express_early_address_count": 0,
            "express_late_address_count": int(express_late_addresses),
            "normal_late_address_rate": (
                normal_late_addresses / normal_addresses * 100
                if normal_addresses
                else 0
            ),
            "express_late_address_rate": (
                express_late_addresses / express_addresses * 100
                if express_addresses
                else 0
            ),
            "normal_routes": int(normal_routes),
            "express_routes": int(express_routes),
            "estimated_max_revenue": float(estimated_max_revenue),
            "avg_revenue_per_route": (
                estimated_max_revenue / route_count
                if route_count
                else 0
            ),
            "previous_month_revenue": 0,
        }

    return pd.DataFrame(
        summary.values()
    ).sort_values(
        ["name", "courier_id"],
        ascending=True,
    )


def build_db_statistics(start_date=None, end_date=None, user=None):
    raw_rows = read_driver_detail_raw(
        start_date=start_date,
        end_date=end_date,
    )
    route_df, checkpoint_df = build_db_source_frames(
        raw_rows
    )
    route_df = filter_period(
        route_df,
        start_date=start_date,
        end_date=end_date,
    )
    checkpoint_df = filter_period(
        checkpoint_df,
        start_date=start_date,
        end_date=end_date,
    )
    summary_df = build_summary(
        route_df,
        checkpoint_df,
    )

    if user and user.get("role") == "user" and not summary_df.empty:
        courier_id = normalize_id(
            user.get("courierId")
        )
        summary_df = summary_df[
            summary_df["courier_id"].apply(normalize_id) == courier_id
        ].copy()
        route_df = route_df[
            route_df["courier_id"].apply(normalize_id) == courier_id
        ].copy()
        checkpoint_df = checkpoint_df[
            checkpoint_df["courier_id"].apply(normalize_id) == courier_id
        ].copy()

    return summary_df, {
        "orders": route_df,
        "customers": checkpoint_df,
        "attendance_routes": route_df,
        "giriton_login": pd.DataFrame(),
        "db_raw": True,
    }


def build_db_company_kpis(summary_df):
    if summary_df.empty:
        return {}

    routes = summary_df["routes"].sum()
    delivered = summary_df["delivered_orders"].sum()
    worked_days = summary_df["worked_days"].sum()
    total_addresses = summary_df["total_address_count"].sum()
    early_addresses = summary_df["early_address_count"].sum()
    late_addresses = summary_df["late_address_count"].sum()
    normal_addresses = summary_df["normal_address_count"].sum()
    express_addresses = summary_df["express_address_count"].sum()

    return {
        "couriers": int(summary_df["courier_id"].nunique()),
        "delivered_orders": int(delivered),
        "routes": int(routes),
        "worked_days": int(worked_days),
        "avg_orders_per_route": delivered / routes if routes else 0,
        "avg_routes_per_workday": routes / worked_days if worked_days else 0,
        "avg_wait_minutes": summary_df["avg_wait_minutes"].mean(),
        "avg_route_minutes": summary_df["avg_route_minutes"].mean(),
        "avg_real_loading_minutes": summary_df[
            "avg_real_loading_minutes"
        ].mean(),
        "total_address_count": int(total_addresses),
        "early_address_count": int(early_addresses),
        "late_address_count": int(late_addresses),
        "early_address_rate": (
            early_addresses / total_addresses * 100
            if total_addresses
            else 0
        ),
        "late_address_rate": (
            late_addresses / total_addresses * 100
            if total_addresses
            else 0
        ),
        "normal_address_count": int(normal_addresses),
        "express_address_count": int(express_addresses),
        "normal_address_rate": (
            normal_addresses / total_addresses * 100
            if total_addresses
            else 0
        ),
        "express_address_rate": (
            express_addresses / total_addresses * 100
            if total_addresses
            else 0
        ),
    }
