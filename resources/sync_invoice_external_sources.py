#!/usr/bin/env python3
"""
Három külső Google Sheet importja Supabase-be:

1. ATM Balance
2. Ügyfélértékelési bónusz
3. Havi bónusz/málusz összesítő

Dry-run:
    python .\scripts\sync_invoice_external_sources.py --month 2026-06

Éles:
    python .\scripts\sync_invoice_external_sources.py --month 2026-06 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials


ATM_SPREADSHEET_ID = "1Ax3TFDGVHZKiRbJby6YKWoptPJznwQk8WZ7__-zTfvs"
ATM_WORKSHEET = "ATM Balance"

RATING_SPREADSHEET_ID = "1hd-rCwJcEeFCVRQ0wdt35URlYKuw89iVwGWgp5gNNwE"
RATING_WORKSHEET = "Futár Értékelések és Túrák"

MONTHLY_SPREADSHEET_ID = "1D2lqZsNoUPdL3c-8Wj2ytKGVeiRqgerFM5Uo5gTZj8k"
MONTHLY_WORKSHEET = "Havizaras_2026-06.xls"

ATM_TABLE = "bill_jitt_invoice_atm_balance"
RATING_TABLE = "bill_jitt_invoice_customer_rating_bonus"
MONTHLY_TABLE = "bill_jitt_invoice_monthly_adjustments"

SCOPES = (
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


def normalize_person_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value).casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(sorted(re.findall(r"[a-z0-9]+", text)))


def parse_number(value: Any) -> Decimal:
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
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)

    if not cleaned or cleaned in {"-", ".", "-."}:
        return Decimal("0")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Hibás szám: {text!r}") from exc


def parse_int(value: Any) -> int:
    return int(parse_number(value))


def month_start(value: str) -> str:
    return datetime.strptime(value, "%Y-%m").date().replace(day=1).isoformat()


def google_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        setting("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def read_values(client: gspread.Client, spreadsheet_id: str, worksheet_name: str):
    worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    return worksheet.get_all_values()


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


def supabase_upsert(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    url = setting("SUPABASE_URL").rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(
            "resolution=merge-duplicates,return=minimal"
        ),
        params={
            "on_conflict": (
                "source_spreadsheet_id,worksheet_name,"
                "source_row_number,billing_month"
            )
        },
        json=rows,
        timeout=90,
    )

    if not response.ok:
        raise RuntimeError(
            f"{table}: HTTP {response.status_code}: {response.text[:3000]}"
        )


def load_courier_lookup() -> dict[str, int]:
    url = setting("SUPABASE_URL").rstrip("/")
    response = requests.get(
        f"{url}/rest/v1/courier_master",
        headers=supabase_headers(),
        params={
            "select": "courier_id,courier_name",
            "limit": "10000",
        },
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"courier_master: HTTP {response.status_code}: {response.text[:2000]}"
        )

    lookup = {}
    for row in response.json() or []:
        name = normalize_text(row.get("courier_name"))
        if not name:
            continue
        lookup[normalize_person_key(name)] = int(row["courier_id"])
    return lookup


def parse_atm_rows(values, billing_month, courier_lookup):
    rows = []
    for row_number, row in enumerate(values[1:], start=2):
        padded = list(row) + [""] * 4
        driver_name = normalize_text(padded[0])
        if not driver_name:
            continue

        rows.append(
            {
                "source_spreadsheet_id": ATM_SPREADSHEET_ID,
                "worksheet_name": ATM_WORKSHEET,
                "source_row_number": row_number,
                "billing_month": billing_month,
                "courier_id": courier_lookup.get(normalize_person_key(driver_name)),
                "driver_name": driver_name,
                "balance_huf": str(parse_number(padded[1])),
                "dsp": normalize_text(padded[2]) or None,
                "warehouse_name": normalize_text(padded[3]) or None,
                "row_data": {
                    "Name": padded[0],
                    "Balance": padded[1],
                    "DSP": padded[2],
                    "Standort": padded[3],
                },
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def parse_rating_rows(values, billing_month, courier_lookup):
    rows = []

    # Fejléc a 3. sorban, adatok a 4. sortól.
    for row_number, row in enumerate(values[3:], start=4):
        padded = list(row) + [""] * 7
        courier_id_text = normalize_text(padded[0])
        driver_name = normalize_text(padded[1])

        if not driver_name:
            continue

        courier_id = None
        try:
            courier_id = int(courier_id_text)
        except (TypeError, ValueError):
            courier_id = courier_lookup.get(normalize_person_key(driver_name))

        rows.append(
            {
                "source_spreadsheet_id": RATING_SPREADSHEET_ID,
                "worksheet_name": RATING_WORKSHEET,
                "source_row_number": row_number,
                "billing_month": billing_month,
                "courier_id": courier_id,
                "driver_name": driver_name,
                "rating_count": parse_int(padded[2]),
                "average_rating": str(parse_number(padded[3])),
                "bonus_per_route_huf": str(parse_number(padded[4])),
                "completed_routes": parse_int(padded[5]),
                "bonus_total_huf": str(parse_number(padded[6])),
                "row_data": {
                    "Futár ID": padded[0],
                    "Futár Neve": padded[1],
                    "Értékelések Száma": padded[2],
                    "Átlagos Rating": padded[3],
                    "Túránkénti Bónusz": padded[4],
                    "Teljesített Túrák": padded[5],
                    "Összes Bónusz": padded[6],
                },
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def parse_monthly_rows(values, billing_month, courier_lookup):
    rows = []
    for row_number, row in enumerate(values[1:], start=2):
        padded = list(row) + [""] * 6
        driver_name = normalize_text(padded[0])
        if not driver_name:
            continue

        rows.append(
            {
                "source_spreadsheet_id": MONTHLY_SPREADSHEET_ID,
                "worksheet_name": MONTHLY_WORKSHEET,
                "source_row_number": row_number,
                "billing_month": billing_month,
                "courier_id": courier_lookup.get(normalize_person_key(driver_name)),
                "driver_name": driver_name,
                "bonus_huf": str(parse_number(padded[1])),
                "malus_huf": str(parse_number(padded[2])),
                "returned_route_huf": str(parse_number(padded[3])),
                "accepted_route_huf": str(parse_number(padded[4])),
                "source_total_huf": str(parse_number(padded[5])),
                "row_data": {
                    "Futár": padded[0],
                    "Bónusz": padded[1],
                    "Málusz": padded[2],
                    "Kör Leadott": padded[3],
                    "Kör Felvett": padded[4],
                    "Összesen": padded[5],
                },
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def print_summary(name, rows, amount_columns):
    print(f"\n{name}: {len(rows)} sor")
    for column in amount_columns:
        total = sum(Decimal(str(row.get(column) or "0")) for row in rows)
        print(f"  {column}: {total} Ft")


def upload_chunks(table, rows):
    chunk_size = 500
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        supabase_upsert(table, chunk)
        print(f"{table}: {min(start + chunk_size, len(rows))}/{len(rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    billing_month = month_start(args.month)
    client = google_client()
    courier_lookup = load_courier_lookup()

    print("ATM Balance olvasása...")
    atm_rows = parse_atm_rows(
        read_values(client, ATM_SPREADSHEET_ID, ATM_WORKSHEET),
        billing_month,
        courier_lookup,
    )

    print("Ügyfélértékelési bónusz olvasása...")
    rating_rows = parse_rating_rows(
        read_values(client, RATING_SPREADSHEET_ID, RATING_WORKSHEET),
        billing_month,
        courier_lookup,
    )

    print("Havi bónusz/málusz olvasása...")
    monthly_rows = parse_monthly_rows(
        read_values(client, MONTHLY_SPREADSHEET_ID, MONTHLY_WORKSHEET),
        billing_month,
        courier_lookup,
    )

    print_summary("ATM", atm_rows, ["balance_huf"])
    print_summary("Ügyfélértékelés", rating_rows, ["bonus_total_huf"])
    print_summary(
        "Havizárás",
        monthly_rows,
        [
            "bonus_huf",
            "malus_huf",
            "returned_route_huf",
            "accepted_route_huf",
            "source_total_huf",
        ],
    )

    if not args.apply:
        print("\nDRY-RUN: nem történt adatbázis-módosítás.")
        print(
            f"Éles futtatás: python .\\scripts\\sync_invoice_external_sources.py "
            f"--month {args.month} --apply"
        )
        return 0

    upload_chunks(ATM_TABLE, atm_rows)
    upload_chunks(RATING_TABLE, rating_rows)
    upload_chunks(MONTHLY_TABLE, monthly_rows)

    print("Kész.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())