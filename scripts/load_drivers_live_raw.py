import argparse
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests

try:
    import psycopg2
    from psycopg2.extras import Json, execute_values
except ImportError:
    print("Hianyzik a psycopg2-binary csomag. Telepites: pip install psycopg2-binary")
    raise

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-drivers"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_SQL_PATH = PROJECT_ROOT / "docs" / "dsp_live_driver_tables.sql"
RAW_COLUMNS = [
    "fetch_batch_id",
    "source_name",
    "organization_id",
    "dsp_id",
    "agency_id",
    "driver_id",
    "courier_name",
    "warehouse_name",
    "active",
    "license_plate",
    "current_state",
    "route_assigned_at",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "courier_registered_at",
    "attendance_assigned_at",
    "queue_wait_minutes",
    "fetched_at",
    "request_url",
    "status_code",
    "response_json",
]
KM_COLUMNS = [
    "driver_id",
    "route_assigned_at",
    "courier_name",
    "warehouse_name",
    "license_plate",
    "active",
    "current_state",
    "next_stop",
    "is_departure_delayed",
    "delay_minutes",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "courier_registered_at",
    "attendance_assigned_at",
    "queue_wait_minutes",
    "temperature",
    "last_measurement_timestamp",
    "loading_finished_at",
    "warehouse_departure_real",
    "total_distance_km",
    "distance_covered_km",
    "parcels_delivered",
    "parcels_total",
    "last_seen_at",
    "last_raw_fetch_batch_id",
]


def get_required_env(name):
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value


def get_optional_env(name):
    return os.getenv(name, "").strip()


def build_fetch_drivers_url():
    return (
        f"{KIFLI_API_BASE_URL}/fetch-drivers"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )


def fetch_drivers():
    url = build_fetch_drivers_url()
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()
    return url, response.status_code, response.json()


def build_fetch_attendance_url(work_date):
    return (
        f"{KIFLI_API_BASE_URL}/fetch-attendance/{DSP_ID}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )


def fetch_attendance(work_date):
    url = build_fetch_attendance_url(work_date)
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()
    return url, response.status_code, response.json()


def nested_get(data, *keys):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

        if current is None:
            return None

    return current


def first_value(*values):
    for value in values:
        if value not in [None, ""]:
            return value

    return None


def parse_timestamp(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def to_decimal(value):
    if value in [None, ""]:
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def to_int(value):
    if value in [None, ""]:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get_route_assigned_at(driver):
    return first_value(
        nested_get(driver, "route", "route_assigned_at"),
        nested_get(driver, "route", "routeAssignedAt"),
        nested_get(driver, "route", "assignedAt"),
        nested_get(driver, "status", "route_assigned_at"),
        nested_get(driver, "status", "routeAssignedAt"),
        nested_get(driver, "status", "assignedAt"),
        driver.get("route_assigned_at"),
        driver.get("routeAssignedAt"),
    )


def get_statistics(driver):
    route_statistics = nested_get(driver, "route", "statistics")

    if isinstance(route_statistics, dict):
        return route_statistics

    statistics = driver.get("statistics")

    if isinstance(statistics, dict):
        return statistics

    return {}


def build_attendance_by_driver(payload):
    couriers = []

    for key in ["couriers", "drivers", "data"]:
        value = payload.get(key)

        if isinstance(value, list):
            couriers = value
            break

    attendance_by_driver = {}

    for courier in couriers:
        driver_id = to_int(
            first_value(
                courier.get("courierId"),
                courier.get("driver_id"),
                courier.get("courier_id"),
            )
        )

        if driver_id is not None:
            attendance_by_driver[driver_id] = courier

    return attendance_by_driver


def sort_timestamp(value, fallback):
    return value or fallback


def select_attendance_shift(courier, now):
    shifts = []

    for shift in courier.get("shifts", []) or []:
        start_at = parse_timestamp(shift.get("shiftStart"))
        end_at = parse_timestamp(shift.get("shiftEnd"))
        available_since = parse_timestamp(shift.get("availableForShiftSince"))
        shifts.append(
            {
                "raw": shift,
                "shift_id": str(shift.get("shiftId") or "").strip() or None,
                "shift_name": str(shift.get("shiftName") or "").strip(),
                "shift_start": start_at,
                "shift_end": end_at,
                "available_for_shift_since": available_since,
            }
        )

    if not shifts:
        return {}

    active_window_start = now - timedelta(minutes=15)
    active_or_future = [
        shift
        for shift in shifts
        if shift["shift_end"] is None or shift["shift_end"] >= active_window_start
    ]
    with_queue_time = [
        shift
        for shift in active_or_future
        if shift["available_for_shift_since"] is not None
    ]

    if with_queue_time:
        return sorted(
            with_queue_time,
            key=lambda item: sort_timestamp(
                item["shift_start"],
                datetime.max.replace(tzinfo=timezone.utc),
            ),
        )[0]

    if active_or_future:
        return sorted(
            active_or_future,
            key=lambda item: sort_timestamp(
                item["shift_start"],
                datetime.max.replace(tzinfo=timezone.utc),
            ),
        )[0]

    return sorted(
        shifts,
        key=lambda item: sort_timestamp(
            item["shift_start"],
            datetime.min.replace(tzinfo=timezone.utc),
        ),
    )[-1]


def timestamps_match(left, right, tolerance_seconds=90):
    if left is None or right is None:
        return False

    return abs((left - right).total_seconds()) <= tolerance_seconds


def select_attendance_route(courier, route_assigned_at):
    routes = courier.get("routes", []) or []

    if not routes:
        return {}

    normalized_routes = []

    for route in routes:
        assigned_at = parse_timestamp(route.get("assignedAt"))
        registered_at = parse_timestamp(route.get("courierRegisteredAt"))
        normalized_routes.append(
            {
                "raw": route,
                "assigned_at": assigned_at,
                "registered_at": registered_at,
                "real_return": parse_timestamp(route.get("realReturn")),
            }
        )

    if route_assigned_at is not None:
        for route in normalized_routes:
            if timestamps_match(route["assigned_at"], route_assigned_at):
                return route

    open_routes = [
        route
        for route in normalized_routes
        if route["real_return"] is None
    ]

    if open_routes:
        return sorted(
            open_routes,
            key=lambda item: sort_timestamp(
                item["assigned_at"] or item["registered_at"],
                datetime.min.replace(tzinfo=timezone.utc),
            ),
        )[-1]

    return sorted(
        normalized_routes,
        key=lambda item: sort_timestamp(
            item["assigned_at"] or item["registered_at"],
            datetime.min.replace(tzinfo=timezone.utc),
        ),
    )[-1]


def calculate_queue_wait_minutes(available_since, courier_registered_at, assigned_at, fetched_at):
    if available_since is None:
        return None

    wait_until = None

    for candidate in [courier_registered_at, assigned_at, fetched_at]:
        if candidate is not None and candidate >= available_since:
            wait_until = candidate
            break

    if wait_until is None:
        return None

    return int(round((wait_until - available_since).total_seconds() / 60))


def get_attendance_info(attendance_by_driver, driver_id, route_assigned_at, fetched_at):
    courier = attendance_by_driver.get(driver_id) or {}
    shift = select_attendance_shift(courier, fetched_at)
    route = select_attendance_route(courier, route_assigned_at)
    route_raw = route.get("raw", {}) or {}
    courier_registered_at = parse_timestamp(route_raw.get("courierRegisteredAt"))
    attendance_assigned_at = parse_timestamp(route_raw.get("assignedAt"))
    available_since = shift.get("available_for_shift_since")

    return {
        "shift_id": shift.get("shift_id"),
        "shift_name": shift.get("shift_name"),
        "shift_start": shift.get("shift_start"),
        "shift_end": shift.get("shift_end"),
        "available_for_shift_since": available_since,
        "courier_registered_at": courier_registered_at,
        "attendance_assigned_at": attendance_assigned_at,
        "queue_wait_minutes": calculate_queue_wait_minutes(
            available_since,
            courier_registered_at,
            attendance_assigned_at,
            fetched_at,
        ),
    }


def build_rows(payload, request_url, status_code, fetch_batch_id, fetched_at, attendance_by_driver=None):
    agency_id = payload.get("agency_id")
    attendance_by_driver = attendance_by_driver or {}
    raw_rows = []
    km_rows = []

    for driver in payload.get("drivers", []) or []:
        driver_id = to_int(driver.get("driver_id"))

        if driver_id is None:
            continue

        personal_info = driver.get("personal_info", {}) or {}
        vehicle = driver.get("vehicle", {}) or {}
        status = driver.get("status", {}) or {}
        route_assigned_at = parse_timestamp(
            get_route_assigned_at(driver)
        )
        statistics = get_statistics(driver)
        courier_name = str(personal_info.get("name") or "").strip()
        warehouse_name = str(personal_info.get("warehouse_name") or "").strip()
        license_plate = str(vehicle.get("license_plate") or "").strip()
        current_state = str(status.get("current_state") or "").strip()
        attendance_info = get_attendance_info(
            attendance_by_driver,
            driver_id,
            route_assigned_at,
            fetched_at,
        )

        raw_rows.append(
            (
                fetch_batch_id,
                SOURCE_NAME,
                ORGANIZATION_ID,
                DSP_ID,
                agency_id,
                driver_id,
                courier_name,
                warehouse_name,
                driver.get("active"),
                license_plate,
                current_state,
                route_assigned_at,
                attendance_info["shift_id"],
                attendance_info["shift_name"],
                attendance_info["shift_start"],
                attendance_info["shift_end"],
                attendance_info["available_for_shift_since"],
                attendance_info["courier_registered_at"],
                attendance_info["attendance_assigned_at"],
                attendance_info["queue_wait_minutes"],
                fetched_at,
                request_url,
                status_code,
                Json(driver),
            )
        )

        if route_assigned_at is None:
            continue

        km_rows.append(
            (
                driver_id,
                route_assigned_at,
                courier_name,
                warehouse_name,
                license_plate,
                driver.get("active"),
                current_state,
                status.get("next_stop"),
                status.get("is_departure_delayed"),
                to_int(status.get("delay_minutes")),
                attendance_info["shift_id"],
                attendance_info["shift_name"],
                attendance_info["shift_start"],
                attendance_info["shift_end"],
                attendance_info["available_for_shift_since"],
                attendance_info["courier_registered_at"],
                attendance_info["attendance_assigned_at"],
                attendance_info["queue_wait_minutes"],
                to_decimal(vehicle.get("temperature")),
                parse_timestamp(vehicle.get("last_measurement_timestamp")),
                parse_timestamp(status.get("loading_finished_at")),
                parse_timestamp(status.get("warehouse_departure_real")),
                to_decimal(statistics.get("total_distance_km")),
                to_decimal(statistics.get("distance_covered_km")),
                to_int(statistics.get("parcels_delivered")),
                to_int(statistics.get("parcels_total")),
                fetched_at,
                fetch_batch_id,
            )
        )

    return raw_rows, km_rows


def ensure_tables(cursor):
    if not TABLE_SQL_PATH.exists():
        raise RuntimeError(
            f"Hianyzik a tabla SQL fajl: {TABLE_SQL_PATH}"
        )

    cursor.execute(
        TABLE_SQL_PATH.read_text(encoding="utf-8")
    )


def serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if hasattr(value, "adapted"):
        return value.adapted

    return value


def rows_to_dicts(columns, rows):
    return [
        {
            column: serialize_value(value)
            for column, value in zip(columns, row)
        }
        for row in rows
    ]


def raise_for_supabase_error(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()

        if detail:
            raise requests.HTTPError(
                f"{exc}; Supabase valasz: {detail[:1000]}",
                response=response,
            ) from exc

        raise


def post_supabase_rows(table_name, rows, columns, on_conflict, prefer):
    if not rows:
        return 0

    supabase_url = get_required_env("SUPABASE_URL").rstrip("/")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = f"{supabase_url}/rest/v1/{table_name}"

    if on_conflict:
        endpoint = f"{endpoint}?on_conflict={on_conflict}"

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows_to_dicts(columns, rows),
        timeout=60,
    )
    raise_for_supabase_error(response)
    return len(rows)


def insert_raw_rows_rest(rows):
    return post_supabase_rows(
        "dsp_drivers_live_raw",
        rows,
        RAW_COLUMNS,
        "fetch_batch_id,driver_id",
        "resolution=ignore-duplicates,return=minimal",
    )


def upsert_km_rows_rest(rows):
    return post_supabase_rows(
        "dsp_route_km_latest",
        rows,
        KM_COLUMNS,
        "driver_id,route_assigned_at",
        "resolution=merge-duplicates,return=minimal",
    )


def insert_raw_rows(cursor, rows):
    if not rows:
        return 0

    sql = """
        insert into public.dsp_drivers_live_raw (
            fetch_batch_id,
            source_name,
            organization_id,
            dsp_id,
            agency_id,
            driver_id,
            courier_name,
            warehouse_name,
            active,
            license_plate,
            current_state,
            route_assigned_at,
            shift_id,
            shift_name,
            shift_start,
            shift_end,
            available_for_shift_since,
            courier_registered_at,
            attendance_assigned_at,
            queue_wait_minutes,
            fetched_at,
            request_url,
            status_code,
            response_json
        )
        values %s
        on conflict (fetch_batch_id, driver_id)
        do nothing
    """
    execute_values(cursor, sql, rows, page_size=100)
    return len(rows)


def upsert_km_rows(cursor, rows):
    if not rows:
        return 0

    sql = """
        insert into public.dsp_route_km_latest (
            driver_id,
            route_assigned_at,
            courier_name,
            warehouse_name,
            license_plate,
            active,
            current_state,
            next_stop,
            is_departure_delayed,
            delay_minutes,
            shift_id,
            shift_name,
            shift_start,
            shift_end,
            available_for_shift_since,
            courier_registered_at,
            attendance_assigned_at,
            queue_wait_minutes,
            temperature,
            last_measurement_timestamp,
            loading_finished_at,
            warehouse_departure_real,
            total_distance_km,
            distance_covered_km,
            parcels_delivered,
            parcels_total,
            last_seen_at,
            last_raw_fetch_batch_id
        )
        values %s
        on conflict (driver_id, route_assigned_at)
        do update set
            courier_name = excluded.courier_name,
            warehouse_name = excluded.warehouse_name,
            license_plate = excluded.license_plate,
            active = excluded.active,
            current_state = excluded.current_state,
            next_stop = excluded.next_stop,
            is_departure_delayed = excluded.is_departure_delayed,
            delay_minutes = excluded.delay_minutes,
            shift_id = excluded.shift_id,
            shift_name = excluded.shift_name,
            shift_start = excluded.shift_start,
            shift_end = excluded.shift_end,
            available_for_shift_since = excluded.available_for_shift_since,
            courier_registered_at = excluded.courier_registered_at,
            attendance_assigned_at = excluded.attendance_assigned_at,
            queue_wait_minutes = excluded.queue_wait_minutes,
            temperature = excluded.temperature,
            last_measurement_timestamp = excluded.last_measurement_timestamp,
            loading_finished_at = excluded.loading_finished_at,
            warehouse_departure_real = excluded.warehouse_departure_real,
            total_distance_km = excluded.total_distance_km,
            distance_covered_km = excluded.distance_covered_km,
            parcels_delivered = excluded.parcels_delivered,
            parcels_total = excluded.parcels_total,
            last_seen_at = excluded.last_seen_at,
            last_raw_fetch_batch_id = excluded.last_raw_fetch_batch_id,
            updated_at = now()
    """
    execute_values(cursor, sql, rows, page_size=100)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="fetch-drivers live RAW es route km logger."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API-t hiv, de DB-be nem ir.",
    )
    args = parser.parse_args()

    request_url, status_code, payload = fetch_drivers()
    fetched_at = datetime.now(timezone.utc)
    work_date = fetched_at.astimezone(LOCAL_TIMEZONE).date().isoformat()
    attendance_by_driver = {}

    try:
        attendance_url, attendance_status, attendance_payload = fetch_attendance(work_date)
        attendance_by_driver = build_attendance_by_driver(attendance_payload)
        print(
            f"fetch-attendance status={attendance_status} date={work_date} couriers={len(attendance_by_driver)} url={attendance_url}"
        )
    except requests.RequestException as exc:
        print(
            f"FIGYELEM: fetch-attendance sikertelen date={work_date}: {exc}"
        )

    fetch_batch_id = str(uuid4())
    raw_rows, km_rows = build_rows(
        payload,
        request_url,
        status_code,
        fetch_batch_id,
        fetched_at,
        attendance_by_driver,
    )

    print(
        f"fetch-drivers status={status_code} drivers={len(raw_rows)} route_km={len(km_rows)} batch={fetch_batch_id}"
    )

    if args.dry_run:
        return

    database_url = get_optional_env("DATABASE_URL")

    if database_url:
        with psycopg2.connect(database_url) as connection:
            with connection.cursor() as cursor:
                ensure_tables(cursor)
                raw_count = insert_raw_rows(cursor, raw_rows)
                km_count = upsert_km_rows(cursor, km_rows)
                connection.commit()
    else:
        raw_count = insert_raw_rows_rest(raw_rows)
        km_count = upsert_km_rows_rest(km_rows)

    print(
        f"DB kesz: raw_snapshot={raw_count}, route_km_upsert={km_count}"
    )


if __name__ == "__main__":
    main()
