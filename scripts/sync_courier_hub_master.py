#!/usr/bin/env python3
"""Courier Hub roster -> public.courier_hub_master sync."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
    supabase_headers,
)


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service"
WAREHOUSE_CODES = {1: "BUD1", 2: "BUD2"}
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
IDENTITY_TABLE = "courier_hub_courier_identity_raw"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def text_or_none(value: Any) -> str | None:
    text = clean_text(value)
    return text or None


def int_or_none(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in {"true", "1", "yes", "y", "active", "enabled"}:
        return True
    if text in {"false", "0", "no", "n", "inactive", "disabled"}:
        return False
    return None


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and clean_text(row.get(key)):
            return row.get(key)
    return None


def parse_warehouse_ids(value: str) -> list[int]:
    ids: list[int] = []
    for part in value.split(","):
        text = part.strip()
        if text:
            ids.append(int(text))
    return ids or [1, 2]


def date_range(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("--end-date nem lehet korábbi, mint --start-date.")

    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def build_roster_url(
    base_url: str,
    warehouse_id: int,
    dsp_id: int,
    roster_date: date,
    page: int,
    page_size: int,
) -> str:
    query = urlencode({
        "date": roster_date.isoformat(),
        "page": int(page),
        "pageSize": int(page_size),
        "sort": "name,asc",
    })
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{int(dsp_id)}/roster?{query}"
    )


def courier_hub_get_with_retries(url: str, *, attempts: int = 4, timeout: int = 60) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=courier_hub_headers(), timeout=timeout)
            if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
                response = requests.get(url, headers=courier_hub_headers(), timeout=timeout)
            if response.status_code in RETRY_STATUS_CODES and attempt < attempts:
                time.sleep(min(2 ** attempt, 10))
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2 ** attempt, 10))
    if last_error:
        raise last_error
    raise RuntimeError("Courier Hub roster request failed without response.")


def request_json(url: str) -> tuple[int, Any]:
    response = courier_hub_get_with_retries(url)
    status_code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {"text": response.text[:2000]}
    return status_code, payload


def roster_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("content", "items", "data", "couriers", "roster"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def has_next_page(payload: Any, item_count: int, page: int, page_size: int) -> bool:
    if not isinstance(payload, dict):
        return item_count >= page_size

    if isinstance(payload.get("last"), bool):
        return not payload["last"]
    if isinstance(payload.get("hasNext"), bool):
        return payload["hasNext"]
    if isinstance(payload.get("has_next"), bool):
        return payload["has_next"]

    total_pages = int_or_none(payload.get("totalPages") or payload.get("total_pages"))
    if total_pages is not None:
        return page + 1 < total_pages

    total_elements = int_or_none(payload.get("totalElements") or payload.get("total") or payload.get("total_count"))
    if total_elements is not None:
        return (page + 1) * page_size < total_elements

    return item_count >= page_size


def courier_id_from_row(row: dict[str, Any]) -> int | None:
    return int_or_none(first_value(
        row,
        "courierId",
        "courier_id",
        "id",
        "userId",
        "user_id",
        "externalId",
        "external_id",
    ))


def parse_registered_since_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None

    match = re.search(r"(\d{4})[-.\/](\d{1,2})[-.\/](\d{1,2})", text)
    if not match:
        return None

    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def jitt_internal_id(courier_id: int, registered_since: Any, giriton_person_id: Any = "") -> str:
    registered_date = parse_registered_since_date(registered_since)
    registered_part = registered_date.replace("-", "") if registered_date else "00000000"
    seed = f"{int(courier_id)}|{clean_text(giriton_person_id)}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    numeric_tail = str(int(digest[:12], 16) % 100000000).zfill(8)
    return f"{registered_part}{numeric_tail}"


def name_without_identifier(name: Any, courier_id: int | None, giriton_person_id: Any = "") -> str | None:
    text = clean_text(name)
    if not text:
        return None

    tokens_to_remove = []
    if courier_id is not None:
        tokens_to_remove.append(str(courier_id))

    giriton_text = clean_text(giriton_person_id)
    if giriton_text:
        tokens_to_remove.append(giriton_text)
        tokens_to_remove.append(re.sub(r"\D+", "", giriton_text))

    cleaned = text
    for token in tokens_to_remove:
        if token:
            cleaned = re.sub(rf"\b{re.escape(token)}\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\b\d{4,6}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—_")
    return cleaned or text


def build_master_row(
    *,
    warehouse_id: int,
    dsp_id: int,
    roster_date: date,
    source_page: int,
    source_row_index: int,
    request_url: str,
    fetched_at: datetime,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    courier_id = courier_id_from_row(row)
    if courier_id is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    fetched_at_text = fetched_at.isoformat()
    vehicle = row.get("vehicle") if isinstance(row.get("vehicle"), dict) else {}
    return {
        "courier_id": courier_id,
        "warehouse_id": int(warehouse_id),
        "warehouse_code": WAREHOUSE_CODES.get(int(warehouse_id), f"WH{warehouse_id}"),
        "dsp_id": int(dsp_id),
        "courier_name": text_or_none(first_value(row, "name", "courierName", "courier_name", "fullName", "full_name")),
        "giriton_person_id": text_or_none(first_value(row, "giritonPersonId", "giriton_person_id")),
        "user_number": text_or_none(first_value(row, "userNumber", "user_number", "employeeNumber", "employee_number")),
        "email": text_or_none(first_value(row, "email", "emailAddress", "email_address")),
        "phone_number": text_or_none(first_value(row, "phone", "phoneNumber", "phone_number", "mobile", "mobilePhone")),
        "rfid": text_or_none(first_value(row, "rfid", "rfidNumber", "rfid_number")),
        "status": text_or_none(first_value(row, "status", "state", "activityStatus", "activity_status")),
        "active": bool_or_none(first_value(row, "active", "enabled", "isActive")),
        "vehicle_id": int_or_none(vehicle.get("id")),
        "vehicle_registration_number": text_or_none(vehicle.get("registrationNumber")),
        "vehicle_type": text_or_none(vehicle.get("type")),
        "registered_since": text_or_none(first_value(row, "registeredSince", "registered_since")),
        "assignment_load": int_or_none(first_value(row, "assignmentLoad", "assignment_load")),
        "roster_date": roster_date.isoformat(),
        "source_page": source_page,
        "source_row_index": source_row_index,
        "request_url": request_url,
        "response_json": row,
        "last_seen_at": fetched_at_text,
        "fetched_at": fetched_at_text,
        "updated_at": now,
    }


def build_identity_row(
    *,
    warehouse_id: int,
    dsp_id: int,
    source_page: int,
    source_row_index: int,
    request_url: str,
    fetched_at: datetime,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    courier_id = courier_id_from_row(row)
    if courier_id is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    fetched_at_text = fetched_at.isoformat()
    name = text_or_none(first_value(row, "name", "courierName", "courier_name", "fullName", "full_name"))
    giriton_person_id = text_or_none(first_value(row, "giritonPersonId", "giriton_person_id"))
    registered_since = text_or_none(first_value(row, "registeredSince", "registered_since"))
    registered_since_date = parse_registered_since_date(registered_since)
    return {
        "source_name": "courier_hub_roster_identity",
        "courier_id": courier_id,
        "dsp_id": int(dsp_id),
        "warehouse_id": int(warehouse_id),
        "warehouse_code": WAREHOUSE_CODES.get(int(warehouse_id), f"WH{warehouse_id}"),
        "jitt_internal_id": jitt_internal_id(courier_id, registered_since, giriton_person_id),
        "name_without_identifier": name_without_identifier(name, courier_id, giriton_person_id),
        "name_json": name,
        "phone_number": text_or_none(first_value(row, "phone", "phoneNumber", "phone_number", "mobile", "mobilePhone")),
        "email": text_or_none(first_value(row, "email", "emailAddress", "email_address")),
        "giriton_person_id": giriton_person_id,
        "registered_since": registered_since,
        "registered_since_date": registered_since_date,
        "source_page": source_page,
        "source_row_index": source_row_index,
        "request_url": request_url,
        "response_json": row,
        "last_seen_at": fetched_at_text,
        "fetched_at": fetched_at_text,
        "updated_at": now,
    }


def is_missing_table_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def supabase_upsert(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{supabase_url}/rest/v1/courier_hub_master",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "courier_id,warehouse_id,dsp_id,roster_date"},
        json=rows,
        timeout=60,
    )
    raise_for_response(response, "courier_hub_master upsert")
    return len(rows)


def supabase_upsert_identities(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{supabase_url}/rest/v1/{IDENTITY_TABLE}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "courier_id,dsp_id"},
        json=rows,
        timeout=60,
    )
    raise_for_response(response, f"{IDENTITY_TABLE} upsert")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-ids", default="1,2")
    parser.add_argument("--dsp-id", type=int, default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"))
    parser.add_argument("--date", default=os.getenv("COURIER_HUB_ROSTER_DATE") or date.today().isoformat())
    parser.add_argument("--start-date", default=os.getenv("COURIER_HUB_ROSTER_START_DATE") or "")
    parser.add_argument("--end-date", default=os.getenv("COURIER_HUB_ROSTER_END_DATE") or "")
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--page-size", type=int, default=int(os.getenv("COURIER_HUB_ROSTER_PAGE_SIZE") or "25"))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("COURIER_HUB_ROSTER_MAX_PAGES") or "50"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date or args.date)
    end_date = date.fromisoformat(args.end_date or args.start_date or args.date)
    roster_dates = date_range(start_date, end_date)
    fetched_at = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    identity_rows: list[dict[str, Any]] = []
    failures = 0

    for roster_date in roster_dates:
        for warehouse_id in parse_warehouse_ids(args.warehouse_ids):
            for page in range(args.max_pages):
                request_url = build_roster_url(
                    args.base_url,
                    warehouse_id,
                    args.dsp_id,
                    roster_date,
                    page,
                    args.page_size,
                )
                status_code, payload = request_json(request_url)
                items = roster_items(payload)
                if status_code >= 400:
                    failures += 1

                for index, item in enumerate(items):
                    master_row = build_master_row(
                        warehouse_id=warehouse_id,
                        dsp_id=args.dsp_id,
                        roster_date=roster_date,
                        source_page=page,
                        source_row_index=index,
                        request_url=request_url,
                        fetched_at=fetched_at,
                        row=item,
                    )
                    if master_row:
                        rows.append(master_row)
                    identity_row = build_identity_row(
                        warehouse_id=warehouse_id,
                        dsp_id=args.dsp_id,
                        source_page=page,
                        source_row_index=index,
                        request_url=request_url,
                        fetched_at=fetched_at,
                        row=item,
                    )
                    if identity_row:
                        identity_rows.append(identity_row)

                print(
                    f"COURIER_HUB_MASTER_ROSTER date={roster_date.isoformat()} "
                    f"warehouse={warehouse_id} page={page} status={status_code} rows={len(items)}",
                    flush=True,
                )

                if status_code >= 400 or not has_next_page(payload, len(items), page, args.page_size):
                    break

    if args.dry_run:
        print(
            f"DRY_RUN courier_hub_master_rows={len(rows)} "
            f"identity_rows={len(identity_rows)} failures={failures}",
            flush=True,
        )
        return 1 if failures else 0

    written = supabase_upsert(rows)
    identities_written = 0
    try:
        identities_written = supabase_upsert_identities(identity_rows)
    except RuntimeError as exc:
        if is_missing_table_error(exc):
            print(
                f"COURIER_HUB_IDENTITY_SYNC_SKIPPED missing_table={IDENTITY_TABLE}",
                flush=True,
            )
        else:
            raise
    print(
        f"COURIER_HUB_MASTER_SYNC rows={len(rows)} written={written} "
        f"identity_rows={len(identity_rows)} identities_written={identities_written} "
        f"failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
