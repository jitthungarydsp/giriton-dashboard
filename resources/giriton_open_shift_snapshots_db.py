from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import requests

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


TABLE_NAME = "ops_giriton_open_shift_snapshots"
SOURCE_NAME = "giriton-raw-export"


def clean(value) -> str:
    return str(value or "").strip()


def optional_int(value) -> int | None:
    text = clean(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _row_value(row, index: int) -> str:
    if index >= len(row):
        return ""
    return clean(row[index])


def _build_snapshot_rows(rows) -> list[dict]:
    snapshot_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    groups = defaultdict(
        lambda: {
            "open_shift_count": 0,
            "total_capacity": 0,
            "booked_capacity": 0,
            "raw_row_count": 0,
            "open_shift_detail": [],
        }
    )

    for row in rows or []:
        values = list(row)
        work_date = _row_value(values, 0)
        start_time = _row_value(values, 1)
        end_time = _row_value(values, 2)
        warehouse = _row_value(values, 3).upper()
        booked = optional_int(_row_value(values, 5))
        maximum = optional_int(_row_value(values, 6))

        if not work_date or warehouse not in {"BUD1", "BUD2"}:
            continue
        if booked is None or maximum is None:
            continue

        open_count = max(maximum - booked, 0)
        for key in [(work_date, warehouse), (work_date, "ALL")]:
            item = groups[key]
            item["open_shift_count"] += open_count
            item["total_capacity"] += maximum
            item["booked_capacity"] += booked
            item["raw_row_count"] += 1
            if open_count > 0:
                item["open_shift_detail"].append(
                    {
                        "warehouse": warehouse,
                        "start_time": start_time,
                        "end_time": end_time,
                        "open": open_count,
                        "booked": booked,
                        "maximum": maximum,
                    }
                )

    return [
        {
            "source_name": SOURCE_NAME,
            "snapshot_at": snapshot_at,
            "work_date": work_date,
            "warehouse": warehouse,
            **values,
        }
        for (work_date, warehouse), values in sorted(groups.items())
    ]


def insert_giriton_open_shift_snapshot(rows) -> dict:
    db_rows = _build_snapshot_rows(rows)
    if not db_rows:
        return {
            "status": "empty",
            "rows": 0,
        }

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        return {
            "status": "skipped_missing_supabase",
            "rows": 0,
        }

    endpoint = f"{supabase_url}/rest/v1/{TABLE_NAME}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=db_rows,
        timeout=60,
    )

    if response.status_code in (400, 404) and TABLE_NAME in response.text:
        return {
            "status": "skipped_missing_table",
            "rows": 0,
            "message": response.text[:300],
        }

    raise_for_supabase_error(response)
    return {
        "status": "ok",
        "rows": len(db_rows),
    }
