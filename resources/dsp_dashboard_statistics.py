from datetime import datetime
import re

import pandas as pd

from resources.google_auth import get_client
from resources.users import load_users

SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"


def normalize_id(value):
    if value in [None, ""]:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def to_number(series):
    if series is None:
        return pd.Series(dtype=float)

    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0)


def parse_datetime_series(series):
    return pd.to_datetime(
        series,
        errors="coerce",
    )


def parse_time_value(value):
    text = str(value or "").strip()

    if not text:
        return None

    for fmt in ["%H:%M:%S", "%H:%M"]:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass

    return None


def time_to_minutes(value):
    parsed = parse_time_value(value)

    if not parsed:
        return None

    return parsed.hour * 60 + parsed.minute + parsed.second / 60


def shift_start_from_text(value):
    text = str(value or "")
    match = re.search(r"_(\d{1,2}:\d{2})", text)

    if not match:
        match = re.search(r"\b(\d{1,2}:\d{2})\b", text)

    if not match:
        return None

    return time_to_minutes(match.group(1))


def read_sheet_dataframe(sheet_name):
    try:
        worksheet = get_client().open_by_key(
            SPREADSHEET_ID
        ).worksheet(sheet_name)
        values = worksheet.get_all_values()

        if not values:
            return pd.DataFrame()

        header = values[0]
        records = []

        for row in values[1:]:
            records.append({
                column: row[index] if index < len(row) else ""
                for index, column in enumerate(header)
            })

        return pd.DataFrame(
            records
        )
    except Exception:
        return pd.DataFrame()


def load_source_data():
    return {
        "orders": read_sheet_dataframe("DSP_Orders"),
        "customers": read_sheet_dataframe("DSP_Order_Customers"),
        "drivers": read_sheet_dataframe("DSP_Drivers"),
        "attendance_routes": read_sheet_dataframe("DSP_Attendance_Route_Stats"),
        "giriton_login": read_sheet_dataframe("Futar_Bejelentkezes_Statisztika"),
        "route_statistics": read_sheet_dataframe("Route_Statistics"),
    }


def normalize_orders(df):
    if df.empty:
        return df

    df = df.copy()

    for column in ["courierId", "routeId", "id"]:
        if column in df.columns:
            df[column] = df[column].apply(normalize_id)
        else:
            df[column] = ""

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        df["date"] = pd.NaT

    for column in [
        "numDeliveredOrders",
        "numTotalOrders",
        "numDelayedOrdersSlot",
        "numDelayedOrdersPlan",
        "numDelayedOrdersEstimate",
        "waitForRouteMinutes",
        "waitForLoadingMinutes",
        "totalWaitMinutes",
        "departureDelayMinutes",
        "plannedTourMinutes",
        "realTourMinutes",
        "returnDelayMinutes",
    ]:
        if column not in df.columns:
            df[column] = 0

        df[column] = to_number(df[column])

    for column in [
        "loadingTime",
        "plannedDeparture",
        "realDeparture",
        "plannedReturn",
        "realReturn",
    ]:
        if column not in df.columns:
            df[column] = ""

        df[f"{column}_dt"] = parse_datetime_series(df[column])

    computed_tour = (
        df["realReturn_dt"] - df["realDeparture_dt"]
    ).dt.total_seconds() / 60
    computed_loading = (
        df["realDeparture_dt"] - df["loadingTime_dt"]
    ).dt.total_seconds() / 60

    df["real_tour_minutes_calc"] = df["realTourMinutes"]
    df.loc[df["real_tour_minutes_calc"] <= 0, "real_tour_minutes_calc"] = (
        computed_tour
    )
    df["real_tour_minutes_calc"] = df["real_tour_minutes_calc"].fillna(0)

    df["loading_minutes_calc"] = computed_loading.fillna(0)
    df.loc[df["loading_minutes_calc"] < 0, "loading_minutes_calc"] = 0

    return df


def normalize_attendance_routes(df):
    if df.empty:
        return df

    df = df.copy()

    for column in ["courierId", "routeId"]:
        if column in df.columns:
            df[column] = df[column].apply(normalize_id)
        else:
            df[column] = ""

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        df["date"] = pd.NaT

    for column in [
        "wait_minutes",
        "departure_diff_minutes",
        "return_diff_minutes",
        "real_route_minutes",
    ]:
        if column not in df.columns:
            df[column] = 0

        df[column] = to_number(df[column])

    return df


def normalize_customers(df):
    if df.empty:
        return df

    df = df.copy()

    for column in ["courierId", "routeId", "id", "orderId"]:
        if column in df.columns:
            df[column] = df[column].apply(normalize_id)
        else:
            df[column] = ""

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        df["date"] = pd.NaT

    if "arrival_status" not in df.columns:
        df["arrival_status"] = ""

    df["arrival_status_normalized"] = (
        df["arrival_status"].astype(str).str.strip().str.upper()
    )
    df["early_address_count"] = (
        df["arrival_status_normalized"] == "EARLY"
    ).astype(int)
    df["late_address_count"] = (
        df["arrival_status_normalized"] == "LATE"
    ).astype(int)

    if "arrival_diff_minutes" in df.columns:
        df["arrival_diff_minutes"] = to_number(
            df["arrival_diff_minutes"]
        )
    else:
        df["arrival_diff_minutes"] = 0

    return df


def normalize_giriton_login(df):
    if df.empty:
        return df

    df = df.copy()

    if "datum" in df.columns:
        df["date"] = pd.to_datetime(df["datum"], errors="coerce")
    else:
        df["date"] = pd.NaT

    if "tervezett_muszak_db_giriton" not in df.columns:
        df["tervezett_muszak_db_giriton"] = 0

    df["planned_shift_count"] = to_number(
        df["tervezett_muszak_db_giriton"]
    )
    df["checkin_minutes"] = df.get(
        "bejelentkezes_kezdete",
        "",
    ).apply(time_to_minutes)
    df["shift_start_minutes"] = df.get(
        "attendance_muszak",
        "",
    ).apply(shift_start_from_text)

    df["shift_late_minutes"] = (
        df["checkin_minutes"] - df["shift_start_minutes"]
    )
    df.loc[df["shift_late_minutes"] < 0, "shift_late_minutes"] = 0
    df["late_shift_count"] = (
        df["shift_late_minutes"].fillna(0) > 0
    ).astype(int)

    if "ledolgozott_ora" in df.columns:
        df["worked_hours"] = to_number(df["ledolgozott_ora"])
    else:
        df["worked_hours"] = 0

    return df


def build_driver_map(drivers, attendance_routes, route_statistics):
    driver_map = {}

    if not drivers.empty:
        for _, row in drivers.iterrows():
            driver_id = normalize_id(row.get("driver_id", ""))

            if not driver_id:
                continue

            driver_map[driver_id] = {
                "courier_id": driver_id,
                "name": str(row.get("name", "")).strip(),
                "warehouse": str(row.get("warehouse_name", "")).strip(),
            }

    if not attendance_routes.empty:
        for _, row in attendance_routes.iterrows():
            driver_id = normalize_id(row.get("courierId", ""))

            if not driver_id:
                continue

            driver_map.setdefault(
                driver_id,
                {
                    "courier_id": driver_id,
                    "name": "",
                    "warehouse": "",
                },
            )
            if row.get("courierName"):
                driver_map[driver_id]["name"] = str(
                    row.get("courierName", "")
                ).strip()
            if row.get("warehouseName"):
                driver_map[driver_id]["warehouse"] = str(
                    row.get("warehouseName", "")
                ).strip()

    if not route_statistics.empty:
        for _, row in route_statistics.iterrows():
            driver_id = normalize_id(row.get("driver_id", ""))

            if not driver_id:
                continue

            driver_map.setdefault(
                driver_id,
                {
                    "courier_id": driver_id,
                    "name": "",
                    "warehouse": "",
                },
            )
            if row.get("driver_name"):
                driver_map[driver_id]["name"] = str(
                    row.get("driver_name", "")
                ).strip()

    return driver_map


def filter_by_user(summary_df, user):
    if summary_df.empty or user.get("role") == "admin":
        return summary_df

    if user.get("role") == "trainer":
        users_data = load_users()
        trainer_ids = {
            normalize_id(portal_user.get("courierId"))
            for portal_user in users_data.get("users", [])
            if portal_user.get("trainer") == user.get("username")
        }

        return summary_df[
            summary_df["courier_id"].isin(trainer_ids)
        ].copy()

    courier_id = normalize_id(user.get("courierId"))
    return summary_df[
        summary_df["courier_id"] == courier_id
    ].copy()


def filter_detail_by_user(dataframes, allowed_ids):
    if not allowed_ids:
        return dataframes

    filtered = {}

    for name, df in dataframes.items():
        if df.empty:
            filtered[name] = df
            continue

        id_column = None
        for candidate in ["courierId", "driver_id", "courier_id"]:
            if candidate in df.columns:
                id_column = candidate
                break

        if not id_column:
            filtered[name] = df
            continue

        filtered[name] = df[
            df[id_column].apply(normalize_id).isin(allowed_ids)
        ].copy()

    return filtered


def build_statistics(start_date=None, end_date=None, user=None):
    source = load_source_data()
    orders = normalize_orders(source["orders"])
    customers = normalize_customers(source["customers"])
    attendance_routes = normalize_attendance_routes(
        source["attendance_routes"]
    )
    giriton_login = normalize_giriton_login(source["giriton_login"])
    drivers = source["drivers"]
    route_statistics = source["route_statistics"]

    if start_date is not None:
        start = pd.to_datetime(start_date)

        if not orders.empty:
            orders = orders[orders["date"] >= start]
        if not customers.empty:
            customers = customers[customers["date"] >= start]
        if not attendance_routes.empty:
            attendance_routes = attendance_routes[
                attendance_routes["date"] >= start
            ]
        if not giriton_login.empty:
            giriton_login = giriton_login[
                giriton_login["date"] >= start
            ]

    if end_date is not None:
        end = pd.to_datetime(end_date)

        if not orders.empty:
            orders = orders[orders["date"] <= end]
        if not customers.empty:
            customers = customers[customers["date"] <= end]
        if not attendance_routes.empty:
            attendance_routes = attendance_routes[
                attendance_routes["date"] <= end
            ]
        if not giriton_login.empty:
            giriton_login = giriton_login[
                giriton_login["date"] <= end
            ]

    driver_map = build_driver_map(
        drivers,
        attendance_routes,
        route_statistics,
    )

    summary = {}

    def ensure_driver(driver_id, name="", warehouse=""):
        driver_id = normalize_id(driver_id)
        base = driver_map.get(
            driver_id,
            {
                "courier_id": driver_id,
                "name": name,
                "warehouse": warehouse,
            },
        )

        key = driver_id or name

        if key not in summary:
            summary[key] = {
                "courier_id": driver_id,
                "name": base.get("name") or name,
                "warehouse": base.get("warehouse") or warehouse,
                "delivered_orders": 0,
                "total_orders": 0,
                "routes": 0,
                "worked_days": 0,
                "avg_orders_per_route": 0,
                "avg_routes_per_workday": 0,
                "avg_wait_minutes": 0,
                "late_shift_count": 0,
                "planned_shift_count": 0,
                "avg_route_minutes": 0,
                "avg_loading_minutes": 0,
                "_work_dates": set(),
                "_route_ids": set(),
                "_wait_values": [],
                "_route_minutes": [],
                "_loading_minutes": [],
                "early_address_count": 0,
                "late_address_count": 0,
            }

        return summary[key]

    if not orders.empty:
        for _, row in orders.iterrows():
            item = ensure_driver(
                row.get("courierId", ""),
                warehouse=str(row.get("warehouseName", "")).strip(),
            )
            route_id = normalize_id(row.get("routeId") or row.get("id"))

            if route_id:
                item["_route_ids"].add(route_id)

            if not pd.isna(row.get("date")):
                item["_work_dates"].add(
                    row.get("date").strftime("%Y-%m-%d")
                )

            item["delivered_orders"] += float(
                row.get("numDeliveredOrders", 0)
            )
            item["total_orders"] += float(
                row.get("numTotalOrders", 0)
            )

            if row.get("real_tour_minutes_calc", 0) > 0:
                item["_route_minutes"].append(
                    float(row.get("real_tour_minutes_calc", 0))
                )

            if row.get("loading_minutes_calc", 0) > 0:
                item["_loading_minutes"].append(
                    float(row.get("loading_minutes_calc", 0))
                )

    if not customers.empty:
        for _, row in customers.iterrows():
            item = ensure_driver(
                row.get("courierId", ""),
            )

            if not pd.isna(row.get("date")):
                item["_work_dates"].add(
                    row.get("date").strftime("%Y-%m-%d")
                )

            item["early_address_count"] += int(
                row.get("early_address_count", 0)
            )
            item["late_address_count"] += int(
                row.get("late_address_count", 0)
            )

    if not attendance_routes.empty:
        for _, row in attendance_routes.iterrows():
            item = ensure_driver(
                row.get("courierId", ""),
                name=str(row.get("courierName", "")).strip(),
                warehouse=str(row.get("warehouseName", "")).strip(),
            )
            route_id = normalize_id(row.get("routeId"))

            if route_id:
                item["_route_ids"].add(route_id)

            if not pd.isna(row.get("date")):
                item["_work_dates"].add(
                    row.get("date").strftime("%Y-%m-%d")
                )

            if row.get("wait_minutes", 0) >= 0:
                item["_wait_values"].append(
                    float(row.get("wait_minutes", 0))
                )

            if row.get("real_route_minutes", 0) > 0:
                item["_route_minutes"].append(
                    float(row.get("real_route_minutes", 0))
                )

    if not giriton_login.empty:
        name_to_id = {
            data.get("name", ""): driver_id
            for driver_id, data in driver_map.items()
            if data.get("name")
        }

        for _, row in giriton_login.iterrows():
            name = str(row.get("futar_nev", "")).strip()
            driver_id = name_to_id.get(name, "")
            item = ensure_driver(driver_id, name=name)
            item["planned_shift_count"] += float(
                row.get("planned_shift_count", 0)
            )
            item["late_shift_count"] += int(
                row.get("late_shift_count", 0)
            )

            if not pd.isna(row.get("date")):
                item["_work_dates"].add(
                    row.get("date").strftime("%Y-%m-%d")
                )

    rows = []

    for item in summary.values():
        routes = len(item["_route_ids"])
        worked_days = len(item["_work_dates"])
        delivered_orders = int(round(item["delivered_orders"]))
        total_orders = int(round(item["total_orders"]))

        rows.append({
            "courier_id": item["courier_id"],
            "name": item["name"] or item["courier_id"],
            "warehouse": item["warehouse"],
            "delivered_orders": delivered_orders,
            "total_orders": total_orders,
            "routes": routes,
            "worked_days": worked_days,
            "avg_orders_per_route": (
                delivered_orders / routes
                if routes
                else 0
            ),
            "avg_routes_per_workday": (
                routes / worked_days
                if worked_days
                else 0
            ),
            "avg_wait_minutes": (
                sum(item["_wait_values"]) / len(item["_wait_values"])
                if item["_wait_values"]
                else 0
            ),
            "late_shift_count": int(item["late_shift_count"]),
            "early_address_count": int(item["early_address_count"]),
            "late_address_count": int(item["late_address_count"]),
            "planned_shift_count": int(item["planned_shift_count"]),
            "avg_route_minutes": (
                sum(item["_route_minutes"]) / len(item["_route_minutes"])
                if item["_route_minutes"]
                else 0
            ),
            "avg_loading_minutes": (
                sum(item["_loading_minutes"]) / len(item["_loading_minutes"])
                if item["_loading_minutes"]
                else 0
            ),
        })

    summary_df = pd.DataFrame(rows)

    if summary_df.empty:
        return summary_df, {
            "orders": orders,
            "customers": customers,
            "attendance_routes": attendance_routes,
            "giriton_login": giriton_login,
        }

    summary_df = summary_df.sort_values(
        ["name", "courier_id"],
        ascending=[True, True],
    )

    if user:
        summary_df = filter_by_user(summary_df, user)
        allowed_ids = set(summary_df["courier_id"].dropna().astype(str))
        details = filter_detail_by_user(
            {
                "orders": orders,
                "customers": customers,
                "attendance_routes": attendance_routes,
                "giriton_login": giriton_login,
            },
            allowed_ids,
        )
    else:
        details = {
            "orders": orders,
            "customers": customers,
            "attendance_routes": attendance_routes,
            "giriton_login": giriton_login,
        }

    return summary_df, details


def build_company_kpis(summary_df):
    if summary_df.empty:
        return {
            "couriers": 0,
            "delivered_orders": 0,
            "routes": 0,
            "worked_days": 0,
            "avg_orders_per_route": 0,
            "avg_routes_per_workday": 0,
            "avg_wait_minutes": 0,
            "late_shift_count": 0,
            "early_address_count": 0,
            "late_address_count": 0,
            "avg_route_minutes": 0,
            "avg_loading_minutes": 0,
        }

    routes = summary_df["routes"].sum()
    delivered = summary_df["delivered_orders"].sum()
    worked_days = summary_df["worked_days"].sum()

    return {
        "couriers": int(summary_df["courier_id"].replace("", pd.NA).nunique()),
        "delivered_orders": int(delivered),
        "routes": int(routes),
        "worked_days": int(worked_days),
        "avg_orders_per_route": delivered / routes if routes else 0,
        "avg_routes_per_workday": routes / worked_days if worked_days else 0,
        "avg_wait_minutes": summary_df["avg_wait_minutes"].mean(),
        "late_shift_count": int(summary_df["late_shift_count"].sum()),
        "early_address_count": int(summary_df["early_address_count"].sum()),
        "late_address_count": int(summary_df["late_address_count"].sum()),
        "avg_route_minutes": summary_df["avg_route_minutes"].mean(),
        "avg_loading_minutes": summary_df["avg_loading_minutes"].mean(),
    }
