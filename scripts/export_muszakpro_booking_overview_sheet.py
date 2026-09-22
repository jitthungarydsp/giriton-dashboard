#!/usr/bin/env python3
"""Export the MuszakPro blockKey validation overview to Google Sheets."""

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

from google_client import open_spreadsheet  # noqa: E402
from resources.supabase_raw import (  # noqa: E402
    get_supabase_config,
    raise_for_supabase_error,
)


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 249042641
VIEW_NAME = "vw_muszakpro_booking_overview"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "Frissítve",
    "Dátum",
    "Raktár",
    "E-mail",
    "Futár",
    "courierId",
    "JITT azonosító",
    "BlockKey",
    "Booking key",
    "Shift template ID",
    "MűszakPro műszak",
    "Slot kezdete",
    "Slot vége",
    "Tervezett indulás",
    "Tervezett visszaérkezés",
    "Block státusz",
    "Nyitott slot",
    "Foglalt slot",
    "Szabad slot",
    "Kifli foglalás",
    "Mozgás",
    "Jogos?",
    "Visszajelzés",
    "MűszakPro státusz",
    "MűszakPro foglalási kód",
    "MűszakPro sor",
    "Első észlelés",
    "Utolsó észlelés",
    "Törölve",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_overview_rows(start_date: date, end_date: date, limit: int = 50000) -> list[dict[str, Any]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")

    params = [
        (
            "select",
            (
                "work_date,warehouse_code,email,courier_name,courier_id,jitt_internal_id,"
                "block_key,booking_key,shift_template_id,shift_text,slot_from,slot_to,"
                "occupancy_from,occupancy_to,block_status,opened,assigned,free_slots,"
                "kifli_booking_courier_id,kifli_movement_type,kifli_booking_active,"
                "validation_status,validation_reason,muszakpro_status,booking_code,"
                "source_row,kifli_first_seen_at,kifli_last_seen_at,kifli_deleted_at"
            ),
        ),
        ("work_date", f"gte.{start_date.isoformat()}"),
        ("work_date", f"lte.{end_date.isoformat()}"),
        ("order", "work_date.asc,warehouse_code.asc,slot_from.asc,courier_name.asc,email.asc"),
        ("limit", str(int(limit))),
    ]
    response = requests.get(
        f"{supabase_url.rstrip('/')}/rest/v1/{VIEW_NAME}",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params=params,
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def format_bool(value: Any) -> str:
    if value is True:
        return "Igen"
    if value is False:
        return "Nem"
    return ""


def row_to_sheet_row(row: dict[str, Any], exported_at: str) -> list[Any]:
    return [
        exported_at,
        clean_text(row.get("work_date")),
        clean_text(row.get("warehouse_code")),
        clean_text(row.get("email")),
        clean_text(row.get("courier_name")),
        row.get("courier_id") or "",
        clean_text(row.get("jitt_internal_id")),
        clean_text(row.get("block_key")),
        clean_text(row.get("booking_key")),
        row.get("shift_template_id") or "",
        clean_text(row.get("shift_text")),
        clean_text(row.get("slot_from")),
        clean_text(row.get("slot_to")),
        clean_text(row.get("occupancy_from")),
        clean_text(row.get("occupancy_to")),
        clean_text(row.get("block_status")),
        row.get("opened") if row.get("opened") is not None else "",
        row.get("assigned") if row.get("assigned") is not None else "",
        row.get("free_slots") if row.get("free_slots") is not None else "",
        format_bool(row.get("kifli_booking_active")),
        clean_text(row.get("kifli_movement_type")),
        clean_text(row.get("validation_status")),
        clean_text(row.get("validation_reason")),
        clean_text(row.get("muszakpro_status")),
        clean_text(row.get("booking_code")),
        row.get("source_row") or "",
        clean_text(row.get("kifli_first_seen_at")),
        clean_text(row.get("kifli_last_seen_at")),
        clean_text(row.get("kifli_deleted_at")),
    ]


def export_overview(start_date: date, end_date: date, dry_run: bool = False) -> int:
    records = read_overview_rows(start_date, end_date)
    if dry_run:
        return len(records)

    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    if records:
        values = [
            HEADER,
            *[row_to_sheet_row(record, exported_at) for record in records],
        ]
    else:
        values = [
            HEADER,
            [
                exported_at,
                f"Nincs DB adat {start_date.isoformat()} - {end_date.isoformat()} között.",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Előbb fusson le a MűszakPro import és a Kifli shift-block sync.",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ]

    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    worksheet = spreadsheet.get_worksheet_by_id(WORKSHEET_GID)
    if worksheet is None:
        raise RuntimeError(f"Nem található worksheet gid={WORKSHEET_GID}.")

    worksheet.clear()
    worksheet.update(
        range_name="A1",
        values=values,
    )
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=datetime.now(LOCAL_TIMEZONE).date().isoformat(),
    )
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=21)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date or args.date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)
    elif args.lookahead_days > 0:
        end_date = start_date + timedelta(days=args.lookahead_days)
    else:
        end_date = start_date

    rows = export_overview(start_date, end_date, dry_run=args.dry_run)
    print(
        "MUSZAKPRO_BOOKING_OVERVIEW_SHEET "
        f"start_date={start_date.isoformat()} end_date={end_date.isoformat()} "
        f"rows={rows} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
