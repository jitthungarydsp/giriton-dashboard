from __future__ import annotations

import argparse
from io import StringIO
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resources.google_auth import get_client
from resources.supabase_raw import get_supabase_config


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


load_dotenv_if_available()


BOOKING_SHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
BOOKING_WORKSHEET_GID = 1961182696
TARGET_TABLE = "courier_loyalty_booking_log"
BOOKING_EXPORT_URL = (
    f"https://docs.google.com/spreadsheets/d/{BOOKING_SHEET_ID}/export"
    f"?format=csv&gid={BOOKING_WORKSHEET_GID}"
)


def supabase_config() -> tuple[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    return url.rstrip("/"), key


def headers(schema: str | None = None) -> dict[str, str]:
    _, key = supabase_config()
    result = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if schema:
        result["Accept-Profile"] = schema
        result["Content-Profile"] = schema
    return result


def raise_for_response(response: requests.Response, label: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(f"{label}: HTTP {response.status_code}: {response.text[:2000]}")


def normalize_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def parse_datetime(value: object) -> str | None:
    parsed = pd.to_datetime(value, format="%Y.%m.%d. %H:%M:%S", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Europe/Budapest")
    return parsed.tz_convert("UTC").isoformat()


def parse_shift_data(value: object) -> dict[str, str]:
    text = str(value or "")
    result = {"shift_date": "", "shift_time": "", "warehouse": "", "proxy_email": ""}
    date_match = re.search(r"D[áa]tum:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, flags=re.IGNORECASE)
    shift_match = re.search(r"M[űu]szak:\s*([^,]+)", text, flags=re.IGNORECASE)
    warehouse_match = re.search(r"Rakt[áa]r:\s*([^,]+)", text, flags=re.IGNORECASE)
    proxy_match = re.search(r"Proxy:\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", text, flags=re.IGNORECASE)
    if date_match:
        result["shift_date"] = date_match.group(1).strip()
    if shift_match:
        result["shift_time"] = shift_match.group(1).strip()
    if warehouse_match:
        result["warehouse"] = warehouse_match.group(1).strip()
    if proxy_match:
        result["proxy_email"] = proxy_match.group(1).strip()
    return result


def read_courier_lookup() -> dict[str, dict[str, str]]:
    url, _ = supabase_config()
    lookup_sources = []
    for table_name in ["courier_master", "courier_master_sheet_import"]:
        response = requests.get(
            f"{url}/rest/v1/{table_name}",
            headers=headers(),
            params={
                "select": "courier_id,courier_name,email,billing_email",
                "limit": "20000",
            },
            timeout=30,
        )
        if response.status_code >= 400 and table_name == "courier_master_sheet_import":
            continue
        raise_for_response(response, table_name)
        lookup_sources.extend(response.json() or [])
    lookup: dict[str, dict[str, str]] = {}
    for row in lookup_sources:
        courier_id = str(row.get("courier_id") or "").strip()
        if not courier_id:
            continue
        payload = {
            "courier_id": courier_id,
            "courier_name": str(row.get("courier_name") or "").strip(),
        }
        for key in [row.get("email"), row.get("billing_email")]:
            normalized = normalize_key(key)
            if normalized and normalized not in lookup:
                lookup[normalized] = payload
    return lookup


def read_booking_values_from_gspread() -> list[tuple[int, list[str]]]:
    worksheet = get_client().open_by_key(BOOKING_SHEET_ID).get_worksheet_by_id(BOOKING_WORKSHEET_GID)
    values = worksheet.get_all_values()
    if not values:
        return []
    header_index = next(
        (
            index
            for index, row in enumerate(values[:10])
            if "Idopont" in _ascii(row[0] if row else "") or "Idopont" in [_ascii(cell) for cell in row]
        ),
        0,
    )
    return [
        (row_number, row)
        for row_number, row in enumerate(values[header_index + 1 :], start=header_index + 2)
    ]


def read_booking_values_from_csv_export() -> list[tuple[int, list[str]]]:
    response = requests.get(BOOKING_EXPORT_URL, timeout=60)
    raise_for_response(response, "booking_google_csv_export")
    response.encoding = "utf-8"
    df = pd.read_csv(StringIO(response.text), dtype=str).fillna("")
    return [
        (index + 2, [str(value or "") for value in row.tolist()])
        for index, (_, row) in enumerate(df.iterrows())
    ]


def read_booking_rows(source: str = "csv") -> list[dict[str, Any]]:
    if source == "gspread":
        values = read_booking_values_from_gspread()
    elif source == "auto":
        try:
            values = read_booking_values_from_csv_export()
        except Exception:
            values = read_booking_values_from_gspread()
    else:
        values = read_booking_values_from_csv_export()
    rows = []
    for row_number, row in values:
        booked_at = row[0] if len(row) > 0 else ""
        user_email = row[1] if len(row) > 1 else ""
        operation = row[2] if len(row) > 2 else ""
        raw_shift_data = row[3] if len(row) > 3 else ""
        if not any([booked_at, user_email, operation, raw_shift_data]):
            continue
        shift = parse_shift_data(raw_shift_data)
        raw_user_email = str(user_email or "").strip()
        lookup_email = raw_user_email
        source_key = f"loyalty_booking:{BOOKING_SHEET_ID}:{BOOKING_WORKSHEET_GID}:{row_number}"
        rows.append(
            {
                "user_email": raw_user_email,
                "_lookup_email": lookup_email,
                "booked_at": parse_datetime(booked_at),
                "operation": str(operation or "").strip(),
                "shift_date": shift["shift_date"] or None,
                "shift_time": shift["shift_time"],
                "warehouse": shift["warehouse"],
                "raw_shift_data": str(raw_shift_data or "").strip(),
                "source_sheet_id": BOOKING_SHEET_ID,
                "source_gid": BOOKING_WORKSHEET_GID,
                "source_row": row_number,
                "source_key": source_key,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def _ascii(value: object) -> str:
    text = str(value or "")
    return (
        text.replace("ő", "o")
        .replace("Ő", "O")
        .replace("ű", "u")
        .replace("Ű", "U")
        .replace("á", "a")
        .replace("Á", "A")
        .replace("é", "e")
        .replace("É", "E")
    )


def upsert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    url, _ = supabase_config()
    written = 0
    for start in range(0, len(rows), 500):
        chunk = rows[start : start + 500]
        response = requests.post(
            f"{url}/rest/v1/{TARGET_TABLE}",
            headers={**headers("settlement"), "Prefer": "resolution=merge-duplicates,return=representation"},
            params={"on_conflict": "source_key"},
            json=chunk,
            timeout=60,
        )
        raise_for_response(response, TARGET_TABLE)
        written += len(response.json() or chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Lojalitasi muszakfoglalas LOG Google Sheet szinkron.")
    parser.add_argument("--apply", action="store_true", help="Ment Supabase-be. Enelkul csak dry-run.")
    parser.add_argument(
        "--source",
        choices=["csv", "gspread", "auto"],
        default="csv",
        help="Google tabla olvasasi mod. Alap: publikus CSV export.",
    )
    args = parser.parse_args()

    lookup = read_courier_lookup()
    rows = read_booking_rows(args.source)
    for row in rows:
        match = lookup.get(normalize_key(row.pop("_lookup_email", "") or row.get("user_email"))) or {}
        row["courier_id"] = match.get("courier_id") or None
        row["courier_name"] = match.get("courier_name") or ""

    unmatched = sum(1 for row in rows if not row.get("courier_id"))
    print(f"Foglalasi sorok: {len(rows)}")
    print(f"Courier match nelkul: {unmatched}")
    if not args.apply:
        print("DRY-RUN: menteshez add meg: --apply")
        return 0
    written = upsert_rows(rows)
    print(f"OK: mentett/frissitett sorok: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
