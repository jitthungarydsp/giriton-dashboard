import argparse
import base64
import json
import os
from collections import Counter
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

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
PUSH_SUBSCRIPTION_TABLE = "pwa_push_subscriptions"
PUSH_DELIVERY_TABLE = "pwa_push_delivery_log"
PUSH_NOTIFICATION_TYPE = "route_assigned"
ATTENDANCE_CACHE = {}


def normalize_id(value):
    return "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )


def normalize_warehouse(value):
    raw_value = str(value or "").strip().upper()
    compact_value = "".join(
        character
        for character in raw_value
        if character.isalnum()
    )

    if compact_value in {"1", "BUD1", "BUD1JIT"}:
        return "BUD1"

    if compact_value in {"2", "BUD2", "BUD2JIT"}:
        return "BUD2"

    if "BUD2" in compact_value:
        return "BUD2"

    if "BUD1" in compact_value or compact_value in {"BUD", "BUDAPEST"}:
        return "BUD1"

    return ""


def find_route_warehouse(*sources):
    keys = (
        "warehouse",
        "warehouse_name",
        "warehouseName",
        "warehouse_code",
        "warehouseCode",
        "warehouse_id",
        "warehouseId",
    )

    def walk(value):
        if isinstance(value, dict):
            for key in keys:
                normalized = normalize_warehouse(value.get(key))
                if normalized:
                    return normalized
            for nested_value in value.values():
                normalized = walk(nested_value)
                if normalized:
                    return normalized
        elif isinstance(value, list):
            for item in value:
                normalized = walk(item)
                if normalized:
                    return normalized
        else:
            raw_value = str(value or "").upper()
            if "BUD" in raw_value:
                return normalize_warehouse(value)
        return ""

    for source in sources:
        normalized = walk(source)
        if normalized:
            return normalized

    return ""


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


def format_datetime_time(value):
    if not value:
        return ""

    return value.strftime("%H:%M")


def format_wait_duration(start_at, end_at):
    if not start_at or not end_at:
        return ""

    minutes = int((end_at - start_at).total_seconds() // 60)
    minutes = max(minutes, 0)

    if minutes < 60:
        return f"{minutes} perc"

    hours = minutes // 60
    remainder = minutes % 60

    if not remainder:
        return f"{hours} ora"

    return f"{hours} ora {remainder} perc"


def format_shift_label(shift, include_times=True):
    if not shift:
        return ""

    label = str(shift.get("shift_name") or "").strip()
    start_at = shift.get("shift_start")
    end_at = shift.get("shift_end")

    if not label and start_at:
        label = format_datetime_time(start_at)

    if include_times and start_at:
        if end_at:
            time_part = f"{format_datetime_time(start_at)}-{format_datetime_time(end_at)}"
        else:
            time_part = format_datetime_time(start_at)

        if label and time_part not in label:
            return f"{label} ({time_part})"

    return label or "nincs adat"


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


def load_attendance_for_date(work_date):
    if work_date in ATTENDANCE_CACHE:
        return ATTENDANCE_CACHE[work_date]

    url = (
        f"{BASE_URL}/fetch-attendance/{DEPOT_ID}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )
    headers = {
        "apikey": SUPABASE_ANON_KEY,
    }

    attendance_data = request_json("GET", url, headers=headers)
    ATTENDANCE_CACHE[work_date] = attendance_data
    return attendance_data


def route_work_date(route):
    for key in ["assignedAt", "courierRegisteredAt", "plannedDeparture"]:
        parsed = parse_datetime(route.get(key))
        if parsed:
            return parsed.date().isoformat()

    return datetime.now(LOCAL_TIMEZONE).date().isoformat()


def find_attendance_courier(attendance_data, courier_id):
    normalized_courier_id = normalize_id(courier_id)

    for courier in attendance_data.get("couriers", []) or []:
        if normalize_id(courier.get("courierId")) == normalized_courier_id:
            return courier

    return {}


def parse_shift_times(courier):
    shifts = []

    for shift in courier.get("shifts", []) or []:
        shift_start = parse_datetime(shift.get("shiftStart"))
        shift_end = parse_datetime(shift.get("shiftEnd"))

        if not shift_start:
            continue

        shifts.append(
            {
                "shift_id": shift.get("shiftId"),
                "shift_name": shift.get("shiftName") or "",
                "shift_start": shift_start,
                "shift_end": shift_end,
                "available_for_shift_since": parse_datetime(
                    shift.get("availableForShiftSince")
                ),
            }
        )

    return sorted(shifts, key=lambda item: item["shift_start"])


def choose_current_shift(shifts, assigned_at, return_at):
    if not shifts:
        return None

    if assigned_at:
        for shift in shifts:
            shift_start = shift["shift_start"]
            shift_end = shift.get("shift_end")

            if shift_end and shift_start <= assigned_at < shift_end:
                return shift

            if assigned_at < shift_start and return_at and return_at >= shift_start:
                return shift

        previous_shifts = [
            shift
            for shift in shifts
            if shift["shift_start"] <= assigned_at
        ]
        if previous_shifts:
            return previous_shifts[-1]

    return shifts[0]


def build_shift_notification_notes(courier_id, route):
    work_date = route_work_date(route)

    try:
        attendance_data = load_attendance_for_date(work_date)
    except Exception as exc:
        error_note = f"nem ellenorizheto (fetch-attendance hiba: {exc})"
        return {
            "current_shift_note": error_note,
            "next_shift_note": error_note,
            "next_shift_delay_note": "",
            "queue_since_note": "",
            "queue_wait_note": "",
        }

    courier = find_attendance_courier(attendance_data, courier_id)
    if not courier:
        error_note = "nem ellenorizheto (nincs attendance adat)"
        return {
            "current_shift_note": error_note,
            "next_shift_note": error_note,
            "next_shift_delay_note": "",
            "queue_since_note": "",
            "queue_wait_note": "",
        }

    shifts = parse_shift_times(courier)
    now = datetime.now(LOCAL_TIMEZONE)
    assigned_at = parse_datetime(route.get("assignedAt")) or now
    current_shift = None

    for shift in shifts:
        shift_start = shift["shift_start"]
        shift_end = shift.get("shift_end")

        if shift_end and shift_start <= now < shift_end:
            current_shift = shift
            break

    current_shift_note = (
        format_shift_label(current_shift)
        if current_shift
        else "jelenleg nincs aktualis muszakban"
    )

    next_shifts = [
        shift
        for shift in shifts
        if shift["shift_start"] > now
    ]
    next_shift_note = (
        format_shift_label(next_shifts[0], include_times=False)
        if next_shifts
        else "nincs kovetkezo muszak"
    )
    next_shift_delay_note = ""
    route_return_at = parse_datetime(route.get("realReturn") or route.get("plannedReturn"))

    if next_shifts and route_return_at:
        delay_minutes = int(
            (route_return_at - next_shifts[0]["shift_start"]).total_seconds() // 60
        )

        if delay_minutes > 0:
            next_shift_delay_note = f"{delay_minutes} perc"

    queue_shift = current_shift
    if not queue_shift:
        checked_in_shifts = [
            shift
            for shift in shifts
            if shift.get("available_for_shift_since")
        ]
        if checked_in_shifts:
            queue_shift = checked_in_shifts[-1]

    queue_since = (
        queue_shift.get("available_for_shift_since")
        if queue_shift
        else None
    )
    queue_until = assigned_at or now
    queue_since_note = format_datetime_time(queue_since)
    queue_wait_note = format_wait_duration(queue_since, queue_until)

    return {
        "current_shift_note": current_shift_note,
        "next_shift_note": next_shift_note,
        "next_shift_delay_note": next_shift_delay_note,
        "queue_since_note": queue_since_note or "nincs adat",
        "queue_wait_note": queue_wait_note or "nincs adat",
    }


def build_next_shift_note(courier_id, route):
    return build_shift_notification_notes(courier_id, route).get(
        "next_shift_note",
        "",
    )


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


def notification_already_logged(courier_id, route_id, warehouse=""):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return False

    endpoint = (
        f"{supabase_url}/rest/v1/{NOTIFICATION_TABLE}"
        "?select=route_id"
        f"&courier_id=eq.{courier_id}"
        f"&route_id=eq.{route_id}"
    )
    normalized_warehouse = normalize_warehouse(warehouse)
    if normalized_warehouse:
        endpoint += f"&warehouse=eq.{normalized_warehouse}"
    endpoint += "&limit=1"
    response = requests.get(
        endpoint,
        headers=supabase_headers(service_role_key),
        timeout=20,
    )

    if response.status_code == 400 and normalized_warehouse:
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


def log_notification(
    courier_id,
    courier_name,
    route_id,
    route,
    checkpoint,
    licence_plate,
    orders_in_route,
    warehouse="",
):
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
        "licence_plate": str(licence_plate),
        "orders_in_route": str(orders_in_route),
    }
    normalized_warehouse = normalize_warehouse(warehouse)
    if normalized_warehouse:
        payload["warehouse"] = normalized_warehouse

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

    if response.status_code == 400 and "warehouse" in payload:
        payload.pop("warehouse", None)
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



def env_setting(name):
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Hiányzó környezeti változó: {name}")
    return value


def vapid_private_key_setting():
    value = str(os.getenv("VAPID_PRIVATE_KEY_B64") or "").strip()
    if value:
        try:
            return base64.b64decode(value).decode("utf-8").strip()
        except Exception as exc:
            raise RuntimeError("Hibás VAPID_PRIVATE_KEY_B64 formátum.") from exc
    return env_setting("VAPID_PRIVATE_KEY")


def normalize_pem_private_key(value):
    text = str(value or "").strip()
    if not text:
        return ""

    text = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    begin = "-----BEGIN PRIVATE KEY-----"
    end = "-----END PRIVATE KEY-----"

    if begin not in text or end not in text:
        return text

    body = text.split(begin, 1)[1].split(end, 1)[0]
    body = "".join(body.split())
    lines = [body[index:index + 64] for index in range(0, len(body), 64)]
    return "\n".join([begin, *lines, end])


def vapid_private_key_setting():
    value = str(os.getenv("VAPID_PRIVATE_KEY_B64") or "").strip()
    if value:
        try:
            key = normalize_pem_private_key(base64.b64decode(value).decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Hibas VAPID_PRIVATE_KEY_B64 formatum.") from exc
    else:
        key = normalize_pem_private_key(env_setting("VAPID_PRIVATE_KEY"))
    if "-----BEGIN" in key:
        return Vapid.from_pem(key.encode("utf-8"))
    return key


def get_active_push_subscriptions(courier_id):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return []

    endpoint = (
        f"{supabase_url}/rest/v1/{PUSH_SUBSCRIPTION_TABLE}"
        "?select=id,courier_id,endpoint,p256dh,auth"
        f"&courier_id=eq.{courier_id}"
        "&active=eq.true"
        "&order=updated_at.desc"
        "&limit=20"
    )

    response = requests.get(
        endpoint,
        headers=supabase_headers(service_role_key),
        timeout=20,
    )

    if response.status_code in [404, 406]:
        return []

    raise_for_supabase_error(response)
    return response.json() or []


def push_already_logged(courier_id, route_id):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return False

    endpoint = (
        f"{supabase_url}/rest/v1/{PUSH_DELIVERY_TABLE}"
        "?select=id"
        f"&courier_id=eq.{courier_id}"
        f"&notification_type=eq.{PUSH_NOTIFICATION_TYPE}"
        f"&message=eq.route:{route_id}"
        "&status=eq.sent"
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


def log_push_delivery(courier_id, route_id, status, detail):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return

    payload = {
        "courier_id": int(courier_id),
        "work_date": datetime.now(LOCAL_TIMEZONE).date().isoformat(),
        "notification_type": PUSH_NOTIFICATION_TYPE,
        "status": status,
        "message": f"route:{route_id}",
        "sent_at": datetime.now(LOCAL_TIMEZONE).isoformat(),
    }

    endpoint = f"{supabase_url}/rest/v1/{PUSH_DELIVERY_TABLE}"
    response = requests.post(
        endpoint,
        headers=supabase_headers(
            service_role_key,
            "return=minimal",
        ),
        json=payload,
        timeout=20,
    )

    if response.status_code in [404, 406]:
        return

    raise_for_supabase_error(response)


def deactivate_push_subscription(subscription_id):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return

    endpoint = (
        f"{supabase_url}/rest/v1/{PUSH_SUBSCRIPTION_TABLE}"
        f"?id=eq.{subscription_id}"
    )

    response = requests.patch(
        endpoint,
        headers=supabase_headers(
            service_role_key,
            "return=minimal",
        ),
        json={
            "active": False,
            "updated_at": datetime.now(LOCAL_TIMEZONE).isoformat(),
        },
        timeout=20,
    )

    if response.status_code in [404, 406]:
        return

    raise_for_supabase_error(response)


def build_route_push_body(
    route_id,
    address,
    planned_departure,
    planned_return,
    licence_plate,
    orders_in_route,
):
    lines = []

    if planned_departure:
        lines.append(f"Indulás: {planned_departure}")
    if planned_return:
        lines.append(f"Várható visszaérkezés: {planned_return}")
    if orders_in_route:
        lines.append(f"Címek: {orders_in_route} db")
    if licence_plate:
        lines.append(f"Rendszám: {licence_plate}")
    if address:
        lines.append(f"Első cím: {address}")

    if not lines:
        lines.append(f"Túraazonosító: {route_id}")

    return "\n".join(lines)


def send_route_push(
    courier_id,
    courier_name,
    route_id,
    *,
    address="",
    planned_departure="",
    planned_return="",
    licence_plate="",
    orders_in_route="",
):
    if push_already_logged(courier_id, route_id):
        return "already_sent"

    subscriptions = get_active_push_subscriptions(courier_id)
    if not subscriptions:
        return "no_subscription"

    body = build_route_push_body(
        route_id,
        address,
        planned_departure,
        planned_return,
        licence_plate,
        orders_in_route,
    )

    payload = json.dumps(
        {
            "title": "Új túrát kaptál",
            "body": body,
            "tag": f"route-assigned-{courier_id}-{route_id}",
            "url": "/",
            "renotify": False,
            "data": {
                "section": "home",
                "routeId": str(route_id),
                "courierId": str(courier_id),
            },
        },
        ensure_ascii=False,
    )

    sent = False
    errors = []

    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.get("endpoint"),
            "keys": {
                "p256dh": subscription.get("p256dh"),
                "auth": subscription.get("auth"),
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key_setting(),
                vapid_claims={"sub": env_setting("VAPID_SUBJECT")},
                ttl=60 * 60,
            )
            sent = True
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            errors.append(f"id={subscription.get('id')} status={status_code} {exc}")

            if status_code in [403, 404, 410]:
                deactivate_push_subscription(subscription.get("id"))
        except Exception as exc:
            errors.append(f"id={subscription.get('id')} error={exc}")

    if sent:
        log_push_delivery(
            courier_id,
            route_id,
            "sent",
            body,
        )
        return "sent"

    log_push_delivery(
        courier_id,
        route_id,
        "failed",
        " | ".join(errors) or "Ismeretlen push hiba.",
    )
    print(
        f"Push hiba #{courier_id} route {route_id}: "
        + (" | ".join(errors) or "ismeretlen hiba"),
        flush=True,
    )
    return "failed"


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

        route_warehouse = find_route_warehouse(
            dashboard_route,
            route,
            driver_detail,
        )

        checkpoint = find_first_checkpoint(route)
        order_id = normalize_id(checkpoint.get("orderId"))
        address = str(checkpoint.get("address") or "").strip()
        licence_plate = ( 
            str(dashboard_route.get("licence_plate") or "").strip()
        )
        orders_in_route = (
            str(
                dashboard_route.get("orders_in_route")
                or route.get("numTotalOrders")
                or len(route.get("checkpoints", []) or [])
                or ""
            ).strip()
        )
        courier_name = (
            str(dashboard_route.get("courier_name") or "").strip()
            or get_courier_name(courier_id, driver_detail)
        )
        shift_notes = build_shift_notification_notes(courier_id, route)

        if dry_run:
            counters["dry_run_would_send"] += 1
            skipped_count += 1
            print(
                "DRY RUN Discord route jelzes: "
                f"#{courier_id} {courier_name} route {route_id} "
                f"warehouse={route_warehouse or '-'} "
                f"order {order_id or '-'} "
                f"planned_departure={format_time(route.get('plannedDeparture')) or '-'} "
                f"return_time={format_time(route.get('realReturn') or route.get('plannedReturn')) or '-'} "
                f"current_shift={shift_notes.get('current_shift_note') or '-'} "
                f"next_shift={shift_notes.get('next_shift_note') or '-'} "
                f"next_shift_delay={shift_notes.get('next_shift_delay_note') or '-'} "
                f"queue_since={shift_notes.get('queue_since_note') or '-'} "
                f"queue_wait={shift_notes.get('queue_wait_note') or '-'}",
                flush=True,
            )
            continue

        if notification_already_logged(courier_id, route_id, route_warehouse):
            counters["already_logged"] += 1
            print(
                f"Discord route jelzes kihagyva: "
                f"#{courier_id} route {route_id} (already_logged)"
            )
        else:
            result = notify_route_assigned_once(
                courier_id,
                courier_name,
                route_id,
                order_id="",
                address=address,
                planned_departure=format_time(route.get("plannedDeparture")),
                planned_return=format_time(
                    route.get("realReturn") or route.get("plannedReturn")
                ),
                ignore_courier_filter=True,
                licence_plate=licence_plate,
                orders_in_route="",
                warehouse=route_warehouse,
                current_shift_note=shift_notes.get("current_shift_note", ""),
                next_shift_note=shift_notes.get("next_shift_note", ""),
                next_shift_delay_note=shift_notes.get("next_shift_delay_note", ""),
                queue_since_note=shift_notes.get("queue_since_note", ""),
                queue_wait_note=shift_notes.get("queue_wait_note", ""),
            )

            if result == "sent":
                log_notification(
                    courier_id,
                    courier_name,
                    route_id,
                    route,
                    checkpoint,
                    licence_plate,
                    orders_in_route,
                    route_warehouse
                )
                sent_count += 1
                print(
                    f"Discord route jelzes elkuldve: "
                    f"#{courier_id} route {route_id} warehouse={route_warehouse or '-'}"
                )
            else:
                counters[result or "not_sent"] += 1
                skipped_count += 1
                print(
                    f"Discord route jelzes kihagyva: "
                    f"#{courier_id} route {route_id} ({result})"
                )

        push_result = send_route_push(
            courier_id,
            courier_name,
            route_id,
            address=address,
            planned_departure=format_time(route.get("plannedDeparture")),
            planned_return=format_time(
                route.get("realReturn") or route.get("plannedReturn")
            ),
            licence_plate=licence_plate,
            orders_in_route=orders_in_route,
        )
        counters[f"push_{push_result}"] += 1
        print(
            f"Push route jelzes: #{courier_id} route {route_id} "
            f"({push_result})",
            flush=True,
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
