import argparse
import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

try:
    from scripts.dsp_incremental_common import (
        get_supabase_config,
        raise_for_supabase_error,
        supabase_headers,
    )
except ModuleNotFoundError:
    from dsp_incremental_common import (
        get_supabase_config,
        raise_for_supabase_error,
        supabase_headers,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")

OUTPUT_COLUMNS = [
    "work_date",
    "source_table",
    "source_kind",
    "courier_id",
    "courier_name",
    "warehouse",
    "shift_id",
    "shift_name",
    "shift_text",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "route_id",
    "assigned_at",
    "real_departure",
    "real_return",
    "status",
    "note",
]


def parse_date(value):
    if isinstance(value, date):
        return value

    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

    if parsed.tzinfo:
        return parsed.astimezone(BUDAPEST_TZ).replace(tzinfo=None)

    return parsed


def format_datetime(value):
    parsed = parse_datetime(value)

    if not parsed:
        return ""

    return parsed.isoformat(timespec="minutes", sep=" ")


def format_time(value):
    if not value:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    if "T" in text or len(text) > 8:
        parsed = parse_datetime(text)

        if parsed:
            return parsed.strftime("%H:%M")

    return text[:5]


def is_missing_response(response):
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
    table_name,
    start_date,
    end_date,
    filter_column=None,
    filter_value=None,
    page_size=1000,
):
    rows = []
    offset = 0

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
            filters.append(f"{filter_column}=eq.{quote(str(filter_value), safe='')}")

        endpoint = f"{supabase_url}/rest/v1/{table_name}?" + "&".join(filters)
        response = requests.get(
            endpoint,
            headers=supabase_headers({"Accept": "application/json"}),
            timeout=60,
        )

        if is_missing_response(response):
            return None

        raise_for_supabase_error(response, table_name)
        page = response.json()
        rows.extend(page)

        if len(page) < page_size:
            return rows

        offset += page_size


def read_first_existing(
    supabase_url,
    candidates,
    start_date,
    end_date,
    filter_column=None,
    filter_value=None,
):
    for table_name in candidates:
        rows = read_table_rows(
            supabase_url=supabase_url,
            table_name=table_name,
            start_date=start_date,
            end_date=end_date,
            filter_column=filter_column,
            filter_value=filter_value,
        )

        if rows is not None:
            return table_name, rows

    return "", []


def empty_output(work_date, source_table, source_kind):
    return {
        "work_date": str(work_date or ""),
        "source_table": source_table,
        "source_kind": source_kind,
        "courier_id": "",
        "courier_name": "",
        "warehouse": "",
        "shift_id": "",
        "shift_name": "",
        "shift_text": "",
        "shift_start": "",
        "shift_end": "",
        "available_for_shift_since": "",
        "route_id": "",
        "assigned_at": "",
        "real_departure": "",
        "real_return": "",
        "status": "",
        "note": "",
    }


def append_attendance_raw(output, table_name, rows, courier_id):
    courier_id_text = str(courier_id)

    for raw in rows:
        payload = raw.get("response_json") or {}
        work_date = str(payload.get("date") or raw.get("work_date") or "")[:10]

        for courier in payload.get("couriers", []) or []:
            if str(courier.get("courierId")) != courier_id_text:
                continue

            for shift in courier.get("shifts", []) or []:
                item = empty_output(work_date, table_name, "attendance_raw_shift")
                item.update(
                    {
                        "courier_id": courier_id_text,
                        "courier_name": courier.get("courierName") or "",
                        "warehouse": courier.get("warehouseName") or "",
                        "shift_id": shift.get("shiftId") or "",
                        "shift_name": shift.get("shiftName") or "",
                        "shift_text": shift.get("shiftName") or "",
                        "shift_start": format_datetime(shift.get("shiftStart")),
                        "shift_end": format_datetime(shift.get("shiftEnd")),
                        "available_for_shift_since": format_datetime(
                            shift.get("availableForShiftSince")
                        ),
                        "note": "DSP attendance API shift. Ez a muszak-keret forras.",
                    }
                )
                output.append(item)

            for route in courier.get("routes", []) or []:
                item = empty_output(work_date, table_name, "attendance_raw_route")
                item.update(
                    {
                        "courier_id": courier_id_text,
                        "courier_name": courier.get("courierName") or "",
                        "warehouse": courier.get("warehouseName") or "",
                        "route_id": route.get("routeId") or "",
                        "assigned_at": format_datetime(route.get("assignedAt")),
                        "real_departure": format_datetime(route.get("realDeparture")),
                        "real_return": format_datetime(route.get("realReturn")),
                        "note": "DSP attendance API route. Ez nem plusz muszak, hanem tura bizonyitek.",
                    }
                )
                output.append(item)


def append_driver_detail_raw(output, table_name, rows, courier_id):
    for raw in rows:
        work_date = str(raw.get("work_date") or "")[:10]
        payload = raw.get("response_json") or {}

        for route in payload.get("routes", []) or []:
            item = empty_output(work_date, table_name, "driver_detail_route")
            item.update(
                {
                    "courier_id": courier_id,
                    "courier_name": payload.get("courierName") or "",
                    "warehouse": payload.get("warehouseName") or "",
                    "route_id": route.get("id") or route.get("routeId") or "",
                    "assigned_at": format_datetime(route.get("assignedAt")),
                    "real_departure": format_datetime(route.get("realDeparture")),
                    "real_return": format_datetime(route.get("realReturn")),
                    "note": "fetch-drivers-detail route. Tura szintu tenyadat, nem muszak sor.",
                }
            )
            output.append(item)


def append_generic_shift_rows(output, table_name, rows, source_kind, courier_id):
    for row in rows:
        work_date = str(row.get("work_date") or "")[:10]
        item = empty_output(work_date, table_name, source_kind)
        shift_start = row.get("shift_start") or row.get("start_time") or row.get("start")
        shift_end = row.get("shift_end") or row.get("end_time") or row.get("end")
        shift_text = (
            row.get("shift_text")
            or row.get("shift_name")
            or row.get("shift")
            or ""
        )
        item.update(
            {
                "courier_id": row.get("courier_id") or courier_id,
                "courier_name": row.get("courier_name") or row.get("driver_name") or "",
                "warehouse": row.get("warehouse") or row.get("warehouse_name") or "",
                "shift_id": row.get("shift_id") or "",
                "shift_name": row.get("shift_name") or "",
                "shift_text": shift_text,
                "shift_start": format_datetime(shift_start)
                if "T" in str(shift_start or "")
                else format_time(shift_start),
                "shift_end": format_datetime(shift_end)
                if "T" in str(shift_end or "")
                else format_time(shift_end),
                "available_for_shift_since": format_datetime(
                    row.get("available_for_shift_since")
                ),
                "route_id": row.get("route_id") or "",
                "assigned_at": format_datetime(row.get("assigned_at")),
                "real_departure": format_datetime(row.get("real_departure")),
                "real_return": format_datetime(row.get("real_return")),
                "status": row.get("status") or row.get("activity_status") or "",
            }
        )
        output.append(item)


def append_giriton_attendance_rows(output, table_name, rows, courier_id):
    for row in rows:
        work_date = str(row.get("work_date") or "")[:10]
        shift_text = str(row.get("shift_text") or "").strip()
        shifts = [part.strip() for part in shift_text.split(",") if part.strip()]

        if not shifts:
            shifts = [""]

        for shift in shifts:
            item = empty_output(work_date, table_name, "giriton_attendance_shift_text")
            item.update(
                {
                    "courier_id": courier_id,
                    "courier_name": row.get("courier_name") or "",
                    "shift_text": shift,
                    "shift_start": format_time(shift.split("_", 1)[1])
                    if "_" in shift
                    else "",
                    "status": row.get("activity_status") or "",
                    "note": "Giriton Attendance oldali shift_text. Nem DSP muszakforras, hanem Giriton jelenleti oldal.",
                }
            )
            output.append(item)


def get_courier_name_from_output(rows):
    for row in rows:
        name = str(row.get("courier_name") or "").strip()

        if name:
            return name

    return ""


def get_courier_name_from_master(supabase_url, courier_id):
    for table_name in ["core_couriers", "courier_master"]:
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            "?select=*&"
            f"courier_id=eq.{quote(str(courier_id), safe='')}&"
            "limit=1"
        )
        response = requests.get(
            endpoint,
            headers=supabase_headers({"Accept": "application/json"}),
            timeout=30,
        )

        if is_missing_response(response):
            continue

        raise_for_supabase_error(response, table_name)
        rows = response.json()

        if rows:
            return str(
                rows[0].get("name")
                or rows[0].get("courier_name")
                or rows[0].get("full_name")
                or rows[0].get("driver_name")
                or ""
            ).strip()

    return ""


def name_variants(name):
    clean_name = " ".join(str(name or "").split())

    if not clean_name:
        return []

    variants = [clean_name]
    parts = clean_name.split()

    if len(parts) >= 2:
        reversed_name = " ".join(parts[1:] + parts[:1])

        if reversed_name not in variants:
            variants.append(reversed_name)

    return variants


def normalize_start_key(value):
    text = str(value or "").strip()

    if not text:
        return ""

    parsed = parse_datetime(text)

    if parsed:
        return parsed.strftime("%H:%M")

    if len(text) >= 5:
        return text[:5]

    return text


def print_source_summary(rows):
    by_date_kind = defaultdict(list)

    for row in rows:
        if row["source_kind"].endswith("_route") or row["source_kind"] == "driver_detail_route":
            continue

        key = (row["work_date"], row["source_table"], row["source_kind"])
        start = normalize_start_key(row["shift_start"] or row["shift_text"])

        if start:
            by_date_kind[key].append(start)

    print("")
    print("Muszak forras osszefoglalo")
    print("--------------------------")

    for key in sorted(by_date_kind):
        starts = sorted(set(by_date_kind[key]))
        print(f"{key[0]} | {key[1]} | {key[2]} | {len(starts)} db | {', '.join(starts)}")

    print("")
    print("Attendance-only gyanus muszakok")
    print("-------------------------------")

    by_date_source = defaultdict(lambda: defaultdict(set))

    for row in rows:
        if row["source_kind"].endswith("_route") or row["source_kind"] == "driver_detail_route":
            continue

        start = normalize_start_key(row["shift_start"] or row["shift_text"])

        if not start:
            continue

        by_date_source[row["work_date"]][row["source_kind"]].add(start)

    for work_date, source_map in sorted(by_date_source.items()):
        attendance_starts = source_map.get("attendance_raw_shift", set())
        other_starts = set()

        for kind, starts in source_map.items():
            if kind != "attendance_raw_shift":
                other_starts.update(starts)

        only_attendance = sorted(attendance_starts - other_starts)

        if only_attendance:
            print(f"{work_date}: csak attendance raw-ban latszik -> {', '.join(only_attendance)}")


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Futar muszakforras audit minden relevans DB tablabol."
    )
    parser.add_argument("--courier-id", default="7644")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", default="")
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    courier_id = str(args.courier_id).strip()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else start_date

    if end_date < start_date:
        raise ValueError("Az end-date nem lehet korabbi, mint a start-date.")

    supabase_url, _service_role_key = get_supabase_config()
    output = []

    attendance_table, attendance_rows = read_first_existing(
        supabase_url,
        ["raw_dsp_attendance", "dsp_attendance_raw"],
        start_date,
        end_date,
    )
    append_attendance_raw(output, attendance_table, attendance_rows, courier_id)
    courier_name = get_courier_name_from_output(output) or get_courier_name_from_master(
        supabase_url,
        courier_id,
    )

    driver_detail_table, driver_detail_rows = read_first_existing(
        supabase_url,
        ["raw_dsp_driver_detail", "dsp_driver_detail_raw"],
        start_date,
        end_date,
        "driver_id",
        courier_id,
    )
    append_driver_detail_raw(output, driver_detail_table, driver_detail_rows, courier_id)

    table_specs = [
        (
            ["stg_dsp_attendance_shifts", "dsp_attendance_shifts"],
            "attendance_stage_shift",
            "courier_id",
            courier_id,
        ),
        (
            ["stg_dsp_shift_route_summary", "dsp_shift_route_summary"],
            "shift_route_summary_shift",
            "courier_id",
            courier_id,
        ),
        (
            ["mart_dsp_route_stories"],
            "route_story_shift",
            "courier_id",
            courier_id,
        ),
        (
            ["raw_muszakpro_bookings", "foglalasok_raw"],
            "muszakpro_booking",
            "courier_id",
            courier_id,
        ),
        (
            ["raw_giriton_shifts", "giriton_shifts_raw"],
            "giriton_shift",
            "courier_id",
            courier_id,
        ),
    ]

    for candidates, source_kind, filter_column, filter_value in table_specs:
        table_name, rows = read_first_existing(
            supabase_url,
            candidates,
            start_date,
            end_date,
            filter_column,
            filter_value,
        )
        append_generic_shift_rows(output, table_name, rows, source_kind, courier_id)

    for courier_name_variant in name_variants(courier_name):
        table_name, rows = read_first_existing(
            supabase_url,
            ["raw_giriton_attendance", "giriton_attendance_raw"],
            start_date,
            end_date,
            "courier_name",
            courier_name_variant,
        )

        if rows:
            append_giriton_attendance_rows(output, table_name, rows, courier_id)
            break

    output.sort(
        key=lambda row: (
            row["work_date"],
            normalize_start_key(row["shift_start"] or row["shift_text"]),
            row["source_kind"],
            str(row["route_id"] or ""),
        )
    )

    print(
        f"Muszakforras audit #{courier_id} {courier_name or ''}: "
        f"{start_date.isoformat()} - {end_date.isoformat()}"
    )
    print(f"Sorok: {len(output)}")
    print_source_summary(output)

    output_path = (
        Path(args.output)
        if args.output
        else PROJECT_ROOT
        / "reports"
        / f"courier_shift_sources_{courier_id}_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    )
    write_csv(output_path, output)
    print("")
    print(f"CSV mentve: {output_path}")


if __name__ == "__main__":
    main()
