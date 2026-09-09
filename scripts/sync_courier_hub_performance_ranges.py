#!/usr/bin/env python3
"""Sync Courier Hub performance routes and shifts by date range.

This uses the newer range endpoints:
- /external/performance/courier/{courier_id}/routes?dateFrom=...&dateTo=...
- /external/performance/courier/{courier_id}/shifts?dateFrom=...&dateTo=...

Existing successful raw pulls are skipped by default for the same
endpoint/courier/warehouse/date range.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    COURIER_TARGET_TABLES,
    clean_text,
    courier_hub_auth_configured,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
    safe_int,
    supabase_headers,
)


COURIER_HUB_BASE_URL = os.getenv(
    "COURIER_HUB_BASE_URL",
    "https://courier-hub.kifli.hu/services/courier-hub-service",
).rstrip("/")
COURIER_HUB_DSP_ID = int(os.getenv("COURIER_HUB_DSP_ID") or "8")


def parse_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def date_ranges(start_date: date, end_date: date, chunk_days: int) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=max(1, chunk_days) - 1), end_date)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def read_courier_refs(year: int, month: int, courier_id: int | None, warehouse_id: int | None) -> list[dict[str, Any]]:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    target_tables = (
        {warehouse_id: COURIER_TARGET_TABLES[int(warehouse_id)]}
        if warehouse_id
        else COURIER_TARGET_TABLES
    )
    refs: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for wh_id, table_name in target_tables.items():
        params = {
            "select": "courier_id,warehouse_id,response_json,status_code",
            "year": f"eq.{year}",
            "month": f"eq.{month}",
            "status_code": "eq.200",
            "limit": "5000",
        }
        if courier_id:
            params["courier_id"] = f"eq.{courier_id}"
        response = requests.get(
            f"{supabase_url}/rest/v1/{table_name}",
            headers=supabase_headers(),
            params=params,
            timeout=60,
        )
        raise_for_response(response, f"{table_name} courier refs")
        for row in response.json() or []:
            row_courier_id = safe_int(row.get("courier_id"))
            if row_courier_id <= 0:
                continue
            key = (int(wh_id), row_courier_id)
            if key in seen:
                continue
            seen.add(key)
            payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
            refs.append({
                "courier_id": row_courier_id,
                "warehouse_id": int(wh_id),
                "courier_name": clean_text(payload.get("courierName") or payload.get("name")),
            })
    return sorted(refs, key=lambda item: (item["warehouse_id"], item["courier_id"]))


def build_url(endpoint_type: str, courier_id: int, warehouse_id: int, date_from: date, date_to: date) -> str:
    return (
        f"{COURIER_HUB_BASE_URL}/external/performance/courier/{int(courier_id)}/{endpoint_type}"
        f"?dateFrom={date_from.isoformat()}&dateTo={date_to.isoformat()}"
        f"&dspId={COURIER_HUB_DSP_ID}&warehouseId={int(warehouse_id)}"
    )


def fetch_endpoint(endpoint_type: str, courier_id: int, warehouse_id: int, date_from: date, date_to: date) -> tuple[str, int, Any]:
    request_url = build_url(endpoint_type, courier_id, warehouse_id, date_from, date_to)
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))
    response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"_non_json_response": response.text[:5000]}
    return request_url, response.status_code, payload


def payload_items(payload: Any, endpoint_type: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    preferred = "routes" if endpoint_type == "routes" else "shifts"
    value = payload.get(preferred)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    for key in ("items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def total_count(payload: Any, endpoint_type: str) -> int:
    if not isinstance(payload, dict):
        return len(payload_items(payload, endpoint_type))
    keys = (
        ("totalRoutes", "routeCount", "routesTotal")
        if endpoint_type == "routes"
        else ("totalShifts", "shiftCount", "shiftsTotal")
    )
    for key in keys:
        value = safe_int(payload.get(key))
        if value > 0:
            return value
    return len(payload_items(payload, endpoint_type))


def endpoint_already_synced(endpoint_type: str, courier_id: int, warehouse_id: int, date_from: date, date_to: date) -> bool:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.get(
        f"{supabase_url}/rest/v1/courier_hub_performance_endpoint_raw",
        headers=supabase_headers(),
        params={
            "select": "endpoint_type",
            "endpoint_type": f"eq.{endpoint_type}",
            "courier_id": f"eq.{courier_id}",
            "warehouse_id": f"eq.{warehouse_id}",
            "dsp_id": f"eq.{COURIER_HUB_DSP_ID}",
            "date_from": f"eq.{date_from.isoformat()}",
            "date_to": f"eq.{date_to.isoformat()}",
            "status_code": "eq.200",
            "limit": "1",
        },
        timeout=30,
    )
    if response.status_code in (404, 406):
        return False
    raise_for_response(response, "performance endpoint raw existing check")
    return bool(response.json())


def money_amount(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("amount")
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def timestamp_or_none(value: Any) -> str | None:
    text = clean_text(value)
    return text or None


def route_date(item: dict[str, Any]) -> date | None:
    return parse_date(
        item.get("deliveryDate")
        or item.get("date")
        or item.get("workDate")
        or item.get("plannedStartAt")
        or item.get("plannedDepartureAt")
    )


def route_id(item: dict[str, Any]) -> int:
    return safe_int(item.get("routeId") or item.get("route_id") or item.get("id") or item.get("cargoRouteId"))


def route_time(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if "T" in text and len(text) >= 16:
        return text[11:16]
    if len(text) >= 5:
        return text[:5]
    return text


def route_type_label(value: Any) -> str:
    text = clean_text(value).lower()
    if "city" in text:
        return "City"
    if "express" in text:
        return "Express"
    if "region" in text:
        return "Regionális"
    return "Normál"


def route_minutes(start_value: Any, end_value: Any) -> int | None:
    start = parse_datetime(start_value)
    end = parse_datetime(end_value)
    if not start or not end or end < start:
        return None
    return int(round((end - start).total_seconds() / 60))


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def make_endpoint_raw_row(
    *,
    endpoint_type: str,
    ref: dict[str, Any],
    date_from: date,
    date_to: date,
    request_url: str,
    status_code: int,
    payload: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "endpoint_type": endpoint_type,
        "courier_id": int(ref["courier_id"]),
        "warehouse_id": int(ref["warehouse_id"]),
        "dsp_id": COURIER_HUB_DSP_ID,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "request_url": request_url,
        "status_code": status_code,
        "response_json": payload,
        "item_count": len(payload_items(payload, endpoint_type)),
        "total_count": total_count(payload, endpoint_type),
        "fetched_at": now,
        "updated_at": now,
    }


def make_route_rows(ref: dict[str, Any], date_from: date, date_to: date, request_url: str, status_code: int, payload: Any) -> list[dict[str, Any]]:
    if status_code != 200:
        return []
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    courier_id = int(ref["courier_id"])
    warehouse_id = int(ref["warehouse_id"])
    courier_name = clean_text(ref.get("courier_name"))
    for index, item in enumerate(payload_items(payload, "routes"), start=1):
        work_date = route_date(item)
        item_route_id = route_id(item)
        if not work_date or work_date < date_from or work_date > date_to or item_route_id <= 0:
            continue
        route_layer = clean_text(item.get("routeLayer") or item.get("routeType") or item.get("type"))
        planned_departure = item.get("plannedDepartureAt") or item.get("plannedDeparture")
        departed = item.get("departedAt") or item.get("warehouseDepartureActual") or item.get("realDeparture")
        planned_return = item.get("plannedReturnAt") or item.get("plannedReturn")
        returned = item.get("returnedAt") or item.get("warehouseArrivalActual") or item.get("realReturn")
        rows.append({
            "courier_id": courier_id,
            "warehouse_id": warehouse_id,
            "dsp_id": COURIER_HUB_DSP_ID,
            "work_date": work_date.isoformat(),
            "route_id": item_route_id,
            "route_key": f"{courier_id}:{warehouse_id}:{work_date.isoformat()}:{item_route_id}",
            "courier_name": clean_text(item.get("courierName") or item.get("name")) or courier_name or None,
            "route_type": route_layer or None,
            "route_type_label": route_type_label(route_layer),
            "shift_name": clean_text(item.get("shiftName") or item.get("shift") or route_time(item.get("plannedStartAt"))) or None,
            "planned_start_at": timestamp_or_none(item.get("plannedStartAt")),
            "actual_start_at": timestamp_or_none(item.get("actualStartAt")),
            "planned_departure_at": timestamp_or_none(planned_departure),
            "departed_at": timestamp_or_none(departed),
            "planned_return_at": timestamp_or_none(planned_return),
            "returned_at": timestamp_or_none(returned),
            "planned_route_minutes": route_minutes(planned_departure, planned_return),
            "actual_route_minutes": route_minutes(departed, returned),
            "planned_km": float_or_none(item.get("plannedKm")),
            "mileage_km": float_or_none(item.get("mileageKm")),
            "order_count": safe_int(item.get("orderCount") or item.get("orders")),
            "stops_total": safe_int(item.get("stopsTotal") or item.get("stops")),
            "delivered_count": safe_int(item.get("deliveredCount") or item.get("deliveriesCompleted")),
            "delayed_count": safe_int(item.get("delayedCount") or item.get("lateStopCount")),
            "delay_minutes": safe_int(item.get("delayMinutes") or item.get("finalDelayMinutes")),
            "customer_tips_huf": money_amount(item.get("customerTipsTotal") or item.get("tipsHuf") or item.get("tipHuf")) or 0,
            "vehicle_plate": clean_text(item.get("vehiclePlate") or item.get("licencePlate")) or None,
            "raw_route": item,
            "source_date_from": date_from.isoformat(),
            "source_date_to": date_to.isoformat(),
            "source_raw_updated_at": now,
            "updated_at": now,
        })
    return rows


def shift_items(payload: Any) -> list[dict[str, Any]]:
    return payload_items(payload, "shifts")


def make_shift_key(courier_id: int, item: dict[str, Any], index: int) -> str:
    return ":".join([
        str(courier_id),
        clean_text(item.get("date")),
        clean_text(item.get("plannedStart")),
        clean_text(item.get("plannedEnd")),
        str(index),
    ])


def make_shift_rows(ref: dict[str, Any], date_from: date, date_to: date, request_url: str, status_code: int, payload: Any) -> list[dict[str, Any]]:
    if status_code != 200:
        return []
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    courier_id = int(ref["courier_id"])
    warehouse_id = int(ref["warehouse_id"])
    for index, item in enumerate(shift_items(payload), start=1):
        work_date = parse_date(item.get("date"))
        if not work_date or work_date < date_from or work_date > date_to:
            continue
        planned_start = route_time(item.get("plannedStart"))
        planned_end = route_time(item.get("plannedEnd"))
        rows.append({
            "courier_id": courier_id,
            "year": work_date.year,
            "month": work_date.month,
            "dsp_id": COURIER_HUB_DSP_ID,
            "warehouse_id": warehouse_id,
            "work_date": work_date.isoformat(),
            "shift_key": make_shift_key(courier_id, item, index),
            "shift_id": None,
            "shift_name": planned_start,
            "shift_start": planned_start,
            "shift_end": planned_end,
            "planned_start_at": timestamp_or_none(f"{work_date.isoformat()}T{planned_start}:00" if planned_start else ""),
            "planned_end_at": timestamp_or_none(f"{work_date.isoformat()}T{planned_end}:00" if planned_end else ""),
            "actual_start_at": timestamp_or_none(item.get("actualStart")),
            "evaluation": clean_text(item.get("evaluation")) or None,
            "status": clean_text(item.get("evaluation")) or None,
            "raw_shift": item,
            "request_url": request_url,
            "response_status_code": status_code,
            "source_raw_updated_at": now,
            "updated_at": now,
        })
    return rows


def upsert(table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str) -> int:
    payload = rows if isinstance(rows, list) else [rows]
    if not payload:
        return 0
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    total = 0
    for start in range(0, len(payload), 500):
        batch = payload[start:start + 500]
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true", help="A mar sikeresen mentett range-eket is ujrahuzza.")
    parser.add_argument("--courier-id", type=int)
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--chunk-days", type=int, default=7)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--only", choices=["routes", "shifts", "both"], default="both")
    args = parser.parse_args()

    start_date = parse_date(args.date_from)
    end_date = parse_date(args.date_to)
    if not start_date or not end_date:
        if not args.year or not args.month:
            raise RuntimeError("--year es --month vagy --date-from es --date-to kotelezo.")
        start_date, end_date = month_bounds(args.year, args.month)
    if start_date > end_date:
        raise RuntimeError("A --date-from nem lehet kesobbi, mint a --date-to.")
    if not courier_hub_auth_configured():
        raise RuntimeError("Courier Hub auth nincs beallitva.")

    refs = read_courier_refs(start_date.year, start_date.month, args.courier_id, args.warehouse_id)
    ranges = date_ranges(start_date, end_date, args.chunk_days)
    endpoint_types = ["routes", "shifts"] if args.only == "both" else [args.only]
    total_targets = len(refs) * len(ranges) * len(endpoint_types)
    print(
        f"Performance range target: couriers={len(refs)} ranges={len(ranges)} endpoints={','.join(endpoint_types)} "
        f"period={start_date.isoformat()}..{end_date.isoformat()} mode={'APPLY' if args.apply else 'DRY-RUN'}",
        flush=True,
    )

    fetched = 0
    skipped = 0
    failed = 0
    raw_written = 0
    route_rows_written = 0
    shift_rows_written = 0
    processed = 0
    for range_from, range_to in ranges:
        for ref in refs:
            for endpoint_type in endpoint_types:
                processed += 1
                courier_id = int(ref["courier_id"])
                warehouse_id = int(ref["warehouse_id"])
                try:
                    if not args.force and endpoint_already_synced(endpoint_type, courier_id, warehouse_id, range_from, range_to):
                        skipped += 1
                        continue
                    request_url, status_code, payload = fetch_endpoint(endpoint_type, courier_id, warehouse_id, range_from, range_to)
                    raw_row = make_endpoint_raw_row(
                        endpoint_type=endpoint_type,
                        ref=ref,
                        date_from=range_from,
                        date_to=range_to,
                        request_url=request_url,
                        status_code=status_code,
                        payload=payload,
                    )
                    route_rows = (
                        make_route_rows(ref, range_from, range_to, request_url, status_code, payload)
                        if endpoint_type == "routes"
                        else []
                    )
                    shift_rows = (
                        make_shift_rows(ref, range_from, range_to, request_url, status_code, payload)
                        if endpoint_type == "shifts"
                        else []
                    )
                    if args.apply:
                        raw_written += upsert(
                            "courier_hub_performance_endpoint_raw",
                            raw_row,
                            "endpoint_type,courier_id,warehouse_id,dsp_id,date_from,date_to",
                        )
                        route_rows_written += upsert(
                            "courier_hub_performance_routes",
                            route_rows,
                            "courier_id,warehouse_id,dsp_id,work_date,route_id",
                        )
                        shift_rows_written += upsert(
                            "courier_shift_overview",
                            shift_rows,
                            "courier_id,work_date,shift_key,dsp_id,warehouse_id",
                        )
                    fetched += 1 if status_code == 200 else 0
                    if status_code != 200:
                        failed += 1
                        print(f"HTTP {status_code}: {endpoint_type} courier={courier_id} WH={warehouse_id} {range_from}..{range_to}")
                except Exception as exc:
                    failed += 1
                    print(f"ERROR {endpoint_type}: courier={courier_id} WH={warehouse_id} {range_from}..{range_to}: {exc}", flush=True)
                if processed == total_targets or processed % 50 == 0:
                    print(
                        f"PROGRESS {processed}/{total_targets} fetched={fetched} skipped={skipped} "
                        f"raw={raw_written} routes={route_rows_written} shifts={shift_rows_written}",
                        flush=True,
                    )
                if args.sleep > 0:
                    time.sleep(args.sleep)

    print(
        f"Done. fetched={fetched} skipped_existing={skipped} failed={failed} "
        f"raw_written={raw_written} route_rows={route_rows_written} shift_rows={shift_rows_written}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
