#!/usr/bin/env python3
"""Export MuszakPro vs Courier Hub shift start mismatches to Google Sheets."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.google_sheets_values import replace_sheet_values_by_id  # noqa: E402
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 855530605
VIEW_NAME = "vw_muszakpro_hub_shift_time_mismatch"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "Frissítve",
    "Dátum",
    "Raktár",
    "courierId",
    "Futár",
    "MűszakPro kezdés",
    "HUB foglalás kezdés",
    "HUB slot kezdés",
    "HUB slot vége",
    "Eltérés perc",
    "Státusz",
    "Indok",
    "MűszakPro műszak",
    "HUB műszak",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def supabase_headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def paged_get(
    *,
    endpoint: str,
    headers: dict[str, str],
    base_params: list[tuple[str, str]],
    limit: int,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    max_rows = max(int(limit), 1)
    current_page_size = max(min(int(page_size), 1000), 1)

    while len(records) < max_rows:
        current_limit = min(current_page_size, max_rows - len(records))
        response = requests.get(
            endpoint,
            headers=headers,
            params=[
                *base_params,
                ("limit", str(current_limit)),
                ("offset", str(offset)),
            ],
            timeout=60,
        )
        raise_for_supabase_error(response)
        payload = response.json()
        page = payload if isinstance(payload, list) else []
        records.extend(page)
        if len(page) < current_limit:
            break
        offset += len(page)

    return records


def read_mismatch_rows(start_date: date, end_exclusive: date, limit: int) -> list[dict[str, Any]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")

    return paged_get(
        endpoint=f"{supabase_url.rstrip('/')}/rest/v1/{VIEW_NAME}",
        headers=supabase_headers(service_role_key),
        base_params=[
            (
                "select",
                (
                    "work_date,warehouse_code,courier_id,courier_name,"
                    "muszakpro_shift_start_time,hub_booking_shift_start_time,"
                    "hub_slot_from,hub_slot_to,signed_diff_minutes,"
                    "comparison_status,comparison_reason,muszakpro_shift_text,hub_shift_text"
                ),
            ),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lt.{end_exclusive.isoformat()}"),
            ("order", "work_date.asc,warehouse_code.asc,courier_name.asc,muszakpro_shift_start_time.asc"),
        ],
        limit=limit,
    )


def row_to_sheet_row(row: dict[str, Any], exported_at: str) -> list[Any]:
    return [
        exported_at,
        clean_text(row.get("work_date")),
        clean_text(row.get("warehouse_code")),
        row.get("courier_id") or "",
        clean_text(row.get("courier_name")),
        clean_text(row.get("muszakpro_shift_start_time")),
        clean_text(row.get("hub_booking_shift_start_time")),
        clean_text(row.get("hub_slot_from")),
        clean_text(row.get("hub_slot_to")),
        row.get("signed_diff_minutes") if row.get("signed_diff_minutes") is not None else "",
        clean_text(row.get("comparison_status")),
        clean_text(row.get("comparison_reason")),
        clean_text(row.get("muszakpro_shift_text")),
        clean_text(row.get("hub_shift_text")),
    ]


def export_sheet(start_date: date, end_exclusive: date, limit: int, dry_run: bool = False) -> dict[str, Any]:
    rows = read_mismatch_rows(start_date, end_exclusive, limit)
    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    values: list[list[Any]] = [HEADER]
    if rows:
        values.extend(row_to_sheet_row(row, exported_at) for row in rows)
    else:
        values.append([
            exported_at,
            f"Nincs eltérés {start_date.isoformat()} - {(end_exclusive - timedelta(days=1)).isoformat()} között.",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "OK",
            "",
            "",
            "",
        ])

    if not dry_run:
        replace_sheet_values_by_id(SPREADSHEET_ID, WORKSHEET_GID, values)

    return {
        "records": len(rows),
        "written_rows": 0 if dry_run else len(values),
        "worksheet_id": WORKSHEET_GID,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(LOCAL_TIMEZONE).date().isoformat())
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=31)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date or args.date)
    if args.end_date:
        end_exclusive = date.fromisoformat(args.end_date) + timedelta(days=1)
    elif args.lookahead_days > 0:
        end_exclusive = start_date + timedelta(days=args.lookahead_days + 1)
    else:
        end_exclusive = start_date + timedelta(days=1)

    result = export_sheet(
        start_date=start_date,
        end_exclusive=end_exclusive,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(
        "MUSZAKPRO_HUB_SHIFT_TIME_MISMATCH_SHEET "
        f"start_date={start_date.isoformat()} end_exclusive={end_exclusive.isoformat()} "
        f"rows={result['records']} written_rows={result['written_rows']} "
        f"worksheet_id={result['worksheet_id']} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
