from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import gspread

from resources.dsp_dashboard_statistics import (
    SPREADSHEET_ID,
    build_statistics,
    normalize_id,
    read_sheet_dataframe,
)
from resources.google_auth import get_client


WORKSHEET_NAME = "Courier_Card_Snapshot"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "snapshot_month",
    "period_start",
    "period_end",
    "generated_at",
    "courier_id",
    "name",
    "warehouse",
    "delivered_orders",
    "total_orders",
    "routes",
    "worked_days",
    "avg_orders_per_route",
    "avg_routes_per_workday",
    "avg_wait_minutes",
    "late_shift_count",
    "planned_shift_count",
    "avg_route_minutes",
    "avg_loading_minutes",
    "avg_planned_loading_minutes",
    "avg_real_loading_minutes",
    "total_address_count",
    "early_address_count",
    "late_address_count",
    "early_address_rate",
    "late_address_rate",
    "normal_address_count",
    "express_address_count",
    "normal_address_rate",
    "express_address_rate",
    "normal_early_address_count",
    "normal_late_address_count",
    "express_early_address_count",
    "express_late_address_count",
    "normal_late_address_rate",
    "express_late_address_rate",
    "normal_routes",
    "express_routes",
    "estimated_max_revenue",
    "avg_revenue_per_route",
    "previous_month_revenue",
]


NUMERIC_COLUMNS = [
    column
    for column in HEADER
    if column
    not in [
        "snapshot_month",
        "period_start",
        "period_end",
        "generated_at",
        "courier_id",
        "name",
        "warehouse",
    ]
]


def month_bounds(month_text=None, today=None):
    today = today or date.today()

    if month_text:
        year_text, month_text = str(month_text).split("-")
        year = int(year_text)
        month = int(month_text)
    else:
        year = today.year
        month = today.month

    start = date(year, month, 1)
    end = date(
        year,
        month,
        monthrange(year, month)[1],
    )

    if start.year == today.year and start.month == today.month:
        end = today

    return start, end


def previous_month_bounds(month_start):
    previous_end = month_start - timedelta(days=1)
    return previous_end.replace(day=1), previous_end


def get_worksheet():
    spreadsheet = get_client().open_by_key(SPREADSHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(HEADER) + 5,
        )
        worksheet.update("A1", [HEADER])

    return worksheet


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def read_earnings():
    df = read_sheet_dataframe("DSP_Earning_Estimate")

    if df.empty:
        return df

    df = df.copy()

    if "courierId" in df.columns:
        df["courierId"] = df["courierId"].apply(normalize_id)
    else:
        df["courierId"] = ""

    if "date" in df.columns:
        df["date_dt"] = pd.to_datetime(
            df["date"],
            errors="coerce",
        ).dt.date
    else:
        df["date_dt"] = pd.NaT

    for column in [
        "normal_routes",
        "express_routes",
        "estimated_max_revenue",
        "total_routes",
    ]:
        if column not in df.columns:
            df[column] = 0

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    return df


def revenue_for_period(earnings, courier_id, start, end):
    if earnings.empty or not courier_id:
        return {
            "normal_routes": 0,
            "express_routes": 0,
            "estimated_max_revenue": 0,
            "avg_revenue_per_route": 0,
        }

    filtered = earnings[
        (earnings["courierId"].apply(normalize_id) == normalize_id(courier_id))
        & (earnings["date_dt"] >= start)
        & (earnings["date_dt"] <= end)
    ]

    if filtered.empty:
        return {
            "normal_routes": 0,
            "express_routes": 0,
            "estimated_max_revenue": 0,
            "avg_revenue_per_route": 0,
        }

    normal_routes = int(filtered["normal_routes"].sum())
    express_routes = int(filtered["express_routes"].sum())
    total_routes = int(filtered["total_routes"].sum())
    estimated_max_revenue = float(filtered["estimated_max_revenue"].sum())

    return {
        "normal_routes": normal_routes,
        "express_routes": express_routes,
        "estimated_max_revenue": estimated_max_revenue,
        "avg_revenue_per_route": (
            estimated_max_revenue / total_routes
            if total_routes
            else 0
        ),
    }


def build_snapshot_records(month_text=None):
    today = datetime.now(LOCAL_TIMEZONE).date()
    period_start, period_end = month_bounds(month_text, today)
    previous_start, previous_end = previous_month_bounds(period_start)
    snapshot_month = period_start.strftime("%Y-%m")
    generated_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    summary_df, _details = build_statistics(
        start_date=period_start,
        end_date=period_end,
        user=None,
    )
    earnings = read_earnings()
    records = []

    if summary_df.empty:
        return records

    for _, row in summary_df.iterrows():
        courier_id = normalize_id(row.get("courier_id"))
        revenue = revenue_for_period(
            earnings,
            courier_id,
            period_start,
            period_end,
        )
        previous_revenue = revenue_for_period(
            earnings,
            courier_id,
            previous_start,
            previous_end,
        )
        record = {
            "snapshot_month": snapshot_month,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "generated_at": generated_at,
            "courier_id": courier_id,
            "name": row.get("name", ""),
            "warehouse": row.get("warehouse", ""),
            "normal_routes": revenue["normal_routes"],
            "express_routes": revenue["express_routes"],
            "estimated_max_revenue": revenue["estimated_max_revenue"],
            "avg_revenue_per_route": revenue["avg_revenue_per_route"],
            "previous_month_revenue": previous_revenue["estimated_max_revenue"],
        }

        for column in HEADER:
            if column not in record:
                record[column] = row.get(column, 0)

        records.append(record)

    return records


def records_to_rows(records):
    rows = [HEADER]

    for record in records:
        rows.append([
            record.get(column, "")
            for column in HEADER
        ])

    return rows


def write_snapshot(month_text=None):
    records = build_snapshot_records(month_text)
    worksheet = get_worksheet()
    snapshot_month = (
        records[0].get("snapshot_month")
        if records
        else month_bounds(month_text)[0].strftime("%Y-%m")
    )
    existing_values = worksheet.get_all_values()
    preserved_records = []

    if existing_values:
        header = existing_values[0]

        for row in existing_values[1:]:
            record = {
                column: row[index] if index < len(row) else ""
                for index, column in enumerate(header)
            }

            if record.get("snapshot_month") != snapshot_month:
                preserved_records.append(record)

    worksheet.update(
        "A1",
        records_to_rows(preserved_records + records),
    )
    return {
        "rows": len(records),
        "worksheet": WORKSHEET_NAME,
    }


def read_snapshot(month_text):
    try:
        worksheet = get_worksheet()
        values = worksheet.get_all_values()
    except Exception:
        return pd.DataFrame()

    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = []

    for row in values[1:]:
        rows.append({
            column: row[index] if index < len(row) else ""
            for index, column in enumerate(header)
        })

    df = pd.DataFrame(rows)

    if df.empty or "snapshot_month" not in df.columns:
        return pd.DataFrame()

    df = df[df["snapshot_month"].astype(str) == str(month_text)].copy()

    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            ).fillna(0)

    return df
