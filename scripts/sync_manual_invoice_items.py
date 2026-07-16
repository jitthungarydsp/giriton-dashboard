#!/usr/bin/env python3
"""
Google Sheets "Adatok" munkalap -> Supabase
public.bill_jitt_invoice_manual_items

Forrás:
https://docs.google.com/spreadsheets/d/1G58HK2dyefsIOOBEZIlI9gDuAiFCe4zKHNgPYg3OiXM

Oszlop-hozzárendelés:
A  dátum              -> item_date
B  Név                -> driver_name
C  Típus              -> item_type (BONUS / MALUS)
D  Indok              -> item_label
E  Malusz             -> amount_huf, ha MALUS
F  Bónusz             -> amount_huf, ha BONUS
G  Rögzítő kódja      -> created_by
H  TRANZAKCIÓ ID      -> note

Alapból csak ellenőriz (dry-run). Tényleges feltöltés:
    python sync_manual_invoice_items.py --apply

Szükséges környezeti változók:
    GOOGLE_SERVICE_ACCOUNT_FILE
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Példa PowerShell:
    $env:GOOGLE_SERVICE_ACCOUNT_FILE="$PWD\girition-a89bab5e91bc.json"
    $env:SUPABASE_URL="https://....supabase.co"
    $env:SUPABASE_SERVICE_ROLE_KEY="..."
    python .\scripts\sync_manual_invoice_items.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials


SPREADSHEET_ID = "1G58HK2dyefsIOOBEZIlI9gDuAiFCe4zKHNgPYg3OiXM"
WORKSHEET_NAME = "Adatok"
TARGET_TABLE = "bill_jitt_invoice_manual_items"
SOURCE_NAME = "manual_invoice_sheet"

GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)


def setting(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Hiányzó környezeti változó: {name}")
    return value


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_ascii(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_item_type(value: Any) -> str:
    text = normalize_ascii(value).upper().replace("Ó", "O")
    if "BONUS" in text:
        return "BONUS"
    if "MALUS" in text:
        return "MALUS"
    return text


def parse_hungarian_date(value: Any) -> date:
    text = normalize_text(value)
    if not text:
        raise ValueError("Üres dátum.")

    formats = (
        "%Y.%m.%d. %H:%M:%S",
        "%Y.%m.%d. %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    # Biztonsági fallback: csak az első YYYY.MM.DD / YYYY-MM-DD részt használjuk.
    match = re.search(r"(\d{4})[.-](\d{1,2})[.-](\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        return date(year, month, day)

    raise ValueError(f"Ismeretlen dátumformátum: {text!r}")


def parse_amount(value: Any) -> Decimal:
    text = normalize_text(value)
    if not text:
        return Decimal("0")

    cleaned = (
        text.replace("\u00a0", "")
        .replace(" ", "")
        .replace("Ft", "")
        .replace("HUF", "")
        .replace(",", ".")
    )

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Hibás összeg: {text!r}") from exc

    return abs(amount)


def google_client() -> gspread.Client:
    credentials_file = setting("GOOGLE_SERVICE_ACCOUNT_FILE")
    credentials = Credentials.from_service_account_file(
        credentials_file,
        scopes=GOOGLE_SCOPES,
    )
    return gspread.authorize(credentials)


def read_sheet_rows() -> list[list[str]]:
    client = google_client()
    worksheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    return worksheet.get_all_values()


def row_to_payload(row: list[str], row_number: int) -> dict[str, Any] | None:
    padded = list(row) + [""] * max(0, 8 - len(row))

    raw_date = padded[0]
    driver_name = normalize_text(padded[1])
    item_type = normalize_item_type(padded[2])
    item_label = normalize_text(padded[3])
    malus = parse_amount(padded[4])
    bonus = parse_amount(padded[5])
    created_by = normalize_text(padded[6])
    transaction_id = normalize_text(padded[7])

    # Teljesen üres sor.
    if not any(normalize_text(value) for value in padded[:8]):
        return None

    if not driver_name:
        raise ValueError(f"{row_number}. sor: hiányzik a futár neve.")

    if item_type not in {"BONUS", "MALUS"}:
        raise ValueError(
            f"{row_number}. sor: ismeretlen típus: {padded[2]!r}"
        )

    item_date = parse_hungarian_date(raw_date)
    amount = bonus if item_type == "BONUS" else malus

    if amount == 0:
        # A forrásban vannak nulla értékű sorok is. Ezeket megtartjuk,
        # mert üzletileg lehet jelentőségük.
        amount = Decimal("0")

    note_parts = []
    if transaction_id:
        note_parts.append(f"transaction_id={transaction_id}")
    note_parts.append(f"sheet_row={row_number}")
    note = "; ".join(note_parts)

    return {
        "source_name": SOURCE_NAME,
        "item_date": item_date.isoformat(),
        "worksheet_name": WORKSHEET_NAME,
        "driver_name": driver_name,
        "item_type": item_type,
        "item_label": item_label or item_type,
        "amount_huf": str(amount),
        "note": note,
        "created_by": created_by or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def supabase_headers(prefer: str = "") -> dict[str, str]:
    key = setting("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }

    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"

    if prefer:
        headers["Prefer"] = prefer

    return headers


def supabase_request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str = "",
) -> Any:
    url = setting("SUPABASE_URL").rstrip("/")
    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(prefer),
        params=params,
        json=payload,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase {table}: HTTP {response.status_code}: "
            f"{response.text[:3000]}"
        )

    if not response.content:
        return []

    return response.json()


def existing_keys() -> set[tuple[str, ...]]:
    rows = supabase_request(
        "GET",
        TARGET_TABLE,
        params={
            "select": (
                "source_name,item_date,worksheet_name,driver_name,"
                "item_type,item_label,amount_huf,note,created_by"
            ),
            "source_name": f"eq.{SOURCE_NAME}",
            "worksheet_name": f"eq.{WORKSHEET_NAME}",
            "limit": "10000",
        },
    )

    return {
        (
            normalize_text(row.get("source_name")),
            normalize_text(row.get("item_date")),
            normalize_text(row.get("worksheet_name")),
            normalize_text(row.get("driver_name")),
            normalize_text(row.get("item_type")),
            normalize_text(row.get("item_label")),
            str(Decimal(str(row.get("amount_huf") or "0"))),
            normalize_text(row.get("note")),
            normalize_text(row.get("created_by")),
        )
        for row in rows
    }


def payload_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        normalize_text(row.get("source_name")),
        normalize_text(row.get("item_date")),
        normalize_text(row.get("worksheet_name")),
        normalize_text(row.get("driver_name")),
        normalize_text(row.get("item_type")),
        normalize_text(row.get("item_label")),
        str(Decimal(str(row.get("amount_huf") or "0"))),
        normalize_text(row.get("note")),
        normalize_text(row.get("created_by")),
    )


def insert_rows(rows: list[dict[str, Any]]) -> None:
    chunk_size = 500

    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        supabase_request(
            "POST",
            TARGET_TABLE,
            payload=chunk,
            prefer="return=minimal",
        )
        print(
            f"Feltöltve: {min(start + chunk_size, len(rows))}/{len(rows)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ténylegesen feltölti az új sorokat.",
    )
    parser.add_argument(
        "--show-errors",
        action="store_true",
        help="Minden hibás forrássort részletesen kiír.",
    )
    args = parser.parse_args()

    print("Google Sheets adatok olvasása...")
    values = read_sheet_rows()

    if not values:
        raise RuntimeError("A munkalap üres.")

    # Az első sor fejléc. A forrás fejlécének első cellája jelenleg dinamikus,
    # ezért nem a fejlécnevekre, hanem a stabil A:H oszlopsorrendre építünk.
    source_rows = values[1:]

    parsed: list[dict[str, Any]] = []
    errors: list[str] = []

    for row_number, row in enumerate(source_rows, start=2):
        try:
            payload = row_to_payload(row, row_number)
            if payload:
                parsed.append(payload)
        except Exception as exc:
            errors.append(str(exc))
            if args.show_errors:
                print(f"HIBA: {exc}", file=sys.stderr)

    print(f"Feldolgozható forrássorok: {len(parsed)}")
    print(f"Hibás/kihagyott sorok: {len(errors)}")

    print("Meglévő Supabase sorok ellenőrzése...")
    known = existing_keys()
    new_rows = [row for row in parsed if payload_key(row) not in known]

    print(f"Már létező sorok: {len(parsed) - len(new_rows)}")
    print(f"Új feltöltendő sorok: {len(new_rows)}")

    bonus_total = sum(
        Decimal(row["amount_huf"])
        for row in new_rows
        if row["item_type"] == "BONUS"
    )
    malus_total = sum(
        Decimal(row["amount_huf"])
        for row in new_rows
        if row["item_type"] == "MALUS"
    )

    print(f"Új BONUS összeg: {bonus_total} Ft")
    print(f"Új MALUS összeg: {malus_total} Ft")

    if errors and not args.show_errors:
        print(
            "A hibák részleteihez futtasd --show-errors kapcsolóval."
        )

    if not args.apply:
        print("DRY-RUN: nem történt adatbázis-módosítás.")
        print("Tényleges feltöltés: python sync_manual_invoice_items.py --apply")
        return 0

    if not new_rows:
        print("Nincs új feltöltendő adat.")
        return 0

    insert_rows(new_rows)
    print("Kész.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())