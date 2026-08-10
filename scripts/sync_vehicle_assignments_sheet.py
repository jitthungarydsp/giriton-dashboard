#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resources.google_auth import get_client, get_service_account_email
from resources.supabase_raw import get_supabase_config


DEFAULT_SHEET_ID = "1zcLlf4VzkKAVrODbbpS4-bYjvu9vaZuR2tIWUUqwLzU"
DEFAULT_GID = 321601566
SOURCE_NAME = "google-vehicle-assignments"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DSP_ID = "JIT"


def normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_time(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.strftime("%H:%M:%S")
    match = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}:00"
    return None


def parse_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def worksheet_by_gid(sheet_id: str, gid: int):
    try:
        spreadsheet = get_client().open_by_key(sheet_id)
    except PermissionError as exc:
        email = get_service_account_email() or "a beallitott Google service account"
        raise RuntimeError(
            f"A Google Sheet nincs megosztva ezzel a fiokkal: {email}"
        ) from exc
    for worksheet in spreadsheet.worksheets():
        if int(worksheet.id) == int(gid):
            return worksheet
    raise RuntimeError(f"Nincs worksheet ezzel a gid-del: {gid}")


def first_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def detect_header(values: list[list[str]]) -> tuple[int, list[str]]:
    for index, row in enumerate(values[:20]):
        headers = [normalize_header(cell) for cell in row]
        joined = " ".join(headers)
        if (
            any(token in joined for token in ["futar", "driver", "courier", "nev", "name"])
            and any(token in joined for token in ["rendszam", "plate", "auto", "car", "kocsi"])
        ):
            return index, headers
    return 0, [normalize_header(cell) for cell in values[0]]


def rows_from_sheet(sheet_id: str, gid: int, default_date: date) -> list[dict[str, Any]]:
    values = worksheet_by_gid(sheet_id, gid).get_all_values()
    if not values:
        return []
    header_index, headers = detect_header(values)
    rows: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for row_number, raw in enumerate(values[header_index + 1 :], start=header_index + 2):
        padded = raw + [""] * max(0, len(headers) - len(raw))
        item = {headers[index]: padded[index] for index in range(min(len(headers), len(padded)))}

        driver_name = first_value(item, "futar", "futar_nev", "driver", "driver_name", "courier", "courier_name", "nev", "name")
        work_date = (
            parse_date(first_value(item, "datum", "date", "work_date", "nap", "munkanap"))
            or parse_date(first_value(item, "tol", "ettol", "ervenyes_tol", "valid_from", "from"))
            or default_date
        )
        valid_to = parse_date(first_value(item, "ig", "eddig", "ervenyes_ig", "valid_to", "to")) or work_date
        if valid_to < work_date:
            valid_to = work_date

        car = first_value(item, "auto", "auto_tipus", "kocsi", "car", "vehicle", "vehicle_model", "tipus", "type")
        plate = first_value(item, "rendszam", "rendszam_", "license_plate", "plate", "rendsz", "frsz")
        if not driver_name or not (car or plate):
            continue

        shift_start = normalize_time(first_value(item, "kezdes", "muszak_kezdete", "shift_start", "start", "start_time")) or "00:00:00"
        shift_end = normalize_time(first_value(item, "vege", "muszak_vege", "shift_end", "end", "end_time"))
        shift_type = first_value(item, "muszak", "muszak_tipus", "shift", "shift_type", "megjegyzes", "note")
        warehouse = first_value(item, "raktar", "warehouse")

        day = work_date
        while day <= valid_to and (day - work_date).days <= 120:
            rows.append(
                {
                    "source_name": SOURCE_NAME,
                    "organization_id": ORGANIZATION_ID,
                    "dsp_id": DSP_ID,
                    "work_date": day.isoformat(),
                    "driver_name": driver_name,
                    "shift_start": shift_start,
                    "shift_end": shift_end,
                    "car": car,
                    "license_plate": plate,
                    "shift_type": shift_type,
                    "vehicle_type_id": "",
                    "response_json": {
                        "source_sheet_id": sheet_id,
                        "source_gid": gid,
                        "source_row": row_number,
                        "warehouse": warehouse,
                        "raw": item,
                    },
                    "fetched_at": fetched_at,
                }
            )
            day += timedelta(days=1)
    return rows


def supabase_config() -> tuple[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    return url.rstrip("/"), key


def headers() -> dict[str, str]:
    _url, key = supabase_config()
    result = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        result["Authorization"] = f"Bearer {key}"
    return result


def upsert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    url, _key = supabase_config()
    written = 0
    for start in range(0, len(rows), 500):
        chunk = rows[start : start + 500]
        response = requests.post(
            f"{url}/rest/v1/dsp_vehicle_assignments",
            headers=headers(),
            params={"on_conflict": "source_name,work_date,driver_name,shift_start,shift_end"},
            json=chunk,
            timeout=60,
        )
        response.raise_for_status()
        written += len(chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Sheet auto-hozzarendelesek szinkronja Supabase-be.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--gid", type=int, default=DEFAULT_GID)
    parser.add_argument("--default-date", default=date.today().isoformat())
    parser.add_argument("--apply", action="store_true", help="Ment Supabase-be. Enelkul csak dry-run.")
    args = parser.parse_args()

    rows = rows_from_sheet(args.sheet_id, args.gid, parse_date(args.default_date) or date.today())
    print(f"Jarmu-hozzarendeles sorok: {len(rows)}")
    for row in rows[:5]:
        print(f"MINTA {row['work_date']} {row['driver_name']} {row['license_plate']} {row['car']}")
    if not args.apply:
        print("DRY-RUN: menteshez add meg: --apply")
        return 0
    print(f"DB feltoltes: {upsert_rows(rows)} sor")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        raise SystemExit(1)
