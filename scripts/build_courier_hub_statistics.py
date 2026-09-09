#!/usr/bin/env python3
"""Build route-level and courier-day Courier Hub statistics from Hub raw data."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import COURIER_TARGET_TABLES, clean_text, raise_for_response, safe_int, supabase_headers  # noqa: E402


COURIER_HUB_DSP_ID = int(os.getenv("COURIER_HUB_DSP_ID") or "8")
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
WAREHOUSE_CODES = {1: "BUD1", 2: "BUD2"}
WAREHOUSE_ADDRESSES = {
    1: "Budapest, Jaszberenyi ut 45, 1106",
    2: "Biatorbagy, Meszarosok utja 6, 2051",
}


def google_routes_api_key() -> str:
    return clean_text(os.getenv("GOOGLE_ROUTES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY"))


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Hianyzik a(z) {name} kornyezeti valtozo.")
    return value


def parse_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    has_timezone = text.endswith("Z") or bool(re.search(r"[+-]\d{2}:\d{2}$", text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BUDAPEST_TZ if not has_timezone else timezone.utc)
    return parsed


def parse_time(value: Any) -> time | None:
    text = clean_text(value)
    if not text:
        return None
    if "T" in text and len(text) >= 16:
        parsed_dt = parse_datetime(text)
        if parsed_dt:
            return parsed_dt.astimezone(BUDAPEST_TZ).time().replace(second=0, microsecond=0)
        text = text[11:16]
    else:
        text = text[:5]
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def budapest_datetime(value: Any) -> datetime | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    return parsed.astimezone(BUDAPEST_TZ)


def huf(value: Any) -> str:
    if value is None:
        return "0 Ft"
    try:
        return f"{int(round(float(value))):,} Ft".replace(",", " ")
    except (TypeError, ValueError):
        return "0 Ft"


def minutes_text(minutes: int | None) -> str:
    if minutes is None:
        return "nincs adat"
    hours, mins = divmod(max(0, int(minutes)), 60)
    if hours and mins:
        return f"{hours}:{mins:02d}"
    if hours:
        return f"{hours}:00"
    return f"{mins} perc"


def km_text(value: Any) -> str:
    if value is None:
        return "nincs adat"
    try:
        return f"{float(value):.1f} km".replace(".", ",")
    except (TypeError, ValueError):
        return "nincs adat"


def time_text(value: datetime | time | str | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(BUDAPEST_TZ).strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    parsed_dt = parse_datetime(value)
    if parsed_dt:
        return parsed_dt.astimezone(BUDAPEST_TZ).strftime("%H:%M")
    parsed_time = parse_time(value)
    if parsed_time:
        return parsed_time.strftime("%H:%M")
    return "nincs adat"


def float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def round2(value: float | None) -> float | None:
    return round(float(value), 2) if value is not None else None


def parse_google_duration_seconds(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    if text.endswith("s"):
        text = text[:-1]
    try:
        return int(round(float(text)))
    except (TypeError, ValueError):
        return None


def minutes_between(start: Any, end: Any) -> int | None:
    start_at = parse_datetime(start)
    end_at = parse_datetime(end)
    if not start_at or not end_at or end_at < start_at:
        return None
    return int(round((end_at - start_at).total_seconds() / 60))


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, next_month - timedelta(days=1)


def route_log_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    containers = [payload]
    for nested_key in ("shift", "route"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            containers.append(nested)
    for container in containers:
        for key in ("routeLogs", "routeLog", "logs", "log", "events", "timeline"):
            value = container.get(key)
            if isinstance(value, list):
                items.extend(event for event in value if isinstance(event, dict))
    return items


def first_log_event_at(payload: dict[str, Any], event_name: str) -> str:
    wanted = clean_text(event_name).upper()
    for event in route_log_items(payload):
        if not isinstance(event, dict):
            continue
        event_type = clean_text(event.get("type") or event.get("eventType") or event.get("event")).upper()
        if event_type != wanted:
            continue
        return clean_text(
            event.get("occurredAt")
            or event.get("createdAt")
            or event.get("created_at")
            or event.get("time")
            or event.get("timestamp")
        )
    return ""


def route_log_events(payload: dict[str, Any], event_name: str) -> list[datetime]:
    wanted = clean_text(event_name).upper()
    events: list[datetime] = []
    for event in route_log_items(payload):
        if not isinstance(event, dict):
            continue
        event_type = clean_text(event.get("type") or event.get("eventType") or event.get("event")).upper()
        if event_type != wanted:
            continue
        event_at = parse_datetime(
            event.get("occurredAt")
            or event.get("createdAt")
            or event.get("created_at")
            or event.get("time")
            or event.get("timestamp")
        )
        if event_at:
            events.append(event_at)
    return sorted(events)


def route_log_event_text(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def nearest_route_assigned(payload: dict[str, Any], planned_start: Any) -> datetime | None:
    assigned_events = route_log_events(payload, "ROUTE_ASSIGNED")
    if not assigned_events:
        return None
    planned = parse_datetime(planned_start)
    if not planned:
        return assigned_events[0]
    window_start = planned - timedelta(hours=3)
    window_end = planned + timedelta(hours=4)
    candidates = [event for event in assigned_events if window_start <= event <= window_end]
    candidates = candidates or assigned_events
    return min(candidates, key=lambda event: abs((event - planned).total_seconds()))


def paired_route_events(payload: dict[str, Any], planned_start: Any) -> dict[str, str]:
    assigned = nearest_route_assigned(payload, planned_start)
    shift_available_events = route_log_events(payload, "SHIFT_AVAILABLE")
    departed_events = route_log_events(payload, "DEPARTED")
    returned_events = route_log_events(payload, "WAREHOUSE_ARRIVED")

    queue_started = None
    if assigned:
        previous_queue_events = [event for event in shift_available_events if event <= assigned]
        queue_started = previous_queue_events[-1] if previous_queue_events else None
    elif shift_available_events:
        queue_started = shift_available_events[0]

    departed = None
    if assigned:
        next_departed_events = [event for event in departed_events if event >= assigned]
        departed = next_departed_events[0] if next_departed_events else None
    elif departed_events:
        departed = departed_events[0]

    returned = None
    if departed:
        next_returned_events = [event for event in returned_events if event >= departed]
        returned = next_returned_events[0] if next_returned_events else None
    elif returned_events:
        returned = returned_events[0]

    return {
        "queue_started": route_log_event_text(queue_started),
        "route_assigned": route_log_event_text(assigned),
        "departed": route_log_event_text(departed),
        "returned": route_log_event_text(returned),
    }


def route_work_date(payload: dict[str, Any], shift: dict[str, Any] | None = None) -> date | None:
    shift = shift or (payload.get("shift") if isinstance(payload.get("shift"), dict) else {})
    direct_date = parse_date(
        payload.get("deliveryDate")
        or payload.get("date")
        or shift.get("deliveryDate")
        or shift.get("date")
        or shift.get("plannedStartAt")
        or shift.get("actualStartAt")
    )
    if direct_date:
        return direct_date
    for event_name in ("ROUTE_ASSIGNED", "DEPARTED", "WAREHOUSE_ARRIVED", "SHIFT_AVAILABLE"):
        events = route_log_events(payload, event_name)
        if events:
            return events[0].astimezone(BUDAPEST_TZ).date()
    return None


def route_type_label(value: Any) -> str:
    text = clean_text(value).lower()
    if "express" in text:
        return "Express"
    if "regional" in text or "regio" in text or "régio" in text:
        return "Regionális"
    if "city" in text:
        return "City"
    return "Normál"


def shift_name_from_start(value: Any) -> str:
    parsed = parse_time(value)
    return parsed.strftime("%H:%M") if parsed else clean_text(value)


def stop_delay_totals(stops: list[Any]) -> tuple[int, int]:
    count = 0
    minutes = 0
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        delay = int_or_none(stop.get("delayMinutes") or stop.get("deltaMinutes"))
        if delay and delay > 0:
            count += 1
            minutes += delay
    return count, minutes


def compact_stop_addresses(stops: list[Any]) -> list[str]:
    addresses: list[str] = []
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        address = clean_text(stop.get("address") or stop.get("formattedAddress") or stop.get("customerAddress"))
        if address:
            addresses.append(address)
    return addresses


def calculate_google_route_distance(warehouse_id: int, stop_addresses: list[str]) -> dict[str, Any]:
    warehouse_address = WAREHOUSE_ADDRESSES.get(int(warehouse_id), "")
    stops = [clean_text(address) for address in stop_addresses if clean_text(address)]
    if not warehouse_address:
        return {"available": False, "message": "Ismeretlen raktar cim."}
    if not stops:
        return {"available": False, "message": "Nincs stop cim."}
    api_key = google_routes_api_key()
    if not api_key:
        return {"available": False, "message": "Nincs GOOGLE_ROUTES_API_KEY vagy GOOGLE_MAPS_API_KEY."}

    route_points = [warehouse_address, *stops, warehouse_address]
    segments = [route_points[index:index + 25] for index in range(0, len(route_points) - 1, 24)]
    total_distance_meters = 0.0
    total_duration_seconds = 0
    total_static_seconds = 0
    has_duration = False
    has_static = False
    for segment in segments:
        if len(segment) < 2:
            continue
        body: dict[str, Any] = {
            "origin": {"address": segment[0]},
            "destination": {"address": segment[-1]},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "languageCode": "hu-HU",
            "units": "METRIC",
        }
        if len(segment) > 2:
            body["intermediates"] = [{"address": address} for address in segment[1:-1]]
        try:
            response = requests.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
                },
                json=body,
                timeout=20,
            )
            if response.status_code >= 400:
                return {"available": False, "message": f"Google Routes HTTP {response.status_code}"}
            payload = response.json()
        except Exception as exc:
            return {"available": False, "message": f"Google Routes hiba: {exc}"}

        route = (payload.get("routes") or [{}])[0]
        distance_meters = route.get("distanceMeters")
        if distance_meters is None:
            return {"available": False, "message": "Google Routes valaszban nincs tavolsag."}
        total_distance_meters += float(distance_meters)
        duration_seconds = parse_google_duration_seconds(route.get("duration"))
        static_seconds = parse_google_duration_seconds(route.get("staticDuration"))
        if duration_seconds is not None:
            has_duration = True
            total_duration_seconds += duration_seconds
        if static_seconds is not None:
            has_static = True
            total_static_seconds += static_seconds

    if total_distance_meters <= 0:
        return {"available": False, "message": "Google Routes nulla tavolsagot adott."}
    traffic_delta_seconds = total_duration_seconds - total_static_seconds if has_duration and has_static else None
    return {
        "available": True,
        "distance_km": round(total_distance_meters / 1000, 2),
        "duration_minutes": max(0, round(total_duration_seconds / 60)) if has_duration else None,
        "traffic_delay_minutes": round(traffic_delta_seconds / 60) if traffic_delta_seconds is not None else None,
        "message": "OK",
    }


def story_for_route(row: dict[str, Any]) -> str:
    return (
        f"{row.get('courier_name') or 'A futar'} {row['work_date']} napon "
        f"{row.get('warehouse_code') or 'WH'} raktarbol vitte a(z) {row['route_id']} route-ot. "
        f"Muszak: {row.get('shift_name') or 'nincs adat'}, sorbaallt: {time_text(row.get('queue_started_at'))}, "
        f"turat kapott: {time_text(row.get('route_assigned_at'))}, indulas: {time_text(row.get('departed_at'))}, "
        f"visszaerkezes: {time_text(row.get('returned_at'))}. "
        f"Varakozas turakiosztasig: {minutes_text(row.get('waiting_minutes'))}, "
        f"bepakolasi ido: {minutes_text(row.get('loading_minutes'))}, "
        f"Keseses megallo: {row.get('late_stop_count') or 0} db, "
        f"tervezett ido: {minutes_text(row.get('planned_route_minutes'))}, "
        f"tenyleges ido raktarbol raktarig: {minutes_text(row.get('actual_route_minutes'))}, "
        f"teljes tura: {minutes_text(row.get('total_minutes'))}, "
        f"tervezett km: {km_text(row.get('planned_km'))}, Google km: {km_text(row.get('google_route_km'))}, "
        f"tenyleges km: {km_text(row.get('actual_km'))}. "
        f"Tipus: {row.get('route_type_label') or 'nincs adat'}, borravalo: {huf(row.get('tip_huf'))}."
    )


def story_for_day(row: dict[str, Any]) -> str:
    return (
        f"{row.get('courier_name') or 'A futar'} {row['work_date']} napon "
        f"{row.get('warehouse_code') or 'WH'} raktarban {row.get('shift_count') or 0} muszakot es "
        f"{row.get('route_count') or 0} turat teljesitett. "
        f"Keseses route: {row.get('late_route_count') or 0}, keseses megallo: {row.get('late_stop_count') or 0} db. "
        f"Osszes tervezett ido: {minutes_text(row.get('planned_route_minutes_total'))}, "
        f"tenyleges ido: {minutes_text(row.get('actual_route_minutes_total'))}, "
        f"tervezett km: {km_text(row.get('planned_km_total'))}, tenyleges km: {km_text(row.get('actual_km_total'))}. "
        f"Napi borravalo: {huf(row.get('tip_huf_total'))}."
    )


def read_supabase_rows(table: str, params: dict[str, str], limit: int = 10000) -> list[dict[str, Any]]:
    supabase_url = require_env("SUPABASE_URL").rstrip("/")
    rows: list[dict[str, Any]] = []
    page_size = 1000
    headers_base = supabase_headers()
    while len(rows) < limit:
        start = len(rows)
        end = min(start + page_size - 1, limit - 1)
        headers = {**headers_base, "Range-Unit": "items", "Range": f"{start}-{end}"}
        response = requests.get(
            f"{supabase_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            timeout=90,
        )
        raise_for_response(response, f"{table} lekeres")
        chunk = response.json() or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
    return rows


def read_route_raw_rows(
    *,
    start_date: date,
    end_date: date,
    courier_id: int | None,
    warehouse_id: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    params = {
        "select": "courier_id,route_id,year,month,dsp_id,warehouse_id,request_url,status_code,response_json,fetched_at,updated_at",
        "status_code": "eq.200",
        "year": f"gte.{start_date.year}",
        "order": "year.asc,month.asc,courier_id.asc,route_id.asc",
    }
    if start_date.year == end_date.year and start_date.month == end_date.month:
        params["year"] = f"eq.{start_date.year}"
        params["month"] = f"eq.{start_date.month}"
    elif start_date.year == end_date.year:
        params["year"] = f"eq.{start_date.year}"
        params["and"] = f"(month.gte.{start_date.month},month.lte.{end_date.month})"
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"
    if warehouse_id:
        params["warehouse_id"] = f"eq.{warehouse_id}"

    rows = read_supabase_rows("courier_route_performance_detail_raw", params, limit=limit)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
        shift = payload.get("shift") if isinstance(payload.get("shift"), dict) else {}
        work_date = route_work_date(payload, shift)
        if not work_date or work_date < start_date or work_date > end_date:
            continue
        filtered.append(row)
    return filtered


def read_shift_rows(
    *,
    start_date: date,
    end_date: date,
    courier_id: int | None,
    warehouse_id: int | None,
) -> list[dict[str, Any]]:
    params = {
        "select": "courier_id,work_date,warehouse_id,dsp_id,shift_name,shift_start,shift_end,planned_start_at,planned_end_at,actual_start_at,evaluation,status,raw_shift",
        "work_date": f"gte.{start_date.isoformat()}",
        "order": "courier_id.asc,work_date.asc,shift_start.asc",
        "limit": "10000",
    }
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"
    if warehouse_id:
        params["warehouse_id"] = f"eq.{warehouse_id}"
    rows = read_supabase_rows("courier_shift_overview", params)
    return [row for row in rows if (parse_date(row.get("work_date")) or date.min) <= end_date]


def read_courier_name_lookup() -> dict[int, str]:
    try:
        rows = read_supabase_rows(
            "courier_master",
            {"select": "courier_id,courier_name,name", "limit": "10000", "order": "courier_id.asc"},
        )
    except Exception as exc:
        print(f"courier_master nev lookup kihagyva: {exc}", flush=True)
        return {}
    lookup: dict[int, str] = {}
    for row in rows:
        courier_id = safe_int(row.get("courier_id"))
        name = clean_text(row.get("courier_name") or row.get("name"))
        if courier_id > 0 and name:
            lookup[courier_id] = name
    return lookup


def read_live_latest_lookup(
    *,
    courier_id: int | None,
    warehouse_id: int | None,
) -> dict[tuple[int, int], dict[str, Any]]:
    params = {
        "select": "courier_id,warehouse_id,warehouse_code,courier_name,route_id,response_json,fetched_at",
        "status_code": "eq.200",
        "limit": "10000",
    }
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"
    if warehouse_id:
        params["warehouse_id"] = f"eq.{warehouse_id}"
    try:
        rows = read_supabase_rows("courier_hub_live_monitoring_courier_latest", params)
    except Exception as exc:
        print(f"live latest lookup kihagyva: {exc}", flush=True)
        return {}
    lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        row_courier_id = safe_int(row.get("courier_id"))
        row_warehouse_id = safe_int(row.get("warehouse_id"))
        if row_courier_id > 0 and row_warehouse_id > 0:
            lookup[(row_courier_id, row_warehouse_id)] = row
    return lookup


def financial_route_id(route: dict[str, Any]) -> int:
    return safe_int(route.get("routeId") or route.get("route_id") or route.get("id"))


def money_amount(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("amount")
    return float_or_none(value)


def read_financial_route_lookup(
    *,
    start_date: date,
    end_date: date,
    courier_id: int | None,
    warehouse_id: int | None,
) -> dict[tuple[int, int, int], dict[str, Any]]:
    lookup: dict[tuple[int, int, int], dict[str, Any]] = {}
    target_tables = (
        {warehouse_id: COURIER_TARGET_TABLES[int(warehouse_id)]}
        if warehouse_id
        else COURIER_TARGET_TABLES
    )
    for wh_id, table_name in target_tables.items():
        params = {
            "select": "courier_id,courier_name,warehouse_id,response_json,status_code",
            "year": f"eq.{start_date.year}",
            "status_code": "eq.200",
            "limit": "10000",
        }
        if start_date.year == end_date.year and start_date.month == end_date.month:
            params["month"] = f"eq.{start_date.month}"
        elif start_date.year == end_date.year:
            params["and"] = f"(month.gte.{start_date.month},month.lte.{end_date.month})"
        if courier_id:
            params["courier_id"] = f"eq.{courier_id}"
        try:
            rows = read_supabase_rows(table_name, params)
        except Exception as exc:
            print(f"{table_name} borravalo lookup kihagyva: {exc}", flush=True)
            continue
        for row in rows:
            row_courier_id = safe_int(row.get("courier_id"))
            row_warehouse_id = safe_int(row.get("warehouse_id") or wh_id)
            payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
            routes = payload.get("routes") if isinstance(payload.get("routes"), list) else []
            for route in routes:
                if not isinstance(route, dict):
                    continue
                route_date = parse_date(route.get("deliveryDate") or route.get("date"))
                if not route_date or route_date < start_date or route_date > end_date:
                    continue
                route_id = financial_route_id(route)
                if row_courier_id <= 0 or row_warehouse_id <= 0 or route_id <= 0:
                    continue
                lookup[(row_courier_id, row_warehouse_id, route_id)] = {
                    "tip_huf": money_amount(route.get("customerTipsTotal") or route.get("tipsHuf") or route.get("tipHuf")),
                    "courier_name": clean_text(row.get("courier_name") or payload.get("courierName") or payload.get("name")),
                    "route_type": clean_text(route.get("routeLayer") or route.get("routeType")),
                    "orders": safe_int(route.get("orderCount") or route.get("orders")),
                }
    return lookup


def next_shift_text(route_row: dict[str, Any], shifts: list[dict[str, Any]]) -> str | None:
    route_date = parse_date(route_row.get("work_date"))
    if not route_date:
        return None
    reference = parse_datetime(route_row.get("route_assigned_at")) or parse_datetime(route_row.get("departed_at"))
    reference_time = reference.astimezone(BUDAPEST_TZ).time() if reference else parse_time(route_row.get("shift_name"))
    candidates: list[tuple[time, str]] = []
    for shift in shifts:
        if parse_date(shift.get("work_date")) != route_date:
            continue
        shift_start = parse_time(shift_start_value(shift))
        if not shift_start:
            continue
        if reference_time and shift_start <= reference_time:
            continue
        label = clean_text(shift.get("shift_name")) or shift_start.strftime("%H:%M")
        candidates.append((shift_start, label))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def raw_shift_dict(shift: dict[str, Any]) -> dict[str, Any]:
    return shift.get("raw_shift") if isinstance(shift.get("raw_shift"), dict) else {}


def shift_start_value(shift: dict[str, Any]) -> Any:
    raw_shift = raw_shift_dict(shift)
    return (
        shift.get("shift_start")
        or shift.get("planned_start_at")
        or shift.get("shift_name")
        or raw_shift.get("plannedStart")
        or raw_shift.get("plannedStartAt")
    )


def shift_end_value(shift: dict[str, Any]) -> Any:
    raw_shift = raw_shift_dict(shift)
    return (
        raw_shift.get("plannedEnd")
        or raw_shift.get("plannedEndAt")
        or shift.get("planned_end_at")
        or shift.get("shift_end")
    )


def shift_actual_start_value(shift: dict[str, Any]) -> Any:
    raw_shift = raw_shift_dict(shift)
    return raw_shift.get("actualStart") or raw_shift.get("actualStartAt") or shift.get("actual_start_at")


def actual_shift_start_for_route(
    shift_name: str,
    planned_start: Any,
    route_assigned: Any,
    shifts: list[dict[str, Any]],
) -> str | None:
    target_time = parse_time(planned_start) or parse_time(shift_name)
    route_assigned_dt = parse_datetime(route_assigned)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for shift in shifts:
        shift_start = parse_time(shift_start_value(shift))
        if not shift_start:
            continue
        score = 0
        if target_time:
            shift_minutes = shift_start.hour * 60 + shift_start.minute
            target_minutes = target_time.hour * 60 + target_time.minute
            score = abs(shift_minutes - target_minutes)
        actual_start = clean_text(shift_actual_start_value(shift))
        actual_start_dt = parse_datetime(actual_start)
        if not actual_start_dt:
            continue
        assigned_score = 0
        if route_assigned_dt:
            assigned_delta = int((route_assigned_dt - actual_start_dt).total_seconds() / 60)
            if assigned_delta < -10:
                assigned_score = 10000 + abs(assigned_delta)
            else:
                assigned_score = max(0, assigned_delta)
        candidates.append((score, assigned_score, shift))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    best_shift = candidates[0][2]
    actual_start = clean_text(shift_actual_start_value(best_shift))
    parsed_actual_start = parse_datetime(actual_start)
    return iso_datetime(parsed_actual_start) if parsed_actual_start else None


def shift_datetime_for_work_date(value: Any, work_date: date) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    parsed_dt = parse_datetime(text)
    if parsed_dt:
        return iso_datetime(parsed_dt)
    parsed_time = parse_time(text)
    if not parsed_time:
        return None
    return datetime.combine(work_date, parsed_time, tzinfo=BUDAPEST_TZ).isoformat()


def planned_shift_end_for_route(
    shift_name: str,
    planned_start: Any,
    work_date: date,
    shifts: list[dict[str, Any]],
) -> str | None:
    target_time = parse_time(planned_start) or parse_time(shift_name)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for shift in shifts:
        shift_start = parse_time(shift_start_value(shift))
        if not shift_start:
            continue
        score = 0
        if target_time:
            shift_minutes = shift_start.hour * 60 + shift_start.minute
            target_minutes = target_time.hour * 60 + target_time.minute
            score = abs(shift_minutes - target_minutes)
        planned_end = clean_text(shift_end_value(shift))
        if planned_end:
            candidates.append((score, shift))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    best_shift = candidates[0][1]
    planned_end = clean_text(shift_end_value(best_shift))
    return shift_datetime_for_work_date(planned_end, work_date)


def build_route_stat(
    row: dict[str, Any],
    shifts_by_courier_day: dict[tuple[int, int, date], list[dict[str, Any]]],
    *,
    calculate_google: bool,
    courier_names: dict[int, str],
    live_latest: dict[tuple[int, int], dict[str, Any]],
    financial_routes: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any] | None:
    payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
    if not payload:
        return None
    shift = payload.get("shift") if isinstance(payload.get("shift"), dict) else {}
    stops = payload.get("stops") if isinstance(payload.get("stops"), list) else []
    courier_id = safe_int(row.get("courier_id") or payload.get("courierId"))
    route_id = safe_int(row.get("route_id") or payload.get("routeId") or payload.get("id"))
    warehouse_id = safe_int(row.get("warehouse_id"))
    if courier_id <= 0 or route_id <= 0 or warehouse_id <= 0:
        return None
    live_row = live_latest.get((courier_id, warehouse_id), {})
    live_payload = live_row.get("response_json") if isinstance(live_row.get("response_json"), dict) else {}
    financial_route = financial_routes.get((courier_id, warehouse_id, route_id), {})

    planned_start = clean_text(shift.get("plannedStartAt"))
    actual_start = clean_text(shift.get("actualStartAt") or live_payload.get("actualStartAt"))
    paired_events = paired_route_events(payload, planned_start)
    route_assigned = paired_events["route_assigned"] or clean_text(payload.get("assignedAt") or payload.get("routeAssignedAt") or live_payload.get("routeAssignedAt"))
    queue_started = (
        paired_events["queue_started"]
        or clean_text(payload.get("courierRegisteredAt") or live_payload.get("courierRegisteredAt"))
    )
    queue_started_dt = parse_datetime(queue_started)
    route_assigned_dt = parse_datetime(route_assigned)
    if queue_started_dt and route_assigned_dt and queue_started_dt > route_assigned_dt:
        queue_started = ""
    if queue_started and not route_assigned:
        queue_started = ""
    departed = paired_events["departed"] or clean_text(shift.get("departedAt") or live_payload.get("departedAt"))
    returned = (
        paired_events["returned"]
        or clean_text(shift.get("warehouseArrivedAt") or payload.get("warehouseArrivedAt") or payload.get("realReturn"))
    )
    planned_departure = clean_text(shift.get("plannedDepartureAt") or live_payload.get("plannedDepartureAt"))
    work_date = route_work_date(payload, shift) or parse_date(planned_start or actual_start)
    if not work_date:
        return None

    late_count, late_minutes = stop_delay_totals(stops)
    stop_addresses = compact_stop_addresses(stops)
    planned_km = float_or_none(shift.get("plannedKm") or payload.get("plannedKm") or live_payload.get("plannedKm"))
    mileage_km = float_or_none(shift.get("mileageKm"))
    google_result = (
        calculate_google_route_distance(warehouse_id, stop_addresses)
        if calculate_google
        else {"available": False, "message": "Google Routes szamitas kihagyva."}
    )
    google_route_km = float_or_none(google_result.get("distance_km")) if google_result.get("available") else None
    actual_km = google_route_km
    distance_delta = actual_km - planned_km if actual_km is not None and planned_km is not None else None
    route_type = clean_text(
        payload.get("routeLayer")
        or payload.get("routeType")
        or shift.get("routeLayer")
        or shift.get("routeType")
        or financial_route.get("route_type")
        or "normal"
    ).lower()
    shift_name = clean_text(shift.get("shiftName") or shift.get("name") or shift.get("title") or shift.get("label")) or shift_name_from_start(planned_start)
    shifts_key = (courier_id, warehouse_id, work_date)
    day_shifts = shifts_by_courier_day.get(shifts_key, [])
    actual_shift_start_for_stat = (
        actual_shift_start_for_route(shift_name, planned_start, route_assigned, day_shifts)
        or iso_datetime(parse_datetime(actual_start))
    )
    queue_started = actual_shift_start_for_stat
    planned_return = (
        clean_text(shift.get("plannedReturnAt") or payload.get("plannedReturnAt") or payload.get("plannedReturn"))
        or planned_shift_end_for_route(shift_name, planned_start, work_date, day_shifts)
    )
    courier_name = (
        clean_text(payload.get("courierName") or payload.get("name") or shift.get("courierName"))
        or clean_text(live_row.get("courier_name") or live_payload.get("name") or live_payload.get("courierName"))
        or clean_text(financial_route.get("courier_name"))
        or courier_names.get(courier_id)
    )
    detail_tip = float_or_none(
        payload.get("customerTipsTotal")
        or payload.get("tipsHuf")
        or payload.get("tipHuf")
        or shift.get("customerTipsTotal")
    )
    financial_tip = float_or_none(financial_route.get("tip_huf"))
    tip_huf = financial_tip if financial_tip is not None else (detail_tip or 0)

    stat = {
        "courier_id": courier_id,
        "work_date": work_date.isoformat(),
        "route_id": route_id,
        "warehouse_id": warehouse_id,
        "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
        "dsp_id": safe_int(row.get("dsp_id")) or COURIER_HUB_DSP_ID,
        "courier_name": courier_name or None,
        "shift_name": shift_name or None,
        "queue_started_at": queue_started or None,
        "actual_shift_start_at": actual_shift_start_for_stat,
        "route_assigned_at": route_assigned or None,
        "departed_at": departed or None,
        "returned_at": returned or None,
        "planned_departure_at": planned_departure or None,
        "planned_return_at": planned_return or None,
        "next_shift_same_day": next_shift_text({"work_date": work_date.isoformat(), "route_assigned_at": route_assigned, "departed_at": departed, "shift_name": shift_name}, day_shifts),
        "late_stop_count": late_count,
        "late_stop_minutes": late_minutes,
        "planned_route_minutes": minutes_between(planned_departure, planned_return),
        "actual_route_minutes": minutes_between(route_assigned, returned),
        "waiting_minutes": minutes_between(queue_started, route_assigned),
        "loading_minutes": minutes_between(route_assigned, departed),
        "total_minutes": minutes_between(route_assigned, returned),
        "planned_km": round2(planned_km),
        "hub_mileage_km": round2(mileage_km),
        "google_route_km": round2(google_route_km),
        "google_route_minutes": int_or_none(google_result.get("duration_minutes")),
        "google_traffic_delay_minutes": int_or_none(google_result.get("traffic_delay_minutes")),
        "google_route_status": clean_text(google_result.get("message")) or None,
        "actual_km": round2(actual_km),
        "distance_delta_km": round2(distance_delta),
        "distance_source": "Google Routes" if google_route_km is not None else "Nincs Google Routes adat",
        "route_type": route_type or None,
        "route_type_label": route_type_label(route_type),
        "tip_huf": round2(tip_huf),
        "tip_source": "financial-overview routes" if financial_tip is not None else ("route performance detail" if detail_tip is not None else "nincs adat"),
        "orders": safe_int(payload.get("orderCount") or payload.get("orders")) or safe_int(financial_route.get("orders")) or len(stops),
        "stops": len(stops),
        "vehicle_plate": clean_text(shift.get("vehiclePlate")) or None,
        "warehouse_address": WAREHOUSE_ADDRESSES.get(warehouse_id),
        "source_table": "courier_route_performance_detail_raw",
        "source_updated_at": row.get("updated_at") or row.get("fetched_at"),
        "request_url": row.get("request_url"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    stat["story_text"] = story_for_route(stat)
    return stat


def shift_day_summary(shifts: list[dict[str, Any]]) -> dict[str, int]:
    late_login = 0
    no_show = 0
    for shift in shifts:
        text = clean_text(shift.get("evaluation") or shift.get("status")).upper()
        if text == "LATE":
            late_login += 1
        if text in {"NO_SHOW", "NOSHOW", "ABSENT", "MISSING"}:
            no_show += 1
    return {"shift_count": len(shifts), "late_login_shift_count": late_login, "no_show_shift_count": no_show}


def build_daily_stats(route_stats: list[dict[str, Any]], shifts_by_courier_day: dict[tuple[int, int, date], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, date, int], list[dict[str, Any]]] = defaultdict(list)
    for row in route_stats:
        grouped[(int(row["courier_id"]), int(row["warehouse_id"]), parse_date(row["work_date"]) or date.min, int(row["dsp_id"]))].append(row)

    for courier_id, warehouse_id, work_date in shifts_by_courier_day.keys():
        grouped.setdefault((courier_id, warehouse_id, work_date, COURIER_HUB_DSP_ID), [])

    daily_rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for (courier_id, warehouse_id, work_date, dsp_id), rows in sorted(grouped.items(), key=lambda item: item[0]):
        if work_date == date.min:
            continue
        shifts = shifts_by_courier_day.get((courier_id, warehouse_id, work_date), [])
        shift_summary = shift_day_summary(shifts)
        courier_name = next((row.get("courier_name") for row in rows if row.get("courier_name")), None)
        planned_km_total = sum(float(row.get("planned_km") or 0) for row in rows) if rows else None
        hub_mileage_km_total = sum(float(row.get("hub_mileage_km") or 0) for row in rows) if rows else None
        google_route_km_total = sum(float(row.get("google_route_km") or 0) for row in rows) if rows else None
        actual_km_total = sum(float(row.get("actual_km") or 0) for row in rows) if rows else None
        google_route_minutes_total = sum(int(row.get("google_route_minutes") or 0) for row in rows) if rows else None
        google_traffic_delay_minutes_total = sum(int(row.get("google_traffic_delay_minutes") or 0) for row in rows) if rows else None
        planned_minutes = sum(int(row.get("planned_route_minutes") or 0) for row in rows) if rows else None
        actual_minutes = sum(int(row.get("actual_route_minutes") or 0) for row in rows) if rows else None
        waiting_minutes = sum(int(row.get("waiting_minutes") or 0) for row in rows) if rows else None
        loading_minutes = sum(int(row.get("loading_minutes") or 0) for row in rows) if rows else None
        total_minutes = sum(int(row.get("total_minutes") or 0) for row in rows) if rows else None
        route_types = sorted({clean_text(row.get("route_type_label")) for row in rows if clean_text(row.get("route_type_label"))})
        first_queue = min((parse_datetime(row.get("queue_started_at")) for row in rows if parse_datetime(row.get("queue_started_at"))), default=None)
        first_assigned = min((parse_datetime(row.get("route_assigned_at")) for row in rows if parse_datetime(row.get("route_assigned_at"))), default=None)
        last_returned = max((parse_datetime(row.get("returned_at")) for row in rows if parse_datetime(row.get("returned_at"))), default=None)
        daily = {
            "courier_id": courier_id,
            "work_date": work_date.isoformat(),
            "warehouse_id": warehouse_id,
            "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
            "dsp_id": dsp_id,
            "courier_name": courier_name,
            "shift_count": shift_summary["shift_count"],
            "route_count": len(rows),
            "late_route_count": sum(1 for row in rows if int(row.get("late_stop_count") or 0) > 0),
            "late_stop_count": sum(int(row.get("late_stop_count") or 0) for row in rows),
            "late_stop_minutes": sum(int(row.get("late_stop_minutes") or 0) for row in rows),
            "no_show_shift_count": shift_summary["no_show_shift_count"],
            "late_login_shift_count": shift_summary["late_login_shift_count"],
            "planned_route_minutes_total": planned_minutes,
            "actual_route_minutes_total": actual_minutes,
            "waiting_minutes_total": waiting_minutes,
            "loading_minutes_total": loading_minutes,
            "total_minutes_total": total_minutes,
            "planned_km_total": round2(planned_km_total),
            "hub_mileage_km_total": round2(hub_mileage_km_total),
            "google_route_km_total": round2(google_route_km_total),
            "google_route_minutes_total": google_route_minutes_total,
            "google_traffic_delay_minutes_total": google_traffic_delay_minutes_total,
            "actual_km_total": round2(actual_km_total),
            "distance_delta_km_total": round2(actual_km_total - planned_km_total) if actual_km_total is not None and planned_km_total is not None else None,
            "tip_huf_total": round2(sum(float(row.get("tip_huf") or 0) for row in rows)),
            "first_queue_started_at": iso_datetime(first_queue),
            "first_route_assigned_at": iso_datetime(first_assigned),
            "last_returned_at": iso_datetime(last_returned),
            "route_types": route_types,
            "updated_at": now,
        }
        daily["daily_story_text"] = story_for_day(daily)
        daily_rows.append(daily)
    return daily_rows


def dates_between(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def print_route_raw_coverage(raw_rows: list[dict[str, Any]], start_date: date, end_date: date) -> None:
    covered_dates: set[date] = set()
    for row in raw_rows:
        payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
        shift = payload.get("shift") if isinstance(payload.get("shift"), dict) else {}
        work_date = route_work_date(payload, shift)
        if work_date:
            covered_dates.add(work_date)
    missing_dates = [day for day in dates_between(start_date, end_date) if day not in covered_dates]
    print(
        f"Route raw coverage: days_with_data={len(covered_dates)} "
        f"expected_days={(end_date - start_date).days + 1}",
        flush=True,
    )
    if missing_dates:
        preview = ", ".join(day.isoformat() for day in missing_dates[:12])
        suffix = "..." if len(missing_dates) > 12 else ""
        print(f"Route raw missing days: {preview}{suffix}", flush=True)


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
    if not rows:
        return 0
    supabase_url = require_env("SUPABASE_URL").rstrip("/")
    total = 0
    for start in range(0, len(rows), 500):
        batch = rows[start:start + 500]
        response = requests.post(
            f"{supabase_url}/rest/v1/{table}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": on_conflict},
            json=batch,
            timeout=90,
        )
        raise_for_response(response, f"{table} upsert")
        total += len(batch)
    return total


def delete_stats_for_period(
    *,
    start_date: date,
    end_date: date,
    courier_id: int | None,
    warehouse_id: int | None,
) -> None:
    supabase_url = require_env("SUPABASE_URL").rstrip("/")
    date_filter = f"(work_date.gte.{start_date.isoformat()},work_date.lte.{end_date.isoformat()})"
    for table in ("courier_hub_route_statistics", "courier_hub_courier_daily_statistics"):
        params: dict[str, str] = {"and": date_filter}
        if courier_id:
            params["courier_id"] = f"eq.{courier_id}"
        if warehouse_id:
            params["warehouse_id"] = f"eq.{warehouse_id}"
        response = requests.delete(
            f"{supabase_url}/rest/v1/{table}",
            headers=supabase_headers("return=minimal"),
            params=params,
            timeout=90,
        )
        raise_for_response(response, f"{table} period torles")
        print(
            f"Korabbi stat sorok torolve: table={table} "
            f"period={start_date.isoformat()}..{end_date.isoformat()}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Courier Hub route es napi statisztika epitese raw Hub adatokbol.")
    parser.add_argument("--apply", action="store_true", help="Mentse az eredmenyt Supabase-be.")
    parser.add_argument(
        "--replace-period",
        action="store_true",
        help="Mentes elott torli az adott idoszak korabbi stat sorait, majd ujraepiti oket.",
    )
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--courier-id", type=int)
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument(
        "--skip-google-routes",
        action="store_true",
        help="Ne szamoljon Google Routes km-et, csak a Hub mileageKm/plannedKm mezoket hasznalja.",
    )
    args = parser.parse_args()

    start_date = parse_date(args.date_from)
    end_date = parse_date(args.date_to)
    if not start_date or not end_date:
        if not args.year or not args.month:
            raise RuntimeError("--year es --month vagy --date-from es --date-to kotelezo.")
        start_date, end_date = month_bounds(args.year, args.month)
    if start_date > end_date:
        raise RuntimeError("A --date-from nem lehet kesobbi, mint a --date-to.")
    if args.replace_period and not args.apply:
        raise RuntimeError("A --replace-period csak --apply mellett hasznalhato.")
    require_env("SUPABASE_URL")
    require_env("SUPABASE_SERVICE_ROLE_KEY")
    calculate_google = not args.skip_google_routes

    shift_rows = read_shift_rows(
        start_date=start_date,
        end_date=end_date,
        courier_id=args.courier_id,
        warehouse_id=args.warehouse_id,
    )
    shifts_by_courier_day: dict[tuple[int, int, date], list[dict[str, Any]]] = defaultdict(list)
    for shift in shift_rows:
        work_date = parse_date(shift.get("work_date"))
        courier_id = safe_int(shift.get("courier_id"))
        warehouse_id = safe_int(shift.get("warehouse_id"))
        if work_date and courier_id > 0 and warehouse_id > 0:
            shifts_by_courier_day[(courier_id, warehouse_id, work_date)].append(shift)
    courier_names = read_courier_name_lookup()
    live_latest = read_live_latest_lookup(courier_id=args.courier_id, warehouse_id=args.warehouse_id)
    financial_routes = read_financial_route_lookup(
        start_date=start_date,
        end_date=end_date,
        courier_id=args.courier_id,
        warehouse_id=args.warehouse_id,
    )

    raw_rows = read_route_raw_rows(
        start_date=start_date,
        end_date=end_date,
        courier_id=args.courier_id,
        warehouse_id=args.warehouse_id,
        limit=args.limit,
    )
    print_route_raw_coverage(raw_rows, start_date, end_date)
    route_stats = [
        stat
        for row in raw_rows
        if (
            stat := build_route_stat(
                row,
                shifts_by_courier_day,
                calculate_google=calculate_google,
                courier_names=courier_names,
                live_latest=live_latest,
                financial_routes=financial_routes,
            )
        ) is not None
    ]
    daily_stats = build_daily_stats(route_stats, shifts_by_courier_day)

    print(
        f"Hub stat target: routes={len(route_stats)} daily={len(daily_stats)} "
        f"raw_rows={len(raw_rows)} "
        f"period={start_date.isoformat()}..{end_date.isoformat()} "
        f"google_routes={'on' if calculate_google else 'off'} "
        f"name_lookup={len(courier_names)} live_lookup={len(live_latest)} "
        f"financial_route_lookup={len(financial_routes)} "
        f"mode={'APPLY' if args.apply else 'DRY-RUN'}",
        flush=True,
    )
    for row in route_stats[:5]:
        print(
            f"ROUTE {row['work_date']} WH={row['warehouse_id']} courier={row['courier_id']} "
            f"route={row['route_id']} shift={row.get('shift_name') or '-'} "
            f"plannedKm={row.get('planned_km')} googleKm={row.get('google_route_km')} "
            f"hubKm={row.get('hub_mileage_km')} actualKm={row.get('actual_km')} tip={row.get('tip_huf')}",
            flush=True,
        )
    for row in daily_stats[:5]:
        print(
            f"DAY {row['work_date']} WH={row['warehouse_id']} courier={row['courier_id']} "
            f"routes={row['route_count']} shifts={row['shift_count']} km={row.get('actual_km_total')} tip={row.get('tip_huf_total')}",
            flush=True,
        )

    if args.apply:
        if args.replace_period:
            delete_stats_for_period(
                start_date=start_date,
                end_date=end_date,
                courier_id=args.courier_id,
                warehouse_id=args.warehouse_id,
            )
        route_written = upsert(
            "courier_hub_route_statistics",
            route_stats,
            "courier_id,work_date,route_id,warehouse_id,dsp_id",
        )
        daily_written = upsert(
            "courier_hub_courier_daily_statistics",
            daily_stats,
            "courier_id,work_date,warehouse_id,dsp_id",
        )
        print(f"Mentve: route_stat={route_written}, daily_stat={daily_written}", flush=True)
    else:
        print("Dry-run kesz. Menteshez add hozza: --apply", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
