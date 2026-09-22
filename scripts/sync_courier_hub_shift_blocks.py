#!/usr/bin/env python3
"""Courier Hub shift-blocks and roster subscriptions sync."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    courier_hub_auth_configured,
    raise_for_response,
    supabase_headers,
)
from sync_courier_hub_master import (  # noqa: E402
    DEFAULT_BASE_URL,
    WAREHOUSE_CODES,
    build_roster_url,
    clean_text,
    courier_id_from_row,
    has_next_page,
    int_or_none,
    parse_warehouse_ids,
    request_json,
    roster_items,
    text_or_none,
)


SHIFT_BLOCK_TABLE = "courier_hub_shift_blocks_raw"
SUBSCRIBER_TABLE = "courier_hub_roster_shift_subscribers_raw"
BOOKING_TABLE = "courier_hub_shift_bookings_raw"
SUBSCRIBER_COLUMNS = [
    "source_name",
    "work_date",
    "warehouse_id",
    "warehouse_code",
    "dsp_id",
    "courier_id",
    "courier_name",
    "email",
    "phone_number",
    "subscriber_key",
    "block_key",
    "shift_template_id",
    "shift_text",
    "slot_from",
    "slot_to",
    "status",
    "source_page",
    "source_row_index",
    "source_shift_index",
    "request_url",
    "subscription_json",
    "courier_json",
    "fetched_at",
    "updated_at",
]


def date_range(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("--end-date nem lehet korábbi, mint --start-date.")

    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if clean_text(value):
            return value
    return None


def build_shift_blocks_url(base_url: str, warehouse_id: int, dsp_id: int, work_date: date) -> str:
    query = urlencode({
        "dateFrom": work_date.isoformat(),
        "dateTo": work_date.isoformat(),
    })
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{int(dsp_id)}/shift-blocks?{query}"
    )


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("content", "items", "data", "shiftBlocks", "shift_blocks", "blocks"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def normalize_time(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if len(text) == 5:
        return f"{text}:00"
    return text


def build_block_row(
    *,
    warehouse_id: int,
    dsp_id: int,
    work_date: date,
    request_url: str,
    fetched_at: datetime,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    block_key = text_or_none(first_value(item, "blockKey", "block_key"))
    if not block_key:
        return None

    assigned = int_or_none(item.get("assigned"))
    opened = int_or_none(item.get("opened"))
    free_slots = None
    if assigned is not None and opened is not None:
        free_slots = max(opened - assigned, 0)

    now = datetime.now(timezone.utc).isoformat()
    fetched_at_text = fetched_at.isoformat()
    return {
        "source_name": "courier_hub_shift_blocks",
        "work_date": clean_text(item.get("date")) or work_date.isoformat(),
        "warehouse_id": int(warehouse_id),
        "warehouse_code": WAREHOUSE_CODES.get(int(warehouse_id), f"WH{warehouse_id}"),
        "dsp_id": int(dsp_id),
        "block_key": block_key,
        "shift_template_id": int_or_none(item.get("shiftTemplateId") or item.get("shift_template_id")),
        "layer_id": int_or_none(item.get("layerId") or item.get("layer_id")),
        "dsp_company_id": int_or_none(item.get("dspCompanyId") or item.get("dsp_company_id")),
        "template_name": text_or_none(item.get("templateName") or item.get("template_name")),
        "slot_from": normalize_time(item.get("slotFrom") or item.get("slot_from")),
        "slot_to": normalize_time(item.get("slotTo") or item.get("slot_to")),
        "occupancy_from": text_or_none(item.get("occupancyFrom") or item.get("occupancy_from")),
        "occupancy_to": text_or_none(item.get("occupancyTo") or item.get("occupancy_to")),
        "status": text_or_none(item.get("status")),
        "assigned": assigned,
        "opened": opened,
        "free_slots": free_slots,
        "capacity_published": bool_or_none(item.get("capacityPublished") or item.get("capacity_published")),
        "subscribe_locked": bool_or_none(item.get("subscribeLocked") or item.get("subscribe_locked")),
        "unsubscribe_locked": bool_or_none(item.get("unsubscribeLocked") or item.get("unsubscribe_locked")),
        "allow_subscribing_till": text_or_none(item.get("allowSubscribingTill") or item.get("allow_subscribing_till")),
        "allow_unsubscribing_till": text_or_none(item.get("allowUnsubscribingTill") or item.get("allow_unsubscribing_till")),
        "subscribe_seconds_remaining": int_or_none(item.get("subscribeSecondsRemaining") or item.get("subscribe_seconds_remaining")),
        "unsubscribe_seconds_remaining": int_or_none(item.get("unsubscribeSecondsRemaining") or item.get("unsubscribe_seconds_remaining")),
        "request_url": request_url,
        "response_json": item,
        "fetched_at": fetched_at_text,
        "updated_at": now,
    }


def extract_subscription_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "shifts",
        "shiftBlocks",
        "shift_blocks",
        "assignments",
        "subscriptions",
        "bookings",
        "rosterItems",
        "roster_items",
    ):
        value = row.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return [{}]


def subscriber_key_for(
    *,
    courier_id: int,
    source_row_index: int,
    source_shift_index: int,
    subscription: dict[str, Any],
) -> str:
    block_key = text_or_none(first_value(subscription, "blockKey", "block_key"))
    if block_key:
        return block_key

    shift_template_id = text_or_none(first_value(subscription, "shiftTemplateId", "shift_template_id"))
    start = text_or_none(first_value(subscription, "slotFrom", "slot_from", "shiftStart", "shift_start", "start"))
    if shift_template_id or start:
        return "|".join([str(courier_id), shift_template_id or "", start or ""])

    return f"{courier_id}|row:{source_row_index}|shift:{source_shift_index}"


def build_subscriber_rows(
    *,
    warehouse_id: int,
    dsp_id: int,
    work_date: date,
    source_page: int,
    source_row_index: int,
    request_url: str,
    fetched_at: datetime,
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    courier_id = courier_id_from_row(row)
    if courier_id is None:
        return []

    now = datetime.now(timezone.utc).isoformat()
    fetched_at_text = fetched_at.isoformat()
    subscriptions = extract_subscription_items(row)
    rows: list[dict[str, Any]] = []
    for shift_index, subscription in enumerate(subscriptions):
        if not isinstance(subscription, dict):
            subscription = {}

        block_key = text_or_none(first_value(subscription, "blockKey", "block_key"))
        subscriber_key = subscriber_key_for(
            courier_id=courier_id,
            source_row_index=source_row_index,
            source_shift_index=shift_index,
            subscription=subscription,
        )
        shift_text = text_or_none(first_value(
            subscription,
            "shiftText",
            "shift_text",
            "shift",
            "name",
            "templateName",
            "template_name",
        )) or text_or_none(first_value(row, "shiftText", "shift_text", "shift"))

        rows.append({
            "source_name": "courier_hub_roster_shift_subscribers",
            "work_date": work_date.isoformat(),
            "warehouse_id": int(warehouse_id),
            "warehouse_code": WAREHOUSE_CODES.get(int(warehouse_id), f"WH{warehouse_id}"),
            "dsp_id": int(dsp_id),
            "courier_id": courier_id,
            "courier_name": text_or_none(first_value(row, "name", "courierName", "courier_name", "fullName", "full_name")),
            "email": text_or_none(first_value(row, "email", "emailAddress", "email_address")),
            "phone_number": text_or_none(first_value(row, "phone", "phoneNumber", "phone_number", "mobile", "mobilePhone")),
            "subscriber_key": subscriber_key,
            "block_key": block_key,
            "shift_template_id": int_or_none(first_value(subscription, "shiftTemplateId", "shift_template_id")),
            "shift_text": shift_text,
            "slot_from": normalize_time(first_value(subscription, "slotFrom", "slot_from", "shiftStart", "shift_start", "start")),
            "slot_to": normalize_time(first_value(subscription, "slotTo", "slot_to", "shiftEnd", "shift_end", "end")),
            "status": text_or_none(first_value(subscription, "status", "state")) or text_or_none(first_value(row, "status", "state")),
            "source_page": source_page,
            "source_row_index": source_row_index,
            "source_shift_index": shift_index,
            "request_url": request_url,
            "subscription_json": subscription,
            "courier_json": row,
            "fetched_at": fetched_at_text,
            "updated_at": now,
        })

    return rows


def assignment_courier_id(assignment: dict[str, Any]) -> int | None:
    courier_id = int_or_none(assignment.get("courierId") or assignment.get("courier_id"))
    if courier_id is not None:
        return courier_id
    courier = assignment.get("courier") if isinstance(assignment.get("courier"), dict) else {}
    return int_or_none(courier.get("courierId") or courier.get("courier_id"))


def assignment_courier_field(assignment: dict[str, Any], *keys: str) -> Any:
    courier = assignment.get("courier") if isinstance(assignment.get("courier"), dict) else {}
    return first_value(courier, *keys) or first_value(assignment, *keys)


def build_assignment_rows_from_block(
    *,
    warehouse_id: int,
    dsp_id: int,
    work_date: date,
    request_url: str,
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    block_key = text_or_none(first_value(block, "blockKey", "block_key"))
    assignments = block.get("assignments")
    if not block_key or not isinstance(assignments, list):
        return []

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, dict):
            continue
        courier_id = assignment_courier_id(assignment)
        if courier_id is None:
            continue
        courier = assignment.get("courier") if isinstance(assignment.get("courier"), dict) else {}
        rows.append({
            "source_name": "courier_hub_shift_block_assignments",
            "work_date": clean_text(block.get("date")) or work_date.isoformat(),
            "warehouse_id": int(warehouse_id),
            "warehouse_code": WAREHOUSE_CODES.get(int(warehouse_id), f"WH{warehouse_id}"),
            "dsp_id": int(dsp_id),
            "courier_id": courier_id,
            "courier_name": text_or_none(assignment_courier_field(assignment, "name", "courierName", "courier_name", "fullName", "full_name")),
            "email": text_or_none(assignment_courier_field(assignment, "email", "emailAddress", "email_address")),
            "phone_number": text_or_none(assignment_courier_field(assignment, "phone", "phoneNumber", "phone_number", "mobile", "mobilePhone")),
            "subscriber_key": f"{block_key}|{courier_id}|{index}",
            "block_key": block_key,
            "shift_template_id": int_or_none(first_value(block, "shiftTemplateId", "shift_template_id")),
            "shift_text": text_or_none(first_value(block, "templateName", "template_name")) or block_key,
            "slot_from": normalize_time(first_value(block, "slotFrom", "slot_from")),
            "slot_to": normalize_time(first_value(block, "slotTo", "slot_to")),
            "status": text_or_none(first_value(assignment, "source", "status", "state")) or text_or_none(first_value(block, "status")),
            "source_page": 0,
            "source_row_index": 0,
            "source_shift_index": index,
            "request_url": request_url,
            "subscription_json": assignment,
            "courier_json": courier or assignment,
            "fetched_at": now,
            "updated_at": now,
        })

    return rows


def supabase_upsert(table: str, rows: list[dict[str, Any]], conflict: str, *, chunk_size: int = 500) -> int:
    if not rows:
        return 0

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    written = 0
    for index in range(0, len(rows), chunk_size):
        chunk = rows[index:index + chunk_size]
        response = requests.post(
            f"{supabase_url}/rest/v1/{table}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": conflict},
            json=chunk,
            timeout=60,
        )
        raise_for_response(response, f"{table} upsert")
        written += len(chunk)
    return written


def normalize_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append({
            column: row.get(column)
            for column in columns
        })
    return normalized


def dedupe_rows(rows: list[dict[str, Any]], key_columns: list[str]) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(column) for column in key_columns)
        by_key[key] = row
    return list(by_key.values())


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


def is_missing_table_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def supabase_get_rows(table: str, params: dict[str, str] | list[tuple[str, str]]) -> list[dict[str, Any]]:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.get(
        f"{supabase_url}/rest/v1/{table}",
        headers=supabase_headers(),
        params=params,
        timeout=60,
    )
    if is_missing_table_response(response):
        return []
    raise_for_response(response, f"{table} lekérés")
    payload = response.json()
    return payload if isinstance(payload, list) else []


def booking_key(row: dict[str, Any]) -> tuple[str, int, int, int, str]:
    return (
        clean_text(row.get("work_date")),
        int(row.get("warehouse_id") or 0),
        int(row.get("dsp_id") or 0),
        int(row.get("courier_id") or 0),
        clean_text(row.get("block_key")),
    )


def load_identity_lookup(dsp_id: int) -> dict[tuple[int, int], str]:
    rows = supabase_get_rows(
        "courier_hub_courier_identity_raw",
        {
            "select": "courier_id,dsp_id,jitt_internal_id",
            "dsp_id": f"eq.{int(dsp_id)}",
            "limit": "20000",
        },
    )
    lookup: dict[tuple[int, int], str] = {}
    for row in rows:
        courier_id = int_or_none(row.get("courier_id"))
        row_dsp_id = int_or_none(row.get("dsp_id"))
        jitt_id = text_or_none(row.get("jitt_internal_id"))
        if courier_id is not None and row_dsp_id is not None and jitt_id:
            lookup[(courier_id, row_dsp_id)] = jitt_id
    return lookup


def load_existing_active_bookings_for_range(
    *,
    start_date: date,
    end_date: date,
    warehouse_ids: list[int],
    dsp_id: int,
) -> dict[tuple[str, int, int, int, str], dict[str, Any]]:
    warehouse_filter = ",".join(str(int(value)) for value in warehouse_ids)
    params = [
        ("select", (
            "work_date,warehouse_id,warehouse_code,dsp_id,courier_id,"
            "jitt_internal_id,courier_name,email,phone_number,block_key,"
            "shift_template_id,shift_text,slot_from,slot_to,status,"
            "first_seen_at,last_seen_at,request_url,subscription_json,courier_json"
        )),
        ("work_date", f"gte.{start_date.isoformat()}"),
        ("work_date", f"lte.{end_date.isoformat()}"),
        ("warehouse_id", f"in.({warehouse_filter})"),
        ("dsp_id", f"eq.{int(dsp_id)}"),
        ("active", "eq.true"),
        ("limit", "50000"),
    ]
    rows = supabase_get_rows(BOOKING_TABLE, params)
    return {
        booking_key(row): row
        for row in rows
        if clean_text(row.get("block_key"))
    }


def build_booking_state_rows(
    *,
    subscriber_rows: list[dict[str, Any]],
    existing_active: dict[tuple[str, int, int, int, str], dict[str, Any]],
    identity_lookup: dict[tuple[int, int], str],
    fetched_at: datetime,
) -> list[dict[str, Any]]:
    now = fetched_at.isoformat()
    current_rows: list[dict[str, Any]] = []
    current_keys: set[tuple[str, int, int, int, str]] = set()

    for row in subscriber_rows:
        block_key = text_or_none(row.get("block_key"))
        if not block_key:
            continue
        key = booking_key(row)
        current_keys.add(key)
        existing = existing_active.get(key) or {}
        courier_id = int(row.get("courier_id") or 0)
        dsp_id = int(row.get("dsp_id") or 0)
        current_rows.append({
            "source_name": "courier_hub_shift_booking_state",
            "work_date": row.get("work_date"),
            "warehouse_id": row.get("warehouse_id"),
            "warehouse_code": row.get("warehouse_code"),
            "dsp_id": dsp_id,
            "courier_id": courier_id,
            "jitt_internal_id": identity_lookup.get((courier_id, dsp_id)) or existing.get("jitt_internal_id"),
            "courier_name": row.get("courier_name"),
            "email": row.get("email"),
            "phone_number": row.get("phone_number"),
            "block_key": block_key,
            "shift_template_id": row.get("shift_template_id"),
            "shift_text": row.get("shift_text"),
            "slot_from": row.get("slot_from"),
            "slot_to": row.get("slot_to"),
            "status": row.get("status"),
            "movement_type": "SEEN" if key in existing_active else "BOOK",
            "active": True,
            "first_seen_at": existing.get("first_seen_at") or now,
            "last_seen_at": now,
            "deleted_at": None,
            "request_url": row.get("request_url"),
            "subscription_json": row.get("subscription_json") or {},
            "courier_json": row.get("courier_json") or {},
            "updated_at": now,
        })

    for key, existing in existing_active.items():
        if key in current_keys:
            continue
        current_rows.append({
            "source_name": "courier_hub_shift_booking_state",
            "work_date": existing.get("work_date"),
            "warehouse_id": existing.get("warehouse_id"),
            "warehouse_code": existing.get("warehouse_code"),
            "dsp_id": existing.get("dsp_id"),
            "courier_id": existing.get("courier_id"),
            "jitt_internal_id": existing.get("jitt_internal_id"),
            "courier_name": existing.get("courier_name"),
            "email": existing.get("email"),
            "phone_number": existing.get("phone_number"),
            "block_key": existing.get("block_key"),
            "shift_template_id": existing.get("shift_template_id"),
            "shift_text": existing.get("shift_text"),
            "slot_from": existing.get("slot_from"),
            "slot_to": existing.get("slot_to"),
            "status": existing.get("status"),
            "movement_type": "DELETE",
            "active": False,
            "first_seen_at": existing.get("first_seen_at") or now,
            "last_seen_at": now,
            "deleted_at": now,
            "request_url": existing.get("request_url"),
            "subscription_json": existing.get("subscription_json") or {},
            "courier_json": existing.get("courier_json") or {},
            "updated_at": now,
        })

    return current_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-ids", default="1,2")
    parser.add_argument("--dsp-id", type=int, default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"))
    parser.add_argument("--date", default=os.getenv("COURIER_HUB_SHIFT_BLOCK_DATE") or date.today().isoformat())
    parser.add_argument("--start-date", default=os.getenv("COURIER_HUB_SHIFT_BLOCK_START_DATE") or "")
    parser.add_argument("--end-date", default=os.getenv("COURIER_HUB_SHIFT_BLOCK_END_DATE") or "")
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=int(os.getenv("COURIER_HUB_SHIFT_BLOCK_LOOKAHEAD_DAYS") or "0"),
        help="Ennyi nappal nezzen elore a kezdodatumtol. 0 eseten csak a megadott end-date/date ervenyes.",
    )
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--page-size", type=int, default=int(os.getenv("COURIER_HUB_ROSTER_PAGE_SIZE") or "100"))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("COURIER_HUB_ROSTER_MAX_PAGES") or "50"))
    parser.add_argument("--skip-roster", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not courier_hub_auth_configured():
        print(
            "COURIER_HUB_SHIFT_BLOCK_SYNC_AUTH_MISSING "
            "Állítsd be a COURIER_HUB_COOKIE vagy COURIER_HUB_AUTHORIZATION "
            "változót, vagy futtasd a refresh_courier_hub_auth.py scriptet cache fájllal.",
            flush=True,
        )
        return 2

    start_date = date.fromisoformat(args.start_date or args.date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)
    elif args.lookahead_days > 0:
        end_date = start_date + timedelta(days=args.lookahead_days)
    else:
        end_date = date.fromisoformat(args.start_date or args.date)
    work_dates = date_range(start_date, end_date)
    warehouse_ids = parse_warehouse_ids(args.warehouse_ids)
    fetched_at = datetime.now(timezone.utc)
    block_rows: list[dict[str, Any]] = []
    subscriber_rows: list[dict[str, Any]] = []
    failures = 0

    for work_date in work_dates:
        for warehouse_id in warehouse_ids:
            shift_blocks_url = build_shift_blocks_url(
                args.base_url,
                warehouse_id,
                args.dsp_id,
                work_date,
            )
            status_code, payload = request_json(shift_blocks_url)
            items = payload_items(payload)
            if status_code >= 400:
                failures += 1
            for item in items:
                row = build_block_row(
                    warehouse_id=warehouse_id,
                    dsp_id=args.dsp_id,
                    work_date=work_date,
                    request_url=shift_blocks_url,
                    fetched_at=fetched_at,
                    item=item,
                )
                if row:
                    block_rows.append(row)
                subscriber_rows.extend(build_assignment_rows_from_block(
                    warehouse_id=warehouse_id,
                    dsp_id=args.dsp_id,
                    work_date=work_date,
                    request_url=shift_blocks_url,
                    block=item,
                ))

            print(
                f"COURIER_HUB_SHIFT_BLOCKS date={work_date.isoformat()} "
                f"warehouse={warehouse_id} status={status_code} rows={len(items)}",
                flush=True,
            )

            if args.skip_roster:
                continue

            for page in range(args.max_pages):
                roster_url = build_roster_url(
                    args.base_url,
                    warehouse_id,
                    args.dsp_id,
                    work_date,
                    page,
                    args.page_size,
                )
                roster_status, roster_payload = request_json(roster_url)
                roster_rows = roster_items(roster_payload)
                if roster_status >= 400:
                    failures += 1

                for index, roster_row in enumerate(roster_rows):
                    subscriber_rows.extend(build_subscriber_rows(
                        warehouse_id=warehouse_id,
                        dsp_id=args.dsp_id,
                        work_date=work_date,
                        source_page=page,
                        source_row_index=index,
                        request_url=roster_url,
                        fetched_at=fetched_at,
                        row=roster_row,
                    ))

                print(
                    f"COURIER_HUB_SHIFT_SUBSCRIBERS date={work_date.isoformat()} "
                    f"warehouse={warehouse_id} page={page} status={roster_status} "
                    f"rows={len(roster_rows)}",
                    flush=True,
                )

                if roster_status >= 400 or not has_next_page(roster_payload, len(roster_rows), page, args.page_size):
                    break

    if args.dry_run:
        print(
            f"DRY_RUN courier_hub_shift_blocks={len(block_rows)} "
            f"subscribers={len(subscriber_rows)} failures={failures}",
            flush=True,
        )
        return 1 if failures else 0

    if failures and not block_rows and not subscriber_rows:
        print(
            "COURIER_HUB_SHIFT_BLOCK_SYNC_NO_ROWS "
            f"failures={failures}. Valószínű auth hiba, például 401.",
            flush=True,
        )
        return 1

    blocks_written = supabase_upsert(
        SHIFT_BLOCK_TABLE,
        dedupe_rows(block_rows, ["work_date", "warehouse_id", "dsp_id", "block_key"]),
        "work_date,warehouse_id,dsp_id,block_key",
    )
    subscriber_rows = dedupe_rows(
        subscriber_rows,
        ["work_date", "warehouse_id", "dsp_id", "courier_id", "subscriber_key"],
    )
    subscribers_written = supabase_upsert(
        SUBSCRIBER_TABLE,
        normalize_rows(subscriber_rows, SUBSCRIBER_COLUMNS),
        "work_date,warehouse_id,dsp_id,courier_id,subscriber_key",
    )
    bookings_written = 0
    booking_rows: list[dict[str, Any]] = []
    try:
        existing_active = load_existing_active_bookings_for_range(
            start_date=start_date,
            end_date=end_date,
            warehouse_ids=warehouse_ids,
            dsp_id=args.dsp_id,
        )
        identity_lookup = load_identity_lookup(args.dsp_id)
        booking_rows = build_booking_state_rows(
            subscriber_rows=subscriber_rows,
            existing_active=existing_active,
            identity_lookup=identity_lookup,
            fetched_at=fetched_at,
        )
        booking_rows = dedupe_rows(
            booking_rows,
            ["work_date", "warehouse_id", "dsp_id", "courier_id", "block_key"],
        )
        bookings_written = supabase_upsert(
            BOOKING_TABLE,
            booking_rows,
            "work_date,warehouse_id,dsp_id,courier_id,block_key",
        )
    except RuntimeError as exc:
        if is_missing_table_error(exc):
            print(
                f"COURIER_HUB_SHIFT_BOOKING_SYNC_SKIPPED missing_table={BOOKING_TABLE}",
                flush=True,
            )
        else:
            raise

    print(
        f"COURIER_HUB_SHIFT_BLOCK_SYNC blocks={len(block_rows)} "
        f"blocks_written={blocks_written} subscribers={len(subscriber_rows)} "
        f"subscribers_written={subscribers_written} bookings={len(booking_rows)} "
        f"bookings_written={bookings_written} failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
