#!/usr/bin/env python3
"""Persist the live MuszakPro/Hub identity reconciliation view."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import get_supabase_config  # noqa: E402


VIEW_NAME = "vw_muszakpro_booking_identity_matches"
TARGET_TABLE = "muszakpro_booking_identity_matches"


def supabase_headers(prefer: str = "") -> dict[str, str]:
    _url, key = get_supabase_config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if prefer:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer
    return headers


def read_view_rows(start_date: date, end_date: date) -> list[dict[str, Any]]:
    supabase_url, _key = get_supabase_config()
    select = (
        "work_date,muszakpro_email,normalized_email,muszakpro_entry_count,"
        "hub_shift_count,muszakpro_booking_rows,robot_id,robot_courier_id,"
        "robot_courier_name,robot_email,hub_courier_id,hub_courier_name,"
        "hub_email,hub_robot_id,hub_warehouse,robot_match_method,"
        "hub_match_method,match_status"
    )
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "select": select,
            "work_date": f"gte.{start_date.isoformat()}",
            "and": f"(work_date.lte.{end_date.isoformat()})",
            "order": "work_date.asc,normalized_email.asc",
            "limit": "1000",
            "offset": str(offset),
        }
        response = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/{VIEW_NAME}",
            headers=supabase_headers(),
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += len(batch)
    return rows


def persist_rows(rows: list[dict[str, Any]], dry_run: bool = False) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = []
    for row in rows:
        payload.append({
            "work_date": row.get("work_date"),
            "muszakpro_email": row.get("muszakpro_email"),
            "normalized_email": row.get("normalized_email"),
            "muszakpro_entry_count": row.get("muszakpro_entry_count") or 0,
            # Keep the live Hub count from the reconciliation view.  The PWA
            # uses this persisted value for the daily MűszakPro-vs-Hub
            # comparison and the red mismatch indicator.
            "hub_shift_count": row.get("hub_shift_count"),
            "muszakpro_booking_rows": row.get("muszakpro_booking_rows") or [],
            "robot_id": row.get("robot_id"),
            "robot_courier_id": row.get("robot_courier_id"),
            "robot_courier_name": row.get("robot_courier_name"),
            "robot_email": row.get("robot_email"),
            "hub_courier_id": row.get("hub_courier_id"),
            "hub_courier_name": row.get("hub_courier_name"),
            "hub_email": row.get("hub_email"),
            "hub_robot_id": row.get("hub_robot_id"),
            "hub_warehouse": row.get("hub_warehouse"),
            "robot_match_method": row.get("robot_match_method") or "unmatched",
            "hub_match_method": row.get("hub_match_method") or "unmatched",
            "match_status": row.get("match_status") or "unmatched",
            "match_details": {"source": VIEW_NAME},
            "fetched_at": now,
            "updated_at": now,
        })
    if dry_run:
        return len(payload)

    supabase_url, _key = get_supabase_config()
    written = 0
    for start in range(0, len(payload), 500):
        batch = payload[start:start + 500]
        response = requests.post(
            f"{supabase_url.rstrip('/')}/rest/v1/{TARGET_TABLE}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "work_date,normalized_email"},
            json=batch,
            timeout=60,
        )
        if response.status_code in (400, 404) and "does not exist" in response.text.lower():
            raise RuntimeError(
                f"A {TARGET_TABLE} tábla nem található. Futtasd le a DB migrációt előbb."
            )
        response.raise_for_status()
        written += len(batch)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=date.today().isoformat())
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date) if args.end_date else start_date + timedelta(days=args.lookahead_days)
    if end_date < start_date:
        raise SystemExit("Az end-date nem lehet korábbi a start-date-nél.")
    rows = read_view_rows(start_date, end_date)
    written = persist_rows(rows, args.dry_run)
    print(
        f"MUSZAKPRO_BOOKING_IDENTITY_REFRESH start={start_date} end={end_date} "
        f"rows={len(rows)} written={written} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
