import argparse
import calendar
import os
from datetime import date, datetime, timedelta

import requests
import pandas as pd

from resources.db_driver_statistics import build_db_statistics


NUMERIC_COLUMNS = [
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


def get_required_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value.rstrip("/")


def month_bounds(month_text):
    year_text, month_text = month_text.split("-")
    year = int(year_text)
    month = int(month_text)
    start = date(year, month, 1)
    end = date(
        year,
        month,
        calendar.monthrange(year, month)[1],
    )
    today = date.today()

    if start.year == today.year and start.month == today.month:
        end = today

    return start, end


def previous_month_bounds(month_start):
    previous_end = month_start - timedelta(days=1)
    return previous_end.replace(day=1), previous_end


def build_previous_revenue_map(previous_start, previous_end):
    previous_summary, _details = build_db_statistics(
        start_date=previous_start,
        end_date=previous_end,
        user=None,
    )

    if previous_summary.empty:
        return {}

    return {
        str(row.get("courier_id", "")).strip(): float(
            row.get("estimated_max_revenue", 0) or 0
        )
        for _, row in previous_summary.iterrows()
    }


def to_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0

    if pd.isna(result):
        return 0

    return result


def to_text(value):
    if value is None or pd.isna(value):
        return ""

    return str(value)


def build_rows(month_text):
    period_start, period_end = month_bounds(
        month_text
    )
    previous_start, previous_end = previous_month_bounds(
        period_start
    )
    previous_revenue = build_previous_revenue_map(
        previous_start,
        previous_end,
    )
    summary_df, _details = build_db_statistics(
        start_date=period_start,
        end_date=period_end,
        user=None,
    )
    generated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    rows = []

    for _, item in summary_df.iterrows():
        courier_id = str(
            item.get("courier_id", "") or ""
        ).strip()

        if not courier_id:
            continue

        row = {
            "snapshot_month": month_text,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "generated_at": generated_at,
            "courier_id": courier_id,
            "name": to_text(item.get("name", "")),
            "warehouse": to_text(item.get("warehouse", "")),
            "source_name": "courier-card-db",
        }

        for column in NUMERIC_COLUMNS:
            row[column] = to_float(
                item.get(column, 0)
            )

        row["previous_month_revenue"] = previous_revenue.get(
            courier_id,
            0,
        )
        rows.append(row)

    return rows


def upsert_rows(rows):
    if not rows:
        return

    supabase_url = get_required_env("SUPABASE_URL")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/courier_card_stats"
        "?on_conflict=snapshot_month,courier_id"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=60,
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Courier card havi statisztika feltoltes DB-be."
    )
    parser.add_argument(
        "--month",
        required=True,
        help="Honap YYYY-MM formatumban, pelda: 2026-07",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak szamol, DB-be nem ir.",
    )
    args = parser.parse_args()
    rows = build_rows(
        args.month
    )

    print(
        f"Courier card stat sorok: {len(rows)}"
    )

    for row in rows[:5]:
        print(
            f"MINTA {row['snapshot_month']} {row['courier_id']} {row['name']} "
            f"{row['routes']} kor {row['delivered_orders']} cim"
        )

    if args.dry_run:
        print(
            "DRY RUN, DB iras kihagyva."
        )
        return

    upsert_rows(
        rows
    )
    print(
        f"DB feltoltes: {len(rows)} sor"
    )


if __name__ == "__main__":
    main()
