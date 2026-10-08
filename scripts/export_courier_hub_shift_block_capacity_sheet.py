#!/usr/bin/env python3
"""Export Courier Hub shift block capacity view to Google Sheets."""

from __future__ import annotations

import argparse
import re
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
SHIFT_BLOCK_TABLE = "courier_hub_shift_blocks_raw"
MUSZAKPRO_SCHEMA = "muszakpro"
MUSZAKPRO_TABLE = "bookings"
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
    "KIFLI_BOOKING",
    "MUSZAKPRO_BOOKING",
    "Kapacitás publikált",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def supabase_config() -> tuple[str, str]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")
    return supabase_url.rstrip("/"), service_role_key


def public_headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def schema_headers(service_role_key: str, schema: str) -> dict[str, str]:
    return {
        **public_headers(service_role_key),
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }


def paged_get(
    *,
    endpoint: str,
    headers: dict[str, str],
    base_params: list[tuple[str, str]],
    limit: int = 50000,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    max_rows = max(int(limit), 1)
    requested_page_size = max(min(int(page_size), 1000), 1)

    while len(records) < max_rows:
        current_limit = min(requested_page_size, max_rows - len(records))
        params = [
            *base_params,
            ("limit", str(current_limit)),
            ("offset", str(offset)),
        ]
        response = requests.get(
            endpoint,
            headers=headers,
            params=params,
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


def read_capacity_rows(start_date: date, end_date: date, warehouse_code: str) -> list[dict[str, Any]]:
    supabase_url, service_role_key = supabase_config()
    select_clause = (
        "work_date,warehouse_id,warehouse_code,dsp_id,block_key,"
        "shift_template_id,template_name,slot_from,slot_to,"
        "occupancy_from,occupancy_to,status,assigned,opened,"
        "free_slots,kifli_booking,muszakpro_booking,capacity_published,fetched_at,updated_at"
    )
    return paged_get(
        endpoint=f"{supabase_url}/rest/v1/{SHIFT_BLOCK_TABLE}",
        headers=public_headers(service_role_key),
        base_params=[
            ("select", select_clause),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("warehouse_code", f"eq.{warehouse_code}"),
            ("order", "work_date.asc,slot_from.asc,shift_template_id.asc,block_key.asc"),
        ],
    )


def parse_shift_start(value: Any) -> str:
    match = re.search(r"(\d{1,2}:\d{2})", clean_text(value))
    if not match:
        return ""
    hour, minute = match.group(1).split(":", 1)
    return f"{int(hour):02d}:{int(minute):02d}:00"


def parse_warehouse(value: Any) -> str:
    match = re.search(r"(BUD[12])", clean_text(value).upper())
    return match.group(1) if match else ""


def normalize_courier_id(value: Any) -> str:
    text = clean_text(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() else ""


def courier_id_from_serial(value: Any) -> str:
    for part in clean_text(value).split("_"):
        courier_id = normalize_courier_id(part)
        if courier_id:
            return courier_id
    return ""


def muszakpro_booking_value(row: dict[str, Any]) -> str:
    courier_id = normalize_courier_id(row.get("courier_id")) or courier_id_from_serial(row.get("serial"))
    return f"D{courier_id}" if courier_id else ""


def logical_booking_key(row: dict[str, Any]) -> str:
    serial = clean_text(row.get("serial"))
    if serial:
        return serial
    legacy_key = re.sub(r"_[0-9]+$", "", clean_text(row.get("legacy_key")))
    if legacy_key:
        return legacy_key
    return "|".join([
        clean_text(row.get("work_date")),
        clean_text(row.get("email")).casefold(),
        clean_text(row.get("shift_text")),
        clean_text(row.get("booking_code")),
    ])


def muszakpro_row_is_deleted(row: dict[str, Any]) -> bool:
    status = clean_text(row.get("status")).upper()
    event_type = clean_text(row.get("event_type")).upper()
    return (
        status in {"TÖRÖLVE", "TOROLVE", "CANCELLED", "CANCELED", "DELETED", "DELETE"}
        or event_type in {"DELETE", "CANCEL", "CANCELLED", "CANCELED", "DELETED"}
        or bool(clean_text(row.get("cancelled_at")))
    )


def muszakpro_event_sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        clean_text(row.get("cancelled_at") or row.get("updated_at") or row.get("fetched_at") or row.get("created_at")),
        int(row.get("source_row") or 0),
        clean_text(row.get("id")),
    )


def read_muszakpro_rows(start_date: date, end_date: date) -> list[dict[str, Any]]:
    supabase_url, service_role_key = supabase_config()
    return paged_get(
        endpoint=f"{supabase_url}/rest/v1/{MUSZAKPRO_TABLE}",
        headers=schema_headers(service_role_key, MUSZAKPRO_SCHEMA),
        base_params=[
            (
                "select",
                (
                    "id,source_row,work_date,email,shift_text,warehouse,booking_code,"
                    "legacy_key,courier_id,serial,status,event_type,cancelled_at,"
                    "updated_at,fetched_at,created_at"
                ),
            ),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("order", "work_date.asc,updated_at.asc,source_row.asc,id.asc"),
        ],
    )


def build_muszakpro_booking_lookup(start_date: date, end_date: date) -> dict[tuple[str, str, str], str]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    for row in read_muszakpro_rows(start_date, end_date):
        key = logical_booking_key(row)
        if not key:
            continue
        existing = latest_by_key.get(key)
        if existing is None or muszakpro_event_sort_key(row) >= muszakpro_event_sort_key(existing):
            latest_by_key[key] = row

    values_by_slot: dict[tuple[str, str, str], set[str]] = {}
    for row in latest_by_key.values():
        if muszakpro_row_is_deleted(row):
            continue
        warehouse_code = (
            parse_warehouse(row.get("warehouse"))
            or parse_warehouse(row.get("shift_text"))
            or parse_warehouse(row.get("booking_code"))
            or parse_warehouse(row.get("serial"))
        )
        shift_start = (
            parse_shift_start(row.get("shift_text"))
            or parse_shift_start(row.get("booking_code"))
            or parse_shift_start(row.get("serial"))
        )
        work_date = clean_text(row.get("work_date"))
        booking_value = muszakpro_booking_value(row)
        if not all([work_date, warehouse_code, shift_start, booking_value]):
            continue
        values_by_slot.setdefault((work_date, warehouse_code, shift_start), set()).add(booking_value)

    return {
        key: ";".join(sorted(values, key=lambda value: (len(value), value)))
        for key, values in values_by_slot.items()
    }


def apply_muszakpro_booking_lookup(
    records: list[dict[str, Any]],
    lookup: dict[tuple[str, str, str], str],
) -> None:
    for record in records:
        work_date = clean_text(record.get("work_date"))
        warehouse_code = clean_text(record.get("warehouse_code")).upper()
        slot_from = clean_text(record.get("slot_from"))
        occupancy_from = parse_shift_start(record.get("occupancy_from"))
        value = (
            lookup.get((work_date, warehouse_code, slot_from))
            or lookup.get((work_date, warehouse_code, occupancy_from))
            or clean_text(record.get("muszakpro_booking"))
        )
        record["muszakpro_booking"] = value


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
        clean_text(row.get("kifli_booking")),
        clean_text(row.get("muszakpro_booking")),
        row.get("capacity_published") if row.get("capacity_published") is not None else "",
    ]


def worksheet_by_gid(spreadsheet, gid: int):
    worksheet = spreadsheet.get_worksheet_by_id(int(gid))
    if worksheet is None:
        raise RuntimeError(f"Nem található worksheet gid={gid}.")
    return worksheet


def export_capacity(start_date: date, end_date: date, dry_run: bool = False) -> dict[str, int]:
    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    output: dict[str, list[list[Any]]] = {}
    counts: dict[str, int] = {}
    kifli_booking_counts: dict[str, int] = {}
    muszakpro_booking_counts: dict[str, int] = {}
    muszakpro_lookup = build_muszakpro_booking_lookup(start_date, end_date)

    for warehouse_code in sorted(WAREHOUSE_WORKSHEETS):
        records = read_capacity_rows(start_date, end_date, warehouse_code)
        apply_muszakpro_booking_lookup(records, muszakpro_lookup)
        kifli_booking_counts[warehouse_code] = sum(1 for record in records if clean_text(record.get("kifli_booking")))
        muszakpro_booking_counts[warehouse_code] = sum(1 for record in records if clean_text(record.get("muszakpro_booking")))
        rows = [
            HEADER,
            *[
                row_to_sheet_row(record, exported_at)
                for record in records
            ],
        ]
        output[warehouse_code] = rows
        counts[warehouse_code] = len(records)
        print(
            "COURIER_HUB_SHIFT_BLOCK_CAPACITY_EXPORT_VALUES "
            f"warehouse={warehouse_code} rows={len(records)} "
            f"kifli_booking_rows={kifli_booking_counts[warehouse_code]} "
            f"muszakpro_booking_rows={muszakpro_booking_counts[warehouse_code]} "
            f"muszakpro_lookup_slots={len(muszakpro_lookup)}",
            flush=True,
        )

    if dry_run:
        return counts

    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    for warehouse_code, rows in output.items():
        worksheet = worksheet_by_gid(
            spreadsheet,
            WAREHOUSE_WORKSHEETS[warehouse_code],
        )
        worksheet.clear()
        worksheet.update(
            range_name="A1",
            values=rows,
        )

    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=datetime.now(LOCAL_TIMEZONE).date().isoformat(),
    )
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=0,
        help="Ennyi nappal nezzen elore a kezdodatumtol. 0 eseten csak egy napot exportal.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date or args.date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)
    elif args.lookahead_days > 0:
        end_date = start_date + timedelta(days=args.lookahead_days)
    else:
        end_date = start_date

    counts = export_capacity(start_date, end_date, dry_run=args.dry_run)
    print(
        "COURIER_HUB_SHIFT_BLOCK_CAPACITY_SHEET "
        f"start_date={start_date.isoformat()} "
        f"end_date={end_date.isoformat()} "
        f"BUD1={counts.get('BUD1', 0)} "
        f"BUD2={counts.get('BUD2', 0)} "
        f"dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
