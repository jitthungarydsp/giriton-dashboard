#!/usr/bin/env python3
"""Export Courier Hub shift block capacity view to Google Sheets."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google_client import open_spreadsheet  # noqa: E402
from resources.supabase_raw import (  # noqa: E402
    get_supabase_config,
    raise_for_supabase_error,
)


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
VIEW_NAME = "vw_courier_hub_shift_block_capacity"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

WAREHOUSE_WORKSHEETS = {
    "BUD1": 30983345,
    "BUD2": 723813954,
}

HEADER = [
    "Frissítve",
    "Dátum",
    "Raktár",
    "Warehouse ID",
    "DSP ID",
    "BlockKey",
    "Shift template ID",
    "Template név",
    "Slot kezdete",
    "Slot vége",
    "Túra kezdete",
    "Túra vége",
    "Státusz",
    "Megnyitott slot",
    "Foglalt slot",
    "Szabad slot",
    "Kapacitás publikált",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_capacity_rows(work_date: date, warehouse_code: str, limit: int = 5000) -> list[dict[str, Any]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")

    response = requests.get(
        f"{supabase_url}/rest/v1/{VIEW_NAME}",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params={
            "select": (
                "work_date,warehouse_id,warehouse_code,dsp_id,block_key,"
                "shift_template_id,template_name,slot_from,slot_to,"
                "occupancy_from,occupancy_to,status,assigned,opened,"
                "free_slots,capacity_published,fetched_at,updated_at"
            ),
            "work_date": f"eq.{work_date.isoformat()}",
            "warehouse_code": f"eq.{warehouse_code}",
            "order": "slot_from.asc,shift_template_id.asc,block_key.asc",
            "limit": str(int(limit)),
        },
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def row_to_sheet_row(row: dict[str, Any], exported_at: str) -> list[Any]:
    return [
        exported_at,
        clean_text(row.get("work_date")),
        clean_text(row.get("warehouse_code")),
        row.get("warehouse_id") or "",
        row.get("dsp_id") or "",
        clean_text(row.get("block_key")),
        row.get("shift_template_id") or "",
        clean_text(row.get("template_name")),
        clean_text(row.get("slot_from")),
        clean_text(row.get("slot_to")),
        clean_text(row.get("occupancy_from")),
        clean_text(row.get("occupancy_to")),
        clean_text(row.get("status")),
        row.get("opened") if row.get("opened") is not None else "",
        row.get("assigned") if row.get("assigned") is not None else "",
        row.get("free_slots") if row.get("free_slots") is not None else "",
        row.get("capacity_published") if row.get("capacity_published") is not None else "",
    ]


def worksheet_by_gid(spreadsheet, gid: int):
    worksheet = spreadsheet.get_worksheet_by_id(int(gid))
    if worksheet is None:
        raise RuntimeError(f"Nem található worksheet gid={gid}.")
    return worksheet


def export_capacity(work_date: date, dry_run: bool = False) -> dict[str, int]:
    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    output: dict[str, list[list[Any]]] = {}
    counts: dict[str, int] = {}

    for warehouse_code in sorted(WAREHOUSE_WORKSHEETS):
        records = read_capacity_rows(work_date, warehouse_code)
        rows = [
            HEADER,
            *[
                row_to_sheet_row(record, exported_at)
                for record in records
            ],
        ]
        output[warehouse_code] = rows
        counts[warehouse_code] = len(records)

    if dry_run:
        return counts

    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    for warehouse_code, rows in output.items():
        worksheet = worksheet_by_gid(
            spreadsheet,
            WAREHOUSE_WORKSHEETS[warehouse_code],
        )
        worksheet.clear()
        worksheet.update("A1", rows)

    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=datetime.now(LOCAL_TIMEZONE).date().isoformat(),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    work_date = date.fromisoformat(args.date)
    counts = export_capacity(work_date, dry_run=args.dry_run)
    print(
        "COURIER_HUB_SHIFT_BLOCK_CAPACITY_SHEET "
        f"date={work_date.isoformat()} "
        f"BUD1={counts.get('BUD1', 0)} "
        f"BUD2={counts.get('BUD2', 0)} "
        f"dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
