#!/usr/bin/env python3
"""Courier Hub live monitoring list + courier detail sync."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
    supabase_headers,
)


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service"
WAREHOUSE_CODES = {1: "BUD1", 2: "BUD2"}


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_id(value: Any) -> str:
    return "".join(character for character in clean_text(value) if character.isdigit())


def live_route_id(row: dict[str, Any]) -> str:
    return normalize_id(
        row.get("cargoRouteId")
        or row.get("routeExternalId")
        or row.get("routeId")
        or row.get("route_id")
        or row.get("id")
    )


def int_or_none(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def float_or_none(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def text_or_none(value: Any) -> str | None:
    text = clean_text(value)
    return text or None


def build_snapshot_key(fetched_at: datetime, warehouse_id: int, dsp_id: int) -> str:
    bucket_minute = 0 if fetched_at.minute < 30 else 30
    return f"{fetched_at:%Y%m%d%H}{bucket_minute:02d}-wh{warehouse_id}-dsp{dsp_id}"


def build_list_url(base_url: str, warehouse_id: int, dsp_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/live-monitoring-dashboard?dspId={int(dsp_id)}"
    )


def build_courier_url(base_url: str, warehouse_id: int, courier_id: int, dsp_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/live-monitoring-dashboard/couriers/{int(courier_id)}"
        f"?dspId={int(dsp_id)}"
    )


def request_courier_hub_json(url: str) -> tuple[int, Any]:
    response = requests.get(url, headers=courier_hub_headers(), timeout=60)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.get(url, headers=courier_hub_headers(), timeout=60)

    status_code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {"text": response.text[:2000]}
    return status_code, payload


def find_live_monitoring_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def top_level_couriers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("couriers"), list):
        return [item for item in payload["couriers"] if isinstance(item, dict)]
    return find_live_monitoring_rows(payload)


def route_like_couriers(payload: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in top_level_couriers(payload)
        if normalize_id(row.get("courierId")) and live_route_id(row)
    ]


def compact_stop_progress(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    stops: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stops.append({
            "sequence": int_or_none(item.get("sequence") or item.get("position") or item.get("stopPosition")),
            "state": clean_text(item.get("state") or item.get("status")) or None,
            "delayMinutes": int_or_none(item.get("delayMinutes") or item.get("deltaMinutes")),
        })
    return stops


def compact_courier_json(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "courierId": int_or_none(row.get("courierId")),
        "name": text_or_none(row.get("name") or row.get("courierName")),
        "dspName": text_or_none(row.get("dspName")),
        "warehouseCode": text_or_none(row.get("warehouseCode")),
        "status": text_or_none(row.get("status")),
        "delayMinutes": int_or_none(row.get("delayMinutes")),
        "deliveriesCompleted": int_or_none(row.get("deliveriesCompleted")),
        "stopsTotal": int_or_none(row.get("stopsTotal")),
        "departureStatus": text_or_none(row.get("departureStatus")),
        "stopProgress": compact_stop_progress(row.get("stopProgress")),
        "temperatureCelsius": float_or_none(row.get("temperatureCelsius")),
        "temperatureStatus": text_or_none(row.get("temperatureStatus")),
        "shiftStatus": text_or_none(row.get("shiftStatus")),
        "shiftDeltaMinutes": int_or_none(row.get("shiftDeltaMinutes")),
        "noShowAutoFlaggedAt": row.get("noShowAutoFlaggedAt"),
        "finishedRouteCount": int_or_none(row.get("finishedRouteCount")),
        "plannedStartAt": text_or_none(row.get("plannedStartAt")),
        "actualStartAt": text_or_none(row.get("actualStartAt")),
        "plannedDepartureAt": text_or_none(row.get("plannedDepartureAt")),
        "departedAt": text_or_none(row.get("departedAt")),
        "vehiclePlate": text_or_none(row.get("vehiclePlate")),
        "fridgeConfig": row.get("fridgeConfig"),
        "cargoRouteId": int_or_none(row.get("cargoRouteId")),
        "routeExternalId": int_or_none(row.get("routeExternalId")),
        "plannedKm": float_or_none(row.get("plannedKm")),
    }


def detail_target_couriers(payload: Any, detail_scope: str) -> list[dict[str, Any]]:
    candidates = (
        top_level_couriers(payload)
        if detail_scope == "all"
        else route_like_couriers(payload)
    )
    targets: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in candidates:
        courier_id_text = normalize_id(row.get("courierId"))
        if not courier_id_text:
            continue
        courier_id = int(courier_id_text)
        if courier_id in seen:
            continue
        seen.add(courier_id)
        targets.append(row)
    return targets


def supabase_post(table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
    if not rows:
        return 0

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=60,
    )
    raise_for_response(response, f"{table} upsert")
    return len(rows)


def supabase_post_optional(table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
    try:
        return supabase_post(table, rows, on_conflict)
    except Exception as exc:
        print(f"OPTIONAL_TABLE_WRITE_SKIPPED table={table} error={exc}", flush=True)
        return 0


def build_list_row(
    *,
    snapshot_key: str,
    warehouse_id: int,
    dsp_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
    fetched_at: datetime,
) -> dict[str, Any]:
    couriers = top_level_couriers(response_json)
    routes = route_like_couriers(response_json)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "snapshot_key": snapshot_key,
        "warehouse_id": warehouse_id,
        "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
        "dsp_id": dsp_id,
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "courier_count": len(couriers),
        "route_count": len(routes),
        "fetched_at": fetched_at.isoformat(),
        "updated_at": now,
    }


def build_detail_row(
    *,
    snapshot_key: str,
    warehouse_id: int,
    dsp_id: int,
    courier_row: dict[str, Any],
    request_url: str,
    status_code: int,
    response_json: Any,
    fetched_at: datetime,
) -> dict[str, Any]:
    courier_id = int(normalize_id(courier_row.get("courierId")))
    now = datetime.now(timezone.utc).isoformat()
    return {
        "snapshot_key": snapshot_key,
        "warehouse_id": warehouse_id,
        "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
        "dsp_id": dsp_id,
        "courier_id": courier_id,
        "courier_name": clean_text(courier_row.get("name") or courier_row.get("courierName")),
        "route_id": live_route_id(courier_row),
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "fetched_at": fetched_at.isoformat(),
        "updated_at": now,
    }


def build_compact_courier_snapshot_row(
    *,
    snapshot_key: str,
    warehouse_id: int,
    dsp_id: int,
    courier_row: dict[str, Any],
    request_url: str,
    status_code: int,
    fetched_at: datetime,
) -> dict[str, Any]:
    courier_json = compact_courier_json(courier_row)
    courier_id = courier_json.get("courierId")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "snapshot_key": snapshot_key,
        "warehouse_id": warehouse_id,
        "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
        "dsp_id": dsp_id,
        "courier_id": courier_id,
        "courier_name": courier_json.get("name"),
        "route_id": clean_text(courier_json.get("cargoRouteId") or live_route_id(courier_row)),
        "route_external_id": courier_json.get("routeExternalId"),
        "status": courier_json.get("status"),
        "departure_status": courier_json.get("departureStatus"),
        "shift_status": courier_json.get("shiftStatus"),
        "delay_minutes": courier_json.get("delayMinutes"),
        "deliveries_completed": courier_json.get("deliveriesCompleted"),
        "stops_total": courier_json.get("stopsTotal"),
        "current_stop_sequence": next(
            (
                stop.get("sequence")
                for stop in courier_json.get("stopProgress", [])
                if clean_text(stop.get("state")).upper() == "CURRENT"
            ),
            None,
        ),
        "vehicle_plate": courier_json.get("vehiclePlate"),
        "planned_start_at": courier_json.get("plannedStartAt"),
        "actual_start_at": courier_json.get("actualStartAt"),
        "planned_departure_at": courier_json.get("plannedDepartureAt"),
        "departed_at": courier_json.get("departedAt"),
        "planned_km": courier_json.get("plannedKm"),
        "request_url": request_url,
        "status_code": status_code,
        "courier_json": courier_json,
        "fetched_at": fetched_at.isoformat(),
        "updated_at": now,
    }


def parse_warehouse_ids(value: str) -> list[int]:
    ids: list[int] = []
    for part in value.split(","):
        text = part.strip()
        if not text:
            continue
        ids.append(int(text))
    return ids or [1, 2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-ids", default="1,2")
    parser.add_argument("--dsp-id", type=int, default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"))
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--detail-scope", choices=["routes", "all"], default="routes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fetched_at = datetime.now(timezone.utc)
    list_rows: list[dict[str, Any]] = []
    compact_courier_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    failures = 0

    for warehouse_id in parse_warehouse_ids(args.warehouse_ids):
        snapshot_key = build_snapshot_key(fetched_at, warehouse_id, args.dsp_id)
        list_url = build_list_url(args.base_url, warehouse_id, args.dsp_id)
        status_code, payload = request_courier_hub_json(list_url)
        if status_code >= 400:
            failures += 1

        list_row = build_list_row(
            snapshot_key=snapshot_key,
            warehouse_id=warehouse_id,
            dsp_id=args.dsp_id,
            request_url=list_url,
            status_code=status_code,
            response_json=payload,
            fetched_at=fetched_at,
        )
        list_rows.append(list_row)

        compact_courier_rows.extend(
            build_compact_courier_snapshot_row(
                snapshot_key=snapshot_key,
                warehouse_id=warehouse_id,
                dsp_id=args.dsp_id,
                courier_row=courier,
                request_url=list_url,
                status_code=status_code,
                fetched_at=fetched_at,
            )
            for courier in top_level_couriers(payload)
            if normalize_id(courier.get("courierId"))
        )

        couriers = detail_target_couriers(payload, args.detail_scope) if status_code < 400 else []
        print(
            f"HUB_LIVE_LIST warehouse={warehouse_id} status={status_code} "
            f"couriers={list_row['courier_count']} routes={list_row['route_count']} "
            f"detail_targets={len(couriers)} scope={args.detail_scope}",
            flush=True,
        )

        for courier in couriers:
            courier_id = int(normalize_id(courier.get("courierId")))
            detail_url = build_courier_url(args.base_url, warehouse_id, courier_id, args.dsp_id)
            detail_status, detail_payload = request_courier_hub_json(detail_url)
            if detail_status >= 400:
                failures += 1
            detail_rows.append(
                build_detail_row(
                    snapshot_key=snapshot_key,
                    warehouse_id=warehouse_id,
                    dsp_id=args.dsp_id,
                    courier_row=courier,
                    request_url=detail_url,
                    status_code=detail_status,
                    response_json=detail_payload,
                    fetched_at=fetched_at,
                )
            )
            print(
                f"HUB_LIVE_DETAIL warehouse={warehouse_id} courier={courier_id} "
                f"route={live_route_id(courier) or '-'} status={detail_status}",
                flush=True,
            )

    if args.dry_run:
        print(
            f"DRY_RUN list_rows={len(list_rows)} compact_courier_rows={len(compact_courier_rows)} "
            f"detail_rows={len(detail_rows)} failures={failures}",
            flush=True,
        )
        return 1 if failures else 0

    written_lists = supabase_post(
        "courier_hub_live_monitoring_raw",
        list_rows,
        "snapshot_key",
    )
    written_compact_couriers = supabase_post_optional(
        "courier_hub_live_monitoring_courier_snapshots",
        compact_courier_rows,
        "snapshot_key,warehouse_id,dsp_id,courier_id",
    )
    written_latest_compact_couriers = supabase_post_optional(
        "courier_hub_live_monitoring_courier_snapshot_latest",
        compact_courier_rows,
        "courier_id,warehouse_id,dsp_id",
    )
    written_raw_details = supabase_post(
        "courier_hub_live_monitoring_courier_raw",
        detail_rows,
        "snapshot_key,courier_id",
    )
    written_latest_details = supabase_post(
        "courier_hub_live_monitoring_courier_latest",
        detail_rows,
        "courier_id,warehouse_id,dsp_id",
    )

    print(
        "SUMMARY "
        f"live_snapshots={written_lists} "
        f"courier_snapshots={written_compact_couriers} "
        f"courier_snapshots_latest={written_latest_compact_couriers} "
        f"courier_details_raw={written_raw_details} "
        f"courier_details_latest={written_latest_details} "
        f"failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
