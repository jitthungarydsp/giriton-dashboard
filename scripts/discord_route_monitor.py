import argparse
import base64
import json
import os
from collections import Counter
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
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

from sync_courier_financial_overview import (
    courier_hub_headers,
    refresh_courier_hub_headers,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
NOTIFICATION_TABLE = "discord_route_notifications"
PUSH_SUBSCRIPTION_TABLE = "pwa_push_subscriptions"
PUSH_DELIVERY_TABLE = "pwa_push_delivery_log"
PUSH_NOTIFICATION_TYPE = "route_assigned"
ATTENDANCE_CACHE = {}
COURIER_HUB_BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service"
COURIER_HUB_DSP_ID = int(os.getenv("COURIER_HUB_DSP_ID") or "8")
COURIER_HUB_LIVE_MAP_WAREHOUSE_IDS = [
    int(value)
    for value in str(os.getenv("COURIER_HUB_LIVE_MAP_WAREHOUSE_IDS") or "1,2")
    .replace(";", ",")
    .split(",")
    if str(value).strip().isdigit()
]
COURIER_HUB_LIVE_MAP_TRACK_CHUNK_SIZE = int(
    os.getenv("COURIER_HUB_LIVE_MAP_TRACK_CHUNK_SIZE") or "80"
)
COURIER_HUB_DETAIL_CACHE = {}
COURIER_HUB_PERFORMANCE_SHIFT_CACHE = {}


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


def timestamp_or_none(value):
    text = str(value or "").strip()
    return text or None


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


def warehouse_id_for_courier_hub(value):
    warehouse = normalize_warehouse(value)
    if warehouse == "BUD1":
        return 1
    if warehouse == "BUD2":
        return 2
    return None


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


def load_live_monitoring_dashboard(warehouse_id):
    url = (
        f"{COURIER_HUB_BASE_URL}/external/warehouses/{int(warehouse_id)}"
        f"/live-monitoring-dashboard?dspId={COURIER_HUB_DSP_ID}"
    )
    response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    if response.status_code in {401, 403} and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def load_courier_hub_departure_dashboard(warehouse_id):
    url = (
        f"{COURIER_HUB_BASE_URL}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{COURIER_HUB_DSP_ID}/departure-dashboard"
    )
    response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    if response.status_code in {401, 403} and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def load_live_monitoring_courier_detail(warehouse, courier_id):
    warehouse_id = warehouse_id_for_courier_hub(warehouse)
    normalized_courier_id = normalize_id(courier_id)

    if not warehouse_id or not normalized_courier_id:
        return {}

    cache_key = (warehouse_id, normalized_courier_id)
    if cache_key in COURIER_HUB_DETAIL_CACHE:
        return COURIER_HUB_DETAIL_CACHE[cache_key]

    url = (
        f"{COURIER_HUB_BASE_URL}/external/warehouses/{warehouse_id}"
        f"/live-monitoring-dashboard/couriers/{normalized_courier_id}"
        f"?dspId={COURIER_HUB_DSP_ID}"
    )
    response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    if response.status_code in {401, 403} and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    COURIER_HUB_DETAIL_CACHE[cache_key] = payload

    if isinstance(payload, dict):
        keys = ",".join(sorted(str(key) for key in payload.keys())[:30])
    else:
        keys = type(payload).__name__
    print(
        "COURIER_HUB_COURIER_DETAIL "
        f"warehouse={warehouse_id} courier={normalized_courier_id} keys={keys}",
        flush=True,
    )
    return payload


def load_courier_hub_performance_shifts(courier_id, warehouse, date_from, date_to):
    warehouse_id = warehouse_id_for_courier_hub(warehouse)
    normalized_courier_id = normalize_id(courier_id)
    if not warehouse_id or not normalized_courier_id:
        return {}

    cache_key = (warehouse_id, normalized_courier_id, date_from, date_to)
    if cache_key in COURIER_HUB_PERFORMANCE_SHIFT_CACHE:
        return COURIER_HUB_PERFORMANCE_SHIFT_CACHE[cache_key]

    url = (
        f"{COURIER_HUB_BASE_URL}/external/performance/courier/{int(normalized_courier_id)}/shifts"
        f"?dateFrom={date_from}&dateTo={date_to}"
        f"&dspId={COURIER_HUB_DSP_ID}&warehouseId={warehouse_id}"
    )
    response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    if response.status_code in {401, 403} and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    COURIER_HUB_PERFORMANCE_SHIFT_CACHE[cache_key] = payload
    return payload


def warehouse_code_for_id(warehouse_id):
    if int(warehouse_id) == 1:
        return "BUD1"
    if int(warehouse_id) == 2:
        return "BUD2"
    return f"WH{int(warehouse_id)}"


def safe_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def chunked(items, size):
    size = max(int(size or 1), 1)
    for index in range(0, len(items), size):
        yield items[index:index + size]


def courier_hub_get_json(url):
    response = requests.get(url, headers=courier_hub_headers(), timeout=30)
    if response.status_code in {401, 403} and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=30)

    try:
        payload = response.json()
    except ValueError:
        payload = {"_non_json_response": response.text[:5000]}

    return response.status_code, payload


def live_map_url(warehouse_id):
    return (
        f"{COURIER_HUB_BASE_URL}/external/warehouses/{int(warehouse_id)}"
        f"/live-map?dspId={COURIER_HUB_DSP_ID}"
    )


def live_map_tracks_url(warehouse_id, courier_ids, include_geometry=False):
    joined_ids = ",".join(str(courier_id) for courier_id in courier_ids)
    return (
        f"{COURIER_HUB_BASE_URL}/external/warehouses/{int(warehouse_id)}"
        f"/live-map/tracks?dspId={COURIER_HUB_DSP_ID}"
        f"&courierIds={quote(joined_ids)}"
        f"&includeGeometry={'true' if include_geometry else 'false'}"
    )


def live_map_couriers(payload):
    if not isinstance(payload, dict):
        return []
    couriers = payload.get("couriers")
    return couriers if isinstance(couriers, list) else []


def live_map_tracks(payload):
    if not isinstance(payload, dict):
        return []
    tracks = payload.get("tracks")
    return tracks if isinstance(tracks, list) else []


def supabase_upsert_rows(table, rows, on_conflict, dry_run=False, batch_size=500):
    if not rows:
        return 0

    if dry_run:
        return len(rows)

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        return 0

    written_count = 0
    endpoint = f"{supabase_url}/rest/v1/{table}"
    for batch in chunked(rows, batch_size):
        response = requests.post(
            endpoint,
            headers=supabase_headers(
                service_role_key,
                "resolution=merge-duplicates,return=minimal",
            ),
            params={"on_conflict": on_conflict},
            json=batch,
            timeout=60,
        )
        if response.status_code in {404, 406}:
            print(
                f"Courier Hub live-map DB tabla nem talalhato: {table}",
                flush=True,
            )
            return written_count
        raise_for_supabase_error(response)
        written_count += len(batch)

    return written_count


def build_live_map_raw_row(
    warehouse_id,
    request_url,
    status_code,
    payload,
    fetched_at,
):
    snapshot_key = (
        f"{fetched_at.strftime('%Y%m%d%H%M%S%f')}"
        f"-wh{int(warehouse_id)}-dsp{COURIER_HUB_DSP_ID}-live-map"
    )
    return {
        "snapshot_key": snapshot_key,
        "warehouse_id": int(warehouse_id),
        "warehouse_code": warehouse_code_for_id(warehouse_id),
        "dsp_id": COURIER_HUB_DSP_ID,
        "request_url": request_url,
        "status_code": int(status_code or 0),
        "response_json": payload if isinstance(payload, (dict, list)) else {},
        "courier_count": len(live_map_couriers(payload)),
        "fetched_at": fetched_at.isoformat(),
        "updated_at": fetched_at.isoformat(),
    }


def build_live_map_courier_rows(warehouse_id, payload, fetched_at):
    rows = []
    for courier in live_map_couriers(payload):
        if not isinstance(courier, dict):
            continue

        courier_id = safe_int(
            courier.get("courierId")
            or courier.get("courier_id")
            or courier.get("id")
        )
        if courier_id is None:
            continue

        last_position = (
            courier.get("lastPosition")
            or courier.get("last_position")
            or courier.get("position")
            or {}
        )
        if not isinstance(last_position, dict):
            last_position = {}

        route_ids = (
            courier.get("routeIds")
            or courier.get("route_ids")
            or courier.get("routes")
            or []
        )
        if not isinstance(route_ids, list):
            route_ids = [route_ids] if route_ids else []

        rows.append(
            {
                "warehouse_id": int(warehouse_id),
                "dsp_id": COURIER_HUB_DSP_ID,
                "courier_id": courier_id,
                "courier_name": str(
                    courier.get("name")
                    or courier.get("courierName")
                    or courier.get("courier_name")
                    or ""
                ).strip(),
                "dsp_name": str(
                    courier.get("dspName")
                    or courier.get("dsp_name")
                    or ""
                ).strip(),
                "status": str(courier.get("status") or "").strip(),
                "shift_status": str(
                    courier.get("shiftStatus")
                    or courier.get("shift_status")
                    or ""
                ).strip(),
                "delay_minutes": safe_int(
                    courier.get("delayMinutes")
                    or courier.get("delay_minutes")
                ),
                "deliveries_completed": safe_int(
                    courier.get("deliveriesCompleted")
                    or courier.get("deliveries_completed")
                ),
                "stops_total": safe_int(
                    courier.get("stopsTotal")
                    or courier.get("stops_total")
                ),
                "finished_route_count": safe_int(
                    courier.get("finishedRouteCount")
                    or courier.get("finished_route_count")
                ),
                "route_ids": route_ids,
                "vehicle_plate": str(
                    courier.get("vehiclePlate")
                    or courier.get("vehicle_plate")
                    or ""
                ).strip(),
                "fridge_config": courier.get("fridgeConfig")
                or courier.get("fridge_config"),
                "temperature_celsius": safe_float(
                    courier.get("temperatureCelsius")
                    or courier.get("temperature_celsius")
                ),
                "temperature_status": courier.get("temperatureStatus")
                or courier.get("temperature_status"),
                "last_latitude": safe_float(
                    last_position.get("latitude")
                    or last_position.get("lat")
                ),
                "last_longitude": safe_float(
                    last_position.get("longitude")
                    or last_position.get("lng")
                    or last_position.get("lon")
                ),
                "last_position_time": timestamp_or_none(
                    last_position.get("time")
                    or last_position.get("timestamp")
                    or last_position.get("createdAt")
                    or last_position.get("created_at")
                ),
                "active_from": timestamp_or_none(
                    courier.get("activeFrom")
                    or courier.get("active_from")
                ),
                "active_to": timestamp_or_none(
                    courier.get("activeTo")
                    or courier.get("active_to")
                ),
                "courier_json": courier,
                "fetched_at": fetched_at.isoformat(),
                "updated_at": fetched_at.isoformat(),
            }
        )

    return rows


def build_live_map_track_raw_row(
    warehouse_id,
    courier_ids,
    include_geometry,
    request_url,
    status_code,
    payload,
    fetched_at,
):
    tracks = live_map_tracks(payload)
    stop_count = sum(
        len(track.get("stops") or [])
        for track in tracks
        if isinstance(track, dict)
    )
    point_count = sum(
        len(track.get("points") or [])
        for track in tracks
        if isinstance(track, dict)
    )
    courier_part = "-".join(str(courier_id) for courier_id in courier_ids[:5])
    if len(courier_ids) > 5:
        courier_part = f"{courier_part}-plus{len(courier_ids) - 5}"
    snapshot_key = (
        f"{fetched_at.strftime('%Y%m%d%H%M%S%f')}"
        f"-wh{int(warehouse_id)}-dsp{COURIER_HUB_DSP_ID}"
        f"-tracks-{courier_part or 'empty'}"
    )
    return {
        "snapshot_key": snapshot_key,
        "warehouse_id": int(warehouse_id),
        "warehouse_code": warehouse_code_for_id(warehouse_id),
        "dsp_id": COURIER_HUB_DSP_ID,
        "courier_ids": ",".join(str(courier_id) for courier_id in courier_ids),
        "include_geometry": bool(include_geometry),
        "request_url": request_url,
        "status_code": int(status_code or 0),
        "response_json": payload if isinstance(payload, (dict, list)) else {},
        "track_count": len(tracks),
        "stop_count": stop_count,
        "point_count": point_count,
        "fetched_at": fetched_at.isoformat(),
        "updated_at": fetched_at.isoformat(),
    }


def build_live_map_stop_rows(warehouse_id, payload, fetched_at):
    rows = []
    for track in live_map_tracks(payload):
        if not isinstance(track, dict):
            continue

        courier_id = safe_int(
            track.get("courierId")
            or track.get("courier_id")
            or track.get("courier")
        )
        route_id = safe_int(
            track.get("routeId")
            or track.get("route_id")
            or track.get("route")
        )
        stops = track.get("stops") or []
        if not isinstance(stops, list):
            continue

        for stop in stops:
            if not isinstance(stop, dict):
                continue

            stop_route_id = safe_int(
                stop.get("routeId")
                or stop.get("route_id")
                or route_id
            )
            order_id = safe_int(
                stop.get("orderId")
                or stop.get("order_id")
                or stop.get("id")
            )
            if courier_id is None or stop_route_id is None or order_id is None:
                continue

            rows.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "dsp_id": COURIER_HUB_DSP_ID,
                    "courier_id": courier_id,
                    "route_id": stop_route_id,
                    "order_id": order_id,
                    "sequence": safe_int(stop.get("sequence")) or 0,
                    "latitude": safe_float(stop.get("latitude") or stop.get("lat")),
                    "longitude": safe_float(
                        stop.get("longitude") or stop.get("lng") or stop.get("lon")
                    ),
                    "address": str(stop.get("address") or "").strip(),
                    "planned_arrival_at": timestamp_or_none(
                        stop.get("plannedArrivalAt")
                        or stop.get("planned_arrival_at")
                        or stop.get("plannedArrivalTime")
                    ),
                    "actual_arrival_at": timestamp_or_none(
                        stop.get("actualArrivalAt")
                        or stop.get("actual_arrival_at")
                        or stop.get("realArrivalTime")
                    ),
                    "delay_minutes": safe_int(
                        stop.get("delayMinutes")
                        or stop.get("delay_minutes")
                    ),
                    "state": str(stop.get("state") or stop.get("status") or "").strip(),
                    "stop_json": stop,
                    "fetched_at": fetched_at.isoformat(),
                    "updated_at": fetched_at.isoformat(),
                }
            )

    return rows


def sync_courier_hub_live_map_data(dry_run=False):
    counters = Counter()

    for warehouse_id in COURIER_HUB_LIVE_MAP_WAREHOUSE_IDS:
        fetched_at = datetime.now(LOCAL_TIMEZONE)
        url = live_map_url(warehouse_id)
        status_code, payload = courier_hub_get_json(url)

        try:
            counters["live_map_raw_rows"] += supabase_upsert_rows(
                "courier_hub_live_map_raw",
                [
                    build_live_map_raw_row(
                        warehouse_id,
                        url,
                        status_code,
                        payload,
                        fetched_at,
                    )
                ],
                "snapshot_key",
                dry_run=dry_run,
            )
            courier_rows = build_live_map_courier_rows(
                warehouse_id,
                payload,
                fetched_at,
            )
            counters["live_map_courier_rows"] += supabase_upsert_rows(
                "courier_hub_live_map_courier_latest",
                courier_rows,
                "warehouse_id,dsp_id,courier_id",
                dry_run=dry_run,
            )
        except Exception as exc:
            counters["live_map_db_error"] += 1
            print(
                f"Courier Hub live-map DB mentes hiba warehouse={warehouse_id}: {exc}",
                flush=True,
            )

        if int(status_code or 0) >= 400:
            counters["live_map_http_error"] += 1
            continue

        courier_ids = [
            row["courier_id"]
            for row in build_live_map_courier_rows(warehouse_id, payload, fetched_at)
        ]
        if not courier_ids:
            counters["live_map_no_couriers"] += 1
            continue

        for courier_id_chunk in chunked(
            sorted(set(courier_ids)),
            COURIER_HUB_LIVE_MAP_TRACK_CHUNK_SIZE,
        ):
            track_fetched_at = datetime.now(LOCAL_TIMEZONE)
            track_url = live_map_tracks_url(
                warehouse_id,
                courier_id_chunk,
                include_geometry=False,
            )
            track_status_code, track_payload = courier_hub_get_json(track_url)
            try:
                counters["live_map_track_raw_rows"] += supabase_upsert_rows(
                    "courier_hub_live_map_track_raw",
                    [
                        build_live_map_track_raw_row(
                            warehouse_id,
                            courier_id_chunk,
                            False,
                            track_url,
                            track_status_code,
                            track_payload,
                            track_fetched_at,
                        )
                    ],
                    "snapshot_key",
                    dry_run=dry_run,
                )
                counters["live_map_stop_rows"] += supabase_upsert_rows(
                    "courier_hub_live_map_stop_latest",
                    build_live_map_stop_rows(
                        warehouse_id,
                        track_payload,
                        track_fetched_at,
                    ),
                    "warehouse_id,dsp_id,courier_id,route_id,order_id",
                    dry_run=dry_run,
                )
            except Exception as exc:
                counters["live_map_track_db_error"] += 1
                print(
                    "Courier Hub live-map tracks DB mentes hiba "
                    f"warehouse={warehouse_id}: {exc}",
                    flush=True,
                )

            if int(track_status_code or 0) >= 400:
                counters["live_map_track_http_error"] += 1

    return counters


def format_performance_shift_time(value):
    text = str(value or "").strip()
    if not text:
        return "-"
    parsed = parse_datetime(text)
    if parsed:
        return parsed.strftime("%H:%M")
    return text[:5] if len(text) >= 5 else text


def build_performance_shift_note(courier_id, warehouse, route):
    warehouse_id = warehouse_id_for_courier_hub(warehouse)
    if not warehouse_id:
        return ""
    work_date_text = route_work_date(route)
    try:
        work_date = datetime.strptime(work_date_text[:10], "%Y-%m-%d").date()
    except ValueError:
        work_date = datetime.now(LOCAL_TIMEZONE).date()
    date_from = (work_date - timedelta(days=6)).isoformat()
    date_to = work_date.isoformat()
    try:
        payload = load_courier_hub_performance_shifts(
            courier_id,
            warehouse,
            date_from,
            date_to,
        )
    except Exception as exc:
        return f"nem elerheto ({exc})"

    shifts = payload.get("shifts") if isinstance(payload, dict) else []
    if not isinstance(shifts, list):
        shifts = []
    total = payload.get("totalShifts", len(shifts)) if isinstance(payload, dict) else len(shifts)
    late = payload.get("lateLoginShifts", 0) if isinstance(payload, dict) else 0
    no_show = payload.get("noShowShifts", 0) if isinstance(payload, dict) else 0
    same_day = [
        shift
        for shift in shifts
        if isinstance(shift, dict)
        and str(shift.get("date") or "")[:10] == work_date.isoformat()
    ]
    shift_parts = []
    for shift in same_day[:4]:
        planned = (
            f"{format_performance_shift_time(shift.get('plannedStart'))}-"
            f"{format_performance_shift_time(shift.get('plannedEnd'))}"
        )
        actual = format_performance_shift_time(shift.get("actualStart"))
        evaluation = str(shift.get("evaluation") or "-").strip()
        shift_parts.append(f"{planned} actual {actual} {evaluation}")
    summary = f"{date_from}..{date_to}: osszes {total}, keso {late}, no-show {no_show}"
    if shift_parts:
        summary += " | mai: " + "; ".join(shift_parts)
    return summary


def find_live_monitoring_rows(value):
    rows = []
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        if "courierid" in keys and ("routeexternalid" in keys or "cargorouteid" in keys):
            rows.append(value)
        for child in value.values():
            rows.extend(find_live_monitoring_rows(child))
    elif isinstance(value, list):
        for item in value:
            rows.extend(find_live_monitoring_rows(item))
    return rows


def live_route_id(row):
    return normalize_id(
        row.get("cargoRouteId")
        or row.get("routeExternalId")
        or row.get("routeId")
        or row.get("id")
    )


def coalesce(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return ""


def normalize_live_monitoring_route(row, warehouse_id):
    route_id = live_route_id(row)
    courier_id = normalize_id(row.get("courierId") or row.get("courier_id"))
    warehouse = normalize_warehouse(row.get("warehouseCode") or warehouse_id)
    return {
        "courierId": courier_id,
        "courier_id": courier_id,
        "routeId": route_id,
        "route_id": route_id,
        "courier_name": str(row.get("name") or row.get("courierName") or "").strip(),
        "warehouse": warehouse,
        "warehouseCode": warehouse,
        "licence_plate": str(row.get("vehiclePlate") or "").strip(),
        "orders_in_route": str(row.get("stopsTotal") or row.get("stopProgress") or "").strip(),
        "plannedDeparture": row.get("plannedDepartureAt"),
        "realDeparture": row.get("departedAt"),
        "assignedAt": row.get("actualStartAt") or row.get("plannedDepartureAt") or row.get("plannedStartAt"),
        "plannedStartAt": row.get("plannedStartAt"),
        "actualStartAt": row.get("actualStartAt"),
        "raw_live_monitoring": row,
    }


def normalize_courier_hub_departure_route(row, warehouse_id):
    route_id = live_route_id(row)
    courier_id = normalize_id(
        coalesce(
            row.get("courierId"),
            row.get("courier_id"),
            row.get("driverId"),
            row.get("driver_id"),
        )
    )
    warehouse = normalize_warehouse(row.get("warehouseCode") or warehouse_id)
    return {
        "courierId": courier_id,
        "courier_id": courier_id,
        "routeId": route_id,
        "route_id": route_id,
        "courier_name": str(
            coalesce(
                row.get("name"),
                row.get("courierName"),
                row.get("driverName"),
                row.get("driver_name"),
            )
        ).strip(),
        "warehouse": warehouse,
        "warehouseCode": warehouse,
        "licence_plate": str(
            coalesce(
                row.get("vehiclePlate"),
                row.get("licensePlate"),
                row.get("licencePlate"),
            )
        ).strip(),
        "orders_in_route": str(
            coalesce(
                row.get("stopsTotal"),
                row.get("numTotalOrders"),
                row.get("ordersInRoute"),
                row.get("orders_in_route"),
            )
        ).strip(),
        "plannedDeparture": coalesce(row.get("plannedDeparture"), row.get("plannedDepartureAt")),
        "realDeparture": coalesce(row.get("realDeparture"), row.get("departedAt")),
        "assignedAt": coalesce(
            row.get("assignedAt"),
            row.get("courierRegisteredAt"),
            row.get("plannedDepartureAt"),
            row.get("plannedDeparture"),
            row.get("plannedStartAt"),
        ),
        "raw_courier_hub_departure_dashboard": row,
    }


def find_route_like_rows(value):
    rows = []
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        has_explicit_route_id = bool(
            {
                "routeexternalid",
                "cargorouteid",
                "routeid",
                "route_id",
            } & keys
        )
        has_route_shape_id = "id" in keys and bool(
            {
                "checkpoints",
                "planneddeparture",
                "planneddepartureat",
                "plannedreturn",
                "numtotalorders",
            } & keys
        )
        if live_route_id(value) and (has_explicit_route_id or has_route_shape_id):
            rows.append(value)
        for child in value.values():
            rows.extend(find_route_like_rows(child))
    elif isinstance(value, list):
        for item in value:
            rows.extend(find_route_like_rows(item))
    return rows


def find_courier_hub_detail_route(detail_payload, route_id):
    normalized_route_id = normalize_id(route_id)
    if not normalized_route_id:
        return {}

    for row in find_route_like_rows(detail_payload):
        if live_route_id(row) == normalized_route_id:
            return row

    rows = find_route_like_rows(detail_payload)
    return rows[0] if rows else {}


def normalize_courier_hub_detail_route(detail_route, detail_payload, fallback_route):
    source = detail_route if isinstance(detail_route, dict) else {}
    payload = detail_payload if isinstance(detail_payload, dict) else {}
    fallback = fallback_route if isinstance(fallback_route, dict) else {}

    source_route_id = live_route_id(source)
    fallback_route_id = live_route_id(fallback)
    route_id = source_route_id or fallback_route_id
    if source_route_id and fallback_route_id and source_route_id != fallback_route_id:
        route_id = fallback_route_id
    courier_id = normalize_id(
        coalesce(
            source.get("courierId"),
            source.get("courier_id"),
            payload.get("courierId"),
            payload.get("courier_id"),
            fallback.get("courierId"),
            fallback.get("courier_id"),
        )
    )
    warehouse = normalize_warehouse(
        coalesce(
            source.get("warehouseCode"),
            source.get("warehouse"),
            payload.get("warehouseCode"),
            payload.get("warehouse"),
            fallback.get("warehouseCode"),
            fallback.get("warehouse"),
        )
    )

    return {
        **fallback,
        **source,
        "courierId": courier_id,
        "courier_id": courier_id,
        "routeId": route_id,
        "route_id": route_id,
        "courier_name": str(
            coalesce(
                fallback.get("courier_name"),
                source.get("name"),
                source.get("courierName"),
                payload.get("name"),
                payload.get("courierName"),
            )
        ).strip(),
        "warehouse": warehouse,
        "warehouseCode": warehouse,
        "licence_plate": str(
            coalesce(
                source.get("vehiclePlate"),
                source.get("licensePlate"),
                source.get("licencePlate"),
                fallback.get("licence_plate"),
                fallback.get("vehiclePlate"),
            )
        ).strip(),
        "orders_in_route": str(
            coalesce(
                source.get("stopsTotal"),
                source.get("numTotalOrders"),
                fallback.get("orders_in_route"),
                fallback.get("stopsTotal"),
            )
        ).strip(),
        "plannedDeparture": coalesce(
            source.get("plannedDeparture"),
            source.get("plannedDepartureAt"),
            fallback.get("plannedDeparture"),
            fallback.get("plannedDepartureAt"),
        ),
        "plannedReturn": coalesce(
            source.get("plannedReturn"),
            source.get("plannedReturnAt"),
            source.get("expectedReturn"),
            fallback.get("plannedReturn"),
            fallback.get("plannedReturnAt"),
            fallback.get("expectedReturn"),
        ),
        "realReturn": coalesce(
            source.get("realReturn"),
            source.get("actualReturnAt"),
            source.get("finishedAt"),
            fallback.get("realReturn"),
            fallback.get("actualReturnAt"),
            fallback.get("finishedAt"),
        ),
        "assignedAt": coalesce(
            source.get("assignedAt"),
            source.get("actualStartAt"),
            source.get("plannedDepartureAt"),
            source.get("plannedStartAt"),
            fallback.get("assignedAt"),
        ),
        "raw_live_monitoring": fallback.get("raw_live_monitoring") or source,
        "raw_courier_hub_detail": detail_payload,
    }


def load_live_monitoring_routes():
    routes = []
    errors = []
    for warehouse_id in (1, 2):
        try:
            payload = load_live_monitoring_dashboard(warehouse_id)
        except Exception as exc:
            errors.append(f"WH{warehouse_id}: {exc}")
            continue
        rows = find_live_monitoring_rows(payload)
        routes.extend(
            normalize_live_monitoring_route(row, warehouse_id)
            for row in rows
            if normalize_id(row.get("courierId")) and live_route_id(row)
        )
    if not routes and errors:
        raise RuntimeError("; ".join(errors))
    if errors:
        print(
            "live-monitoring partial hiba: " + " | ".join(errors),
            flush=True,
        )
    return routes


def load_courier_hub_departure_routes():
    routes = []
    errors = []
    for warehouse_id in (1, 2):
        try:
            payload = load_courier_hub_departure_dashboard(warehouse_id)
        except Exception as exc:
            errors.append(f"WH{warehouse_id}: {exc}")
            continue
        rows = find_route_like_rows(payload)
        routes.extend(
            normalize_courier_hub_departure_route(row, warehouse_id)
            for row in rows
            if normalize_id(
                coalesce(
                    row.get("courierId"),
                    row.get("courier_id"),
                    row.get("driverId"),
                    row.get("driver_id"),
                )
            )
            and live_route_id(row)
        )
    if not routes and errors:
        raise RuntimeError("; ".join(errors))
    if errors:
        print(
            "courier-hub departure-dashboard partial hiba: " + " | ".join(errors),
            flush=True,
        )
    return routes


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


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)


def find_named_dict(value, names):
    normalized_names = {
        str(name).lower().replace("_", "").replace("-", "")
        for name in names
    }
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower().replace("_", "").replace("-", "")
            if key_text in normalized_names and isinstance(child, dict):
                return child
            found = find_named_dict(child, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_named_dict(item, names)
            if found:
                return found
    return {}


def parse_courier_hub_shift_item(item):
    if not isinstance(item, dict):
        return {}

    start_at = parse_datetime(
        coalesce(
            item.get("shiftStart"),
            item.get("shiftStartAt"),
            item.get("plannedStartAt"),
            item.get("startAt"),
            item.get("from"),
        )
    )
    end_at = parse_datetime(
        coalesce(
            item.get("shiftEnd"),
            item.get("shiftEndAt"),
            item.get("plannedEndAt"),
            item.get("endAt"),
            item.get("to"),
        )
    )
    label = str(
        coalesce(
            item.get("shiftName"),
            item.get("name"),
            item.get("title"),
            item.get("shiftStatus"),
            item.get("status"),
        )
    ).strip()

    if not start_at and not end_at and not label:
        return {}

    return {
        "shift_name": label,
        "shift_start": start_at,
        "shift_end": end_at,
        "available_for_shift_since": parse_datetime(
            coalesce(
                item.get("availableForShiftSince"),
                item.get("queuedAt"),
                item.get("checkedInAt"),
                item.get("noShowAutoFlaggedAt"),
            )
        ),
    }


def collect_courier_hub_shifts(detail_payload, route):
    shifts = []
    seen = set()

    for item in list(walk_dicts(detail_payload)) + [route]:
        if not isinstance(item, dict):
            continue
        keys = {str(key).lower() for key in item}
        if not (
            {"shiftstart", "shiftstartat", "plannedstartat", "shiftstatus"} & keys
            or any("shift" in key for key in keys)
        ):
            continue
        shift = parse_courier_hub_shift_item(item)
        if not shift:
            continue
        identity = (
            shift.get("shift_name"),
            shift.get("shift_start"),
            shift.get("shift_end"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        shifts.append(shift)

    return sorted(
        shifts,
        key=lambda item: item.get("shift_start") or datetime.max.replace(tzinfo=LOCAL_TIMEZONE),
    )


def build_courier_hub_shift_notification_notes(detail_payload, route):
    if not detail_payload and not route:
        return {}

    current_shift = parse_courier_hub_shift_item(
        find_named_dict(
            detail_payload,
            {"currentShift", "activeShift", "actualShift", "current_shift"},
        )
    )
    next_shift = parse_courier_hub_shift_item(
        find_named_dict(
            detail_payload,
            {"nextShift", "upcomingShift", "next_shift", "followingShift"},
        )
    )
    shifts = collect_courier_hub_shifts(detail_payload, route)
    now = datetime.now(LOCAL_TIMEZONE)

    if not current_shift:
        for shift in shifts:
            shift_start = shift.get("shift_start")
            shift_end = shift.get("shift_end")
            if shift_start and shift_end and shift_start <= now < shift_end:
                current_shift = shift
                break

    if not next_shift:
        future_shifts = [
            shift
            for shift in shifts
            if shift.get("shift_start") and shift["shift_start"] > now
        ]
        if future_shifts:
            next_shift = future_shifts[0]

    current_shift_note = (
        format_shift_label(current_shift)
        if current_shift
        else ""
    )
    next_shift_note = (
        format_shift_label(next_shift, include_times=False)
        if next_shift
        else ""
    )
    next_shift_delay_note = ""
    route_return_at = parse_datetime(route.get("realReturn") or route.get("plannedReturn"))
    next_shift_start = next_shift.get("shift_start") if next_shift else None
    if route_return_at and next_shift_start:
        delay_minutes = int((route_return_at - next_shift_start).total_seconds() // 60)
        if delay_minutes > 0:
            next_shift_delay_note = f"{delay_minutes} perc"

    queue_since = parse_datetime(
        coalesce(
            route.get("queuedAt"),
            route.get("checkedInAt"),
            route.get("availableForShiftSince"),
            route.get("noShowAutoFlaggedAt"),
        )
    )
    if not queue_since:
        for shift in reversed(shifts):
            if shift.get("available_for_shift_since"):
                queue_since = shift["available_for_shift_since"]
                break

    assigned_at = parse_datetime(route.get("assignedAt")) or now

    notes = {}
    if current_shift_note:
        notes["current_shift_note"] = current_shift_note
    if next_shift_note:
        notes["next_shift_note"] = next_shift_note
    if next_shift_delay_note:
        notes["next_shift_delay_note"] = next_shift_delay_note
    if queue_since:
        notes["queue_since_note"] = format_datetime_time(queue_since)
        notes["queue_wait_note"] = format_wait_duration(queue_since, assigned_at)
    return notes


def is_unavailable_shift_note(value):
    text = str(value or "").strip().lower()
    return (
        not text
        or "nem ellenorizheto" in text
        or "nincs attendance adat" in text
        or "nincs adat" in text
        or "jelenleg nincs aktualis muszakban" in text
        or "nincs kovetkezo muszak" in text
    )


def merge_shift_notes(primary, fallback):
    merged = dict(primary or {})
    fallback = fallback or {}

    for key in (
        "current_shift_note",
        "next_shift_note",
        "next_shift_delay_note",
        "queue_since_note",
        "queue_wait_note",
    ):
        if is_unavailable_shift_note(merged.get(key)) and fallback.get(key):
            merged[key] = fallback[key]

    return merged


def build_shift_notification_notes(courier_id, route, courier_hub_detail=None, use_attendance=True):
    courier_hub_notes = build_courier_hub_shift_notification_notes(
        courier_hub_detail,
        route,
    )
    if not use_attendance:
        return courier_hub_notes

    work_date = route_work_date(route)

    try:
        attendance_data = load_attendance_for_date(work_date)
    except Exception as exc:
        error_note = f"nem ellenorizheto (fetch-attendance hiba: {exc})"
        return merge_shift_notes({
            "current_shift_note": error_note,
            "next_shift_note": error_note,
            "next_shift_delay_note": "",
            "queue_since_note": "",
            "queue_wait_note": "",
        }, courier_hub_notes)

    courier = find_attendance_courier(attendance_data, courier_id)
    if not courier:
        error_note = "nem ellenorizheto (nincs attendance adat)"
        return merge_shift_notes({
            "current_shift_note": error_note,
            "next_shift_note": error_note,
            "next_shift_delay_note": "",
            "queue_since_note": "",
            "queue_wait_note": "",
        }, courier_hub_notes)

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

    return merge_shift_notes({
        "current_shift_note": current_shift_note,
        "next_shift_note": next_shift_note,
        "next_shift_delay_note": next_shift_delay_note,
        "queue_since_note": queue_since_note or "nincs adat",
        "queue_wait_note": queue_wait_note or "nincs adat",
    }, courier_hub_notes)


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

    # A route értesítés üzleti kulcsa a futár + route. A raktár csak leíró adat:
    # ha régi log sorban üres vagy eltérő, akkor sem szabad újraküldeni.
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


def build_notification_payload(
    courier_id,
    courier_name,
    route_id,
    route,
    checkpoint,
    licence_plate,
    orders_in_route,
    warehouse="",
):
    payload = {
        "courier_id": str(courier_id),
        "courier_name": str(courier_name or ""),
        "route_id": str(route_id),
        "order_id": str(checkpoint.get("orderId") or ""),
        "assigned_at": timestamp_or_none(route.get("assignedAt")),
        "planned_departure": timestamp_or_none(route.get("plannedDeparture")),
        "planned_return": timestamp_or_none(route.get("plannedReturn")),
        "licence_plate": str(licence_plate),
        "orders_in_route": str(orders_in_route),
    }
    normalized_warehouse = normalize_warehouse(warehouse)
    if normalized_warehouse:
        payload["warehouse"] = normalized_warehouse
    return payload


def reserve_notification_if_new(
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
        return "reserved"

    payload = build_notification_payload(
        courier_id,
        courier_name,
        route_id,
        route,
        checkpoint,
        licence_plate,
        orders_in_route,
        warehouse,
    )

    optional_columns = ("warehouse", "licence_plate", "orders_in_route")
    endpoint = (
        f"{supabase_url}/rest/v1/{NOTIFICATION_TABLE}"
        "?on_conflict=courier_id,route_id"
    )
    while True:
        response = requests.post(
            endpoint,
            headers=supabase_headers(
                service_role_key,
                "resolution=ignore-duplicates,return=representation",
            ),
            json=payload,
            timeout=20,
        )

        if response.status_code in [404, 406]:
            return "reserved"

        if response.status_code == 400:
            response_text = response.text or ""
            if (
                "no unique" in response_text.lower()
                or "42P10" in response_text
                or "ON CONFLICT" in response_text
            ):
                raise RuntimeError(
                    "A discord_route_notifications táblán még nincs aktív "
                    "unique(courier_id, route_id) védelem. Futtasd le: "
                    "docs/discord_route_notifications.sql"
                )
            removed = False
            for column in optional_columns:
                if column in payload:
                    payload.pop(column, None)
                    removed = True
                    break
            if removed:
                continue

        break

    raise_for_supabase_error(response)
    rows = response.json() if response.content else []
    return "reserved" if rows else "already_logged"


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

    payload = build_notification_payload(
        courier_id,
        courier_name,
        route_id,
        route,
        checkpoint,
        licence_plate,
        orders_in_route,
        warehouse,
    )

    optional_columns = ("warehouse", "licence_plate", "orders_in_route")
    endpoint = (
        f"{supabase_url}/rest/v1/{NOTIFICATION_TABLE}"
        "?on_conflict=courier_id,route_id"
    )
    while True:
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

        if response.status_code == 400:
            removed = False
            for column in optional_columns:
                if column in payload:
                    payload.pop(column, None)
                    removed = True
                    break
            if removed:
                continue

        break

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
    COURIER_HUB_DETAIL_CACHE.clear()
    discord_status = read_discord_status()
    counters = Counter()
    sent_count = 0
    skipped_count = 0

    print(
        "Discord monitor status: "
        f"webhook_configured={discord_status.get('webhook_configured')} "
        "source=courier-hub-departure-dashboard "
        f"max_age_minutes={max_age_minutes}",
        flush=True,
    )

    try:
        live_map_counters = sync_courier_hub_live_map_data(dry_run=dry_run)
        counters.update(live_map_counters)
        print(
            f"Courier Hub live-map mentes: {dict(live_map_counters)}",
            flush=True,
        )
    except Exception as exc:
        counters["live_map_sync_error"] += 1
        print(
            f"Courier Hub live-map sync hiba: {exc}",
            flush=True,
        )

    try:
        dashboard_routes = load_courier_hub_departure_routes()
        dashboard_source = "courier-hub-departure-dashboard"
    except Exception as exc:
        counters["courier_hub_departure_dashboard_error"] += 1
        print(
            f"courier-hub departure-dashboard hiba: {exc}",
            flush=True,
        )
        print(
            f"Monitor kor kesz: sent=0, skipped=0, reasons={dict(counters)}",
            flush=True,
        )
        return

    print(
        f"{dashboard_source} routes talalat: {len(dashboard_routes)}",
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

        if (
            dashboard_route.get("raw_live_monitoring")
            or dashboard_route.get("raw_courier_hub_departure_dashboard")
        ):
            route_warehouse_hint = find_route_warehouse(dashboard_route)
            try:
                driver_detail = load_live_monitoring_courier_detail(
                    route_warehouse_hint,
                    courier_id,
                )
            except Exception as exc:
                driver_detail = {}
                counters["courier_hub_detail_error"] += 1
                print(
                    f"#{courier_id} live courier detail hiba: {exc}",
                    flush=True,
                )

            detail_route = find_courier_hub_detail_route(driver_detail, route_id)
            route = normalize_courier_hub_detail_route(
                detail_route,
                driver_detail,
                dashboard_route,
            )
        else:
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
            str(dashboard_route.get("licence_plate") or dashboard_route.get("vehiclePlate") or "").strip()
        )
        orders_in_route = (
            str(
                dashboard_route.get("orders_in_route")
                or dashboard_route.get("stopsTotal")
                or route.get("numTotalOrders")
                or len(route.get("checkpoints", []) or [])
                or ""
            ).strip()
        )
        courier_name = (
            str(dashboard_route.get("courier_name") or "").strip()
            or str(dashboard_route.get("name") or "").strip()
            or get_courier_name(courier_id, driver_detail)
        )
        shift_notes = build_shift_notification_notes(
            courier_id,
            route,
            courier_hub_detail=driver_detail
            if (
                dashboard_route.get("raw_live_monitoring")
                or dashboard_route.get("raw_courier_hub_departure_dashboard")
            )
            else None,
            use_attendance=not (
                dashboard_route.get("raw_live_monitoring")
                or dashboard_route.get("raw_courier_hub_departure_dashboard")
            ),
        )
        performance_shift_note = build_performance_shift_note(
            courier_id,
            route_warehouse,
            route,
        )

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
                f"queue_wait={shift_notes.get('queue_wait_note') or '-'} "
                f"hub_performance={performance_shift_note or '-'}",
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
            try:
                reservation_result = reserve_notification_if_new(
                    courier_id,
                    courier_name,
                    route_id,
                    route,
                    checkpoint,
                    licence_plate,
                    orders_in_route,
                    route_warehouse,
                )
            except Exception as exc:
                counters["notification_reserve_error"] += 1
                skipped_count += 1
                print(
                    f"Discord route foglalas hiba: #{courier_id} route {route_id} | {exc}",
                    flush=True,
                )
                continue

            if reservation_result == "already_logged":
                counters["already_logged"] += 1
                skipped_count += 1
                print(
                    f"Discord route jelzes kihagyva: "
                    f"#{courier_id} route {route_id} (already_reserved)"
                )
                continue

            print(
                f"Discord route foglalva: "
                f"#{courier_id} route {route_id} warehouse={route_warehouse or '-'}",
                flush=True,
            )
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
                orders_in_route=orders_in_route,
                warehouse=route_warehouse,
                current_shift_note=shift_notes.get("current_shift_note", ""),
                next_shift_note=shift_notes.get("next_shift_note", ""),
                next_shift_delay_note=shift_notes.get("next_shift_delay_note", ""),
                queue_since_note=shift_notes.get("queue_since_note", ""),
                queue_wait_note=shift_notes.get("queue_wait_note", ""),
                performance_shift_note=performance_shift_note,
            )

            if result == "sent":
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
    parser.add_argument("--poll-seconds", type=int, default=120)
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
