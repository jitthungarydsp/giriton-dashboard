import argparse
import math
import os
import tomllib
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SOURCE_NAME = "fetch-drivers-detail"
CALCULATION_VERSION = "gps_v1"
DEFAULT_MAX_SPEED_KMH = 130
DEFAULT_MAX_SEGMENT_KM = 5
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_SQL_PATH = PROJECT_ROOT / "docs" / "dsp_route_distance_calculated.sql"
DRIVER_DETAIL_RAW_TABLE_CANDIDATES = [
    "raw_dsp_driver_detail",
    "dsp_driver_detail_raw",
]
ROUTE_DISTANCE_TABLE_CANDIDATES = [
    "stg_dsp_route_distance",
    "dsp_route_distance_calculated",
]
ROUTE_DISTANCE_COLUMNS = [
    "source_name",
    "calculation_version",
    "driver_id",
    "work_date",
    "route_id",
    "warehouse_name",
    "real_departure",
    "real_return",
    "planned_departure",
    "planned_return",
    "gps_distance_km",
    "checkpoint_straight_km",
    "gps_points_count",
    "gps_segments_count",
    "outlier_segments_count",
    "checkpoints_count",
    "max_speed_kmh",
    "max_segment_km",
    "first_location_at",
    "last_location_at",
    "calculated_at",
    "raw_fetched_at",
]


def get_required_env(name):
    value = get_setting(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value


def get_optional_env(name):
    return get_setting(name)


def get_setting(name):
    value = os.getenv(name, "").strip()

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

    value = secrets.get(name)

    if value:
        return str(value).strip()

    supabase_section = secrets.get("supabase", {})

    if isinstance(supabase_section, dict):
        value = supabase_section.get(name)

        if value:
            return str(value).strip()

    return ""


def parse_date(value):
    if not value:
        return None

    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_dates(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


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


def iso_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()

    return value


def decimal_to_json(value):
    if isinstance(value, Decimal):
        return float(value)

    return value


def normalize_id(value):
    if value in [None, ""]:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        return text[:-2]

    return text


def to_int(value):
    if value in [None, ""]:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value):
    if value in [None, ""]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round_decimal(value, digits=3):
    if value is None:
        return None

    return round(float(value), digits)


def haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


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


def supabase_headers():
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


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


def table_exists(table_name, select_column="work_date"):
    supabase_url = get_required_env("SUPABASE_URL").rstrip("/")
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        f"?select={select_column}&limit=1"
    )
    response = requests.get(
        endpoint,
        headers=supabase_headers(),
        timeout=30,
    )

    if is_missing_table_response(response):
        return False

    raise_for_supabase_error(response)
    return True


def resolve_table(candidates, select_column="work_date"):
    for table_name in candidates:
        if table_exists(table_name, select_column=select_column):
            return table_name

    raise RuntimeError(
        "Egyik Supabase tabla sem talalhato: "
        + ", ".join(candidates)
    )


def is_statement_timeout_error(exc):
    text = str(exc).lower()
    return "57014" in text or "statement timeout" in text or "canceling statement" in text


def read_driver_detail_raw_day(
    supabase_url,
    table_name,
    work_date,
    driver_id=None,
    limit=20000,
    page_size=100,
):
    filters = [
        "select=driver_id,work_date,response_json,fetched_at",
        "order=driver_id.asc",
        f"work_date=eq.{work_date.isoformat()}",
    ]

    if driver_id:
        filters.append(f"driver_id=eq.{int(driver_id)}")

    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        f"?{'&'.join(filters)}"
    )
    rows = []
    headers_base = supabase_headers()
    total_limit = int(limit)
    chunk_size = max(min(int(page_size), 500), 1)

    while len(rows) < total_limit:
        range_start = len(rows)
        range_end = min(range_start + chunk_size - 1, total_limit - 1)
        headers = {
            **headers_base,
            "Range-Unit": "items",
            "Range": f"{range_start}-{range_end}",
        }
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=120,
        )

        try:
            raise_for_supabase_error(response)
        except requests.HTTPError as exc:
            if chunk_size <= 10 or not is_statement_timeout_error(exc):
                raise

            chunk_size = max(chunk_size // 2, 10)
            print(
                f"Supabase timeout {work_date.isoformat()} napon, "
                f"kisebb lapmeret: {chunk_size}"
            )
            continue

        chunk = response.json()

        if not chunk:
            break

        rows.extend(chunk)

        if len(chunk) < (range_end - range_start + 1):
            break

    return rows


def read_driver_detail_raw(start_date, end_date, driver_id=None, limit=20000, page_size=100):
    supabase_url = get_required_env("SUPABASE_URL").rstrip("/")
    table_name = resolve_table(DRIVER_DETAIL_RAW_TABLE_CANDIDATES)
    rows = []
    total_limit = int(limit)

    for work_date in iter_dates(start_date, end_date):
        remaining_limit = total_limit - len(rows)

        if remaining_limit <= 0:
            break

        daily_rows = read_driver_detail_raw_day(
            supabase_url=supabase_url,
            table_name=table_name,
            work_date=work_date,
            driver_id=driver_id,
            limit=remaining_limit,
            page_size=page_size,
        )
        rows.extend(daily_rows)
        print(f"RAW driver-detail {work_date.isoformat()}: {len(daily_rows)} sor")

    return rows


def normalize_locations(locations):
    normalized = []

    for location in locations or []:
        location_time = parse_timestamp(location.get("time"))
        latitude = to_float(location.get("latitude"))
        longitude = to_float(location.get("longitude"))

        if location_time is None or latitude is None or longitude is None:
            continue

        normalized.append(
            {
                "time": location_time,
                "latitude": latitude,
                "longitude": longitude,
                "order_id": normalize_id(location.get("orderId")),
            }
        )

    return sorted(normalized, key=lambda item: item["time"])


def route_time_window(route, locations):
    start_at = parse_timestamp(
        route.get("realDeparture") or route.get("plannedDeparture")
    )
    end_at = parse_timestamp(
        route.get("realReturn") or route.get("plannedReturn")
    )

    if start_at is None:
        return None, None

    if end_at is None and locations:
        end_at = locations[-1]["time"]

    return start_at, end_at


def calculate_gps_distance(route, locations, max_speed_kmh, max_segment_km):
    start_at, end_at = route_time_window(route, locations)

    if start_at is None or end_at is None:
        return {
            "distance_km": None,
            "points_count": 0,
            "segments_count": 0,
            "outlier_segments_count": 0,
            "first_location_at": None,
            "last_location_at": None,
        }

    route_locations = [
        location
        for location in locations
        if start_at <= location["time"] <= end_at
    ]

    if len(route_locations) < 2:
        return {
            "distance_km": 0,
            "points_count": len(route_locations),
            "segments_count": 0,
            "outlier_segments_count": 0,
            "first_location_at": route_locations[0]["time"] if route_locations else None,
            "last_location_at": route_locations[-1]["time"] if route_locations else None,
        }

    total_km = 0
    segments_count = 0
    outlier_segments_count = 0
    previous = route_locations[0]

    for current in route_locations[1:]:
        seconds = (current["time"] - previous["time"]).total_seconds()
        distance_km = haversine_km(
            previous["latitude"],
            previous["longitude"],
            current["latitude"],
            current["longitude"],
        )
        speed_kmh = distance_km / (seconds / 3600) if seconds > 0 else 9999

        if (
            seconds > 0
            and speed_kmh <= max_speed_kmh
            and distance_km <= max_segment_km
        ):
            total_km += distance_km
            segments_count += 1
        else:
            outlier_segments_count += 1

        previous = current

    return {
        "distance_km": total_km,
        "points_count": len(route_locations),
        "segments_count": segments_count,
        "outlier_segments_count": outlier_segments_count,
        "first_location_at": route_locations[0]["time"],
        "last_location_at": route_locations[-1]["time"],
    }


def checkpoint_straight_distance(route):
    checkpoints = sorted(
        route.get("checkpoints", []) or [],
        key=lambda item: item.get("position") or 999999,
    )
    points = []

    for checkpoint in checkpoints:
        latitude = to_float(checkpoint.get("latitude"))
        longitude = to_float(checkpoint.get("longitude"))

        if latitude is not None and longitude is not None:
            points.append((latitude, longitude))

    if len(points) < 2:
        return 0, len(points)

    total_km = 0

    for previous, current in zip(points, points[1:]):
        total_km += haversine_km(
            previous[0],
            previous[1],
            current[0],
            current[1],
        )

    return total_km, len(points)


def build_distance_rows(raw_rows, max_speed_kmh, max_segment_km):
    rows = []
    calculated_at = datetime.now(timezone.utc)

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        driver_id = to_int(raw.get("driver_id") or response_json.get("courier-id"))
        work_date = raw.get("work_date")
        warehouse_name = response_json.get("warehouseName") or ""
        locations = normalize_locations(response_json.get("locations", []))
        raw_fetched_at = parse_timestamp(raw.get("fetched_at"))

        if driver_id is None or not work_date:
            continue

        for route in response_json.get("routes", []) or []:
            route_id = normalize_id(route.get("id") or route.get("routeId"))

            if not route_id:
                continue

            gps = calculate_gps_distance(
                route,
                locations,
                max_speed_kmh,
                max_segment_km,
            )
            checkpoint_km, checkpoints_count = checkpoint_straight_distance(route)

            rows.append(
                {
                    "source_name": SOURCE_NAME,
                    "calculation_version": CALCULATION_VERSION,
                    "driver_id": driver_id,
                    "work_date": work_date,
                    "route_id": route_id,
                    "warehouse_name": warehouse_name,
                    "real_departure": iso_datetime(parse_timestamp(route.get("realDeparture"))),
                    "real_return": iso_datetime(parse_timestamp(route.get("realReturn"))),
                    "planned_departure": iso_datetime(parse_timestamp(route.get("plannedDeparture"))),
                    "planned_return": iso_datetime(parse_timestamp(route.get("plannedReturn"))),
                    "gps_distance_km": round_decimal(gps["distance_km"]),
                    "checkpoint_straight_km": round_decimal(checkpoint_km),
                    "gps_points_count": gps["points_count"],
                    "gps_segments_count": gps["segments_count"],
                    "outlier_segments_count": gps["outlier_segments_count"],
                    "checkpoints_count": checkpoints_count,
                    "max_speed_kmh": max_speed_kmh,
                    "max_segment_km": max_segment_km,
                    "first_location_at": iso_datetime(gps["first_location_at"]),
                    "last_location_at": iso_datetime(gps["last_location_at"]),
                    "calculated_at": calculated_at.isoformat(),
                    "raw_fetched_at": iso_datetime(raw_fetched_at),
                }
            )

    return rows


def upsert_distance_rows(rows, batch_size=200):
    if not rows:
        return 0

    supabase_url = get_required_env("SUPABASE_URL").rstrip("/")
    table_name = resolve_table(ROUTE_DISTANCE_TABLE_CANDIDATES)
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?on_conflict=calculation_version,driver_id,work_date,route_id"
    )
    headers = {
        **supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    total = 0

    for index in range(0, len(rows), batch_size):
        batch = [
            {
                key: decimal_to_json(row.get(key))
                for key in ROUTE_DISTANCE_COLUMNS
            }
            for row in rows[index:index + batch_size]
        ]
        response = requests.post(
            endpoint,
            headers=headers,
            json=batch,
            timeout=60,
        )
        raise_for_supabase_error(response)
        total += len(batch)

    return total


def ensure_table_if_possible():
    database_url = get_optional_env("DATABASE_URL")

    if not database_url:
        return

    if psycopg2 is None:
        print("DATABASE_URL van, de psycopg2 nincs telepitve, tabla letrehozas kihagyva.")
        return

    if not TABLE_SQL_PATH.exists():
        raise RuntimeError(
            f"Hianyzik a tabla SQL fajl: {TABLE_SQL_PATH}"
        )

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                TABLE_SQL_PATH.read_text(encoding="utf-8")
            )
            connection.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Route GPS kilometer szamitas dsp_driver_detail_raw JSON-bol."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Kezdo datum YYYY-MM-DD formatumban.",
    )
    parser.add_argument(
        "--end-date",
        required=False,
        help="Zaro datum YYYY-MM-DD formatumban. Ha nincs, a kezdo datum lesz.",
    )
    parser.add_argument(
        "--driver-id",
        required=False,
        type=int,
        help="Opcionalis futar ID szures.",
    )
    parser.add_argument(
        "--max-speed-kmh",
        type=float,
        default=DEFAULT_MAX_SPEED_KMH,
        help="E feletti GPS szakasz outlier.",
    )
    parser.add_argument(
        "--max-segment-km",
        type=float,
        default=DEFAULT_MAX_SEGMENT_KM,
        help="E feletti egy szakasz outlier.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Szamol, de nem ir DB-be.",
    )
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else start_date

    if start_date is None or end_date is None:
        parser.error(
            "Hibas datum. Formatum: YYYY-MM-DD."
        )

    if end_date < start_date:
        parser.error(
            "--end-date nem lehet kisebb, mint --start-date."
        )

    raw_rows = read_driver_detail_raw(
        start_date,
        end_date,
        driver_id=args.driver_id,
    )
    distance_rows = build_distance_rows(
        raw_rows,
        args.max_speed_kmh,
        args.max_segment_km,
    )

    print(
        f"RAW sorok: {len(raw_rows)} | route distance sorok: {len(distance_rows)}"
    )

    for row in distance_rows[:5]:
        print(
            f"MINTA {row['work_date']} #{row['driver_id']} route {row['route_id']} gps={row['gps_distance_km']} km pont={row['gps_points_count']} outlier={row['outlier_segments_count']}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    ensure_table_if_possible()
    upserted = upsert_distance_rows(distance_rows)
    print(
        f"DB feltoltes kesz: {upserted} route distance sor"
    )


if __name__ == "__main__":
    main()
