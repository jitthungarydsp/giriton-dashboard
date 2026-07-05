import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.api import BASE_URL, DEPOT_ID, ORGANIZATION_ID
from resources.discord_notifier import (
    notify_route_assigned_once,
    read_discord_status,
)
from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
NOTIFICATION_TABLE = "discord_route_notifications"


def normalize_id(value):
    return "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )


def parse_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return parsed.astimezone(LOCAL_TIMEZONE)


def format_time(value):
    parsed = parse_datetime(value)

    if not parsed:
        return ""

    return parsed.strftime("%H:%M")


def request_json(url):
    response = requests.get(
        url,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def load_drivers():
    url = (
        f"{BASE_URL}/fetch-drivers"
        f"?id={DEPOT_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )
    return request_json(url).get("drivers", [])


def load_driver_detail(driver_id):
    today = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d")
    url = (
        f"{BASE_URL}/fetch-drivers-detail/{driver_id}/{today}"
        f"?organizationId={ORGANIZATION_ID}"
    )
    return request_json(url)


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def first_nested_value(data, paths, default=""):
    for path in paths:
        value = nested_get(data, path, "")

        if value not in ["", None]:
            return value

    return default


def get_driver_route_id(driver):
    return first_nested_value(
        driver,
        [
            ["route", "id"],
            ["route", "route_id"],
            ["route", "routeId"],
            ["route_id"],
            ["routeId"],
            ["status", "route_id"],
            ["status", "routeId"],
        ],
    )


def get_driver_assigned_at(driver):
    return first_nested_value(
        driver,
        [
            ["status", "assignedAt"],
            ["status", "assigned_at"],
            ["route", "assignedAt"],
            ["route", "assigned_at"],
            ["route", "route_assigned_at"],
            ["route_assigned_at"],
            ["status", "loading_finished_at"],
        ],
    )


def route_sort_datetime(route):
    assigned_at = parse_datetime(route.get("assignedAt"))

    if assigned_at:
        return assigned_at

    candidates = [
        route.get("realDeparture"),
        route.get("plannedDeparture"),
        route.get("plannedReturn"),
        route.get("realReturn"),
    ]
    parsed_candidates = [
        parse_datetime(candidate)
        for candidate in candidates
        if candidate
    ]
    parsed_candidates = [
        candidate
        for candidate in parsed_candidates
        if candidate
    ]

    if not parsed_candidates:
        return datetime.min.replace(tzinfo=LOCAL_TIMEZONE)

    return max(parsed_candidates)


def get_matching_route(driver, driver_detail):
    routes = driver_detail.get("routes", []) or []

    if not routes:
        return {}

    driver_route_id = normalize_id(get_driver_route_id(driver))
    if driver_route_id:
        for route in routes:
            route_id = normalize_id(route.get("id") or route.get("routeId"))
            if route_id == driver_route_id:
                return route

    assigned_at = get_driver_assigned_at(driver)
    if assigned_at:
        for route in routes:
            if route.get("assignedAt") == assigned_at:
                return route

    open_routes = [
        route
        for route in routes
        if not route.get("realReturn")
    ]
    candidates = open_routes or routes

    return sorted(
        candidates,
        key=route_sort_datetime,
    )[-1]


def find_current_checkpoint(route):
    checkpoints = route.get("checkpoints", []) or []

    for checkpoint in checkpoints:
        if not checkpoint.get("realDepartureTime"):
            return checkpoint

    return checkpoints[-1] if checkpoints else {}


def is_recent_route(route, max_age_minutes):
    assigned_at = parse_datetime(route.get("assignedAt"))

    if not assigned_at:
        return False

    now = datetime.now(LOCAL_TIMEZONE)
    age = now - assigned_at

    return timedelta(minutes=-2) <= age <= timedelta(minutes=max_age_minutes)


def supabase_headers(service_role_key, prefer=None):
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def notification_already_logged(courier_id, route_id):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return False

    endpoint = (
        f"{supabase_url}/rest/v1/{NOTIFICATION_TABLE}"
        "?select=route_id"
        f"&courier_id=eq.{courier_id}"
        f"&route_id=eq.{route_id}"
        "&limit=1"
    )
    response = requests.get(
        endpoint,
        headers=supabase_headers(service_role_key),
        timeout=20,
    )

    if response.status_code in [404, 406]:
        return False

    raise_for_supabase_error(response)

    return bool(response.json())


def log_notification(courier_id, courier_name, route_id, route, checkpoint):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return

    payload = {
        "courier_id": str(courier_id),
        "courier_name": str(courier_name or ""),
        "route_id": str(route_id),
        "order_id": str(checkpoint.get("orderId") or ""),
        "assigned_at": route.get("assignedAt"),
        "planned_departure": route.get("plannedDeparture"),
        "planned_return": route.get("plannedReturn"),
    }
    endpoint = (
        f"{supabase_url}/rest/v1/{NOTIFICATION_TABLE}"
        "?on_conflict=courier_id,route_id"
    )
    response = requests.post(
        endpoint,
        headers=supabase_headers(
            service_role_key,
            "resolution=merge-duplicates,return=minimal",
        ),
        json=payload,
        timeout=20,
    )

    if response.status_code in [404, 406]:
        return

    raise_for_supabase_error(response)


def should_skip_driver(driver, allowed_courier_ids):
    courier_id = normalize_id(driver.get("driver_id"))

    return bool(
        allowed_courier_ids
        and courier_id not in allowed_courier_ids
    )


def run_once(max_age_minutes):
    discord_status = read_discord_status()
    allowed_courier_ids = set(discord_status.get("allowed_courier_ids", []))
    drivers = load_drivers()
    sent_count = 0
    skipped_count = 0

    for driver in drivers:
        courier_id = normalize_id(driver.get("driver_id"))

        if not courier_id or should_skip_driver(driver, allowed_courier_ids):
            skipped_count += 1
            continue

        try:
            driver_detail = load_driver_detail(courier_id)
            route = get_matching_route(driver, driver_detail)
        except Exception as exc:
            print(f"#{courier_id} route detail hiba: {exc}")
            skipped_count += 1
            continue

        if not route or route.get("realReturn"):
            skipped_count += 1
            continue

        route_id = normalize_id(route.get("id") or route.get("routeId"))

        if not route_id or not is_recent_route(route, max_age_minutes):
            skipped_count += 1
            continue

        if notification_already_logged(courier_id, route_id):
            skipped_count += 1
            continue

        checkpoint = find_current_checkpoint(route)
        order_id = normalize_id(checkpoint.get("orderId"))
        address = str(checkpoint.get("address") or "").strip()
        courier_name = (
            nested_get(driver, ["personal_info", "name"], "")
            or driver.get("driver_name")
            or driver_detail.get("courierName")
            or ""
        )
        result = notify_route_assigned_once(
            courier_id,
            courier_name,
            route_id,
            order_id=order_id,
            address=address,
            planned_departure=format_time(route.get("plannedDeparture")),
            planned_return=format_time(route.get("plannedReturn")),
        )

        if result == "sent":
            log_notification(
                courier_id,
                courier_name,
                route_id,
                route,
                checkpoint,
            )
            sent_count += 1
            print(f"Discord route jelzes elkuldve: #{courier_id} route {route_id}")
        else:
            skipped_count += 1
            print(f"Discord route jelzes kihagyva: #{courier_id} route {route_id} ({result})")

    print(f"Monitor kor kesz: sent={sent_count}, skipped={skipped_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-minutes", type=int, default=10)
    parser.add_argument("--loop-minutes", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    if args.loop_minutes <= 0:
        run_once(args.max_age_minutes)
        return

    deadline = time.monotonic() + args.loop_minutes * 60

    while True:
        run_once(args.max_age_minutes)

        if time.monotonic() + args.poll_seconds > deadline:
            break

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
