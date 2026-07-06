import argparse
from collections import Counter
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.api import (
    BASE_URL,
    DEPOT_ID,
    ORGANIZATION_ID,
    SUPABASE_ANON_KEY,
)
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


def request_json(method, url, **kwargs):
    response = requests.request(
        method,
        url,
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def load_departure_dashboard():
    url = f"{BASE_URL}/departure-dashboard"
    payload = {
        "id": DEPOT_ID,
        "organizationId": ORGANIZATION_ID,
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
    }

    return request_json(
        "POST",
        url,
        json=payload,
        headers=headers,
    )


def load_driver_detail(courier_id):
    today = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d")
    url = (
        f"{BASE_URL}/fetch-drivers-detail/{courier_id}/{today}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    return request_json("GET", url)


def get_dashboard_routes(dashboard_data):
    routes = dashboard_data.get("routes", [])

    if not isinstance(routes, list):
        return []

    return [
        route
        for route in routes
        if normalize_id(route.get("courier_id") or route.get("courierId"))
        and normalize_id(route.get("route_id") or route.get("routeId"))
    ]


def route_oldest_datetime(route):
    candidates = [
        route.get("createdAt"),
        route.get("courierRegisteredAt"),
        route.get("assignedAt"),
        route.get("plannedDeparture"),
        route.get("realDeparture"),
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
        return datetime.max.replace(tzinfo=LOCAL_TIMEZONE)

    return min(parsed_candidates)


def get_detail_route_for_dashboard_route(driver_detail, dashboard_route_id):
    routes = driver_detail.get("routes", []) or []

    if not routes:
        return {}

    dashboard_route_id = normalize_id(dashboard_route_id)

    for route in routes:
        route_id = normalize_id(route.get("id") or route.get("routeId"))

        if route_id == dashboard_route_id:
            return route

    return sorted(routes, key=route_oldest_datetime)[0]


def get_courier_name(courier_id, driver_detail):
    return (
        driver_detail.get("courierName")
        or driver_detail.get("courier_name")
        or driver_detail.get("name")
        or f"#{courier_id}"
    )


def find_first_checkpoint(route):
    checkpoints = route.get("checkpoints", []) or []

    if not checkpoints:
        return {}

    return sorted(
        checkpoints,
        key=lambda checkpoint: (
            int(checkpoint.get("position") or 999999),
            parse_datetime(checkpoint.get("plannedArrivalTime"))
            or parse_datetime(checkpoint.get("deliverSince"))
            or datetime.max.replace(tzinfo=LOCAL_TIMEZONE),
        ),
    )[0]


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


def run_once(max_age_minutes, dry_run=False):
    discord_status = read_discord_status()
    counters = Counter()
    sent_count = 0
    skipped_count = 0

    print(
        "Discord monitor status: "
        f"webhook_configured={discord_status.get('webhook_configured')} "
        "source=departure-dashboard.routes "
        f"max_age_minutes={max_age_minutes}",
        flush=True,
    )

    try:
        dashboard_data = load_departure_dashboard()
        dashboard_routes = get_dashboard_routes(dashboard_data)
    except Exception as exc:
        counters["departure_dashboard_error"] += 1
        print(
            f"departure-dashboard hiba: {exc}",
            flush=True,
        )
        print(
            f"Monitor kor kesz: sent=0, skipped=0, reasons={dict(counters)}",
            flush=True,
        )
        return

    print(
        f"departure-dashboard routes talalat: {len(dashboard_routes)}",
        flush=True,
    )

    for dashboard_route in dashboard_routes:
        courier_id = normalize_id(
            dashboard_route.get("courier_id")
            or dashboard_route.get("courierId")
        )
        route_id = normalize_id(
            dashboard_route.get("route_id")
            or dashboard_route.get("routeId")
        )

        if not courier_id:
            counters["missing_courier_id"] += 1
            skipped_count += 1
            continue

        if not route_id:
            counters["missing_route_id"] += 1
            skipped_count += 1
            continue

        try:
            driver_detail = load_driver_detail(courier_id)
            route = get_detail_route_for_dashboard_route(
                driver_detail,
                route_id,
            )
        except Exception as exc:
            print(f"#{courier_id} route detail hiba: {exc}")
            counters["detail_error"] += 1
            skipped_count += 1
            continue

        if not route:
            counters["no_detail_route"] += 1
            skipped_count += 1
            continue

        if max_age_minutes > 0 and not is_recent_route(route, max_age_minutes):
            counters["route_too_old"] += 1
            skipped_count += 1
            continue

        if notification_already_logged(courier_id, route_id):
            counters["already_logged"] += 1
            skipped_count += 1
            continue

        checkpoint = find_first_checkpoint(route)
        order_id = normalize_id(checkpoint.get("orderId"))
        address = str(checkpoint.get("address") or "").strip()
        courier_name = (
            str(dashboard_route.get("courier_name") or "").strip()
            or get_courier_name(courier_id, driver_detail)
        )

        if dry_run:
            counters["dry_run_would_send"] += 1
            skipped_count += 1
            print(
                "DRY RUN Discord route jelzes: "
                f"#{courier_id} {courier_name} route {route_id} "
                f"order {order_id or '-'} "
                f"planned_departure={format_time(route.get('plannedDeparture')) or '-'} "
                f"return_time={format_time(route.get('realReturn') or route.get('plannedReturn')) or '-'}",
                flush=True,
            )
            continue

        result = notify_route_assigned_once(
            courier_id,
            courier_name,
            route_id,
            order_id=order_id,
            address=address,
            planned_departure=format_time(route.get("plannedDeparture")),
            planned_return=format_time(
                route.get("realReturn") or route.get("plannedReturn")
            ),
            ignore_courier_filter=True,
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
            print(
                f"Discord route jelzes elkuldve: #{courier_id} route {route_id}"
            )
        else:
            counters[result or "not_sent"] += 1
            skipped_count += 1
            print(
                f"Discord route jelzes kihagyva: "
                f"#{courier_id} route {route_id} ({result})"
            )

    print(
        f"Monitor kor kesz: sent={sent_count}, skipped={skipped_count}, reasons={dict(counters)}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-minutes", type=int, default=10)
    parser.add_argument("--loop-minutes", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.loop_minutes <= 0:
        run_once(args.max_age_minutes, dry_run=args.dry_run)
        return

    deadline = time.monotonic() + args.loop_minutes * 60

    while True:
        run_once(args.max_age_minutes, dry_run=args.dry_run)

        if time.monotonic() + args.poll_seconds > deadline:
            break

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
