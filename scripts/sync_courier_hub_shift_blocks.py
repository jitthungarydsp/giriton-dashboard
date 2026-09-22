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
    fetched_at = datetime.now(timezone.utc)
    block_rows: list[dict[str, Any]] = []
    subscriber_rows: list[dict[str, Any]] = []
    failures = 0

    for work_date in work_dates:
        for warehouse_id in parse_warehouse_ids(args.warehouse_ids):
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
        block_rows,
        "work_date,warehouse_id,dsp_id,block_key",
    )
    subscribers_written = supabase_upsert(
        SUBSCRIBER_TABLE,
        subscriber_rows,
        "work_date,warehouse_id,dsp_id,courier_id,subscriber_key",
    )
    print(
        f"COURIER_HUB_SHIFT_BLOCK_SYNC blocks={len(block_rows)} "
        f"blocks_written={blocks_written} subscribers={len(subscriber_rows)} "
        f"subscribers_written={subscribers_written} failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
