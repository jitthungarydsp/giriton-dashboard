#!/usr/bin/env python3
"""Load the MuszakPro bookings Google Sheet into muszakpro.bookings."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google_client import open_spreadsheet  # noqa: E402
from resources.foglalasok_db import (  # noqa: E402
    FOGLALASOK_SHEET_NAME,
    SOURCE_SPREADSHEET_ID,
    build_db_rows,
)
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


MUSZAKPRO_SCHEMA = "muszakpro"
TABLE_NAME = "bookings"
SOURCE_NAME = "google-sheet-muszakpro-foglalasok"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    for candidate, fmt in (
        (text[:10], "%Y-%m-%d"),
        (text[:11], "%Y.%m.%d."),
        (text[:10], "%Y.%m.%d"),
        (text[:10], "%Y/%m/%d"),
    ):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            pass
    if len(text) >= 10 and text[4] in {"-", ".", "/"}:
        candidate = f"{text[:4]}-{text[5:7]}-{text[8:10]}"
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return text
    return text


def load_values_from_sheet() -> list[list[str]]:
    spreadsheet = open_spreadsheet(SOURCE_SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(FOGLALASOK_SHEET_NAME)
    return worksheet.get_all_values()


def supabase_headers(prefer: str = "") -> tuple[str, dict[str, str]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept-Profile": MUSZAKPRO_SCHEMA,
        "Content-Profile": MUSZAKPRO_SCHEMA,
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return supabase_url, headers


def normalize_rows(values: list[list[str]]) -> list[dict[str, Any]]:
    rows = build_db_rows(values)
    normalized: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["source_name"] = SOURCE_NAME
        item["work_date"] = normalize_date(item.get("work_date"))
        item.setdefault("status", "ACTIVE")
        key = (
            SOURCE_NAME,
            clean_text(item.get("work_date")),
            clean_text(item.get("email")).casefold(),
            clean_text(item.get("shift_text")),
            clean_text(item.get("booking_code")),
        )
        if all(key[:4]):
            normalized[key] = item
    return list(normalized.values())


def delete_existing_source_rows() -> int:
    supabase_url, headers = supabase_headers(prefer="return=minimal")
    response = requests.delete(
        f"{supabase_url}/rest/v1/{TABLE_NAME}",
        headers=headers,
        params={"source_name": f"eq.{SOURCE_NAME}"},
        timeout=60,
    )
    raise_for_supabase_error(response)
    return 0


def upsert_rows(rows: list[dict[str, Any]], batch_size: int) -> int:
    if not rows:
        return 0
    supabase_url, headers = supabase_headers(prefer="resolution=merge-duplicates,return=minimal")
    endpoint = f"{supabase_url}/rest/v1/{TABLE_NAME}"
    params = {"on_conflict": "source_name,work_date,email,shift_text,booking_code"}
    chunk_size = max(min(int(batch_size), 500), 1)
    written = 0
    for index in range(0, len(rows), chunk_size):
        chunk = rows[index:index + chunk_size]
        response = requests.post(
            endpoint,
            headers=headers,
            params=params,
            json=chunk,
            timeout=60,
        )
        raise_for_supabase_error(response)
        written += len(chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="MuszakPro foglalasok feltoltese muszakpro.bookings tablaba.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--replace-source",
        action="store_true",
        help="Elotte torli a google-sheet-muszakpro-foglalasok forras sorait.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    values = load_values_from_sheet()
    rows = normalize_rows(values)
    print(f"MUSZAKPRO_BOOKINGS_LOAD_SHEET_ROWS={max(len(values) - 1, 0)}")
    print(f"MUSZAKPRO_BOOKINGS_LOAD_DB_ROWS={len(rows)}")
    if rows:
        sample = rows[0]
        print(
            "MUSZAKPRO_BOOKINGS_LOAD_SAMPLE "
            f"{sample.get('work_date')} {sample.get('shift_text')} "
            f"{sample.get('email')} #{sample.get('courier_id') or ''}"
        )

    if args.dry_run:
        print("MUSZAKPRO_BOOKINGS_LOAD_DRY_RUN=1")
        return 0

    if args.replace_source:
        delete_existing_source_rows()
        print(f"MUSZAKPRO_BOOKINGS_LOAD_REPLACE_SOURCE={SOURCE_NAME}")

    written = upsert_rows(rows, args.batch_size)
    print(f"MUSZAKPRO_BOOKINGS_LOAD_WRITTEN={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
