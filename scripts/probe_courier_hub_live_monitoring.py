#!/usr/bin/env python3
"""Probe Courier Hub live monitoring dashboard without logging secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import courier_hub_headers


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service"


def build_url(warehouse_id: int, dsp_id: int) -> str:
    return (
        f"{DEFAULT_BASE_URL}/external/warehouses/{int(warehouse_id)}"
        f"/live-monitoring-dashboard?dspId={int(dsp_id)}"
    )


def list_paths(value: Any, path: str = "$") -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    if isinstance(value, list):
        found.append((path, len(value)))
        for index, item in enumerate(value[:3]):
            found.extend(list_paths(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, child in value.items():
            found.extend(list_paths(child, f"{path}.{key}"))
    return found


def route_like_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        if any(key in keys for key in ("routeid", "route_id", "routeexternalid", "cargorouteid", "courierid", "courier_id")):
            rows.append(value)
        for child in value.values():
            rows.extend(route_like_rows(child))
    elif isinstance(value, list):
        for item in value:
            rows.extend(route_like_rows(item))
    return rows


def pick(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): key for key in row}
    for key in keys:
        real_key = lowered.get(key.lower())
        if real_key is not None:
            return row.get(real_key)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-id", type=int, default=2)
    parser.add_argument("--dsp-id", type=int, default=8)
    args = parser.parse_args()

    url = build_url(args.warehouse_id, args.dsp_id)
    response = requests.get(url, headers=courier_hub_headers(), timeout=60)
    print(f"LIVE_MONITORING_URL={url}")
    print(f"LIVE_MONITORING_STATUS={response.status_code}")
    print(f"LIVE_MONITORING_CONTENT_TYPE={response.headers.get('content-type') or '-'}")

    if response.status_code != 200:
        print(f"LIVE_MONITORING_BODY={response.text[:500]}")
        return 1

    try:
        payload = response.json()
    except ValueError:
        print("LIVE_MONITORING_JSON=invalid")
        print(f"LIVE_MONITORING_BODY={response.text[:500]}")
        return 1

    if isinstance(payload, dict):
        print("LIVE_MONITORING_TOP_LEVEL=dict")
        print("LIVE_MONITORING_KEYS=" + ",".join(sorted(str(key) for key in payload.keys())[:80]))
    elif isinstance(payload, list):
        print("LIVE_MONITORING_TOP_LEVEL=list")
        print(f"LIVE_MONITORING_LIST_SIZE={len(payload)}")
    else:
        print(f"LIVE_MONITORING_TOP_LEVEL={type(payload).__name__}")

    paths = list_paths(payload)
    for path, size in paths[:40]:
        print(f"LIVE_MONITORING_LIST path={path} size={size}")

    route_rows = route_like_rows(payload)
    print(f"LIVE_MONITORING_ROUTE_LIKE_ROWS={len(route_rows)}")
    for row in route_rows[:5]:
        print(
            "LIVE_MONITORING_ROUTE_SAMPLE "
            f"courier={pick(row, 'courierId', 'courier_id', 'driverId', 'driver_id') or '-'} "
            f"route={pick(row, 'routeExternalId', 'cargoRouteId', 'routeId', 'route_id', 'id') or '-'} "
            f"warehouse={pick(row, 'warehouseCode', 'warehouseId', 'warehouse_id', 'warehouse') or '-'} "
            f"plate={pick(row, 'licensePlate', 'licencePlate', 'licence_plate', 'vehiclePlate', 'vehicle_plate') or '-'} "
            f"keys={','.join(sorted(str(key) for key in row.keys())[:30])}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
