#!/usr/bin/env python3
"""
Legacy courier registration/billing CSV -> Supabase staging table.

Target table:
    public.courier_master_sheet_import

Before first run, execute:
    docs/supabase_courier_master_sheet_import.sql

Dry-run:
    python scripts/upload_courier_master_sheet_import.py --csv-file data/courier_master_import.csv

Upload:
    python scripts/upload_courier_master_sheet_import.py --csv-file data/courier_master_import.csv --apply

Replace the same source_file rows before upload:
    python scripts/upload_courier_master_sheet_import.py --csv-file data/courier_master_import.csv --apply --replace-source
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


TARGET_TABLE = "courier_master_sheet_import"
SOURCE_NAME = "courier_master_sheet_import"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "#ref!", "n/a"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value).casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_courier_id(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = text.split(".", 1)[0]
    return re.sub(r"\D+", "", text)


def normalize_tax_number(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value)).upper()


def first_nonempty(row: dict[str, Any], aliases: list[str]) -> str:
    for alias in aliases:
        value = clean_text(row.get(alias))
        if value:
            return value

    normalized = {
        normalize_key(header): value
        for header, value in row.items()
        if normalize_key(header)
    }
    for alias in aliases:
        value = clean_text(normalized.get(normalize_key(alias)))
        if value:
            return value
    return ""


def open_csv_dict_reader(path: Path):
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1250", "iso-8859-2"):
        try:
            handle = path.open("r", encoding=encoding, newline="")
            sample = handle.read(4096)
            handle.seek(0)
            if "Ă" in sample and encoding == "utf-8-sig":
                handle.close()
                continue
            return handle, csv.DictReader(handle)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    handle = path.open("r", encoding="utf-8-sig", newline="")
    return handle, csv.DictReader(handle)


def compact_raw_payload(row: dict[str, Any]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, value in row.items():
        header = clean_text(key)
        if not header:
            continue
        payload[header] = clean_text(value)
    return payload


def row_to_payload(
    row: dict[str, Any],
    *,
    source_file: str,
    source_row_number: int,
    import_batch_id: str,
) -> dict[str, Any] | None:
    raw_payload = compact_raw_payload(row)
    if not any(raw_payload.values()):
        return None

    courier_id = normalize_courier_id(
        first_nonempty(
            row,
            [
                "courier_id",
                "courier_ID",
                "Courier ID",
                "Futar ID",
                "Futár ID",
                "Futar azonosito",
                "Futár azonosító",
                "USERNUMBER",
                "ID",
                "0",
            ],
        )
    )
    courier_name = first_nonempty(
        row,
        [
            "courier_name",
            "Futar",
            "Futár",
            "Nev",
            "Név",
            "1. Az Ön teljes neve: (ahogy a személyi igazolványban szerepel)",
            "Aláíró személy teljes neve",
            "Aláíró teljes neve",
        ],
    )
    email = first_nonempty(
        row,
        [
            "email",
            "E-mail-cím",
            "E-mail",
            "2. e-mail",
            "2. E-mail",
        ],
    )
    phone_number = first_nonempty(
        row,
        [
            "phone_number",
            "Telefonszám",
            "2. Az Ön telefonszáma (0036-tal kezdve, szóközök nélkül!)",
        ],
    )
    source_timestamp = first_nonempty(row, ["Időbélyeg", "Timestamp", "timestamp"])
    company_name = first_nonempty(
        row,
        [
            "company_name",
            "Vallalkozas neve",
            "Vállalkozás neve",
            "Ceg neve",
            "Cég neve",
            "Cegnev",
            "Cégnév",
        ],
    )
    tax_number = normalize_tax_number(
        first_nonempty(
            row,
            [
                "tax_number",
                "Vallalkozas adoszama",
                "Vállalkozás adószáma:",
                "Vállalkozás adószáma",
                "Ceg adoszama",
                "Cég adószáma",
            ],
        )
    )
    company_address = first_nonempty(
        row,
        [
            "company_address",
            "Vallalkozas szekhelye",
            "Vállalkozás székhelye:",
            "Vállalkozás székhelye",
            "Ceg szekhelye",
            "Cég székhelye",
        ],
    )
    bank_account_number = first_nonempty(
        row,
        [
            "bank_account_number",
            "Vallalkozasa bankszamla szama",
            "Vállalkozása bankszámla száma:",
            "Bankszamlaszam",
            "Bankszámlaszám",
        ],
    )
    billing_email = first_nonempty(
        row,
        [
            "billing_email",
            "Szamlazasi email",
            "Számlázási e-mail",
            "Számlázási email",
            "E-mail-cĂ­m",
            "E-mail-cím",
            "E-mail",
        ],
    )
    now = datetime.now(timezone.utc).isoformat()

    return {
        "import_batch_id": import_batch_id,
        "source_name": SOURCE_NAME,
        "source_file": source_file,
        "source_row_number": source_row_number,
        "courier_id": courier_id or None,
        "courier_name": courier_name or None,
        "email": email or None,
        "phone_number": phone_number or None,
        "company_name": company_name or None,
        "tax_number": tax_number or None,
        "company_address": company_address or None,
        "bank_account_number": bank_account_number or None,
        "billing_email": billing_email or None,
        "source_timestamp": source_timestamp or None,
        "raw_payload": raw_payload,
        "updated_at": now,
    }


def read_csv_payloads(path: Path, import_batch_id: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    handle, reader = open_csv_dict_reader(path)
    with handle:
        for row_number, row in enumerate(reader, start=2):
            payload = row_to_payload(
                dict(row),
                source_file=path.name,
                source_row_number=row_number,
                import_batch_id=import_batch_id,
            )
            if payload:
                payloads.append(payload)
    return payloads


class SupabaseRest:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def delete_source(self, source_file: str) -> None:
        response = requests.delete(
            f"{self.url}/rest/v1/{TARGET_TABLE}",
            headers={**self.headers, "Prefer": "return=minimal"},
            params={"source_file": f"eq.{source_file}"},
            timeout=60,
        )
        self.raise_for_error(response)

    def upsert_rows(self, rows: list[dict[str, Any]], chunk_size: int = 500) -> None:
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            response = requests.post(
                f"{self.url}/rest/v1/{TARGET_TABLE}",
                headers={
                    **self.headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                params={"on_conflict": "source_file,source_row_number"},
                data=json.dumps(chunk, ensure_ascii=False),
                timeout=120,
            )
            self.raise_for_error(response)

    @staticmethod
    def raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        if response.status_code == 404 and "courier_master_sheet_import" in response.text:
            raise RuntimeError(
                "Hianyzik a public.courier_master_sheet_import tabla. "
                "Futtasd le Supabase SQL Editorban: "
                "docs/supabase_courier_master_sheet_import.sql"
            )
        raise RuntimeError(
            f"Supabase hiba: HTTP {response.status_code}: {response.text[:2000]}"
        )


def ensure_required_environment() -> None:
    missing = [
        name
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Hianyzo kornyezeti valtozo(k): " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-file", required=True, help="A feltoltendo CSV fajl.")
    parser.add_argument("--apply", action="store_true", help="Tenyleges Supabase feltoltes.")
    parser.add_argument(
        "--replace-source",
        action="store_true",
        help="Feltoltes elott torli az ugyanilyen source_file sorait.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file).expanduser()
    import_batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payloads = read_csv_payloads(csv_path, import_batch_id)

    with_id = sum(1 for row in payloads if row.get("courier_id"))
    with_email = sum(1 for row in payloads if row.get("email"))
    with_company = sum(1 for row in payloads if row.get("company_name"))
    with_tax = sum(1 for row in payloads if row.get("tax_number"))
    with_address = sum(1 for row in payloads if row.get("company_address"))
    print(f"CSV: {csv_path}")
    print(f"Beolvasott sorok: {len(payloads)}")
    print(f"Courier ID-val: {with_id}")
    print(f"E-maillel: {with_email}")
    print(f"Vallalkozas nevvel: {with_company}")
    print(f"Adoszammal: {with_tax}")
    print(f"Szekhellyel: {with_address}")
    print(f"Import batch: {import_batch_id}")

    for row in payloads[:10]:
        print(
            f"  {row['source_row_number']} | "
            f"{row.get('courier_id') or ''} | "
            f"{row.get('courier_name') or ''} | "
            f"{row.get('email') or ''}"
        )
    if len(payloads) > 10:
        print(f"  ... tovabbi {len(payloads) - 10} sor")

    if not args.apply:
        print("\nDRY-RUN: nem tortent adatbazis-modositas.")
        print(
            "Feltoltes: python scripts/upload_courier_master_sheet_import.py "
            f"--csv-file {csv_path} --apply"
        )
        return 0

    ensure_required_environment()
    supabase = SupabaseRest()
    if args.replace_source:
        print(f"Korabbi sorok torlese source_file alapjan: {csv_path.name}")
        supabase.delete_source(csv_path.name)
    supabase.upsert_rows(payloads)
    print(f"Kesz. Feltoltve: {len(payloads)} sor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
