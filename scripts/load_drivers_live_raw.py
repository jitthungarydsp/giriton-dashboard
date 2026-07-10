import argparse
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

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
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_SQL_PATH = PROJECT_ROOT / "docs" / "dsp_live_driver_tables.sql"


def get_required_env(name):
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value


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
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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


def build_rows(payload, request_url, status_code, fetch_batch_id, fetched_at):
    agency_id = payload.get("agency_id")
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
    fetch_batch_id = str(uuid4())
    raw_rows, km_rows = build_rows(
        payload,
        request_url,
        status_code,
        fetch_batch_id,
        fetched_at,
    )

    print(
        f"fetch-drivers status={status_code} drivers={len(raw_rows)} route_km={len(km_rows)} batch={fetch_batch_id}"
    )

    if args.dry_run:
        return

    database_url = get_required_env("DATABASE_URL")

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            ensure_tables(cursor)
            raw_count = insert_raw_rows(cursor, raw_rows)
            km_count = upsert_km_rows(cursor, km_rows)
            connection.commit()

    print(
        f"DB kesz: raw_snapshot={raw_count}, route_km_upsert={km_count}"
    )


if __name__ == "__main__":
    main()
