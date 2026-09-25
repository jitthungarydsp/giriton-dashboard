#!/usr/bin/env python3
"""Courier Hub API autobooking by full courier-day matches.

One candidate is one courier on one work day. The script only books a candidate
when every MuszakPro shift for that courier-day has an exact or allowed
alternative open Courier Hub shift block at the same warehouse.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402
from scripts.courier_hub_api_book_shift import (  # noqa: E402
    build_assign_url,
    hub_request,
    log_result,
    normalize_time,
    normalize_warehouse_id,
    response_payload,
)
from scripts.sync_courier_financial_overview import raise_for_response  # noqa: E402
from scripts.sync_courier_hub_master import DEFAULT_BASE_URL, clean_text, int_or_none  # noqa: E402


WAREHOUSE_CODE_BY_ID = {
    1: "BUD1",
    2: "BUD2",
}


@dataclass
class MuszakProRow:
    work_date: str
    courier_id: int
    courier_name: str
    email: str
    warehouse: str
    shift_start: str
    shift_text: str
    serial: str
    timestamp_text: str
    source_row: int
    fetched_at: str


@dataclass
class CourierIdentity:
    courier_id: int
    email: str
    name_without_identifier: str
    name_json: str
    warehouse: str


@dataclass
class HubBlock:
    work_date: str
    warehouse_id: int
    warehouse: str
    block_key: str
    shift_template_id: int
    slot_from: str
    status: str
    assigned: int
    opened: int
    free_slots: int


def supabase_headers() -> tuple[str, dict[str, str]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return supabase_url, {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def supabase_get(table: str, params: dict[str, str] | list[tuple[str, str]], *, timeout: int = 60) -> list[dict[str, Any]]:
    supabase_url, headers = supabase_headers()
    response = requests.get(
        f"{supabase_url}/rest/v1/{table}",
        headers=headers,
        params=params,
        timeout=timeout,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def optional_supabase_get(table: str, params: dict[str, str] | list[tuple[str, str]]) -> list[dict[str, Any]]:
    try:
        return supabase_get(table, params)
    except requests.HTTPError as exc:
        text = str(exc).lower()
        if "could not find" in text or "column" in text or "pgrst" in text:
            return []
        raise


def normalize_db_time(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    match = re.search(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\b", text)
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}:00"


def time_minutes(value: Any) -> int | None:
    normalized = normalize_db_time(value)
    if not normalized:
        return None
    hour, minute, *_ = normalized.split(":")
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


def shift_start_from_text(value: Any) -> str:
    return normalize_db_time(value)


def normalize_lookup_text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value)).casefold()


def read_courier_identities(dsp_id: int, limit: int) -> tuple[dict[str, CourierIdentity], dict[str, CourierIdentity]]:
    rows = supabase_get(
        "courier_hub_courier_identity_raw",
        [
            ("select", "courier_id,dsp_id,warehouse_id,warehouse_code,email,name_without_identifier,name_json"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("limit", str(int(limit))),
        ],
    )
    by_email: dict[str, CourierIdentity] = {}
    by_name: dict[str, CourierIdentity] = {}
    for row in rows:
        courier_id = int_or_none(row.get("courier_id")) or 0
        warehouse_id = int_or_none(row.get("warehouse_id")) or 0
        warehouse = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, "")
        if not courier_id:
            continue
        identity = CourierIdentity(
            courier_id=int(courier_id),
            email=clean_text(row.get("email")).casefold(),
            name_without_identifier=clean_text(row.get("name_without_identifier")),
            name_json=clean_text(row.get("name_json")),
            warehouse=warehouse,
        )
        if identity.email:
            by_email.setdefault(identity.email, identity)
        for name_value in (identity.name_json, identity.name_without_identifier):
            key = normalize_lookup_text(name_value)
            if key:
                by_name.setdefault(key, identity)
    return by_email, by_name


def parse_timestamp(value: Any) -> datetime:
    text = clean_text(value)
    if not text:
        return datetime.max.replace(tzinfo=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    for candidate in [normalized, normalized[:19], normalized[:16]]:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y.%m.%d. %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.max.replace(tzinfo=timezone.utc)


def booking_order_key(rows: list[MuszakProRow]) -> tuple[datetime, int, str]:
    first = min(rows, key=lambda row: (parse_timestamp(row.timestamp_text), row.source_row or 999999))
    return (
        parse_timestamp(first.timestamp_text),
        first.source_row or 999999,
        f"{first.work_date}|{first.courier_id}|{first.email}",
    )


def read_muszakpro_rows(
    start_date: date,
    end_date: date,
    limit: int,
    identities_by_email: dict[str, CourierIdentity],
    identities_by_name: dict[str, CourierIdentity],
) -> list[MuszakProRow]:
    select_with_optional = (
        "work_date,email,shift_text,warehouse,booking_code,courier_id,courier_name,"
        "serial,timestamp_text,source_row,fetched_at,status,cancelled_at"
    )
    table_rows = []
    for table_name in ("raw_muszakpro_bookings", "foglalasok_raw"):
        rows = optional_supabase_get(
            table_name,
            [
                ("select", select_with_optional),
                ("work_date", f"gte.{start_date.isoformat()}"),
                ("work_date", f"lte.{end_date.isoformat()}"),
                ("order", "work_date.asc,timestamp_text.asc,source_row.asc"),
                ("limit", str(int(limit))),
            ],
        )
        if rows:
            table_rows = rows
            break
        rows = optional_supabase_get(
            table_name,
            [
                ("select", (
                    "work_date,email,shift_text,warehouse,booking_code,courier_id,courier_name,"
                    "serial,timestamp_text,source_row,fetched_at"
                )),
                ("work_date", f"gte.{start_date.isoformat()}"),
                ("work_date", f"lte.{end_date.isoformat()}"),
                ("order", "work_date.asc,timestamp_text.asc,source_row.asc"),
                ("limit", str(int(limit))),
            ],
        )
        if rows:
            table_rows = rows
            break

    result: list[MuszakProRow] = []
    for row in table_rows:
        status = clean_text(row.get("status")).casefold()
        if status in {"cancelled", "deleted", "torolve", "törölve"} or clean_text(row.get("cancelled_at")):
            continue
        shift_start = shift_start_from_text(row.get("shift_text"))
        email = clean_text(row.get("email")).casefold()
        courier_name = clean_text(row.get("courier_name"))
        identity = identities_by_email.get(email) if email else None
        if identity is None and courier_name:
            identity = identities_by_name.get(normalize_lookup_text(courier_name))
        courier_id = int_or_none(row.get("courier_id")) or (identity.courier_id if identity else 0)
        warehouse = clean_text(row.get("warehouse")).upper()
        if not warehouse and identity:
            warehouse = identity.warehouse
        work_date = clean_text(row.get("work_date"))[:10]
        if not work_date or not shift_start or not courier_id or warehouse not in {"BUD1", "BUD2"}:
            continue
        result.append(
            MuszakProRow(
                work_date=work_date,
                courier_id=int(courier_id),
                courier_name=courier_name or (identity.name_json if identity else ""),
                email=email or (identity.email if identity else ""),
                warehouse=warehouse,
                shift_start=shift_start,
                shift_text=clean_text(row.get("shift_text")),
                serial=clean_text(row.get("serial")),
                timestamp_text=clean_text(row.get("timestamp_text")),
                source_row=int_or_none(row.get("source_row")) or 0,
                fetched_at=clean_text(row.get("fetched_at")),
            )
        )
    return result


def read_hub_blocks(start_date: date, end_date: date, dsp_id: int, limit: int) -> dict[tuple[str, str, str], HubBlock]:
    rows = supabase_get(
        "courier_hub_shift_blocks_raw",
        [
            ("select", (
                "work_date,warehouse_id,warehouse_code,dsp_id,block_key,shift_template_id,"
                "slot_from,status,assigned,opened,free_slots"
            )),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("order", "work_date.asc,warehouse_id.asc,slot_from.asc"),
            ("limit", str(int(limit))),
        ],
    )
    blocks: dict[tuple[str, str, str], HubBlock] = {}
    for row in rows:
        work_date = clean_text(row.get("work_date"))[:10]
        warehouse_id = int_or_none(row.get("warehouse_id")) or 0
        warehouse = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, "")
        slot_from = normalize_db_time(row.get("slot_from"))
        shift_template_id = int_or_none(row.get("shift_template_id")) or 0
        if not work_date or warehouse not in {"BUD1", "BUD2"} or not slot_from or not shift_template_id:
            continue
        free_slots = int_or_none(row.get("free_slots"))
        assigned = int_or_none(row.get("assigned")) or 0
        opened = int_or_none(row.get("opened")) or 0
        if free_slots is None:
            free_slots = max(opened - assigned, 0)
        key = (work_date, warehouse, slot_from)
        block = HubBlock(
            work_date=work_date,
            warehouse_id=warehouse_id,
            warehouse=warehouse,
            block_key=clean_text(row.get("block_key")),
            shift_template_id=int(shift_template_id),
            slot_from=slot_from,
            status=clean_text(row.get("status")).upper(),
            assigned=int(assigned),
            opened=int(opened),
            free_slots=int(free_slots),
        )
        existing = blocks.get(key)
        if existing is None or block.free_slots > existing.free_slots:
            blocks[key] = block
    return blocks


def read_existing_subscriptions(start_date: date, end_date: date, dsp_id: int, limit: int) -> set[tuple[str, int, str, str]]:
    rows = optional_supabase_get(
        "courier_hub_shift_bookings_raw",
        [
            ("select", "work_date,dsp_id,courier_id,warehouse_code,warehouse_id,slot_from,shift_template_id,status,active"),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("active", "eq.true"),
            ("limit", str(int(limit))),
        ],
    )
    if not rows:
        rows = supabase_get(
            "courier_hub_roster_shift_subscribers_raw",
            [
                ("select", "work_date,dsp_id,courier_id,warehouse_code,warehouse_id,slot_from,shift_template_id,status"),
                ("work_date", f"gte.{start_date.isoformat()}"),
                ("work_date", f"lte.{end_date.isoformat()}"),
                ("dsp_id", f"eq.{int(dsp_id)}"),
                ("limit", str(int(limit))),
            ],
        )
    existing: set[tuple[str, int, str, str]] = set()
    for row in rows:
        work_date = clean_text(row.get("work_date"))[:10]
        courier_id = int_or_none(row.get("courier_id")) or 0
        warehouse_id = int_or_none(row.get("warehouse_id")) or 0
        warehouse = clean_text(row.get("warehouse_code")).upper() or WAREHOUSE_CODE_BY_ID.get(warehouse_id, "")
        slot_from = normalize_db_time(row.get("slot_from"))
        if work_date and courier_id and warehouse and slot_from:
            existing.add((work_date, int(courier_id), warehouse, slot_from))
    return existing


def unique_shift_rows(rows: list[MuszakProRow]) -> list[MuszakProRow]:
    by_key: dict[tuple[str, str], MuszakProRow] = {}
    for row in sorted(rows, key=lambda item: (parse_timestamp(item.timestamp_text), item.source_row or 999999)):
        key = (row.warehouse, row.shift_start)
        by_key.setdefault(key, row)
    return list(by_key.values())


def build_groups(rows: list[MuszakProRow]) -> list[tuple[tuple[str, int], list[MuszakProRow]]]:
    grouped: dict[tuple[str, int], list[MuszakProRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.work_date, row.courier_id)].append(row)
    return sorted(grouped.items(), key=lambda item: booking_order_key(item[1]))


def group_is_exact_full_day(
    rows: list[MuszakProRow],
    blocks: dict[tuple[str, str, str], HubBlock],
    existing_subscriptions: set[tuple[str, int, str, str]],
    planned_by_block: dict[str, int],
    tolerance_minutes: int,
) -> tuple[bool, str, list[tuple[MuszakProRow, HubBlock, bool, str, int]]]:
    shift_rows = unique_shift_rows(rows)
    if len(shift_rows) < 2:
        return False, "single_shift_day", []

    all_blocks = sorted(
        blocks.values(),
        key=lambda block: (
            block.work_date,
            block.warehouse,
            time_minutes(block.slot_from) or 0,
            block.block_key,
        ),
    )
    matches: list[tuple[MuszakProRow, HubBlock, bool, str, int]] = []
    used_block_keys: set[str] = set()

    for row in shift_rows:
        candidates: list[tuple[int, int, HubBlock, str, int]] = []
        exact_block = blocks.get((row.work_date, row.warehouse, row.shift_start))
        if exact_block:
            candidates.append((0, time_minutes(exact_block.slot_from) or 0, exact_block, "exact", 0))

        for candidate in all_blocks:
            if candidate.work_date != row.work_date or candidate.warehouse != row.warehouse:
                continue
            if exact_block and candidate.block_key == exact_block.block_key:
                continue
            current_diff = diff_minutes(row.shift_start, candidate.slot_from)
            if current_diff is None or abs(current_diff) > max(int(tolerance_minutes), 0):
                continue
            candidates.append((
                abs(current_diff),
                time_minutes(candidate.slot_from) or 0,
                candidate,
                "alternative",
                current_diff,
            ))

        selected: tuple[HubBlock, bool, str, int] | None = None
        rejected_reasons: list[str] = []
        for _score, _minutes, block, match_kind, match_diff in sorted(
            candidates,
            key=lambda item: (item[0], item[1], 0 if item[3] == "exact" else 1, item[2].block_key),
        ):
            if block.block_key in used_block_keys:
                rejected_reasons.append(f"duplicate_block_match {block.block_key}")
                continue

            already_booked = (row.work_date, row.courier_id, row.warehouse, block.slot_from) in existing_subscriptions
            if not already_booked:
                if block.status and block.status != "OPEN":
                    rejected_reasons.append(f"hub_block_not_open {block.block_key} status={block.status}")
                    continue
                remaining = block.free_slots - planned_by_block.get(block.block_key, 0)
                if remaining <= 0:
                    rejected_reasons.append(f"no_free_slot {block.block_key}")
                    continue

            selected = (block, already_booked, match_kind, match_diff)
            break

        if selected is None:
            reason = rejected_reasons[0] if rejected_reasons else f"missing_hub_block {row.warehouse} {row.shift_start}"
            return False, reason, []

        block, already_booked, match_kind, match_diff = selected
        used_block_keys.add(block.block_key)
        matches.append((row, block, already_booked, match_kind, match_diff))

    reason = "exact_full_day" if all(match[3] == "exact" for match in matches) else "alternative_full_day"
    return True, reason, matches


def args_for_log(row: MuszakProRow, block: HubBlock, base_url: str, dsp_id: int) -> argparse.Namespace:
    return argparse.Namespace(
        date=row.work_date,
        warehouse=row.warehouse,
        dsp_id=int(dsp_id),
        shift_template_id=int(block.shift_template_id),
        slot_from=block.slot_from,
        shift_start=block.slot_from,
        courier_id=int(row.courier_id),
        courier_name=row.courier_name,
        email=row.email,
        serial=row.serial,
        base_url=base_url,
    )


def book_one(
    row: MuszakProRow,
    block: HubBlock,
    *,
    base_url: str,
    dsp_id: int,
    dry_run: bool,
    match_kind: str,
    match_diff: int,
) -> bool:
    log_args = args_for_log(row, block, base_url, dsp_id)
    if dry_run:
        log_result(log_args, "HUB_AUTOBOOK_DRY_RUN_OK", f"HUB_JOB_AUTOBOOKING dry-run {match_kind} full-day match.", {
            "blockKey": block.block_key,
            "shiftTemplateId": block.shift_template_id,
            "slotFrom": block.slot_from,
            "muszakproShiftStart": row.shift_start,
            "matchKind": match_kind,
            "matchDiffMinutes": match_diff,
        })
        print(
            "HUB_JOB_AUTOBOOKING_DRY_RUN_BOOK "
            f"date={row.work_date} courier={row.courier_id} warehouse={row.warehouse} "
            f"muszakpro_slot={row.shift_start} hub_slot={block.slot_from} "
            f"template={block.shift_template_id} match={match_kind} diff={match_diff}",
            flush=True,
        )
        return True

    url = build_assign_url(base_url, normalize_warehouse_id(row.warehouse), int(dsp_id))
    request_body = {
        "date": row.work_date,
        "shiftTemplateId": int(block.shift_template_id),
        "slotFrom": block.slot_from,
        "courierIds": [int(row.courier_id)],
    }
    response = hub_request("POST", url, json=request_body)
    payload = response_payload(response)
    if response.ok:
        log_result(log_args, "COURIER_ADDED", "HUB_JOB_AUTOBOOKING API booking accepted.", payload)
        print(
            "HUB_JOB_AUTOBOOKING_BOOKED "
            f"status={response.status_code} date={row.work_date} courier={row.courier_id} "
            f"warehouse={row.warehouse} muszakpro_slot={row.shift_start} hub_slot={block.slot_from} "
            f"template={block.shift_template_id} match={match_kind} diff={match_diff}",
            flush=True,
        )
        return True

    log_result(log_args, "HUB_AUTOBOOK_ERROR", f"HTTP {response.status_code}", payload)
    raise_for_response(response, "HUB_JOB_AUTOBOOKING assign")
    return False


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="HUB_JOB_AUTOBOOKING full-day Courier Hub booking.")
    parser.add_argument("--start-date", default=today.isoformat())
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dsp-id", type=int, default=8)
    parser.add_argument("--max-courier-days", type=int, default=20)
    parser.add_argument("--source-limit", type=int, default=50000)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=max(int(args.days), 1) - 1)
    dry_run = bool(args.dry_run or not args.live)

    identities_by_email, identities_by_name = read_courier_identities(args.dsp_id, args.source_limit)
    muszakpro_rows = read_muszakpro_rows(
        start_date,
        end_date,
        args.source_limit,
        identities_by_email,
        identities_by_name,
    )
    blocks = read_hub_blocks(start_date, end_date, args.dsp_id, args.source_limit)
    existing_subscriptions = read_existing_subscriptions(start_date, end_date, args.dsp_id, args.source_limit)

    groups = build_groups(muszakpro_rows)
    planned_by_block: dict[str, int] = defaultdict(int)
    selected_groups = 0
    booked_rows = 0
    skipped_groups = 0

    print(
        "HUB_JOB_AUTOBOOKING_START "
        f"start={start_date.isoformat()} end={end_date.isoformat()} dry_run={dry_run} "
        f"identities={len(identities_by_email)} muszakpro_rows={len(muszakpro_rows)} "
        f"hub_blocks={len(blocks)} existing_subscriptions={len(existing_subscriptions)}",
        flush=True,
    )

    for (_work_date, _courier_id), rows in groups:
        if selected_groups >= max(int(args.max_courier_days), 1):
            break
        ok, reason, matches = group_is_exact_full_day(
            rows,
            blocks,
            existing_subscriptions,
            planned_by_block,
            args.tolerance_minutes,
        )
        first = min(rows, key=lambda row: (parse_timestamp(row.timestamp_text), row.source_row or 999999))
        if not ok:
            skipped_groups += 1
            print(
                "HUB_JOB_AUTOBOOKING_SKIP "
                f"date={first.work_date} courier={first.courier_id} name={first.courier_name or '-'} "
                f"reason={reason}",
                flush=True,
            )
            continue

        to_book = [
            (row, block, match_kind, match_diff)
            for row, block, already_booked, match_kind, match_diff in matches
            if not already_booked
        ]
        if not to_book:
            skipped_groups += 1
            print(
                "HUB_JOB_AUTOBOOKING_SKIP "
                f"date={first.work_date} courier={first.courier_id} name={first.courier_name or '-'} "
                "reason=already_fully_booked",
                flush=True,
            )
            continue

        selected_groups += 1
        print(
            "HUB_JOB_AUTOBOOKING_SELECT "
            f"date={first.work_date} courier={first.courier_id} name={first.courier_name or '-'} "
            f"shifts={len(matches)} to_book={len(to_book)} reason={reason} "
            f"first_timestamp={first.timestamp_text or '-'}",
            flush=True,
        )
        for row, block, match_kind, match_diff in to_book:
            if book_one(
                row,
                block,
                base_url=args.base_url,
                dsp_id=args.dsp_id,
                dry_run=dry_run,
                match_kind=match_kind,
                match_diff=match_diff,
            ):
                planned_by_block[block.block_key] += 1
                booked_rows += 1

    print(
        "HUB_JOB_AUTOBOOKING_DONE "
        f"selected_groups={selected_groups} booked_rows={booked_rows} skipped_groups={skipped_groups} dry_run={dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
