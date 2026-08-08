import argparse
import os
import re
import sys
import tomllib
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")


load_dotenv_if_available()


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
DEFAULT_START_DATE = "2026-06-01"
TARGET_TABLE = "mart_dsp_route_stories"
SHIFT_QUALITY_TABLE = "dsp_courier_shift_quality_report"
DAILY_QUALITY_TABLE = "dsp_courier_quality_daily"
MONTHLY_QUALITY_TABLE = "dsp_courier_quality_monthly"
SUMMARY_TABLE_CANDIDATES = [
    "stg_dsp_shift_route_summary",
    "dsp_shift_route_summary",
]
ARRIVALS_TABLE_CANDIDATES = [
    "stg_dsp_order_arrivals",
    "dsp_order_arrivals",
]
ATTENDANCE_RAW_TABLE_CANDIDATES = [
    "raw_dsp_attendance",
    "dsp_attendance_raw",
]
DRIVER_DETAIL_RAW_TABLE_CANDIDATES = [
    "raw_dsp_driver_detail",
    "dsp_driver_detail_raw",
]
DISTANCE_TABLE_CANDIDATES = [
    "stg_dsp_route_distance",
    "dsp_route_distance_calculated",
]
BOOKING_TABLE_CANDIDATES = [
    "raw_muszakpro_bookings",
    "foglalasok_raw",
]

ROUTE_STORY_COLUMNS = [
    "work_date",
    "courier_id",
    "courier_name",
    "warehouse_name",
    "route_id",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_at",
    "available_for_shift_since",
    "queue_started_at",
    "courier_registered_at",
    "assigned_at",
    "planned_departure",
    "real_departure",
    "planned_return",
    "real_return",
    "planned_route_minutes",
    "route_type",
    "address_count",
    "time_window_late_count",
    "assignment_mode",
]


SUMMARY_COLUMNS = [
    "work_date",
    "courier_id",
    "courier_name",
    "warehouse_name",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "route_id",
    "courier_registered_at",
    "assigned_at",
    "planned_departure",
    "planned_return",
    "planned_route_minutes",
    "real_departure",
    "real_return",
    "real_route_minutes",
]

ARRIVAL_COLUMNS = [
    "work_date",
    "driver_id",
    "route_id",
    "checkpoint_id",
    "order_id",
    "position",
    "address",
    "idoablak_kezdete",
    "idoablak_vege",
    "tervezett_erkezes",
    "valos_erkezes",
    "tervhez_kepest_perc",
    "idoablak_vegehez_kepest_perc",
    "idoablakhoz_kepest_statusz",
]

ATTENDANCE_RAW_COLUMNS = [
    "work_date",
    "response_json",
]

DRIVER_DETAIL_RAW_COLUMNS = [
    "work_date",
    "driver_id",
    "response_json",
]

DISTANCE_COLUMNS = [
    "work_date",
    "driver_id",
    "route_id",
    "gps_distance_km",
    "checkpoint_straight_km",
    "gps_points_count",
    "checkpoints_count",
]

BOOKING_COLUMNS = [
    "work_date",
    "courier_id",
    "shift_text",
    "warehouse",
    "booking_code",
    "serial",
]


def get_setting(name):
    value = os.getenv(name)

    if value:
        return value

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"

    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            secrets = tomllib.load(file)
    except Exception:
        return ""

    if name in secrets:
        return str(secrets.get(name) or "")

    supabase_section = secrets.get("supabase", {})

    if isinstance(supabase_section, dict) and name in supabase_section:
        return str(supabase_section.get(name) or "")

    return ""


def get_required_setting(name):
    value = str(get_setting(name) or "").strip()

    if not value:
        raise RuntimeError(f"Missing required setting: {name}")

    return value


def today_budapest():
    return datetime.now(BUDAPEST_TZ).date()


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_dates(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def parse_datetime(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(BUDAPEST_TZ).replace(tzinfo=None)

    return parsed


def to_int(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def minutes_between(start, end):
    if not start or not end:
        return None

    return int(round((end - start).total_seconds() / 60))


def parse_time_text(value):
    text = str(value or "").strip()

    if not text:
        return None

    import re

    match = re.search(r"(\d{1,2}):(\d{2})", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23 or minute > 59:
        return None

    return hour, minute


def combine_date_time(work_date, time_parts):
    if not work_date or not time_parts:
        return None

    if isinstance(work_date, date):
        parsed_date = work_date
    else:
        try:
            parsed_date = parse_date(str(work_date)[:10])
        except ValueError:
            return None

    hour, minute = time_parts

    return datetime(
        parsed_date.year,
        parsed_date.month,
        parsed_date.day,
        hour,
        minute,
    )


def format_datetime(value):
    if not value:
        return "nincs adat"

    return value.strftime("%Y-%m-%d %H:%M")


def format_minutes(value):
    if value is None:
        return "nincs adat"

    sign = "-" if value < 0 else ""
    minutes = abs(int(value))
    hours = minutes // 60
    remainder = minutes % 60

    if hours and remainder:
        return f"{sign}{hours} ora {remainder} perc"

    if hours:
        return f"{sign}{hours} ora"

    return f"{sign}{remainder} perc"


def format_queue_delta(value):
    if value is None:
        return "nincs sorba allasi ido"

    if value > 0:
        return f"{format_minutes(value)} kesessel"

    if value < 0:
        return f"{format_minutes(abs(value))} korabban"

    return "pontosan a muszak kezdetekor"


def format_km(value):
    number = to_float(value)

    if number is None:
        return "nincs adat"

    return f"{number:.1f} km"


def supabase_headers(service_role_key, extra=None):
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    if extra:
        headers.update(extra)

    return headers


def raise_for_supabase_error(response, table_name):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()

        if detail:
            raise requests.HTTPError(
                f"{exc}; tabla={table_name}; Supabase valasz: {detail[:1000]}",
                response=response,
            ) from exc

        raise


def missing_column_from_response(response):
    if response.status_code != 400:
        return None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if payload.get("code") != "PGRST204":
        return None

    message = str(payload.get("message") or response.text or "")
    match = re.search(r"Could not find the '([^']+)' column", message)

    if not match:
        return None

    return match.group(1)


def remove_column_from_rows(rows, column_name):
    return [
        {key: value for key, value in row.items() if key != column_name}
        for row in rows
    ]


def is_missing_table_response(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()

    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def read_table_range(
    supabase_url,
    service_role_key,
    table_name,
    columns,
    start_date,
    end_date,
    order,
    page_size=1000,
):
    rows = []
    selected_columns = ",".join(columns)
    filters = [f"select={selected_columns}"]

    if start_date == end_date:
        filters.append(f"work_date=eq.{start_date.isoformat()}")
    else:
        filters.extend(
            [
                f"work_date=gte.{start_date.isoformat()}",
                f"work_date=lte.{end_date.isoformat()}",
            ]
        )

    filters.append(f"order={order}")
    endpoint = f"{supabase_url}/rest/v1/{table_name}?{'&'.join(filters)}"

    while True:
        range_start = len(rows)
        range_end = range_start + page_size - 1
        headers = supabase_headers(
            service_role_key,
            {
                "Range-Unit": "items",
                "Range": f"{range_start}-{range_end}",
            },
        )

        response = requests.get(endpoint, headers=headers, timeout=60)

        if is_missing_table_response(response):
            return None

        raise_for_supabase_error(response, table_name)
        chunk = response.json()

        if not chunk:
            break

        rows.extend(chunk)

        if len(chunk) < page_size:
            break

    return rows


def read_table_range_by_day(
    supabase_url,
    service_role_key,
    table_name,
    columns,
    start_date,
    end_date,
    order,
    page_size=250,
):
    rows = []

    for current_date in iter_dates(start_date, end_date):
        daily_rows = read_table_range(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            table_name=table_name,
            columns=columns,
            start_date=current_date,
            end_date=current_date,
            order=order,
            page_size=page_size,
        )

        if daily_rows is None:
            return None

        rows.extend(daily_rows)
        print(f"{table_name}: {current_date.isoformat()} -> {len(daily_rows)} sor")

    return rows


def read_first_existing_table(
    supabase_url,
    service_role_key,
    candidates,
    columns,
    start_date,
    end_date,
    order,
    chunk_by_day=False,
    page_size=1000,
):
    missing = []
    last_error = None

    for table_name in candidates:
        try:
            if chunk_by_day:
                rows = read_table_range_by_day(
                    supabase_url=supabase_url,
                    service_role_key=service_role_key,
                    table_name=table_name,
                    columns=columns,
                    start_date=start_date,
                    end_date=end_date,
                    order=order,
                    page_size=page_size,
                )
            else:
                rows = read_table_range(
                    supabase_url=supabase_url,
                    service_role_key=service_role_key,
                    table_name=table_name,
                    columns=columns,
                    start_date=start_date,
                    end_date=end_date,
                    order=order,
                    page_size=page_size,
                )
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", 0)
            error_text = str(exc)

            if status_code >= 500 or "statement timeout" in error_text.lower():
                last_error = exc
                missing.append(f"{table_name} ({error_text[:160]})")
                print(f"{table_name} nem hasznalhato, kovetkezo forras probaja indul.")
                continue

            raise

        if rows is None:
            missing.append(table_name)
            continue

        return table_name, rows

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Nem talalhato forras tabla. Probalt tablazatok: "
        + ", ".join(missing or candidates)
    )


def read_latest_work_date_from_table(supabase_url, service_role_key, table_name):
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?select=work_date"
        "&order=work_date.desc"
        "&limit=1"
    )
    response = requests.get(
        endpoint,
        headers=supabase_headers(service_role_key),
        timeout=30,
    )

    if is_missing_table_response(response):
        return None

    raise_for_supabase_error(response, table_name)
    rows = response.json()

    if not rows:
        return None

    return parse_date(rows[0].get("work_date"))


def read_latest_work_date_from_candidates(supabase_url, service_role_key, candidates):
    for table_name in candidates:
        latest_date = read_latest_work_date_from_table(
            supabase_url,
            service_role_key,
            table_name,
        )

        if latest_date:
            return table_name, latest_date

    return "", None


def resolve_incremental_window(supabase_url, service_role_key, force_raw):
    target_table, target_latest = read_latest_work_date_from_candidates(
        supabase_url,
        service_role_key,
        [TARGET_TABLE],
    )

    if force_raw:
        source_groups = [
            ATTENDANCE_RAW_TABLE_CANDIDATES,
            DRIVER_DETAIL_RAW_TABLE_CANDIDATES,
        ]
    else:
        source_groups = [
            SUMMARY_TABLE_CANDIDATES + ATTENDANCE_RAW_TABLE_CANDIDATES,
            ARRIVALS_TABLE_CANDIDATES + DRIVER_DETAIL_RAW_TABLE_CANDIDATES,
        ]

    source_latest_values = []

    for candidates in source_groups:
        source_table, latest_date = read_latest_work_date_from_candidates(
            supabase_url,
            service_role_key,
            candidates,
        )

        if latest_date:
            source_latest_values.append((source_table, latest_date))

    if not source_latest_values:
        return parse_date(DEFAULT_START_DATE), today_budapest(), target_latest, []

    source_latest = min(latest_date for _table_name, latest_date in source_latest_values)

    if target_latest and target_latest >= source_latest:
        return None, None, target_latest, source_latest_values

    start_date = target_latest or parse_date(DEFAULT_START_DATE)
    end_date = source_latest

    return start_date, end_date, target_latest, source_latest_values


def normalize_route_key(work_date, courier_id, route_id):
    courier_value = to_int(courier_id)
    route_value = str(route_id or "").strip()

    if courier_value is None or not route_value:
        return None

    return (str(work_date), courier_value, route_value)


def normalize_status(value):
    text = str(value or "").strip().lower()
    text = (
        text.replace("ő", "o")
        .replace("ö", "o")
        .replace("ó", "o")
        .replace("ű", "u")
        .replace("ü", "u")
        .replace("ú", "u")
        .replace("é", "e")
        .replace("á", "a")
        .replace("í", "i")
    )
    return text


def build_arrival_stats(arrivals):
    grouped = defaultdict(
        lambda: {
            "address_count": 0,
            "planned_early_count": 0,
            "planned_late_count": 0,
            "time_window_early_count": 0,
            "time_window_late_count": 0,
            "city_window_count": 0,
        }
    )

    for row in arrivals:
        key = normalize_route_key(
            row.get("work_date"),
            row.get("driver_id"),
            row.get("route_id"),
        )

        if key is None:
            continue

        stats = grouped[key]
        stats["address_count"] += 1

        planned_delta = to_int(row.get("tervhez_kepest_perc"))

        if planned_delta is not None:
            if planned_delta < 0:
                stats["planned_early_count"] += 1
            elif planned_delta > 0:
                stats["planned_late_count"] += 1

        status = normalize_status(row.get("idoablakhoz_kepest_statusz"))
        window_start = parse_datetime(row.get("idoablak_kezdete"))
        window_end = parse_datetime(row.get("idoablak_vege"))
        window_minutes = minutes_between(window_start, window_end)

        if window_minutes in (15, 60):
            stats["city_window_count"] += 1

        if "kes" in status or "late" in status:
            stats["time_window_late_count"] += 1
        elif "korai" in status or "early" in status:
            stats["time_window_early_count"] += 1
        else:
            real_arrival = parse_datetime(row.get("valos_erkezes"))

            if real_arrival and window_start and real_arrival < window_start:
                stats["time_window_early_count"] += 1
            elif real_arrival and window_end and real_arrival > window_end:
                stats["time_window_late_count"] += 1

    return grouped


def resolve_route_type_from_arrival_stats(stats):
    if (stats or {}).get("city_window_count", 0) > 0:
        return "normal"

    return "express"


def build_distance_lookup(distance_rows):
    lookup = {}

    for row in distance_rows:
        key = normalize_route_key(
            row.get("work_date"),
            row.get("driver_id"),
            row.get("route_id"),
        )

        if key is None:
            continue

        lookup[key] = {
            "gps_distance_km": to_float(row.get("gps_distance_km")),
            "checkpoint_straight_km": to_float(
                row.get("checkpoint_straight_km")
            ),
        }

    return lookup


def build_booking_lookup(booking_rows):
    lookup = defaultdict(list)

    for row in booking_rows:
        courier_id = to_int(row.get("courier_id"))
        work_date = str(row.get("work_date") or "").strip()[:10]
        shift_text = str(row.get("shift_text") or "").strip()

        if courier_id is None or not work_date or not shift_text:
            continue

        shift_start = combine_date_time(
            work_date,
            parse_time_text(shift_text),
        )

        lookup[(work_date, courier_id)].append(
            {
                "work_date": work_date,
                "courier_id": courier_id,
                "shift_text": shift_text,
                "warehouse": row.get("warehouse"),
                "booking_code": row.get("booking_code"),
                "serial": row.get("serial"),
                "shift_start": shift_start,
            }
        )

    for key, rows in lookup.items():
        rows.sort(
            key=lambda item: (
                item.get("shift_start") or datetime.max,
                item.get("shift_text") or "",
            )
        )

    return lookup


def find_booking_context(row, booking_lookup):
    work_date = str(row.get("work_date") or "").strip()[:10]
    courier_id = to_int(row.get("courier_id"))
    bookings = booking_lookup.get((work_date, courier_id), [])
    shift_start = parse_datetime(row.get("shift_start"))
    assigned_at = parse_datetime(row.get("assigned_at"))
    real_return = parse_datetime(row.get("real_return"))
    planned_return = parse_datetime(row.get("planned_return"))
    reference_start = shift_start or assigned_at
    return_reference = real_return or planned_return
    next_booking = None

    for booking in bookings:
        booking_start = booking.get("shift_start")

        if not booking_start:
            continue

        if reference_start and booking_start <= reference_start:
            continue

        next_booking = booking
        break

    next_shift_delay = None

    if next_booking and return_reference and next_booking.get("shift_start"):
        next_shift_delay = minutes_between(
            next_booking["shift_start"],
            return_reference,
        )

    return {
        "booking_shift_count": len(bookings),
        "next_booking_shift_text": (
            next_booking.get("shift_text") if next_booking else None
        ),
        "next_booking_shift_start": (
            next_booking.get("shift_start") if next_booking else None
        ),
        "next_shift_delay_minutes": next_shift_delay,
    }


def choose_matching_shift(route_row, shifts):
    planned_departure = parse_datetime(route_row.get("planned_departure"))
    real_departure = parse_datetime(route_row.get("real_departure"))
    registered_at = parse_datetime(route_row.get("courier_registered_at"))
    assigned_at = parse_datetime(route_row.get("assigned_at"))

    def contains(shift, value):
        if not value:
            return False

        shift_start = parse_datetime(shift.get("shift_start"))
        shift_end = parse_datetime(shift.get("shift_end"))

        if not shift_start or not shift_end:
            return False

        return shift_start <= value <= shift_end

    window_references = [
        planned_departure,
        real_departure,
        assigned_at,
        registered_at,
    ]

    for reference in window_references:
        if not reference:
            continue

        matches = [shift for shift in shifts if contains(shift, reference)]

        if matches:
            return min(
                matches,
                key=lambda shift: abs(
                    (
                        (parse_datetime(shift.get("shift_start")) or reference)
                        - reference
                    ).total_seconds()
                ),
            )

    queue_candidates = []

    if assigned_at:
        for shift in shifts:
            available_at = parse_datetime(
                shift.get("available_for_shift_since")
            )
            shift_start = parse_datetime(shift.get("shift_start"))

            if not available_at or available_at > assigned_at:
                continue

            queue_candidates.append(
                (
                    abs((assigned_at - available_at).total_seconds()),
                    0 if shift_start and shift_start <= assigned_at else 1,
                    abs(
                        (
                            (shift_start or assigned_at)
                            - assigned_at
                        ).total_seconds()
                    ),
                    available_at,
                    shift,
                )
            )

    if queue_candidates:
        queue_candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                -item[3].timestamp(),
            )
        )
        return queue_candidates[0][4]

    if assigned_at:
        shift_start_candidates = []

        for shift in shifts:
            shift_start = parse_datetime(shift.get("shift_start"))

            if not shift_start or shift_start > assigned_at:
                continue

            shift_start_candidates.append(
                (
                    abs((assigned_at - shift_start).total_seconds()),
                    shift_start,
                    shift,
                )
            )

        if shift_start_candidates:
            shift_start_candidates.sort(
                key=lambda item: (
                    item[0],
                    -item[1].timestamp(),
                )
            )
            return shift_start_candidates[0][2]

    for shift in shifts:
        if contains(shift, planned_departure) or contains(shift, registered_at):
            return shift

    if not shifts:
        return {}

    route_reference = planned_departure or registered_at

    if not route_reference:
        return shifts[0]

    return min(
        shifts,
        key=lambda shift: abs(
            (
                (parse_datetime(shift.get("shift_start")) or route_reference)
                - route_reference
            ).total_seconds()
        ),
    )


def parse_raw_attendance_rows(raw_rows):
    summary_rows = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        work_date = response_json.get("date") or raw.get("work_date")
        dsp_id = response_json.get("dspId")
        dsp_name = response_json.get("dspName")

        for courier in response_json.get("couriers", []) or []:
            courier_id = to_int(courier.get("courierId"))

            if courier_id is None:
                continue

            shifts = []

            for shift in courier.get("shifts", []) or []:
                shift_start = parse_datetime(shift.get("shiftStart"))
                shift_end = parse_datetime(shift.get("shiftEnd"))
                available_at = parse_datetime(shift.get("availableForShiftSince"))

                shifts.append(
                    {
                        "work_date": work_date,
                        "dsp_id": dsp_id,
                        "dsp_name": dsp_name,
                        "courier_id": courier_id,
                        "courier_name": courier.get("courierName"),
                        "warehouse_name": courier.get("warehouseName"),
                        "shift_id": shift.get("shiftId"),
                        "shift_name": shift.get("shiftName"),
                        "shift_start": serialize_datetime(shift_start),
                        "shift_end": serialize_datetime(shift_end),
                        "available_for_shift_since": serialize_datetime(available_at),
                    }
                )

            for route in courier.get("routes", []) or []:
                route_id = to_int(route.get("routeId"))

                if route_id is None:
                    continue

                route_row = {
                    "work_date": work_date,
                    "dsp_id": dsp_id,
                    "dsp_name": dsp_name,
                    "courier_id": courier_id,
                    "courier_name": courier.get("courierName"),
                    "warehouse_name": courier.get("warehouseName"),
                    "route_id": route_id,
                    "courier_registered_at": serialize_datetime(
                        parse_datetime(route.get("courierRegisteredAt"))
                    ),
                    "assigned_at": serialize_datetime(
                        parse_datetime(route.get("assignedAt"))
                    ),
                    "planned_departure": serialize_datetime(
                        parse_datetime(route.get("plannedDeparture"))
                    ),
                    "real_departure": serialize_datetime(
                        parse_datetime(route.get("realDeparture"))
                    ),
                    "planned_return": serialize_datetime(
                        parse_datetime(route.get("plannedReturn"))
                    ),
                    "real_return": serialize_datetime(
                        parse_datetime(route.get("realReturn"))
                    ),
                }
                shift = choose_matching_shift(route_row, shifts)
                route_row.update(
                    {
                        "shift_id": shift.get("shift_id"),
                        "shift_name": shift.get("shift_name"),
                        "shift_start": shift.get("shift_start"),
                        "shift_end": shift.get("shift_end"),
                        "available_for_shift_since": shift.get(
                            "available_for_shift_since"
                        ),
                    }
                )
                summary_rows.append(route_row)

    return summary_rows


def parse_raw_attendance_shift_rows(raw_rows):
    shift_rows = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        work_date = response_json.get("date") or raw.get("work_date")

        for courier in response_json.get("couriers", []) or []:
            courier_id = to_int(courier.get("courierId"))

            if courier_id is None:
                continue

            for shift in courier.get("shifts", []) or []:
                shift_start = parse_datetime(shift.get("shiftStart"))
                shift_end = parse_datetime(shift.get("shiftEnd"))
                available_at = parse_datetime(shift.get("availableForShiftSince"))

                shift_rows.append(
                    {
                        "work_date": work_date,
                        "courier_id": courier_id,
                        "courier_name": courier.get("courierName"),
                        "warehouse_name": courier.get("warehouseName"),
                        "shift_id": shift.get("shiftId"),
                        "shift_name": shift.get("shiftName"),
                        "shift_start": serialize_datetime(shift_start),
                        "shift_end": serialize_datetime(shift_end),
                        "available_for_shift_since": serialize_datetime(available_at),
                    }
                )

    return shift_rows


def build_route_detail_lookup(raw_rows):
    lookup = {}

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        work_date = raw.get("work_date")
        driver_id = to_int(raw.get("driver_id")) or to_int(
            response_json.get("courier-id")
        )

        if driver_id is None:
            continue

        for route in response_json.get("routes", []) or []:
            route_id = route.get("id") or route.get("routeId")
            key = normalize_route_key(work_date, driver_id, route_id)

            if key is None:
                continue

            lookup[key] = {
                "route_created_at": serialize_datetime(
                    parse_datetime(route.get("createdAt"))
                ),
                "courier_registered_at": serialize_datetime(
                    parse_datetime(route.get("courierRegisteredAt"))
                ),
                "assigned_at": serialize_datetime(parse_datetime(route.get("assignedAt"))),
                "loading_time": serialize_datetime(
                    parse_datetime(route.get("loadingTime"))
                ),
                "planned_departure": serialize_datetime(
                    parse_datetime(route.get("plannedDeparture"))
                ),
                "real_departure": serialize_datetime(
                    parse_datetime(route.get("realDeparture"))
                ),
                "planned_return": serialize_datetime(
                    parse_datetime(route.get("plannedReturn"))
                ),
                "real_return": serialize_datetime(parse_datetime(route.get("realReturn"))),
            }

    return lookup


def enrich_summary_with_route_details(summary_rows, route_detail_lookup):
    enriched_rows = []
    route_detail_fields = [
        "route_created_at",
        "courier_registered_at",
        "assigned_at",
        "loading_time",
        "planned_departure",
        "real_departure",
        "planned_return",
        "real_return",
    ]

    for row in summary_rows:
        key = normalize_route_key(
            row.get("work_date"),
            row.get("courier_id"),
            row.get("route_id"),
        )
        detail = route_detail_lookup.get(key, {})
        enriched = dict(row)

        for field in route_detail_fields:
            if detail.get(field):
                enriched[field] = detail[field]

        enriched_rows.append(enriched)

    return enriched_rows


def parse_raw_driver_detail_arrivals(raw_rows):
    arrivals = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        work_date = raw.get("work_date")
        driver_id = to_int(raw.get("driver_id")) or to_int(
            response_json.get("courier-id")
        )

        if driver_id is None:
            continue

        for route in response_json.get("routes", []) or []:
            route_id = route.get("id") or route.get("routeId")

            if not route_id:
                continue

            for checkpoint in route.get("checkpoints", []) or []:
                planned_arrival = parse_datetime(
                    checkpoint.get("plannedArrivalTime")
                )
                real_arrival = parse_datetime(checkpoint.get("realArrivalTime"))
                window_start = parse_datetime(checkpoint.get("deliverSince"))
                window_end = parse_datetime(checkpoint.get("deliverTill"))
                planned_delta = minutes_between(planned_arrival, real_arrival)
                window_end_delta = minutes_between(window_end, real_arrival)

                if not real_arrival:
                    window_status = "Nincs valos erkezes"
                elif window_start and real_arrival < window_start:
                    window_status = "Korai"
                elif window_end and real_arrival > window_end:
                    window_status = "Keso"
                elif window_start and window_end:
                    window_status = "Idoben"
                else:
                    window_status = "Nincs idoablak"

                arrivals.append(
                    {
                        "work_date": work_date,
                        "driver_id": driver_id,
                        "route_id": str(route_id),
                        "checkpoint_id": checkpoint.get("id"),
                        "order_id": checkpoint.get("orderId"),
                        "position": checkpoint.get("position"),
                        "address": checkpoint.get("address"),
                        "idoablak_kezdete": serialize_datetime(window_start),
                        "idoablak_vege": serialize_datetime(window_end),
                        "tervezett_erkezes": serialize_datetime(planned_arrival),
                        "valos_erkezes": serialize_datetime(real_arrival),
                        "tervhez_kepest_perc": planned_delta,
                        "idoablak_vegehez_kepest_perc": window_end_delta,
                        "idoablakhoz_kepest_statusz": window_status,
                    }
                )

    return arrivals


def build_story(row, stats, distance, booking):
    shift_start = parse_datetime(row.get("shift_start"))
    shift_end = parse_datetime(row.get("shift_end"))
    available_at = parse_datetime(row.get("available_for_shift_since"))
    route_created_at = parse_datetime(row.get("route_created_at"))
    courier_registered_at = parse_datetime(row.get("courier_registered_at"))
    assigned_at = parse_datetime(row.get("assigned_at"))
    loading_time = parse_datetime(row.get("loading_time"))
    planned_departure = parse_datetime(row.get("planned_departure"))
    real_departure = parse_datetime(row.get("real_departure"))
    planned_return = parse_datetime(row.get("planned_return"))
    real_return = parse_datetime(row.get("real_return"))
    queue_started_at = available_at or courier_registered_at

    queue_entry_delta = minutes_between(shift_start, queue_started_at)
    queue_wait = minutes_between(queue_started_at, assigned_at)
    planned_loading = minutes_between(assigned_at, loading_time or planned_departure)
    real_loading = minutes_between(assigned_at, real_departure)
    planned_route = minutes_between(planned_departure, planned_return)
    real_route = minutes_between(real_departure, real_return)
    assigned_to_return = minutes_between(assigned_at, real_return)
    total_route = assigned_to_return

    if available_at and assigned_at:
        assignment_mode = "QUEUE"
    elif courier_registered_at and assigned_at:
        assignment_mode = "REGISTERED"
    elif assigned_at:
        assignment_mode = "MANUAL"
    else:
        assignment_mode = "UNKNOWN"

    shift_text = f"{format_datetime(shift_start)} - {format_datetime(shift_end)}"

    if available_at:
        availability_text = (
            f"elerheto: {format_datetime(available_at)} "
            f"({format_queue_delta(queue_entry_delta)} a muszakkezdeshez kepest)"
        )
    elif courier_registered_at:
        availability_text = (
            "elerheto: nincs kulon availableForShiftSince, "
            f"route regisztracio: {format_datetime(courier_registered_at)} "
            f"({format_queue_delta(queue_entry_delta)} a muszakkezdeshez kepest)"
        )
    elif assigned_at:
        availability_text = (
            "elerheto/sorba allas: nincs adat, de van assignedAt, "
            "ezert manualis kiosztasnak latszik"
        )
    else:
        availability_text = "elerheto/sorba allas: nincs adat"

    assignment_text = (
        f"tura kiosztva: {format_datetime(assigned_at)}"
    )

    if queue_wait is not None:
        wait_text = f"sorban allt: {format_minutes(queue_wait)}"
    elif assigned_at:
        wait_text = "sorban allt: nem szamolhato, mert nincs sorba allasi ido"
    else:
        wait_text = "sorban allt: nem szamolhato"

    if courier_registered_at:
        registration_text = (
            f"route regisztracio: {format_datetime(courier_registered_at)}"
        )
    elif assigned_at:
        registration_text = (
            "route regisztracio: nincs adat, ez manualis tura kiosztast jelez"
        )
    else:
        registration_text = "route regisztracio: nincs adat"

    loading_text = (
        f"tervezett: {format_minutes(planned_loading)} | "
        f"valos: {format_minutes(real_loading)}"
    )
    route_time_text = (
        f"tervezett: {format_minutes(planned_route)} | "
        f"valos: {format_minutes(real_route)} | "
        f"osszes: {format_minutes(total_route)}"
    )
    distance_text = (
        f"GPS: {format_km(distance.get('gps_distance_km'))} | "
        f"cimek kozti egyenes: {format_km(distance.get('checkpoint_straight_km'))}"
    )
    booking_count = int(booking.get("booking_shift_count") or 0)
    next_shift_start = parse_datetime(booking.get("next_booking_shift_start"))
    next_shift_text = booking.get("next_booking_shift_text")
    next_shift_delay = booking.get("next_shift_delay_minutes")
    booking_text = (
        f"napi foglalt muszakok szama: {booking_count}"
    )

    if next_shift_text and next_shift_start:
        if next_shift_delay is None:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}), de a keses nem szamolhato"
            )
        elif next_shift_delay > 0:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}). "
                f"A route visszaerkezese alapjan ebbol {format_minutes(next_shift_delay)} keses lett"
            )
        else:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}). "
                f"A route visszaerkezese alapjan nem kesik, "
                f"{format_minutes(abs(next_shift_delay))} tartalek maradt"
            )
    elif booking_count:
        next_shift_text_value = "nincs tovabbi aznapi foglalt muszak"
    else:
        next_shift_text_value = "nincs aznapi foglalasi adat"

    address_text = (
        f"osszes: {stats['address_count']} db | "
        f"tervezetthez kepest korai: {stats['planned_early_count']} db | "
        f"tervezetthez kepest keso: {stats['planned_late_count']} db | "
        f"idokapuhoz kepest korai: {stats['time_window_early_count']} db | "
        f"idokapuhoz kepest keso: {stats['time_window_late_count']} db"
    )

    story_text = "\n".join(
        [
            "Route tortenet",
            f"  Futar: {row.get('courier_name') or 'nincs adat'} (#{row.get('courier_id') or 'nincs adat'})",
            f"  Route: {row.get('route_id') or 'nincs adat'}",
            "",
            "Muszak es sor",
            f"  - muszak: {shift_text}",
            f"  - {availability_text}",
            f"  - {registration_text}",
            f"  - {assignment_text}",
            f"  - {wait_text}",
            "",
            "Idok",
            f"  - bepakolas: {loading_text}",
            f"  - tura hossz: {route_time_text}",
            f"  - tavolsag: {distance_text}",
            "",
            "Foglalas es kovetkezo muszak",
            f"  - {booking_text}",
            f"  - {next_shift_text_value}",
            "",
            "Cimek",
            f"  - {address_text}",
        ]
    )

    return {
        "shift_start": shift_start,
        "shift_end": shift_end,
        "available_at": available_at,
        "available_for_shift_since": available_at,
        "queue_started_at": queue_started_at,
        "route_created_at": route_created_at,
        "courier_registered_at": courier_registered_at,
        "assigned_at": assigned_at,
        "loading_time": loading_time,
        "planned_departure": planned_departure,
        "real_departure": real_departure,
        "planned_return": planned_return,
        "real_return": real_return,
        "queue_entry_delta_minutes": queue_entry_delta,
        "queue_wait_minutes": queue_wait,
        "planned_loading_minutes": planned_loading,
        "real_loading_minutes": real_loading,
        "planned_route_minutes": planned_route,
        "real_route_minutes": real_route,
        "assigned_to_return_minutes": assigned_to_return,
        "total_route_minutes": total_route,
        "gps_distance_km": distance.get("gps_distance_km"),
        "checkpoint_straight_km": distance.get("checkpoint_straight_km"),
        "booking_shift_count": booking_count,
        "next_booking_shift_text": next_shift_text,
        "next_booking_shift_start": next_shift_start,
        "next_shift_delay_minutes": next_shift_delay,
        "assignment_mode": assignment_mode,
        "story_text": story_text,
    }


def serialize_datetime(value):
    if value is None:
        return None

    return value.isoformat(timespec="seconds")


def build_output_rows(
    summary_rows,
    arrival_stats,
    distance_lookup,
    booking_lookup,
    source_summary_table,
    source_arrivals_table,
):
    output_rows = []

    for row in summary_rows:
        key = normalize_route_key(
            row.get("work_date"),
            row.get("courier_id"),
            row.get("route_id"),
        )

        if key is None:
            continue

        stats = arrival_stats.get(
            key,
            {
                "address_count": 0,
                "planned_early_count": 0,
                "planned_late_count": 0,
                "time_window_early_count": 0,
                "time_window_late_count": 0,
                "city_window_count": 0,
            },
        )
        distance = distance_lookup.get(
            key,
            {
                "gps_distance_km": None,
                "checkpoint_straight_km": None,
            },
        )
        booking = find_booking_context(row, booking_lookup)
        story = build_story(row, stats, distance, booking)

        output_rows.append(
            {
                "work_date": row.get("work_date"),
                "courier_id": to_int(row.get("courier_id")),
                "courier_name": row.get("courier_name"),
                "warehouse_name": row.get("warehouse_name"),
                "route_id": to_int(row.get("route_id")),
                "shift_id": to_int(row.get("shift_id")),
                "shift_name": row.get("shift_name"),
                "shift_start": serialize_datetime(story["shift_start"]),
                "shift_end": serialize_datetime(story["shift_end"]),
                "available_at": serialize_datetime(story["available_at"]),
                "available_for_shift_since": serialize_datetime(
                    story["available_for_shift_since"]
                ),
                "queue_started_at": serialize_datetime(story["queue_started_at"]),
                "route_created_at": serialize_datetime(story["route_created_at"]),
                "courier_registered_at": serialize_datetime(
                    story["courier_registered_at"]
                ),
                "assigned_at": serialize_datetime(story["assigned_at"]),
                "loading_time": serialize_datetime(story["loading_time"]),
                "planned_departure": serialize_datetime(story["planned_departure"]),
                "real_departure": serialize_datetime(story["real_departure"]),
                "planned_return": serialize_datetime(story["planned_return"]),
                "real_return": serialize_datetime(story["real_return"]),
                "queue_entry_delta_minutes": story["queue_entry_delta_minutes"],
                "queue_wait_minutes": story["queue_wait_minutes"],
                "planned_loading_minutes": story["planned_loading_minutes"],
                "real_loading_minutes": story["real_loading_minutes"],
                "planned_route_minutes": story["planned_route_minutes"],
                "real_route_minutes": story["real_route_minutes"],
                "route_type": resolve_route_type_from_arrival_stats(stats),
                "assigned_to_return_minutes": story["assigned_to_return_minutes"],
                "total_route_minutes": story["total_route_minutes"],
                "gps_distance_km": story["gps_distance_km"],
                "checkpoint_straight_km": story["checkpoint_straight_km"],
                "booking_shift_count": story["booking_shift_count"],
                "next_booking_shift_text": story["next_booking_shift_text"],
                "next_booking_shift_start": serialize_datetime(
                    story["next_booking_shift_start"]
                ),
                "next_shift_delay_minutes": story["next_shift_delay_minutes"],
                "address_count": stats["address_count"],
                "planned_early_count": stats["planned_early_count"],
                "planned_late_count": stats["planned_late_count"],
                "time_window_early_count": stats["time_window_early_count"],
                "time_window_late_count": stats["time_window_late_count"],
                "assignment_mode": story["assignment_mode"],
                "story_text": story["story_text"],
                "source_summary_table": source_summary_table,
                "source_arrivals_table": source_arrivals_table,
            }
        )

    return output_rows


def upsert_rows(supabase_url, service_role_key, rows, chunk_size=500):
    if not rows:
        return

    endpoint = (
        f"{supabase_url}/rest/v1/{TARGET_TABLE}"
        "?on_conflict=work_date,courier_id,route_id"
    )
    headers = supabase_headers(
        service_role_key,
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    skipped_columns = set()

    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        payload = chunk

        if skipped_columns:
            for column_name in skipped_columns:
                payload = remove_column_from_rows(payload, column_name)

        while True:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=60,
            )
            missing_column = missing_column_from_response(response)

            if missing_column:
                if missing_column in skipped_columns and not any(
                    missing_column in row for row in payload
                ):
                    raise_for_supabase_error(response, TARGET_TABLE)

                skipped_columns.add(missing_column)
                payload = remove_column_from_rows(payload, missing_column)
                print(
                    f"FIGYELEM: {TARGET_TABLE} tabla nem tartalmazza ezt az oszlopot, "
                    f"feltoltes kozben kihagyva: {missing_column}"
                )
                continue

            raise_for_supabase_error(response, TARGET_TABLE)
            break

        print(f"Feltoltve: {start + len(chunk)} / {len(rows)} route story")


def shift_group_key(row):
    work_date = str(row.get("work_date") or "").strip()[:10]
    courier_id = to_int(row.get("courier_id"))
    shift_key = str(
        row.get("shift_start")
        or row.get("shift_id")
        or row.get("shift_name")
        or row.get("route_id")
        or ""
    ).strip()

    if courier_id is None or not work_date or not shift_key:
        return None

    return work_date, courier_id, shift_key


def normalize_warehouse(value):
    return str(value or "").strip().upper()


def shift_match_key(work_date, courier_id, warehouse, shift_start):
    parsed_start = parse_datetime(shift_start)

    if courier_id is None or not work_date or not parsed_start:
        return None

    return (
        str(work_date)[:10],
        int(courier_id),
        normalize_warehouse(warehouse),
        parsed_start.strftime("%H:%M"),
    )


def read_settlement_table(supabase_url, service_role_key, table_name, columns, order="priority.asc"):
    response = requests.get(
        f"{supabase_url}/rest/v1/{table_name}",
        headers=supabase_headers(
            service_role_key,
            {"Accept-Profile": "settlement"},
        ),
        params={
            "select": ",".join(columns),
            "is_active": "eq.true",
            "deleted_at": "is.null",
            "order": order,
            "limit": "1000",
        },
        timeout=60,
    )

    if is_missing_table_response(response):
        return []

    raise_for_supabase_error(response, table_name)
    return response.json()


def read_public_table(supabase_url, service_role_key, table_name, columns, params=None):
    request_params = {
        "select": ",".join(columns),
        "limit": "1000",
    }
    request_params.update(params or {})
    response = requests.get(
        f"{supabase_url}/rest/v1/{table_name}",
        headers=supabase_headers(service_role_key),
        params=request_params,
        timeout=60,
    )

    if is_missing_table_response(response):
        return []

    raise_for_supabase_error(response, table_name)
    return response.json()


def shift_id_match_key(work_date, courier_id, shift_id):
    parsed_shift_id = to_int(shift_id)

    if courier_id is None or not work_date or parsed_shift_id is None:
        return None

    return (
        str(work_date)[:10],
        int(courier_id),
        parsed_shift_id,
    )


def first_datetime(rows, field_names):
    values = []

    for row in rows:
        for field_name in field_names:
            parsed = parse_datetime(row.get(field_name))

            if parsed:
                values.append(parsed)
                break

    return min(values) if values else None


def last_datetime(rows, field_names):
    values = []

    for row in rows:
        for field_name in field_names:
            parsed = parse_datetime(row.get(field_name))

            if parsed:
                values.append(parsed)
                break

    return max(values) if values else None


def is_after_order_cutoff(value):
    parsed = parse_datetime(value)

    if not parsed:
        return False

    return (parsed.hour, parsed.minute) >= (20, 45)


def safe_percent(part, total):
    if not total:
        return 0.0

    return round((float(part or 0) / float(total)) * 100, 2)


def delay_level_from_percent(value):
    if value <= 1.50:
        return 1

    if value <= 3.00:
        return 2

    if value <= 5.00:
        return 3

    return 4


def route_quality_level_from_percent(value):
    if value <= 2.00:
        return 1

    if value <= 4.00:
        return 2

    if value <= 10.00:
        return 3

    return 4


def parse_bool(value, default=True):
    if value in (None, ""):
        return default

    return bool(value)


def value_in_range(value, minimum, maximum, min_inclusive=True, max_inclusive=True):
    if minimum is not None:
        if min_inclusive and value < float(minimum):
            return False
        if not min_inclusive and value <= float(minimum):
            return False

    if maximum is not None:
        if max_inclusive and value > float(maximum):
            return False
        if not max_inclusive and value >= float(maximum):
            return False

    return True


def route_type_from_text(value):
    text = normalize_status(value)

    if "express" in text:
        return "express"

    if "regional" in text or "regio" in text:
        return "regional"

    return "normal"


def route_type_from_row(row):
    route_type = normalize_status(row.get("route_type"))

    if route_type in {"express", "normal", "regional"}:
        return route_type

    return route_type_from_text(row.get("shift_name"))


def route_type_from_route_rows(route_rows):
    route_types = {route_type_from_row(row) for row in route_rows or []}

    if "normal" in route_types:
        return "normal"

    if "regional" in route_types:
        return "regional"

    return "express"


def resolve_day_type(work_date, day_rules):
    parsed = parse_date(str(work_date or "")[:10])

    if not parsed:
        return "normal"

    weekday = parsed.isoweekday()

    for rule in day_rules:
        valid_from = parse_date(rule.get("valid_from"))
        valid_to = parse_date(rule.get("valid_to")) if rule.get("valid_to") else None
        weekdays = rule.get("weekdays") or []

        if valid_from and parsed < valid_from:
            continue

        if valid_to and parsed > valid_to:
            continue

        if weekday in [int(item) for item in weekdays]:
            return str(rule.get("day_type") or "normal")

    return "normal"


def planned_route_hours(row):
    minutes = to_int(row.get("planned_route_minutes"))

    if minutes is None:
        planned_departure = parse_datetime(row.get("planned_departure_at"))
        planned_return = parse_datetime(row.get("planned_return_at"))
        minutes = minutes_between(planned_departure, planned_return)

    if minutes is None or minutes <= 0:
        shift_start = parse_datetime(row.get("shift_start_at"))
        shift_end = parse_datetime(row.get("shift_end_at"))
        minutes = minutes_between(shift_start, shift_end)

    return (float(minutes) / 60.0) if minutes and minutes > 0 else 0.0


def matching_amount_rule(rules, metric_percent, row, day_type):
    duration_hours = planned_route_hours(row)
    route_type = route_type_from_row(row)
    warehouse = normalize_warehouse(row.get("warehouse"))

    matches = []

    for rule in rules:
        valid_from = parse_date(rule.get("valid_from"))
        valid_to = parse_date(rule.get("valid_to")) if rule.get("valid_to") else None
        work_date = parse_date(str(row.get("work_date") or "")[:10])

        if valid_from and work_date and work_date < valid_from:
            continue

        if valid_to and work_date and work_date > valid_to:
            continue

        if str(rule.get("day_type") or "any") not in (day_type, "any"):
            continue

        if str(rule.get("route_type") or "any") not in (route_type, "any"):
            continue

        rule_warehouse = normalize_warehouse(rule.get("warehouse_code"))

        if rule_warehouse and rule_warehouse != warehouse:
            continue

        if not value_in_range(
            metric_percent,
            rule.get("threshold_min"),
            rule.get("threshold_max"),
            parse_bool(rule.get("threshold_min_inclusive")),
            parse_bool(rule.get("threshold_max_inclusive")),
        ):
            continue

        if not value_in_range(
            duration_hours,
            rule.get("duration_min_hours"),
            rule.get("duration_max_hours"),
        ):
            continue

        matches.append(rule)

    if not matches:
        return None

    return sorted(
        matches,
        key=lambda item: (
            int(item.get("priority") or 100),
            0 if str(item.get("day_type") or "") == day_type else 1,
            0 if str(item.get("route_type") or "") == route_type else 1,
            str(item.get("id") or ""),
        ),
    )[0]


def amount_from_rule(rule, row, amount_field):
    if not rule:
        return 0

    amount = int(float(rule.get(amount_field) or 0))
    unit = str(rule.get("calculation_unit") or "per_route")
    route_count = max(to_int(row.get("route_count")) or 0, 1)

    if unit == "per_order":
        return amount * max(to_int(row.get("address_count")) or 0, 0)

    if unit == "per_hour":
        return int(round(amount * planned_route_hours(row)))

    if unit == "fixed":
        return amount

    return amount * route_count


def calculate_group_bonus_amounts(rows, delay_percent, route_quality_bad_percent, day_rules, delay_rules, compliance_rules):
    company_delay = 0
    courier_delay = 0
    company_compliance = 0
    courier_compliance = 0

    for row in rows:
        if row.get("no_show") or not (to_int(row.get("route_count")) or 0):
            continue

        day_type = resolve_day_type(row.get("work_date"), day_rules)
        delay_rule = matching_amount_rule(delay_rules, delay_percent, row, day_type)
        compliance_rule = matching_amount_rule(
            compliance_rules,
            route_quality_bad_percent,
            row,
            day_type,
        )
        company_delay += amount_from_rule(delay_rule, row, "company_amount_huf")
        courier_delay += amount_from_rule(delay_rule, row, "courier_amount_huf")
        company_compliance += amount_from_rule(compliance_rule, row, "company_amount_huf")
        courier_compliance += amount_from_rule(compliance_rule, row, "courier_amount_huf")

    return {
        "company_delay_bonus_huf": company_delay,
        "courier_delay_bonus_huf": courier_delay,
        "company_compliance_bonus_huf": company_compliance,
        "courier_compliance_bonus_huf": courier_compliance,
        "company_quality_bonus_total_huf": company_delay + company_compliance,
        "courier_quality_bonus_total_huf": courier_delay + courier_compliance,
    }


def build_shift_quality_rows(output_rows, booking_lookup, attendance_shift_rows=None):
    grouped = defaultdict(list)

    for row in output_rows:
        key = shift_group_key(row)

        if key:
            grouped[key].append(row)

    rows_by_courier_day = defaultdict(list)
    item_by_match_key = {}
    item_by_shift_id_key = {}

    for shift in attendance_shift_rows or []:
        work_date = str(shift.get("work_date") or "").strip()[:10]
        courier_id = to_int(shift.get("courier_id"))
        shift_start = parse_datetime(shift.get("shift_start"))

        if courier_id is None or not work_date or not shift_start:
            continue

        item = {
            "kind": "attendance",
            "shift_key": str(shift.get("shift_start") or shift.get("shift_id") or ""),
            "shift_start": shift_start,
            "route_rows": [],
            "booking": {},
            "attendance": shift,
        }
        rows_by_courier_day[(work_date, courier_id)].append(item)
        match_key = shift_match_key(
            work_date,
            courier_id,
            shift.get("warehouse_name"),
            shift_start,
        )
        shift_id_key = shift_id_match_key(
            work_date,
            courier_id,
            shift.get("shift_id"),
        )

        if match_key:
            item_by_match_key[match_key] = item

        if shift_id_key:
            item_by_shift_id_key[shift_id_key] = item

    for (work_date, courier_id, shift_key), route_rows in grouped.items():
        first = route_rows[0]
        shift_start = parse_datetime(first.get("shift_start"))
        shift_id_key = shift_id_match_key(
            work_date,
            courier_id,
            first.get("shift_id"),
        )
        match_key = shift_match_key(
            work_date,
            courier_id,
            first.get("warehouse_name"),
            shift_start,
        )
        existing_item = item_by_shift_id_key.get(shift_id_key) or item_by_match_key.get(match_key)

        if existing_item:
            existing_item["route_rows"].extend(route_rows)
            continue

        item = {
            "kind": "route",
            "shift_key": shift_key,
            "shift_start": shift_start,
            "route_rows": route_rows,
            "booking": {},
            "attendance": {},
        }
        rows_by_courier_day[(work_date, courier_id)].append(item)

        if match_key:
            item_by_match_key[match_key] = item

        if shift_id_key:
            item_by_shift_id_key[shift_id_key] = item

    for booking_key, booking_rows in booking_lookup.items():
        for booking in booking_rows:
            work_date, courier_id = booking_key
            shift_start = booking.get("shift_start")
            shift_id_key = shift_id_match_key(
                work_date,
                courier_id,
                booking.get("booking_code"),
            )
            match_key = shift_match_key(
                work_date,
                courier_id,
                booking.get("warehouse"),
                shift_start,
            )
            existing_item = item_by_shift_id_key.get(shift_id_key) or item_by_match_key.get(match_key)

            if existing_item:
                existing_item["booking"] = booking
                continue

            item = {
                "kind": "booking_only",
                "shift_key": f"{work_date}_{booking.get('warehouse') or ''}_{booking.get('shift_text') or booking.get('serial') or len(rows_by_courier_day.get(booking_key, [])) + 1}",
                "shift_start": shift_start,
                "route_rows": [],
                "booking": booking,
                "attendance": {},
            }
            rows_by_courier_day[booking_key].append(item)

            if match_key:
                item_by_match_key[match_key] = item

            if shift_id_key:
                item_by_shift_id_key[shift_id_key] = item

    quality_rows = []

    for (work_date, courier_id), shift_items in rows_by_courier_day.items():
        shift_items.sort(
            key=lambda item: (
                item.get("shift_start") or datetime.max,
                str(item.get("shift_key") or ""),
            )
        )
        previous_record = None

        for index, item in enumerate(shift_items):
            route_rows = item.get("route_rows") or []
            booking = item.get("booking") or {}
            attendance = item.get("attendance") or {}
            first = route_rows[0] if route_rows else attendance or booking
            shift_start = item.get("shift_start") or parse_datetime(first.get("shift_start"))
            shift_end = parse_datetime(first.get("shift_end"))
            queue_started = first_datetime(
                route_rows or [attendance],
                ["queue_started_at", "available_for_shift_since", "available_at", "courier_registered_at"],
            )
            available_at = first_datetime(
                route_rows or [attendance],
                ["available_for_shift_since", "available_at", "courier_registered_at"],
            )
            planned_departure = first_datetime(route_rows, ["planned_departure"])
            real_departure = first_datetime(route_rows, ["real_departure"])
            planned_return = last_datetime(route_rows, ["planned_return"])
            real_return = last_datetime(route_rows, ["real_return"])
            planned_route_minutes = sum(
                to_int(row.get("planned_route_minutes")) or 0
                for row in route_rows
            )
            route_ids = ", ".join(
                str(row.get("route_id") or "")
                for row in route_rows
                if str(row.get("route_id") or "").strip()
            )
            assignment_modes = ", ".join(
                sorted(
                    {
                        str(row.get("assignment_mode") or "").strip()
                        for row in route_rows
                        if str(row.get("assignment_mode") or "").strip()
                    }
                )
            )
            route_type = route_type_from_route_rows(route_rows)
            address_count = sum(to_int(row.get("address_count")) or 0 for row in route_rows)
            time_window_late_count = sum(
                to_int(row.get("time_window_late_count")) or 0 for row in route_rows
            )
            queued_on_time = bool(queue_started and shift_start and queue_started <= shift_start)
            no_show = False
            no_show_reason = ""
            cutoff_exception = False

            if index == 0 and not queued_on_time:
                no_show = True
                no_show_reason = "Elso muszak: nem allt sorba idoben."

            if previous_record and shift_start and not queued_on_time:
                previous_planned = parse_datetime(previous_record.get("planned_return_at"))
                planned_return_before_shift = (
                    previous_planned is not None
                    and previous_planned <= shift_start
                )
                cutoff_exception = is_after_order_cutoff(
                    previous_record.get("planned_return_at")
                )

                if planned_return_before_shift and not cutoff_exception:
                    no_show = True
                    no_show_reason = "Kovetkezo muszak: tervezett visszaerkezese idoben volt, de kesobb allt sorba."
                elif cutoff_exception:
                    no_show = False
                    no_show_reason = "20:45 utani tervezett visszaerkezes, 20:30-as rendelesi zaras miatt nem no show."

            if item.get("kind") == "booking_only":
                no_show = True
                no_show_reason = "Van torteneti foglalas, de nincs hozza DSP route story sor."

            record = {
                "courier_id": courier_id,
                "courier_name": first.get("courier_name"),
                "work_date": work_date,
                "shift_key": str(item.get("shift_key") or ""),
                "shift_name": first.get("shift_name") or booking.get("shift_text"),
                "shift_start_at": serialize_datetime(shift_start),
                "shift_end_at": serialize_datetime(shift_end),
                "warehouse": first.get("warehouse_name") or first.get("warehouse"),
                "booking_code": booking.get("booking_code") or first.get("shift_id"),
                "first_shift_of_day": index == 0,
                "last_shift_of_day": index == len(shift_items) - 1,
                "available_at": serialize_datetime(available_at),
                "queue_started_at": serialize_datetime(queue_started),
                "route_id": route_ids,
                "route_count": len(route_rows),
                "route_type": route_type,
                "assignment_mode": assignment_modes or ("NO_ROUTE" if item.get("kind") == "booking_only" else ""),
                "address_count": address_count,
                "time_window_late_count": time_window_late_count,
                "planned_departure_at": serialize_datetime(planned_departure),
                "planned_return_at": serialize_datetime(planned_return),
                "planned_route_minutes": planned_route_minutes,
                "real_departure_at": serialize_datetime(real_departure),
                "real_return_at": serialize_datetime(real_return),
                "queued_on_time": queued_on_time,
                "no_late_time_window": time_window_late_count <= 0,
                "no_show": no_show,
                "no_show_reason": no_show_reason,
                "late_order_cutoff_exception": cutoff_exception,
                "quality_ok": queued_on_time and time_window_late_count <= 0 and not no_show,
                "source": "dsp_route_story",
                "updated_at": serialize_datetime(datetime.now(BUDAPEST_TZ).replace(tzinfo=None)),
            }
            quality_rows.append(record)
            previous_record = record

    return quality_rows


def upsert_shift_quality_rows(supabase_url, service_role_key, rows, chunk_size=500):
    if not rows:
        return

    endpoint = (
        f"{supabase_url}/rest/v1/{SHIFT_QUALITY_TABLE}"
        "?on_conflict=courier_id,work_date,shift_key"
    )
    headers = supabase_headers(
        service_role_key,
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    skipped_columns = set()

    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        payload = chunk

        if skipped_columns:
            for column_name in skipped_columns:
                payload = remove_column_from_rows(payload, column_name)

        while True:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=60,
            )
            missing_column = missing_column_from_response(response)

            if missing_column:
                skipped_columns.add(missing_column)
                payload = remove_column_from_rows(payload, missing_column)
                print(
                    f"FIGYELEM: {SHIFT_QUALITY_TABLE} tabla nem tartalmazza ezt az oszlopot, "
                    f"feltoltes kozben kihagyva: {missing_column}"
                )
                continue

            raise_for_supabase_error(response, SHIFT_QUALITY_TABLE)
            break

        print(f"Feltoltve: {start + len(chunk)} / {len(rows)} muszak quality")


def month_start_from_date(value):
    parsed = parse_date(str(value)[:10])

    if not parsed:
        return None

    return parsed.replace(day=1)


def summarize_quality_group(rows, scope, period_start=None, day_rules=None, delay_rules=None, compliance_rules=None):
    first = rows[0] if rows else {}
    shift_count = len(rows)
    no_show_count = sum(1 for row in rows if row.get("no_show"))
    show_count = max(shift_count - no_show_count, 0)
    late_shift_count = sum(
        1
        for row in rows
        if not row.get("queued_on_time") and not row.get("no_show")
    )
    route_count = sum(to_int(row.get("route_count")) or 0 for row in rows)
    order_count = sum(to_int(row.get("address_count")) or 0 for row in rows)
    delayed_order_count = sum(
        to_int(row.get("time_window_late_count")) or 0 for row in rows
    )
    delay_percent = safe_percent(delayed_order_count, order_count)
    late_percent = safe_percent(late_shift_count, shift_count)
    no_show_percent = safe_percent(no_show_count, shift_count)
    route_quality_bad_percent = round(
        (0.7 * no_show_percent) + (0.3 * late_percent),
        2,
    )
    compliance_score_percent = round(100 - route_quality_bad_percent, 2)
    bonus_amounts = calculate_group_bonus_amounts(
        rows,
        delay_percent,
        route_quality_bad_percent,
        day_rules or [],
        delay_rules or [],
        compliance_rules or [],
    )
    payload = {
        "courier_id": first.get("courier_id"),
        "courier_name": first.get("courier_name"),
        "scope": scope,
        "shift_count": shift_count,
        "show_count": show_count,
        "no_show_count": no_show_count,
        "late_shift_count": late_shift_count,
        "route_count": route_count,
        "order_count": order_count,
        "delayed_order_count": delayed_order_count,
        "delay_percent": delay_percent,
        "late_percent": late_percent,
        "no_show_percent": no_show_percent,
        "route_quality_bad_percent": route_quality_bad_percent,
        "compliance_score_percent": compliance_score_percent,
        **bonus_amounts,
        "delay_level": delay_level_from_percent(delay_percent),
        "route_quality_level": route_quality_level_from_percent(
            route_quality_bad_percent
        ),
        "source": "dsp_shift_quality",
        "updated_at": serialize_datetime(datetime.now(BUDAPEST_TZ).replace(tzinfo=None)),
    }

    if scope == "daily":
        payload["work_date"] = first.get("work_date")
    else:
        payload["period_month"] = period_start.isoformat() if period_start else None

    return payload


def build_quality_summary_rows(shift_quality_rows, day_rules=None, delay_rules=None, compliance_rules=None):
    daily_groups = defaultdict(list)
    monthly_groups = defaultdict(list)

    for row in shift_quality_rows:
        courier_id = row.get("courier_id")
        work_date = str(row.get("work_date") or "").strip()[:10]
        period_month = month_start_from_date(work_date)

        if courier_id is None or not work_date or not period_month:
            continue

        daily_groups[(work_date, courier_id)].append(row)
        monthly_groups[(period_month, courier_id)].append(row)

    daily_rows = [
        summarize_quality_group(
            rows,
            "daily",
            day_rules=day_rules,
            delay_rules=delay_rules,
            compliance_rules=compliance_rules,
        )
        for _key, rows in sorted(daily_groups.items())
    ]
    monthly_rows = [
        summarize_quality_group(
            rows,
            "monthly",
            period_start=period_month,
            day_rules=day_rules,
            delay_rules=delay_rules,
            compliance_rules=compliance_rules,
        )
        for (period_month, _courier_id), rows in sorted(monthly_groups.items())
    ]

    return daily_rows, monthly_rows


def upsert_quality_summary_rows(
    supabase_url,
    service_role_key,
    table_name,
    rows,
    conflict_columns,
    chunk_size=500,
):
    if not rows:
        return

    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        f"?on_conflict={conflict_columns}"
    )
    headers = supabase_headers(
        service_role_key,
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    skipped_columns = set()

    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        payload = chunk

        if skipped_columns:
            for column_name in skipped_columns:
                payload = remove_column_from_rows(payload, column_name)

        while True:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=60,
            )
            missing_column = missing_column_from_response(response)

            if missing_column:
                skipped_columns.add(missing_column)
                payload = remove_column_from_rows(payload, missing_column)
                print(
                    f"FIGYELEM: {table_name} tabla nem tartalmazza ezt az oszlopot, "
                    f"feltoltes kozben kihagyva: {missing_column}"
                )
                continue

            raise_for_supabase_error(response, table_name)
            break

        print(f"Feltoltve: {start + len(chunk)} / {len(rows)} {table_name}")


def upsert_quality_outputs(
    supabase_url,
    service_role_key,
    shift_quality_rows,
    daily_quality_rows,
    monthly_quality_rows,
):
    upsert_shift_quality_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        rows=shift_quality_rows,
    )
    upsert_quality_summary_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        table_name=DAILY_QUALITY_TABLE,
        rows=daily_quality_rows,
        conflict_columns="courier_id,work_date",
    )
    upsert_quality_summary_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        table_name=MONTHLY_QUALITY_TABLE,
        rows=monthly_quality_rows,
        conflict_columns="courier_id,period_month",
    )


def delete_table_rows_by_date_range(
    supabase_url,
    service_role_key,
    table_name,
    date_column,
    start_date,
    end_date,
):
    endpoint = f"{supabase_url}/rest/v1/{table_name}"
    response = requests.delete(
        endpoint,
        headers=supabase_headers(
            service_role_key,
            {"Prefer": "return=minimal"},
        ),
        params={
            date_column: f"gte.{start_date.isoformat()}",
            "and": f"({date_column}.lte.{end_date.isoformat()})",
        },
        timeout=60,
    )
    raise_for_supabase_error(response, table_name)
    print(f"Torolve: {table_name} {start_date} - {end_date}")


def delete_quality_outputs(supabase_url, service_role_key, start_date, end_date):
    month_start = start_date.replace(day=1)
    month_end = end_date.replace(day=1)

    delete_table_rows_by_date_range(
        supabase_url,
        service_role_key,
        SHIFT_QUALITY_TABLE,
        "work_date",
        start_date,
        end_date,
    )
    delete_table_rows_by_date_range(
        supabase_url,
        service_role_key,
        DAILY_QUALITY_TABLE,
        "work_date",
        start_date,
        end_date,
    )
    delete_table_rows_by_date_range(
        supabase_url,
        service_role_key,
        MONTHLY_QUALITY_TABLE,
        "period_month",
        month_start,
        month_end,
    )


def print_quality_counts(output_rows, shift_quality_rows, daily_quality_rows, monthly_quality_rows):
    print(f"Kesz. Route story sorok: {len(output_rows)}")
    print(f"Kesz. Muszak quality sorok: {len(shift_quality_rows)}")
    print(f"Kesz. Napi quality osszesito sorok: {len(daily_quality_rows)}")
    print(f"Kesz. Havi quality osszesito sorok: {len(monthly_quality_rows)}")


def load_existing_route_story_rows(supabase_url, service_role_key, start_date, end_date):
    rows = read_table_range_by_day(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        table_name=TARGET_TABLE,
        columns=ROUTE_STORY_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,courier_id.asc,route_id.asc",
        page_size=500,
    )
    return rows or []


def load_attendance_shift_rows(supabase_url, service_role_key, start_date, end_date):
    source_tables = []
    shift_rows = []
    seen_keys = set()

    for table_name in ATTENDANCE_RAW_TABLE_CANDIDATES:
        try:
            raw_rows = read_table_range_by_day(
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                table_name=table_name,
                columns=ATTENDANCE_RAW_COLUMNS,
                start_date=start_date,
                end_date=end_date,
                order="work_date.asc",
                page_size=50,
            )
        except Exception as exc:
            print(f"Attendance muszak forras kihagyva ({table_name}): {exc}")
            continue

        if raw_rows is None:
            continue

        parsed_rows = parse_raw_attendance_shift_rows(raw_rows)

        if parsed_rows:
            source_tables.append(table_name)

        for row in parsed_rows:
            key = shift_match_key(
                row.get("work_date"),
                row.get("courier_id"),
                row.get("warehouse_name"),
                row.get("shift_start"),
            )

            if not key or key in seen_keys:
                continue

            seen_keys.add(key)
            shift_rows.append(row)

    return "+".join(source_tables), shift_rows


def load_quality_parameter_rules(supabase_url, service_role_key):
    base_rule_columns = [
        "id",
        "level_code",
        "day_type",
        "route_type",
        "warehouse_code",
        "threshold_min",
        "threshold_max",
        "threshold_min_inclusive",
        "threshold_max_inclusive",
        "duration_min_hours",
        "duration_max_hours",
        "company_amount_huf",
        "courier_amount_huf",
        "calculation_unit",
        "valid_from",
        "valid_to",
        "priority",
    ]
    matrix_rule_columns = ["metric_type", *base_rule_columns]
    matrix_rules = read_public_table(
        supabase_url,
        service_role_key,
        "dsp_jitt_quality_bonus_matrix",
        matrix_rule_columns,
        params={
            "is_active": "eq.true",
            "order": "metric_type.asc,priority.asc",
        },
    )
    if matrix_rules:
        delay_rules = [
            rule for rule in matrix_rules
            if str(rule.get("metric_type") or "").strip().casefold() == "delay"
        ]
        compliance_rules = [
            rule for rule in matrix_rules
            if str(rule.get("metric_type") or "").strip().casefold() == "compliance"
        ]
    else:
        delay_rules = []
        compliance_rules = []

    day_rules = read_settlement_table(
        supabase_url,
        service_role_key,
        "cfg_jitt_day_definitions",
        ["id", "day_type", "weekdays", "valid_from", "valid_to", "priority"],
        order="priority.asc",
    )
    if not delay_rules:
        delay_rules = read_settlement_table(
            supabase_url,
            service_role_key,
            "cfg_jitt_delay_bonus_rules",
            base_rule_columns,
            order="priority.asc",
        )
    if not compliance_rules:
        compliance_rules = read_settlement_table(
            supabase_url,
            service_role_key,
            "cfg_jitt_compliance_bonus_rules",
            base_rule_columns,
            order="priority.asc",
        )
    print(
        "JITT quality parameterek: "
        f"nap={len(day_rules)}, delay={len(delay_rules)}, compliance={len(compliance_rules)}"
    )
    return day_rules, delay_rules, compliance_rules


def rebuild_quality_reports_from_existing_stories(
    supabase_url,
    service_role_key,
    start_date,
    end_date,
    dry_run=False,
):
    output_rows = load_existing_route_story_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        start_date=start_date,
        end_date=end_date,
    )
    booking_table, booking_rows = load_optional_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=BOOKING_TABLE_CANDIDATES,
        columns=BOOKING_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,courier_id.asc,shift_text.asc",
        chunk_by_day=True,
        page_size=500,
    )
    booking_lookup = build_booking_lookup(booking_rows)
    attendance_table, attendance_shift_rows = load_attendance_shift_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        start_date=start_date,
        end_date=end_date,
    )
    day_rules, delay_rules, compliance_rules = load_quality_parameter_rules(
        supabase_url,
        service_role_key,
    )
    shift_quality_rows = build_shift_quality_rows(
        output_rows=output_rows,
        booking_lookup=booking_lookup,
        attendance_shift_rows=attendance_shift_rows,
    )
    daily_quality_rows, monthly_quality_rows = build_quality_summary_rows(
        shift_quality_rows,
        day_rules=day_rules,
        delay_rules=delay_rules,
        compliance_rules=compliance_rules,
    )

    print(f"Meglevo route story forras: {TARGET_TABLE}, sorok: {len(output_rows)}")
    print(f"Foglalas forras: {booking_table or 'nincs'}, sorok: {len(booking_rows)}")
    print(f"Attendance muszak forras: {attendance_table or 'nincs'}, sorok: {len(attendance_shift_rows)}")

    if dry_run:
        print("Dry-run mod: quality DB feltoltes kihagyva.")
    else:
        delete_quality_outputs(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            start_date=start_date,
            end_date=end_date,
        )
        upsert_quality_outputs(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            shift_quality_rows=shift_quality_rows,
            daily_quality_rows=daily_quality_rows,
            monthly_quality_rows=monthly_quality_rows,
        )

    print_quality_counts(
        output_rows,
        shift_quality_rows,
        daily_quality_rows,
        monthly_quality_rows,
    )


def load_stage_sources(supabase_url, service_role_key, start_date, end_date):
    summary_table, summary_rows = read_first_existing_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=SUMMARY_TABLE_CANDIDATES,
        columns=SUMMARY_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,courier_id.asc,route_id.asc",
    )
    arrivals_table, arrivals = read_first_existing_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=ARRIVALS_TABLE_CANDIDATES,
        columns=ARRIVAL_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,driver_id.asc,route_id.asc,position.asc",
    )

    return summary_table, summary_rows, arrivals_table, arrivals


def load_raw_sources(supabase_url, service_role_key, start_date, end_date):
    attendance_table, attendance_raw_rows = read_first_existing_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=ATTENDANCE_RAW_TABLE_CANDIDATES,
        columns=ATTENDANCE_RAW_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc",
        chunk_by_day=True,
        page_size=50,
    )
    detail_table, detail_raw_rows = read_first_existing_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=DRIVER_DETAIL_RAW_TABLE_CANDIDATES,
        columns=DRIVER_DETAIL_RAW_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="driver_id.asc",
        chunk_by_day=True,
        page_size=100,
    )

    summary_rows = parse_raw_attendance_rows(attendance_raw_rows)
    route_detail_lookup = build_route_detail_lookup(detail_raw_rows)
    summary_rows = enrich_summary_with_route_details(
        summary_rows,
        route_detail_lookup,
    )
    arrivals = parse_raw_driver_detail_arrivals(detail_raw_rows)

    return (
        f"{attendance_table} JSON",
        summary_rows,
        f"{detail_table} JSON",
        arrivals,
    )


def load_optional_table(
    supabase_url,
    service_role_key,
    candidates,
    columns,
    start_date,
    end_date,
    order,
    chunk_by_day=False,
    page_size=500,
):
    try:
        table_name, rows = read_first_existing_table(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            candidates=candidates,
            columns=columns,
            start_date=start_date,
            end_date=end_date,
            order=order,
            chunk_by_day=chunk_by_day,
            page_size=page_size,
        )
    except Exception as exc:
        print(f"Opcionális forras kihagyva ({', '.join(candidates)}): {exc}")
        return "", []

    print(f"Opcionális forras tabla: {table_name}, sorok: {len(rows)}")
    return table_name, rows


def load_sources(supabase_url, service_role_key, start_date, end_date, force_raw):
    if not force_raw:
        try:
            stage_sources = load_stage_sources(
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                start_date=start_date,
                end_date=end_date,
            )

            if stage_sources[1]:
                return stage_sources

            print("Stage forras elerheto, de nincs route sor. Raw fallback indul.")
        except Exception as exc:
            print(f"Stage forras nem hasznalhato: {exc}")
            print("Raw fallback indul.")

    return load_raw_sources(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        start_date=start_date,
        end_date=end_date,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="DSP route szoveges tortenetek epitese stage tablakbol."
    )
    parser.add_argument(
        "--start-date",
        default="",
        help=(
            "Kezdo datum YYYY-MM-DD formatumban. "
            "Ha nincs megadva, a script a mart tabla legutolso napjatol frissit."
        ),
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Zaro datum YYYY-MM-DD formatumban. Alap: mai nap Budapest szerint.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak osszerakja es kiirja a route story darabszamot, nem tolt DB-be.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Kozvetlenul a raw JSON tablakbol epit, stage tablak kihagyasaval.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Akkor is ujraepiti a tartomanyt, ha az inkrementalis ellenorzes szerint friss.",
    )
    parser.add_argument(
        "--quality-only",
        action="store_true",
        help="Meglevo mart_dsp_route_stories sorokbol csak a quality riport tablak ujratoltese.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")

    if args.start_date:
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date) if args.end_date else today_budapest()
        if args.quality_only:
            rebuild_quality_reports_from_existing_stories(
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                start_date=start_date,
                end_date=end_date,
                dry_run=args.dry_run,
            )
            return
    else:
        (
            start_date,
            end_date,
            target_latest,
            source_latest_values,
        ) = resolve_incremental_window(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            force_raw=args.raw,
        )

        source_text = ", ".join(
            f"{table_name}={latest_date}"
            for table_name, latest_date in source_latest_values
        ) or "nincs forras datum"
        print(
            f"Inkrementalis ellenorzes: target={target_latest or 'nincs adat'}, "
            f"forrasok: {source_text}"
        )

        if start_date is None and end_date is None:
            if not args.force:
                print("Route story adatok frissek, nincs uj nap amit epiteni kell.")
                if target_latest:
                    quality_start = target_latest.replace(day=1)
                    quality_end = parse_date(args.end_date) if args.end_date else today_budapest()
                    print(
                        "Quality riport visszatoltes meglevo route story sorokbol: "
                        f"{quality_start} - {quality_end}"
                    )
                    rebuild_quality_reports_from_existing_stories(
                        supabase_url=supabase_url,
                        service_role_key=service_role_key,
                        start_date=quality_start,
                        end_date=quality_end,
                        dry_run=args.dry_run,
                    )
                return

            start_date = target_latest or parse_date(DEFAULT_START_DATE)
            end_date = parse_date(args.end_date) if args.end_date else today_budapest()

    if end_date < start_date:
        raise ValueError("Az end-date nem lehet korabbi, mint a start-date.")

    print(f"DSP route story epites: {start_date} - {end_date}")

    summary_table, summary_rows, arrivals_table, arrivals = load_sources(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        start_date=start_date,
        end_date=end_date,
        force_raw=args.raw,
    )

    print(f"Forras summary tabla: {summary_table}, sorok: {len(summary_rows)}")
    print(f"Forras cimsor tabla: {arrivals_table}, sorok: {len(arrivals)}")

    distance_table, distance_rows = load_optional_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=DISTANCE_TABLE_CANDIDATES,
        columns=DISTANCE_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,driver_id.asc,route_id.asc",
        chunk_by_day=True,
        page_size=500,
    )
    booking_table, booking_rows = load_optional_table(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        candidates=BOOKING_TABLE_CANDIDATES,
        columns=BOOKING_COLUMNS,
        start_date=start_date,
        end_date=end_date,
        order="work_date.asc,courier_id.asc,shift_text.asc",
        chunk_by_day=True,
        page_size=500,
    )
    attendance_table, attendance_shift_rows = load_attendance_shift_rows(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        start_date=start_date,
        end_date=end_date,
    )
    day_rules, delay_rules, compliance_rules = load_quality_parameter_rules(
        supabase_url,
        service_role_key,
    )

    arrival_stats = build_arrival_stats(arrivals)
    distance_lookup = build_distance_lookup(distance_rows)
    booking_lookup = build_booking_lookup(booking_rows)
    output_rows = build_output_rows(
        summary_rows=summary_rows,
        arrival_stats=arrival_stats,
        distance_lookup=distance_lookup,
        booking_lookup=booking_lookup,
        source_summary_table=summary_table,
        source_arrivals_table=arrivals_table,
    )
    shift_quality_rows = build_shift_quality_rows(
        output_rows=output_rows,
        booking_lookup=booking_lookup,
        attendance_shift_rows=attendance_shift_rows,
    )
    daily_quality_rows, monthly_quality_rows = build_quality_summary_rows(
        shift_quality_rows,
        day_rules=day_rules,
        delay_rules=delay_rules,
        compliance_rules=compliance_rules,
    )

    if args.dry_run:
        print("Dry-run mod: DB feltoltes kihagyva.")

        for sample in output_rows[:3]:
            print(
                f"MINTA route={sample['route_id']} "
                f"courier={sample['courier_id']} "
                f"story={sample['story_text'][:500]}"
            )
    else:
        upsert_rows(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            rows=output_rows,
        )
        delete_quality_outputs(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            start_date=start_date,
            end_date=end_date,
        )
        upsert_quality_outputs(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            shift_quality_rows=shift_quality_rows,
            daily_quality_rows=daily_quality_rows,
            monthly_quality_rows=monthly_quality_rows,
        )

    print_quality_counts(
        output_rows,
        shift_quality_rows,
        daily_quality_rows,
        monthly_quality_rows,
    )


if __name__ == "__main__":
    main()
