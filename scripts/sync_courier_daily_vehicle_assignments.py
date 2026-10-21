#!/usr/bin/env python3
"""Persist one actual courier/vehicle assignment per work day.

The source is the retained Courier Hub Live Monitoring snapshot table.  Every
snapshot observed on a day contributes its vehicle and route; the latest
non-empty vehicle is exposed as the day's actual vehicle, while all observed
values remain available for audit.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error

LOCAL_TZ = ZoneInfo("Europe/Budapest")


def headers(prefer: str = "") -> dict[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    result = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        result["Prefer"] = prefer
    return result


def get_rows(params: dict[str, str], page_size: int = 1000) -> list[dict[str, Any]]:
    url, _key = get_supabase_config()
    rows: list[dict[str, Any]] = []
    for start in range(0, 1_000_000, page_size):
        end = start + page_size - 1
        response = requests.get(
            f"{url.rstrip('/')}/rest/v1/courier_hub_live_monitoring_courier_snapshots",
            headers={**headers(), "Range-Unit": "items", "Range": f"{start}-{end}"},
            params=params,
            timeout=60,
        )
        raise_for_supabase_error(response)
        chunk = response.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
    return rows


def local_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(LOCAL_TZ).date()
    except ValueError:
        return None


def normalize_plate(value: Any) -> str:
    text = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    if len(text) >= 6 and text[-3:].isdigit():
        return f"{text[:-3]}-{text[-3:]}"
    return str(value or "").strip().upper()


def iso_date(value: date) -> str:
    return value.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-back", type=int, default=14, help="Hany napot olvasson vissza a snapshotokbol.")
    parser.add_argument("--since-date", help="YYYY-MM-DD; felulbiralja a --days-back erteket.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = datetime.now(LOCAL_TZ).date()
    start_date = date.fromisoformat(args.since_date) if args.since_date else today - timedelta(days=max(0, args.days_back - 1))
    # fetched_at is UTC; include a small UTC margin around local day boundaries.
    start_utc = datetime.combine(start_date, datetime.min.time(), LOCAL_TZ).astimezone(timezone.utc).isoformat()
    rows = get_rows(
        {
            "select": "snapshot_key,warehouse_id,warehouse_code,dsp_id,courier_id,courier_name,route_id,vehicle_plate,courier_json,fetched_at",
            "fetched_at": f"gte.{start_utc}",
            "order": "fetched_at.asc",
        }
    )
    grouped: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    for row in rows:
        work_date = local_date(row.get("fetched_at"))
        if not work_date or work_date < start_date:
            continue
        courier_id = row.get("courier_id")
        if courier_id is None:
            continue
        key = (work_date.isoformat(), int(row.get("warehouse_id") or 0), int(row.get("dsp_id") or 0), int(courier_id))
        item = grouped.setdefault(
            key,
            {
                "work_date": work_date.isoformat(),
                "warehouse_id": int(row.get("warehouse_id") or 0),
                "warehouse_code": row.get("warehouse_code") or "",
                "dsp_id": int(row.get("dsp_id") or 0),
                "courier_id": int(courier_id),
                "courier_name": row.get("courier_name"),
                "vehicle_plate": None,
                "observed_vehicle_plates": [],
                "route_ids": [],
                "route_count": 0,
                "source": "courier-hub-live-monitoring",
                "source_snapshot_at": row.get("fetched_at"),
                "response_json": row.get("courier_json") or {},
                "last_seen_at": row.get("fetched_at"),
            },
        )
        plate = normalize_plate(row.get("vehicle_plate"))
        if plate and plate not in item["observed_vehicle_plates"]:
            item["observed_vehicle_plates"].append(plate)
            item["vehicle_plate"] = plate
        route_id = str(row.get("route_id") or "").strip()
        if route_id and route_id not in item["route_ids"]:
            item["route_ids"].append(route_id)
        item["route_count"] = len(item["route_ids"])
        item["courier_name"] = row.get("courier_name") or item["courier_name"]
        item["source_snapshot_at"] = row.get("fetched_at") or item["source_snapshot_at"]
        item["last_seen_at"] = row.get("fetched_at") or item["last_seen_at"]
        item["response_json"] = row.get("courier_json") or item["response_json"]
    payload = list(grouped.values())
    print(f"COURIER_DAILY_VEHICLE_ASSIGNMENTS snapshots={len(rows)} assignments={len(payload)} start={start_date} dry_run={args.dry_run}")
    if args.dry_run or not payload:
        return 0
    url, _key = get_supabase_config()
    for start in range(0, len(payload), 500):
        response = requests.post(
            f"{url.rstrip('/')}/rest/v1/courier_daily_vehicle_assignments",
            headers=headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "work_date,warehouse_id,dsp_id,courier_id"},
            json=payload[start : start + 500],
            timeout=60,
        )
        raise_for_supabase_error(response)
    print(f"COURIER_DAILY_VEHICLE_ASSIGNMENTS_DONE upserted={len(payload)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, requests.RequestException) as exc:
        print(f"COURIER_DAILY_VEHICLE_ASSIGNMENTS_ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
