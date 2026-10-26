"""Detect recent Supabase changes and expose a GitHub Actions output."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests


DEFAULT_TABLES = (
    "courier_hub_shift_blocks_raw",
    "courier_hub_shift_bookings_raw",
    "muszakpro_booking_identity_matches",
    "external_shift_deletion_requests",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-minutes", type=int, default=10)
    args = parser.parse_args()

    base_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base_url or not service_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")

    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    threshold = datetime.now(timezone.utc) - timedelta(minutes=args.window_minutes)
    latest: list[tuple[str, datetime]] = []
    for table in DEFAULT_TABLES:
        url = f"{base_url}/rest/v1/{quote(table, safe='')}"
        response = requests.get(
            url,
            headers=headers,
            params={"select": "updated_at", "updated_at": "not.is.null", "order": "updated_at.desc", "limit": "1"},
            timeout=30,
        )
        if response.status_code in {400, 404}:
            print(f"DB_CHANGE_WATCH_SKIP table={table} status={response.status_code}", flush=True)
            continue
        response.raise_for_status()
        rows = response.json()
        if not rows or not rows[0].get("updated_at"):
            continue
        value = str(rows[0]["updated_at"]).replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(value).astimezone(timezone.utc)
        latest.append((table, timestamp))
        print(f"DB_CHANGE_WATCH_LATEST table={table} updated_at={timestamp.isoformat()}", flush=True)

    changed = [(table, timestamp) for table, timestamp in latest if timestamp >= threshold]
    changed_tables = ",".join(table for table, _timestamp in changed)
    latest_text = max((timestamp for _table, timestamp in latest), default=None)
    detected = bool(changed)
    print(
        f"DB_CHANGE_WATCH_RESULT changed={str(detected).lower()} tables={changed_tables or '-'} "
        f"latest={latest_text.isoformat() if latest_text else '-'}",
        flush=True,
    )

    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"changed={'true' if detected else 'false'}\n")
            handle.write(f"tables={changed_tables}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
