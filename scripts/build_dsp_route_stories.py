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


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
DEFAULT_START_DATE = "2026-06-01"
TARGET_TABLE = "mart_dsp_route_stories"
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
        return f"{format_minutes(abs(value))} perccel korabban"

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

        if "kes" in status or "late" in status:
            stats["time_window_late_count"] += 1
        elif "korai" in status or "early" in status:
            stats["time_window_early_count"] += 1
        else:
            real_arrival = parse_datetime(row.get("valos_erkezes"))
            window_start = parse_datetime(row.get("idoablak_kezdete"))
            window_end = parse_datetime(row.get("idoablak_vege"))

            if real_arrival and window_start and real_arrival < window_start:
                stats["time_window_early_count"] += 1
            elif real_arrival and window_end and real_arrival > window_end:
                stats["time_window_late_count"] += 1

    return grouped


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

    queue_candidates = []

    if assigned_at:
        for shift in shifts:
            available_at = parse_datetime(
                shift.get("available_for_shift_since")
            )

            if not available_at or available_at > assigned_at:
                continue

            queue_candidates.append(
                (
                    abs((assigned_at - available_at).total_seconds()),
                    available_at,
                    shift,
                )
            )

    if queue_candidates:
        queue_candidates.sort(
            key=lambda item: (
                item[0],
                -item[1].timestamp(),
            )
        )
        return queue_candidates[0][2]

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

    if available_at and assigned_at:
        assignment_mode = "QUEUE"
    elif courier_registered_at and assigned_at:
        assignment_mode = "REGISTERED"
    elif assigned_at:
        assignment_mode = "MANUAL"
    else:
        assignment_mode = "UNKNOWN"

    shift_text = (
        f"A muszak {format_datetime(shift_start)} es {format_datetime(shift_end)} kozott volt."
    )

    if available_at:
        availability_text = (
            f"Elerhetonek {format_datetime(available_at)} idopontban jelentkezett, "
            f"ez a muszakkezdeshez kepest {format_queue_delta(queue_entry_delta)} tortent."
        )
    elif courier_registered_at:
        availability_text = (
            f"Kulon availableForShiftSince nem latszik, "
            f"de a DSP route regisztracio {format_datetime(courier_registered_at)} idopontban megtortent, "
            f"ez a muszakkezdeshez kepest {format_queue_delta(queue_entry_delta)} tortent."
        )
    elif assigned_at:
        availability_text = (
            "Nem latszik sorba allas, de van assignedAt, "
            "ezert manualisan raktak ra."
        )
    else:
        availability_text = "Nem latszik sorba allas es tura kiosztas sem."

    assignment_text = (
        f"A turat {format_datetime(assigned_at)} idopontban kapta meg."
    )

    if queue_wait is not None:
        wait_text = f"A turara {format_minutes(queue_wait)} ideig vart."
    elif assigned_at:
        wait_text = "Varakozasi ido nem szamolhato, mert nincs sorba allasi ido."
    else:
        wait_text = "Varakozasi ido nem szamolhato."

    if courier_registered_at:
        registration_text = (
            f"A DSP route regisztracio ideje: {format_datetime(courier_registered_at)}."
        )
    elif assigned_at:
        registration_text = (
            "DSP route regisztracio ideje: nincs adat, "
            "ez manualis tura kiosztast jelez."
        )
    else:
        registration_text = "DSP route regisztracio ideje: nincs adat."

    loading_text = (
        "Bepakolasi ido: "
        f"tervezett {format_minutes(planned_loading)}, "
        f"valos {format_minutes(real_loading)}."
    )
    route_time_text = (
        "Tura hossza: "
        f"tervezett {format_minutes(planned_route)}, "
        f"valos {format_minutes(real_route)}, "
        f"kiosztastol visszaerkezesig {format_minutes(assigned_to_return)}."
    )
    distance_text = (
        "Megtett tavolsag: "
        f"GPS alapjan {format_km(distance.get('gps_distance_km'))}, "
        f"cimek kozti egyenes tavolsag {format_km(distance.get('checkpoint_straight_km'))}."
    )
    booking_count = int(booking.get("booking_shift_count") or 0)
    next_shift_start = booking.get("next_booking_shift_start")
    next_shift_text = booking.get("next_booking_shift_text")
    next_shift_delay = booking.get("next_shift_delay_minutes")
    booking_text = (
        f"A Foglalasok tabla szerint ezen a napon {booking_count} muszakja volt."
    )

    if next_shift_text and next_shift_start:
        if next_shift_delay is None:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}), de a keses nem szamolhato."
            )
        elif next_shift_delay > 0:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}). "
                f"A route visszaerkezese alapjan ebbol {format_minutes(next_shift_delay)} keses lett."
            )
        else:
            next_shift_text_value = (
                f"A kovetkezo foglalt muszak: {next_shift_text} "
                f"({format_datetime(next_shift_start)}). "
                f"A route visszaerkezese alapjan nem kesik, "
                f"{format_minutes(abs(next_shift_delay))} tartalek maradt."
            )
    elif booking_count:
        next_shift_text_value = "A Foglalasok tabla szerint nincs tovabbi aznapi muszak."
    else:
        next_shift_text_value = "A Foglalasok tablaban nincs aznapi muszak adat."

    address_text = (
        f"Cimek: {stats['address_count']} db. "
        f"Tervezetthez kepest korai: {stats['planned_early_count']} db, "
        f"keso: {stats['planned_late_count']} db. "
        f"Idokapuhoz kepest korai: {stats['time_window_early_count']} db, "
        f"keso: {stats['time_window_late_count']} db."
    )

    story_text = " ".join(
        [
            shift_text,
            availability_text,
            assignment_text,
            wait_text,
            registration_text,
            loading_text,
            route_time_text,
            distance_text,
            booking_text,
            next_shift_text_value,
            address_text,
        ]
    )

    return {
        "shift_start": shift_start,
        "shift_end": shift_end,
        "available_for_shift_since": available_at,
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
                "available_for_shift_since": serialize_datetime(
                    story["available_for_shift_since"]
                ),
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
                "assigned_to_return_minutes": story["assigned_to_return_minutes"],
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
        default=DEFAULT_START_DATE,
        help="Kezdo datum YYYY-MM-DD formatumban. Alap: 2026-06-01.",
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
    return parser.parse_args()


def main():
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else today_budapest()

    if end_date < start_date:
        raise ValueError("Az end-date nem lehet korabbi, mint a start-date.")

    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")

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

    print(f"Kesz. Route story sorok: {len(output_rows)}")


if __name__ == "__main__":
    main()
