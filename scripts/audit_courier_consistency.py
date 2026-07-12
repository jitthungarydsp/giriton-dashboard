import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

try:
    from scripts.dsp_incremental_common import (
        DEFAULT_BACKFILL_START_DATE,
        get_supabase_config,
        raise_for_supabase_error,
        supabase_headers,
    )
except ModuleNotFoundError:
    from dsp_incremental_common import (
        DEFAULT_BACKFILL_START_DATE,
        get_supabase_config,
        raise_for_supabase_error,
        supabase_headers,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TABLE_GROUPS = [
    {
        "name": "driver_detail_raw",
        "candidates": ["raw_dsp_driver_detail", "dsp_driver_detail_raw"],
        "filter_column": "driver_id",
        "metric": "driver_detail_routes",
    },
    {
        "name": "attendance_shifts_stage",
        "candidates": ["stg_dsp_attendance_shifts", "dsp_attendance_shifts"],
        "filter_column": "courier_id",
        "metric": "stage_shift_rows",
    },
    {
        "name": "attendance_routes_stage",
        "candidates": ["stg_dsp_attendance_routes", "dsp_attendance_routes"],
        "filter_column": "courier_id",
        "metric": "stage_route_rows",
    },
    {
        "name": "shift_route_summary_stage",
        "candidates": ["stg_dsp_shift_route_summary", "dsp_shift_route_summary"],
        "filter_column": "courier_id",
        "metric": "stage_summary_rows",
    },
    {
        "name": "order_arrivals_stage",
        "candidates": ["stg_dsp_order_arrivals", "dsp_order_arrivals"],
        "filter_column": "driver_id",
        "metric": "arrival_rows",
    },
    {
        "name": "route_distance_stage",
        "candidates": ["stg_dsp_route_distance", "dsp_route_distance_calculated"],
        "filter_column": "driver_id",
        "metric": "distance_rows",
    },
    {
        "name": "route_stories_mart",
        "candidates": ["mart_dsp_route_stories"],
        "filter_column": "courier_id",
        "metric": "route_story_rows",
    },
    {
        "name": "muszakpro_bookings_raw",
        "candidates": ["raw_muszakpro_bookings", "foglalasok_raw"],
        "filter_column": "courier_id",
        "metric": "muszakpro_booking_rows",
    },
    {
        "name": "giriton_shifts_raw",
        "candidates": ["raw_giriton_shifts", "giriton_shifts_raw"],
        "filter_column": "courier_id",
        "metric": "giriton_shift_rows",
    },
]

NAME_TABLE_GROUPS = [
    {
        "name": "giriton_attendance_raw",
        "candidates": ["raw_giriton_attendance", "giriton_attendance_raw"],
        "filter_column": "courier_name",
        "metric": "giriton_attendance_rows",
    },
]

SUMMARY_COLUMNS = [
    "work_date",
    "attendance_shift_count",
    "attendance_shift_names",
    "attendance_route_count",
    "attendance_route_ids",
    "driver_detail_routes",
    "driver_detail_route_ids",
    "stage_shift_rows",
    "stage_route_rows",
    "stage_summary_rows",
    "route_story_rows",
    "arrival_rows",
    "arrival_route_ids",
    "distance_rows",
    "muszakpro_booking_rows",
    "muszakpro_shifts",
    "giriton_shift_rows",
    "giriton_shifts",
    "giriton_attendance_rows",
    "issues",
]


def parse_date(value):
    if isinstance(value, date):
        return value

    if not value:
        return None

    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


def today():
    return date.today()


def is_missing_table_or_column(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()

    return (
        "could not find the table" in text
        or "could not find the" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst204" in text
        or "pgrst205" in text
    )


def read_table_rows(
    supabase_url,
    service_role_key,
    table_name,
    start_date,
    end_date,
    filter_column=None,
    filter_value=None,
    page_size=1000,
):
    rows = []
    offset = 0
    headers = supabase_headers({"Accept": "application/json"})

    while True:
        filters = [
            "select=*",
            f"work_date=gte.{start_date.isoformat()}",
            f"work_date=lte.{end_date.isoformat()}",
            "order=work_date.asc",
            f"limit={page_size}",
            f"offset={offset}",
        ]

        if filter_column and filter_value not in (None, ""):
            filters.append(f"{filter_column}=eq.{filter_value}")

        endpoint = f"{supabase_url}/rest/v1/{table_name}?" + "&".join(filters)
        response = requests.get(endpoint, headers=headers, timeout=60)

        if is_missing_table_or_column(response):
            return None

        raise_for_supabase_error(response, table_name)
        page = response.json()
        rows.extend(page)

        if len(page) < page_size:
            return rows

        offset += page_size


def read_first_existing_group(
    supabase_url,
    service_role_key,
    candidates,
    start_date,
    end_date,
    filter_column=None,
    filter_value=None,
):
    for table_name in candidates:
        rows = read_table_rows(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            table_name=table_name,
            start_date=start_date,
            end_date=end_date,
            filter_column=filter_column,
            filter_value=filter_value,
        )

        if rows is not None:
            return table_name, rows

    return None, []


def read_courier_name(supabase_url, service_role_key, courier_id):
    for table_name in ["core_couriers", "courier_master"]:
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            f"?select=courier_id,name&courier_id=eq.{courier_id}&limit=1"
        )
        response = requests.get(
            endpoint,
            headers=supabase_headers({"Accept": "application/json"}),
            timeout=30,
        )

        if is_missing_table_or_column(response):
            continue

        raise_for_supabase_error(response, table_name)
        rows = response.json()

        if rows:
            return str(rows[0].get("name") or "").strip()

    return ""


def get_work_date(row):
    return str(row.get("work_date") or "")[:10]


def normalize_id(value):
    if value in (None, ""):
        return ""

    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def normalize_shift_text(row):
    for key in ["shift_text", "shift_name", "shift", "muszak", "name"]:
        value = str(row.get(key) or "").strip()

        if value:
            return value

    start = str(row.get("shift_start") or row.get("start") or "").strip()
    end = str(row.get("shift_end") or row.get("end") or "").strip()

    if start or end:
        return f"{start}-{end}".strip("-")

    return ""


def parse_attendance_raw_rows(rows, courier_id):
    by_date = {}
    courier_name = ""
    target_id = str(courier_id)

    for row in rows:
        work_date = get_work_date(row)
        payload = row.get("response_json") or {}
        couriers = payload.get("couriers") or []

        for courier in couriers:
            if str(courier.get("courierId")) != target_id:
                continue

            courier_name = str(courier.get("courierName") or courier_name or "").strip()
            shifts = courier.get("shifts") or []
            routes = courier.get("routes") or []
            shift_names = [
                str(shift.get("shiftName") or "").strip()
                for shift in shifts
                if str(shift.get("shiftName") or "").strip()
            ]
            route_ids = [
                normalize_id(route.get("routeId") or route.get("id"))
                for route in routes
                if normalize_id(route.get("routeId") or route.get("id"))
            ]

            by_date[work_date] = {
                "attendance_shift_count": len(shifts),
                "attendance_shift_names": " | ".join(shift_names),
                "attendance_route_count": len(routes),
                "attendance_route_ids": " | ".join(route_ids),
            }

    return courier_name, by_date


def parse_driver_detail_raw_rows(rows):
    by_date = defaultdict(lambda: {"count": 0, "route_ids": set()})

    for row in rows:
        work_date = get_work_date(row)
        payload = row.get("response_json") or {}
        routes = payload.get("routes") or []

        for route in routes:
            route_id = normalize_id(route.get("routeId") or route.get("id"))

            if route_id:
                by_date[work_date]["route_ids"].add(route_id)

        by_date[work_date]["count"] += len(routes)

    return by_date


def group_generic_rows(rows, metric):
    by_date = defaultdict(lambda: {"count": 0, "route_ids": set(), "shifts": set()})

    for row in rows:
        work_date = get_work_date(row)

        if not work_date:
            continue

        by_date[work_date]["count"] += 1

        route_id = normalize_id(row.get("route_id") or row.get("routeId") or row.get("id"))

        if route_id:
            by_date[work_date]["route_ids"].add(route_id)

        shift_text = normalize_shift_text(row)

        if shift_text:
            by_date[work_date]["shifts"].add(shift_text)

    return by_date


def empty_summary_row(work_date):
    row = {column: "" for column in SUMMARY_COLUMNS}
    row["work_date"] = work_date.isoformat() if isinstance(work_date, date) else str(work_date)
    row["issues"] = ""
    return row


def add_issue(row, text):
    if not text:
        return

    if row["issues"]:
        row["issues"] += " | "

    row["issues"] += text


def build_summary(
    start_date,
    end_date,
    attendance_by_date,
    table_group_data,
):
    summary_rows = []

    for work_date in date_range(start_date, end_date):
        key = work_date.isoformat()
        row = empty_summary_row(work_date)
        row.update(attendance_by_date.get(key, {}))

        for group_name, group in table_group_data.items():
            metric = group["metric"]
            item = group["by_date"].get(key, {})
            count = int(item.get("count") or 0)
            row[metric] = count

            route_ids = sorted(item.get("route_ids") or [])
            shifts = sorted(item.get("shifts") or [])

            if metric == "driver_detail_routes":
                row["driver_detail_route_ids"] = " | ".join(route_ids)
            elif metric == "arrival_rows":
                row["arrival_route_ids"] = " | ".join(route_ids)
            elif metric == "muszakpro_booking_rows":
                row["muszakpro_shifts"] = " | ".join(shifts)
            elif metric == "giriton_shift_rows":
                row["giriton_shifts"] = " | ".join(shifts)

        attendance_shift_count = int(row.get("attendance_shift_count") or 0)
        attendance_route_count = int(row.get("attendance_route_count") or 0)
        driver_detail_routes = int(row.get("driver_detail_routes") or 0)
        stage_shift_rows = int(row.get("stage_shift_rows") or 0)
        stage_route_rows = int(row.get("stage_route_rows") or 0)
        stage_summary_rows = int(row.get("stage_summary_rows") or 0)
        route_story_rows = int(row.get("route_story_rows") or 0)

        if attendance_shift_count and stage_shift_rows and attendance_shift_count != stage_shift_rows:
            add_issue(
                row,
                f"attendance shift {attendance_shift_count} != stage shift {stage_shift_rows}",
            )

        if attendance_route_count != driver_detail_routes:
            add_issue(
                row,
                f"attendance route {attendance_route_count} != driver-detail route {driver_detail_routes}",
            )

        if attendance_route_count != stage_route_rows:
            add_issue(
                row,
                f"attendance route {attendance_route_count} != stage route {stage_route_rows}",
            )

        if attendance_route_count != stage_summary_rows:
            add_issue(
                row,
                f"attendance route {attendance_route_count} != summary route {stage_summary_rows}",
            )

        if attendance_route_count != route_story_rows:
            add_issue(
                row,
                f"attendance route {attendance_route_count} != route story {route_story_rows}",
            )

        summary_rows.append(row)

    return summary_rows


def print_summary(summary_rows):
    display_columns = [
        "work_date",
        "attendance_shift_count",
        "attendance_route_count",
        "driver_detail_routes",
        "stage_shift_rows",
        "stage_route_rows",
        "stage_summary_rows",
        "route_story_rows",
        "muszakpro_booking_rows",
        "giriton_shift_rows",
        "issues",
    ]
    widths = {
        column: max(
            len(column),
            max((len(str(row.get(column, ""))) for row in summary_rows), default=0),
        )
        for column in display_columns
    }

    print(" | ".join(column.ljust(widths[column]) for column in display_columns))
    print("-+-".join("-" * widths[column] for column in display_columns))

    for row in summary_rows:
        print(
            " | ".join(
                str(row.get(column, "")).ljust(widths[column])
                for column in display_columns
            )
        )


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Egy futar adategyezosegi auditja a DSP/Giriton/MuszakPro tablak kozott."
        )
    )
    parser.add_argument("--courier-id", default="7644")
    parser.add_argument("--start-date", default=DEFAULT_BACKFILL_START_DATE.isoformat())
    parser.add_argument("--end-date", default=today().isoformat())
    parser.add_argument(
        "--output",
        default="",
        help="Opcionális CSV kimenet. Ha nincs megadva, reports/courier_audit_... lesz.",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Nem nulla exit code, ha van eltérés. CI/robot ellenőrzéshez hasznos.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    courier_id = str(args.courier_id).strip()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)

    if not courier_id:
        raise ValueError("Hianyzik a courier-id.")

    if end_date < start_date:
        raise ValueError("Az end-date nem lehet korabbi, mint a start-date.")

    supabase_url, service_role_key = get_supabase_config()
    print(
        f"Courier audit: #{courier_id}, datum: {start_date.isoformat()} - {end_date.isoformat()}"
    )

    attendance_table, attendance_rows = read_first_existing_group(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=["raw_dsp_attendance", "dsp_attendance_raw"],
        start_date=start_date,
        end_date=end_date,
    )
    courier_name, attendance_by_date = parse_attendance_raw_rows(
        attendance_rows,
        courier_id,
    )
    courier_name = courier_name or read_courier_name(
        supabase_url,
        service_role_key,
        courier_id,
    )
    print(f"Attendance forras: {attendance_table or 'nincs'} ({len(attendance_rows)} nap)")
    print(f"Futar neve: {courier_name or 'ismeretlen'}")

    table_group_data = {}

    for group in TABLE_GROUPS:
        table_name, rows = read_first_existing_group(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            candidates=group["candidates"],
            start_date=start_date,
            end_date=end_date,
            filter_column=group["filter_column"],
            filter_value=courier_id,
        )

        if group["name"] == "driver_detail_raw":
            by_date = parse_driver_detail_raw_rows(rows)
        else:
            by_date = group_generic_rows(rows, group["metric"])

        table_group_data[group["name"]] = {
            "table_name": table_name,
            "metric": group["metric"],
            "rows": rows,
            "by_date": by_date,
        }
        print(f"{group['name']}: {table_name or 'nincs'} ({len(rows)} sor)")

    if courier_name:
        for group in NAME_TABLE_GROUPS:
            table_name, rows = read_first_existing_group(
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                candidates=group["candidates"],
                start_date=start_date,
                end_date=end_date,
                filter_column=group["filter_column"],
                filter_value=courier_name,
            )
            table_group_data[group["name"]] = {
                "table_name": table_name,
                "metric": group["metric"],
                "rows": rows,
                "by_date": group_generic_rows(rows, group["metric"]),
            }
            print(f"{group['name']}: {table_name or 'nincs'} ({len(rows)} sor)")

    summary_rows = build_summary(
        start_date=start_date,
        end_date=end_date,
        attendance_by_date=attendance_by_date,
        table_group_data=table_group_data,
    )
    print("")
    print_summary(summary_rows)

    output_path = (
        Path(args.output)
        if args.output
        else PROJECT_ROOT
        / "reports"
        / f"courier_audit_{courier_id}_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    )
    write_csv(output_path, summary_rows)
    print("")
    print(f"CSV mentve: {output_path}")

    problematic = [row for row in summary_rows if row.get("issues")]
    print(f"Eltéréssel érintett napok: {len(problematic)}")

    if problematic and args.fail_on_issues:
        sys.exit(2)


if __name__ == "__main__":
    main()
