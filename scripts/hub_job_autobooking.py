#!/usr/bin/env python3
"""Courier Hub API autobooking by full courier-day matches.

One candidate is one courier on one work day. The script only books a candidate
when every MuszakPro shift for that courier-day has an exact or allowed
alternative open Courier Hub shift block at the same warehouse.
"""

from __future__ import annotations

import argparse
import json
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


def supabase_headers(schema: str = "public") -> tuple[str, dict[str, str]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    if schema and schema != "public":
        headers["Accept-Profile"] = schema
        headers["Content-Profile"] = schema
    return supabase_url, headers


def supabase_get(
    table: str,
    params: dict[str, str] | list[tuple[str, str]],
    *,
    schema: str = "public",
    timeout: int = 60,
) -> list[dict[str, Any]]:
    supabase_url, headers = supabase_headers(schema=schema)
    response = requests.get(
        f"{supabase_url}/rest/v1/{table}",
        headers=headers,
        params=params,
        timeout=timeout,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def optional_supabase_get(
    table: str,
    params: dict[str, str] | list[tuple[str, str]],
    *,
    schema: str = "public",
) -> list[dict[str, Any]]:
    try:
        return supabase_get(table, params, schema=schema)
    except requests.HTTPError as exc:
        text = str(exc).lower()
        if "could not find" in text or "column" in text or "pgrst" in text:
            return []
        raise


def normalize_db_time(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::\d{2})?(?!\d)", text)
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


def normalize_muszakpro_warehouse(value: Any) -> str:
    text = clean_text(value).upper()
    if not text:
        return ""
    if "BUD1" in text:
        return "BUD1"
    if "BUD2" in text:
        return "BUD2"
    if text in {"1", "1.0"}:
        return "BUD1"
    if text in {"2", "2.0"}:
        return "BUD2"
    return text


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
    table_rows_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    source_counts: list[str] = []
    for schema, table_name in (
        ("muszakpro", "bookings"),
        ("public", "raw_muszakpro_bookings"),
        ("public", "foglalasok_raw"),
    ):
        rows = optional_supabase_get(
            table_name,
            [
                ("select", select_with_optional),
                ("work_date", f"gte.{start_date.isoformat()}"),
                ("work_date", f"lte.{end_date.isoformat()}"),
                ("order", "work_date.asc,timestamp_text.asc,source_row.asc"),
                ("limit", str(int(limit))),
            ],
            schema=schema,
        )
        if not rows:
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
                schema=schema,
            )
        source_counts.append(f"{schema}.{table_name}:{len(rows)}")
        for row in rows:
            key = (
                clean_text(row.get("work_date"))[:10],
                clean_text(row.get("email")).casefold(),
                clean_text(row.get("shift_text")),
                clean_text(row.get("warehouse")).upper(),
                clean_text(row.get("booking_code")),
            )
            if key[0] and key[2]:
                table_rows_by_key.setdefault(key, row)

    table_rows = list(table_rows_by_key.values())

    print(
        "HUB_JOB_AUTOBOOKING_MUSZAKPRO_SOURCE "
        f"sources={','.join(source_counts)} merged_rows={len(table_rows)} "
        f"start={start_date.isoformat()} end={end_date.isoformat()}",
        flush=True,
    )

    result: list[MuszakProRow] = []
    rejected_counts: dict[str, int] = defaultdict(int)
    rejected_samples: dict[str, str] = {}
    for row in table_rows:
        status = clean_text(row.get("status")).casefold()
        if status in {"cancelled", "deleted", "torolve", "törölve"} or clean_text(row.get("cancelled_at")):
            rejected_counts["inactive_status"] += 1
            rejected_samples.setdefault("inactive_status", json.dumps(row, ensure_ascii=False)[:300])
            continue
        shift_start = shift_start_from_text(row.get("shift_text"))
        email = clean_text(row.get("email")).casefold()
        courier_name = clean_text(row.get("courier_name"))
        identity = identities_by_email.get(email) if email else None
        if identity is None and courier_name:
            identity = identities_by_name.get(normalize_lookup_text(courier_name))
        courier_id = int_or_none(row.get("courier_id")) or (identity.courier_id if identity else 0)
        warehouse = normalize_muszakpro_warehouse(row.get("warehouse"))
        if not warehouse and identity:
            warehouse = identity.warehouse
        work_date = clean_text(row.get("work_date"))[:10]
        if not work_date:
            rejected_counts["missing_work_date"] += 1
            rejected_samples.setdefault("missing_work_date", json.dumps(row, ensure_ascii=False)[:300])
            continue
        if not shift_start:
            rejected_counts["missing_shift_start"] += 1
            rejected_samples.setdefault("missing_shift_start", json.dumps(row, ensure_ascii=False)[:300])
            continue
        if not courier_id:
            rejected_counts["missing_courier_id"] += 1
            rejected_samples.setdefault("missing_courier_id", json.dumps(row, ensure_ascii=False)[:300])
            continue
        if warehouse not in {"BUD1", "BUD2"}:
            rejected_counts["invalid_warehouse"] += 1
            rejected_samples.setdefault("invalid_warehouse", json.dumps(row, ensure_ascii=False)[:300])
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
    print(
        "HUB_JOB_AUTOBOOKING_MUSZAKPRO_FILTER "
        f"accepted={len(result)} rejected={sum(rejected_counts.values())} "
        f"reasons={','.join(f'{key}:{value}' for key, value in sorted(rejected_counts.items())) or '-'}",
        flush=True,
    )
    for reason, sample in sorted(rejected_samples.items()):
        print(
            "HUB_JOB_AUTOBOOKING_MUSZAKPRO_FILTER_SAMPLE "
            f"reason={reason} row={sample}",
            flush=True,
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
    min_gap_minutes: int,
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
            return False, reason, matches

        block, already_booked, match_kind, match_diff = selected
        used_block_keys.add(block.block_key)
        matches.append((row, block, already_booked, match_kind, match_diff))

    gap_ok, gap_reason = selected_shift_gap_ok(matches, min_gap_minutes)
    if not gap_ok:
        return False, gap_reason, matches

    reason = "exact_full_day" if all(match[3] == "exact" for match in matches) else "alternative_full_day"
    return True, reason, matches


def selected_shift_gap_ok(
    matches: list[tuple[MuszakProRow, HubBlock, bool, str, int]],
    min_gap_minutes: int,
) -> tuple[bool, str]:
    required = max(int(min_gap_minutes), 0)
    if required <= 0 or len(matches) < 2:
        return True, ""
    slots: list[tuple[int, str]] = []
    for _row, block, _already_booked, _match_kind, _match_diff in matches:
        minutes = time_minutes(block.slot_from)
        if minutes is None:
            return False, f"invalid_hub_slot {block.slot_from or '-'}"
        slots.append((minutes, block.slot_from))
    slots.sort()
    for previous, current in zip(slots, slots[1:]):
        gap = current[0] - previous[0]
        if gap < required:
            return False, (
                f"min_gap_not_met {previous[1]}->{current[1]} "
                f"gap={gap} required={required}"
            )
    return True, ""


def failure_records_for_group(
    rows: list[MuszakProRow],
    reason: str,
    matches: list[tuple[MuszakProRow, HubBlock, bool, str, int]],
) -> list[dict[str, Any]]:
    run_at = datetime.now(timezone.utc).isoformat()
    match_by_key = {
        (row.warehouse, row.shift_start): (block, match_kind, match_diff)
        for row, block, _already_booked, match_kind, match_diff in matches
    }
    records: list[dict[str, Any]] = []
    for row in unique_shift_rows(rows):
        block, match_kind, match_diff = match_by_key.get((row.warehouse, row.shift_start), (None, "", ""))
        records.append({
            "run_at": run_at,
            "work_date": row.work_date,
            "courier_id": row.courier_id,
            "courier_name": row.courier_name,
            "email": row.email,
            "warehouse": row.warehouse,
            "muszakpro_shift_start": row.shift_start,
            "hub_slot_from": block.slot_from if block else "",
            "shift_template_id": block.shift_template_id if block else "",
            "block_key": block.block_key if block else "",
            "match_kind": match_kind,
            "match_diff_minutes": match_diff,
            "reason": reason,
            "timestamp_text": row.timestamp_text,
            "source_row": row.source_row,
            "serial": row.serial,
        })
    return records


def write_failure_output(records: list[dict[str, Any]], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    match_log_payload = {
        "blockKey": block.block_key,
        "shiftTemplateId": block.shift_template_id,
        "slotFrom": block.slot_from,
        "hubSlotFrom": block.slot_from,
        "muszakproShiftStart": row.shift_start,
        "matchKind": match_kind,
        "matchDiffMinutes": match_diff,
    }
    if dry_run:
        log_result(
            log_args,
            "HUB_AUTOBOOK_DRY_RUN_OK",
            f"HUB_JOB_AUTOBOOKING dry-run {match_kind} full-day match.",
            match_log_payload,
        )
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
    log_payload = dict(match_log_payload)
    log_payload["hubResponse"] = payload
    if response.ok:
        log_result(log_args, "COURIER_ADDED", "HUB_JOB_AUTOBOOKING API booking accepted.", log_payload)
        print(
            "HUB_JOB_AUTOBOOKING_BOOKED "
            f"status={response.status_code} date={row.work_date} courier={row.courier_id} "
            f"warehouse={row.warehouse} muszakpro_slot={row.shift_start} hub_slot={block.slot_from} "
            f"template={block.shift_template_id} match={match_kind} diff={match_diff}",
            flush=True,
        )
        return True

    log_result(log_args, "HUB_AUTOBOOK_ERROR", f"HTTP {response.status_code}", log_payload)
    raise_for_response(response, "HUB_JOB_AUTOBOOKING assign")
    return False


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="HUB_JOB_AUTOBOOKING full-day Courier Hub booking.")
    parser.add_argument("--start-date", default=today.isoformat())
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--dsp-id", type=int, default=8)
    parser.add_argument("--max-courier-days", type=int, default=20)
    parser.add_argument("--source-limit", type=int, default=50000)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--min-gap-minutes", type=int, default=270)
    parser.add_argument(
        "--courier-ids",
        default="",
        help="Optional comma separated courier_id allowlist for targeted courier-day booking.",
    )
    parser.add_argument(
        "--failure-output",
        default="results/hub-job-autobooking/failures.json",
        help="JSON output for courier-days that were not bookable.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=max(int(args.days), 1) - 1)
    dry_run = bool(args.dry_run or not args.live)
    target_courier_ids = {
        int(parsed)
        for value in re.split(r"[\s,;]+", clean_text(args.courier_ids))
        if (parsed := int_or_none(value))
    }

    identities_by_email, identities_by_name = read_courier_identities(args.dsp_id, args.source_limit)
    muszakpro_rows = read_muszakpro_rows(
        start_date,
        end_date,
        args.source_limit,
        identities_by_email,
        identities_by_name,
    )
    if target_courier_ids:
        muszakpro_rows = [
            row for row in muszakpro_rows
            if int(row.courier_id) in target_courier_ids
        ]
    blocks = read_hub_blocks(start_date, end_date, args.dsp_id, args.source_limit)
    existing_subscriptions = read_existing_subscriptions(start_date, end_date, args.dsp_id, args.source_limit)

    groups = build_groups(muszakpro_rows)
    planned_by_block: dict[str, int] = defaultdict(int)
    selected_groups = 0
    booked_rows = 0
    skipped_groups = 0
    failed_booking_rows = 0
    failure_records: list[dict[str, Any]] = []

    print(
        "HUB_JOB_AUTOBOOKING_START "
        f"start={start_date.isoformat()} end={end_date.isoformat()} dry_run={dry_run} "
        f"target_couriers={','.join(str(value) for value in sorted(target_courier_ids)) or '-'} "
        f"identities={len(identities_by_email)} muszakpro_rows={len(muszakpro_rows)} "
        f"hub_blocks={len(blocks)} existing_subscriptions={len(existing_subscriptions)}",
        flush=True,
    )

    max_courier_days = max(int(args.max_courier_days), 1)
    for (_work_date, _courier_id), rows in groups:
        ok, reason, matches = group_is_exact_full_day(
            rows,
            blocks,
            existing_subscriptions,
            planned_by_block,
            args.tolerance_minutes,
            args.min_gap_minutes,
        )
        first = min(rows, key=lambda row: (parse_timestamp(row.timestamp_text), row.source_row or 999999))
        if not ok:
            skipped_groups += 1
            failure_records.extend(failure_records_for_group(rows, reason, matches))
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

        if selected_groups >= max_courier_days:
            skipped_groups += 1
            limit_reason = f"max_courier_days_reached limit={max_courier_days}"
            failure_records.extend(failure_records_for_group(rows, limit_reason, matches))
            print(
                "HUB_JOB_AUTOBOOKING_SKIP "
                f"date={first.work_date} courier={first.courier_id} name={first.courier_name or '-'} "
                f"reason={limit_reason}",
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
            try:
                booked = book_one(
                    row,
                    block,
                    base_url=args.base_url,
                    dsp_id=args.dsp_id,
                    dry_run=dry_run,
                    match_kind=match_kind,
                    match_diff=match_diff,
                )
            except Exception as exc:
                failed_booking_rows += 1
                reason_text = f"api_booking_failed {type(exc).__name__}: {str(exc)[:500]}"
                failure_records.extend(
                    failure_records_for_group(
                        [row],
                        reason_text,
                        [(row, block, False, match_kind, match_diff)],
                    )
                )
                print(
                    "HUB_JOB_AUTOBOOKING_BOOK_FAILED "
                    f"date={row.work_date} courier={row.courier_id} warehouse={row.warehouse} "
                    f"muszakpro_slot={row.shift_start} hub_slot={block.slot_from} "
                    f"template={block.shift_template_id} match={match_kind} diff={match_diff} "
                    f"reason={reason_text}",
                    flush=True,
                )
                continue

            if booked:
                planned_by_block[block.block_key] += 1
                booked_rows += 1
            else:
                failed_booking_rows += 1
                failure_records.extend(
                    failure_records_for_group(
                        [row],
                        "api_booking_returned_false",
                        [(row, block, False, match_kind, match_diff)],
                    )
                )

    write_failure_output(failure_records, args.failure_output)
    print(
        "HUB_JOB_AUTOBOOKING_DONE "
        f"selected_groups={selected_groups} booked_rows={booked_rows} failed_booking_rows={failed_booking_rows} "
        f"skipped_groups={skipped_groups} "
        f"failure_records={len(failure_records)} failure_output={args.failure_output} dry_run={dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
