#!/usr/bin/env python3
"""Export MuszakPro bookings vs open Courier Hub blocks to Google Sheets."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import gspread
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google_client import open_spreadsheet  # noqa: E402
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_TITLE = "HUB_MUSZAKPRO_BOOKABLE"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
MUSZAKPRO_SCHEMA = "muszakpro"
MUSZAKPRO_TABLE = "bookings"
DSP_ID = 8

WAREHOUSE_CODE_BY_ID = {
    1: "BUD1",
    2: "BUD2",
}

HEADER = [
    "Frissítve",
    "Sor típusa",
    "Dátum",
    "Raktár",
    "courierId",
    "Futár",
    "email",
    "MűszakPro műszak",
    "MűszakPro státusz",
    "Serial",
    "HUB pontos slot",
    "HUB ajánlott slot",
    "Eltérés perc",
    "Egyezés típusa",
    "HUB státusz",
    "Megnyitott slot",
    "Foglalt slot",
    "Szabad slot",
    "Már HUB-ban",
    "Foglalható",
    "Ok",
    "BlockKey",
    "Shift template ID",
    "MűszakPro sor",
    "MűszakPro frissítve",
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


def normalize_time(value: Any) -> str:
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::\d{2})?(?!\d)", clean_text(value))
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}:00"


def time_minutes(value: Any) -> int | None:
    text = normalize_time(value)
    if not text:
        return None
    hour, minute, _second = text.split(":")
    return int(hour) * 60 + int(minute)


def diff_minutes(left: Any, right: Any) -> int | None:
    left_minutes = time_minutes(left)
    right_minutes = time_minutes(right)
    if left_minutes is None or right_minutes is None:
        return None
    diff = right_minutes - left_minutes
    if diff > 720:
        diff -= 1440
    elif diff < -720:
        diff += 1440
    return diff


def parse_warehouse(value: Any) -> str:
    text = clean_text(value).upper()
    match = re.search(r"(BUD[12])", text)
    if match:
        return match.group(1)
    if text in {"1", "1.0"}:
        return "BUD1"
    if text in {"2", "2.0"}:
        return "BUD2"
    return ""


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


def event_sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        clean_text(row.get("cancelled_at") or row.get("updated_at") or row.get("fetched_at") or row.get("created_at")),
        int(row.get("source_row") or 0),
        clean_text(row.get("id")),
    )


def read_muszakpro_rows(start_date: date, end_date: date, limit: int) -> list[dict[str, Any]]:
    supabase_url, service_role_key = supabase_config()
    return paged_get(
        endpoint=f"{supabase_url}/rest/v1/{MUSZAKPRO_TABLE}",
        headers=schema_headers(service_role_key, MUSZAKPRO_SCHEMA),
        base_params=[
            (
                "select",
                (
                    "id,source_row,timestamp_text,work_date,email,shift_text,warehouse,"
                    "booking_code,courier_id,courier_name,serial,status,event_type,"
                    "cancelled_at,updated_at,fetched_at,created_at"
                ),
            ),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("order", "work_date.asc,updated_at.asc,source_row.asc,id.asc"),
        ],
        limit=limit,
    )


def active_muszakpro_rows(start_date: date, end_date: date, limit: int) -> list[dict[str, Any]]:
    # muszakpro.bookings is the current booking table: rows in it are active
    # MuszakPro bookings. We dedupe repeated imports, but do not look for delete
    # events here.
    latest_by_key: dict[str, dict[str, Any]] = {}
    for row in read_muszakpro_rows(start_date, end_date, limit):
        key = logical_booking_key(row)
        if not key:
            continue
        existing = latest_by_key.get(key)
        if existing is None or event_sort_key(row) >= event_sort_key(existing):
            latest_by_key[key] = row

    rows: list[dict[str, Any]] = []
    for row in latest_by_key.values():
        work_date = clean_text(row.get("work_date"))[:10]
        warehouse = (
            parse_warehouse(row.get("warehouse"))
            or parse_warehouse(row.get("shift_text"))
            or parse_warehouse(row.get("booking_code"))
            or parse_warehouse(row.get("serial"))
        )
        shift_start = (
            normalize_time(row.get("shift_text"))
            or normalize_time(row.get("booking_code"))
            or normalize_time(row.get("serial"))
        )
        courier_id = normalize_courier_id(row.get("courier_id")) or courier_id_from_serial(row.get("serial"))
        if not all([work_date, warehouse, shift_start, courier_id]):
            continue
        row = dict(row)
        row["_work_date"] = work_date
        row["_warehouse"] = warehouse
        row["_shift_start"] = shift_start
        row["_courier_id"] = courier_id
        rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            row["_work_date"],
            row["_warehouse"],
            row["_shift_start"],
            clean_text(row.get("courier_name")),
            row["_courier_id"],
        ),
    )


def read_hub_blocks(start_date: date, end_date: date, dsp_id: int, limit: int) -> list[dict[str, Any]]:
    supabase_url, service_role_key = supabase_config()
    return paged_get(
        endpoint=f"{supabase_url}/rest/v1/courier_hub_shift_blocks_raw",
        headers=public_headers(service_role_key),
        base_params=[
            (
                "select",
                (
                    "work_date,warehouse_id,warehouse_code,dsp_id,block_key,shift_template_id,"
                    "template_name,slot_from,slot_to,status,assigned,opened,free_slots"
                ),
            ),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("order", "work_date.asc,warehouse_id.asc,slot_from.asc,shift_template_id.asc"),
        ],
        limit=limit,
    )


def prepared_hub_blocks(start_date: date, end_date: date, dsp_id: int, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_hub_blocks(start_date, end_date, dsp_id, limit):
        work_date = clean_text(row.get("work_date"))[:10]
        warehouse_id = int(row.get("warehouse_id") or 0)
        warehouse = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, "")
        slot_from = normalize_time(row.get("slot_from"))
        if not all([work_date, warehouse, slot_from]):
            continue
        opened = int(row.get("opened") or 0)
        assigned = int(row.get("assigned") or 0)
        free_slots = row.get("free_slots")
        if free_slots is None:
            free_slots = max(opened - assigned, 0)
        row = dict(row)
        row["_work_date"] = work_date
        row["_warehouse"] = warehouse
        row["_slot_from"] = slot_from
        row["_status"] = clean_text(row.get("status")).upper()
        row["_opened"] = opened
        row["_assigned"] = assigned
        row["_free_slots"] = int(free_slots or 0)
        rows.append(row)
    return rows


def read_existing_subscriptions(start_date: date, end_date: date, dsp_id: int, limit: int) -> set[tuple[str, str, str, str]]:
    supabase_url, service_role_key = supabase_config()
    rows = paged_get(
        endpoint=f"{supabase_url}/rest/v1/courier_hub_shift_bookings_raw",
        headers=public_headers(service_role_key),
        base_params=[
            ("select", "work_date,dsp_id,courier_id,warehouse_code,warehouse_id,slot_from,status,active"),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("active", "eq.true"),
        ],
        limit=limit,
    )
    existing: set[tuple[str, str, str, str]] = set()
    for row in rows:
        work_date = clean_text(row.get("work_date"))[:10]
        courier_id = normalize_courier_id(row.get("courier_id"))
        warehouse_id = int(row.get("warehouse_id") or 0)
        warehouse = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, "")
        slot_from = normalize_time(row.get("slot_from"))
        if all([work_date, courier_id, warehouse, slot_from]):
            existing.add((work_date, courier_id, warehouse, slot_from))
    return existing


def best_hub_match(
    row: dict[str, Any],
    blocks_by_slot: dict[tuple[str, str, str], list[dict[str, Any]]],
    all_blocks: list[dict[str, Any]],
    tolerance_minutes: int,
) -> tuple[dict[str, Any] | None, str, int | str]:
    work_date = row["_work_date"]
    warehouse = row["_warehouse"]
    shift_start = row["_shift_start"]
    exact_candidates = blocks_by_slot.get((work_date, warehouse, shift_start), [])
    if exact_candidates:
        return sorted(exact_candidates, key=block_sort_key)[0], "Pontos", 0

    candidates: list[tuple[int, int, dict[str, Any], int]] = []
    for block in all_blocks:
        if block["_work_date"] != work_date or block["_warehouse"] != warehouse:
            continue
        current_diff = diff_minutes(shift_start, block["_slot_from"])
        if current_diff is None or abs(current_diff) > max(int(tolerance_minutes), 0):
            continue
        candidates.append((abs(current_diff), time_minutes(block["_slot_from"]) or 0, block, current_diff))
    if not candidates:
        return None, "", ""
    _score, _minutes, block, current_diff = sorted(candidates, key=lambda item: (item[0], item[1], block_sort_key(item[2])))[0]
    return block, "Alternatíva", current_diff


def block_sort_key(block: dict[str, Any]) -> tuple[int, int, str]:
    is_open = 0 if block.get("_status") == "OPEN" else 1
    free_rank = -int(block.get("_free_slots") or 0)
    return (is_open, free_rank, clean_text(block.get("block_key")))


def row_status(
    row: dict[str, Any],
    block: dict[str, Any] | None,
    existing_subscriptions: set[tuple[str, str, str, str]],
    planned_by_block: dict[str, int],
) -> tuple[str, str, str]:
    if block is None:
        return "Nem", "Nincs HUB blokk tolerancián belül.", "Nem"

    existing_key = (
        row["_work_date"],
        row["_courier_id"],
        row["_warehouse"],
        block["_slot_from"],
    )
    already_booked = "Igen" if existing_key in existing_subscriptions else "Nem"
    if already_booked == "Igen":
        return "Nem", "Már le van foglalva HUB-ban.", already_booked
    if block["_status"] != "OPEN":
        return "Nem", f"HUB blokk nem nyitott: {block['_status'] or '-'}", already_booked
    remaining = int(block.get("_free_slots") or 0) - planned_by_block.get(clean_text(block.get("block_key")), 0)
    if remaining <= 0:
        return "Nem", "Nincs szabad HUB slot.", already_booked
    return "Igen", "Foglalható.", already_booked


def build_rows(start_date: date, end_date: date, dsp_id: int, tolerance_minutes: int, limit: int) -> list[list[Any]]:
    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    muszakpro_rows = active_muszakpro_rows(start_date, end_date, limit)
    hub_blocks = prepared_hub_blocks(start_date, end_date, dsp_id, limit)
    existing_subscriptions = read_existing_subscriptions(start_date, end_date, dsp_id, limit)

    blocks_by_slot: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for block in hub_blocks:
        blocks_by_slot.setdefault((block["_work_date"], block["_warehouse"], block["_slot_from"]), []).append(block)

    output = [HEADER]
    matched_block_keys: set[str] = set()
    planned_by_block: dict[str, int] = {}
    for row in muszakpro_rows:
        block, match_kind, match_diff = best_hub_match(row, blocks_by_slot, hub_blocks, tolerance_minutes)
        if block:
            matched_block_keys.add(clean_text(block.get("block_key")))
        bookable, reason, already_booked = row_status(row, block, existing_subscriptions, planned_by_block)
        if bookable == "Igen" and block:
            block_key = clean_text(block.get("block_key"))
            planned_by_block[block_key] = planned_by_block.get(block_key, 0) + 1
        output.append([
            exported_at,
            "MUSZAKPRO_BOOKING",
            row["_work_date"],
            row["_warehouse"],
            row["_courier_id"],
            clean_text(row.get("courier_name")),
            clean_text(row.get("email")).casefold(),
            row["_shift_start"],
            clean_text(row.get("status")) or "ACTIVE",
            clean_text(row.get("serial")),
            row["_shift_start"] if blocks_by_slot.get((row["_work_date"], row["_warehouse"], row["_shift_start"])) else "",
            block["_slot_from"] if block else "",
            match_diff,
            match_kind,
            block["_status"] if block else "",
            block["_opened"] if block else "",
            block["_assigned"] if block else "",
            block["_free_slots"] if block else "",
            already_booked,
            bookable,
            reason,
            clean_text(block.get("block_key")) if block else "",
            block.get("shift_template_id") if block else "",
            row.get("source_row") or "",
            clean_text(row.get("updated_at") or row.get("fetched_at") or row.get("created_at")),
        ])

    for block in sorted(hub_blocks, key=lambda item: (item["_work_date"], item["_warehouse"], item["_slot_from"], clean_text(item.get("block_key")))):
        block_key = clean_text(block.get("block_key"))
        if block_key in matched_block_keys:
            continue
        if block["_status"] != "OPEN" or int(block.get("_free_slots") or 0) <= 0:
            continue
        output.append([
            exported_at,
            "HUB_OPEN_ONLY",
            block["_work_date"],
            block["_warehouse"],
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            block["_slot_from"],
            "",
            "Csak HUB",
            block["_status"],
            block["_opened"],
            block["_assigned"],
            block["_free_slots"],
            "",
            "Nem",
            "HUB nyitott, de nincs hozzá aktív MűszakPro booking.",
            block_key,
            block.get("shift_template_id") or "",
            "",
            "",
        ])

    print(
        "MUSZAKPRO_HUB_BOOKABLE_BUILD "
        f"start_date={start_date.isoformat()} end_date={end_date.isoformat()} "
        f"muszakpro_rows={len(muszakpro_rows)} hub_blocks={len(hub_blocks)} "
        f"existing_subscriptions={len(existing_subscriptions)} output_rows={len(output)}",
        flush=True,
    )
    return output


def get_or_create_worksheet(spreadsheet, title: str, rows: int, cols: int):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=max(rows, 1000), cols=max(cols, 25))


def export_sheet(
    start_date: date,
    end_date: date,
    *,
    dsp_id: int,
    tolerance_minutes: int,
    limit: int,
    dry_run: bool,
) -> dict[str, Any]:
    rows = build_rows(start_date, end_date, dsp_id, tolerance_minutes, limit)
    if dry_run:
        return {"rows": len(rows), "worksheet_title": WORKSHEET_TITLE, "dry_run": True}

    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    worksheet = get_or_create_worksheet(spreadsheet, WORKSHEET_TITLE, len(rows), len(HEADER))
    worksheet.clear()
    worksheet.resize(rows=max(len(rows), 1), cols=max(len(HEADER), 1))
    worksheet.update(rows, value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1)
    return {
        "rows": len(rows),
        "worksheet_title": worksheet.title,
        "worksheet_id": worksheet.id,
        "dry_run": False,
    }


def main() -> int:
    today = datetime.now(LOCAL_TIMEZONE).date()
    parser = argparse.ArgumentParser(description="MűszakPro bookingok és HUB nyitott blokkok összevetése.")
    parser.add_argument("--start-date", default=today.replace(day=1).isoformat())
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=60)
    parser.add_argument("--dsp-id", type=int, default=DSP_ID)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date) if args.end_date else start_date + timedelta(days=max(int(args.lookahead_days), 0))
    result = export_sheet(
        start_date,
        end_date,
        dsp_id=int(args.dsp_id),
        tolerance_minutes=int(args.tolerance_minutes),
        limit=int(args.limit),
        dry_run=bool(args.dry_run),
    )
    print(
        "MUSZAKPRO_HUB_BOOKABLE_SHEET "
        f"start_date={start_date.isoformat()} end_date={end_date.isoformat()} "
        f"rows={result['rows']} worksheet_title={result['worksheet_title']!r} "
        f"worksheet_id={result.get('worksheet_id', '')} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
