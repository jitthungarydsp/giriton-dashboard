#!/usr/bin/env python3
"""Refresh PWA schedule calendar capacity from Courier Hub shift blocks."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


SOURCE_TABLE = "courier_hub_shift_blocks_raw"
TARGET_TABLE = "pwa_schedule_capacity_calendar_daily"
WAREHOUSE_CODE_BY_ID = {
    1: "BUD1",
    2: "BUD2",
}


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"1", "true", "yes", "y", "igen"}


def parse_warehouse_ids(value: str) -> list[int]:
    ids: list[int] = []
    for part in str(value or "").split(","):
        try:
            warehouse_id = int(part.strip())
        except ValueError:
            continue
        if warehouse_id and warehouse_id not in ids:
            ids.append(warehouse_id)
    return ids or [1, 2]


def date_window(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("--end-date nem lehet korabbi mint --start-date.")
    days: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def supabase_config() -> tuple[str, str]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return supabase_url.rstrip("/"), service_role_key


def supabase_headers(prefer: str = "") -> dict[str, str]:
    _url, key = supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if prefer:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer
    return headers


def is_missing_table_response(response: requests.Response) -> bool:
    if response.status_code not in (400, 404):
        return False
    text = response.text.lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def supabase_get_paginated(
    table: str,
    params: list[tuple[str, str]],
    *,
    page_size: int = 1000,
    limit: int = 20000,
) -> list[dict[str, Any]]:
    supabase_url, _key = supabase_config()
    rows: list[dict[str, Any]] = []
    while len(rows) < limit:
        start = len(rows)
        end = min(start + page_size - 1, limit - 1)
        headers = supabase_headers()
        headers["Range-Unit"] = "items"
        headers["Range"] = f"{start}-{end}"
        response = requests.get(
            f"{supabase_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            timeout=60,
        )
        raise_for_supabase_error(response)
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        if len(payload) < (end - start + 1):
            break
    return rows


def read_shift_block_rows(
    start_date: date,
    end_date: date,
    warehouse_ids: list[int],
    dsp_id: int,
) -> list[dict[str, Any]]:
    return supabase_get_paginated(
        SOURCE_TABLE,
        [
            (
                "select",
                (
                    "work_date,warehouse_id,warehouse_code,dsp_id,block_key,status,"
                    "assigned,opened,free_slots,capacity_published,fetched_at,updated_at"
                ),
            ),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("warehouse_id", f"in.({','.join(str(item) for item in warehouse_ids)})"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("order", "work_date.asc,warehouse_id.asc,block_key.asc"),
        ],
    )


def aggregate_capacity(
    rows: list[dict[str, Any]],
    *,
    refresh_source: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, int], dict[str, Any]] = defaultdict(lambda: {
        "required_slots": 0,
        "booked_slots": 0,
        "free_slots": 0,
        "source_block_count": 0,
        "source_updated_at": "",
    })
    refreshed_at = datetime.now(timezone.utc).isoformat()

    for row in rows:
        work_date = clean_text(row.get("work_date"))[:10]
        warehouse_id = int_or_none(row.get("warehouse_id")) or 0
        dsp_id = int_or_none(row.get("dsp_id")) or 8
        if not work_date or warehouse_id <= 0:
            continue
        status = clean_text(row.get("status")).upper()
        if status in {"CANCELLED", "CANCELED", "DELETED"}:
            continue
        if not bool_value(row.get("capacity_published")):
            continue

        assigned = int_or_none(row.get("assigned")) or 0
        opened = int_or_none(row.get("opened")) or 0
        free_slots = int_or_none(row.get("free_slots"))
        required = opened if opened > 0 else assigned + max(free_slots or 0, 0)
        if required <= 0 and assigned <= 0:
            continue
        if free_slots is None:
            free_slots = max(required - assigned, 0)

        key = (work_date, warehouse_id, dsp_id)
        target = grouped[key]
        target["work_date"] = work_date
        target["warehouse_id"] = warehouse_id
        target["warehouse_code"] = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, f"WH{warehouse_id}")
        target["dsp_id"] = dsp_id
        target["required_slots"] += required
        target["booked_slots"] += assigned
        target["free_slots"] += max(free_slots, 0)
        target["source_block_count"] += 1
        updated_at = clean_text(row.get("updated_at") or row.get("fetched_at"))
        if updated_at > clean_text(target.get("source_updated_at")):
            target["source_updated_at"] = updated_at

    output: list[dict[str, Any]] = []
    for row in grouped.values():
        required = int(row["required_slots"])
        booked = int(row["booked_slots"])
        row["missing_slots"] = max(required - booked, 0)
        row["extra_slots"] = max(booked - required, 0)
        row["coverage_percent"] = round(booked / required * 100, 2) if required > 0 else None
        row["refresh_source"] = refresh_source
        row["refreshed_at"] = refreshed_at
        row["updated_at"] = refreshed_at
        output.append(row)

    return sorted(output, key=lambda item: (item["work_date"], item["warehouse_id"], item["dsp_id"]))


def delete_existing_rows(start_date: date, end_date: date, warehouse_ids: list[int], dsp_id: int) -> None:
    supabase_url, _key = supabase_config()
    response = requests.delete(
        f"{supabase_url}/rest/v1/{TARGET_TABLE}",
        headers=supabase_headers("return=minimal"),
        params=[
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("warehouse_id", f"in.({','.join(str(item) for item in warehouse_ids)})"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
        ],
        timeout=60,
    )
    if is_missing_table_response(response):
        print(f"PWA_SCHEDULE_CAPACITY_REFRESH_SKIPPED missing_table={TARGET_TABLE}", flush=True)
        return
    raise_for_supabase_error(response)


def upsert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    supabase_url, _key = supabase_config()
    written = 0
    for index in range(0, len(rows), 500):
        chunk = rows[index:index + 500]
        response = requests.post(
            f"{supabase_url}/rest/v1/{TARGET_TABLE}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "work_date,warehouse_id,dsp_id"},
            json=chunk,
            timeout=60,
        )
        if is_missing_table_response(response):
            print(f"PWA_SCHEDULE_CAPACITY_REFRESH_SKIPPED missing_table={TARGET_TABLE}", flush=True)
            return written
        raise_for_supabase_error(response)
        written += len(chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh PWA schedule capacity calendar daily table.")
    parser.add_argument("--start-date", default=date.today().isoformat())
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=0)
    parser.add_argument("--warehouse-ids", default="1,2")
    parser.add_argument("--dsp-id", type=int, default=8)
    parser.add_argument("--refresh-source", default="HUB_JOB_AUTOBOOKING")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)
    elif args.lookahead_days > 0:
        end_date = start_date + timedelta(days=args.lookahead_days)
    else:
        end_date = start_date
    date_window(start_date, end_date)
    warehouse_ids = parse_warehouse_ids(args.warehouse_ids)
    source_rows = read_shift_block_rows(start_date, end_date, warehouse_ids, args.dsp_id)
    rows = aggregate_capacity(source_rows, refresh_source=args.refresh_source)

    if args.dry_run:
        print(
            "PWA_SCHEDULE_CAPACITY_REFRESH_DRY_RUN "
            f"source_rows={len(source_rows)} rows={len(rows)}",
            flush=True,
        )
        for row in rows[:20]:
            print(row, flush=True)
        return 0

    delete_existing_rows(start_date, end_date, warehouse_ids, args.dsp_id)
    written = upsert_rows(rows)
    print(
        "PWA_SCHEDULE_CAPACITY_REFRESH "
        f"source_rows={len(source_rows)} rows={len(rows)} written={written} "
        f"start={start_date.isoformat()} end={end_date.isoformat()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
