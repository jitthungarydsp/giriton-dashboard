#!/usr/bin/env python3
"""
Promote staged courier registration/billing rows into courier_master.

Flow:
  1) courier_master_sheet_import contains the raw Sheet/CSV rows.
  2) This script finds the real courier_master.courier_id by phone number.
  3) Matched rows update courier_master billing/contact fields.

No courier_id is invented. Name-only rows are never promoted.

Dry-run:
    python scripts/promote_courier_master_sheet_import.py

Apply:
    python scripts/promote_courier_master_sheet_import.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import requests


STAGING_TABLE = "courier_master_sheet_import"
MASTER_TABLE = "courier_master"

MASTER_COLUMNS = (
    "courier_id",
    "courier_name",
    "phone_number",
    "email",
    "company_name",
    "company_address",
    "tax_number",
    "bank_account_number",
    "billing_email",
    "billing_data_source",
    "billing_data_updated_at",
)

BILLING_ALIASES: dict[str, list[str]] = {
    "company_name": [
        "Vallalkozas neve",
        "Vállalkozás neve",
        "Ceg neve",
        "Cég neve",
        "Cegnev",
        "Cégnév",
    ],
    "company_address": [
        "Vallalkozas szekhelye",
        "Vállalkozás székhelye:",
        "Vállalkozás székhelye",
        "Ceg szekhelye",
        "Cég székhelye",
    ],
    "tax_number": [
        "Vallalkozas adoszama",
        "Vállalkozás adószáma:",
        "Vállalkozás adószáma",
        "Ceg adoszama",
        "Cég adószáma",
    ],
    "bank_account_number": [
        "Vallalkozasa bankszamla szama",
        "Vállalkozása bankszámla száma:",
        "Bankszamlaszam",
        "Bankszámlaszám",
    ],
    "billing_email": [
        "Szamlazasi email",
        "Számlázási e-mail",
        "Számlázási email",
        "E-mail-cím",
        "E-mail",
    ],
}


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


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", clean_text(value))
    if digits.startswith("0036"):
        digits = "36" + digits[4:]
    elif digits.startswith("06"):
        digits = "36" + digits[2:]
    elif len(digits) == 9 and digits.startswith(("20", "30", "31", "50", "70")):
        digits = "36" + digits
    return digits


def normalize_tax_number(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value)).upper()


def first_raw_value(raw_payload: dict[str, Any], aliases: list[str]) -> str:
    for alias in aliases:
        value = clean_text(raw_payload.get(alias))
        if value:
            return value

    normalized = {
        normalize_key(header): value
        for header, value in raw_payload.items()
        if normalize_key(header)
    }
    for alias in aliases:
        value = clean_text(normalized.get(normalize_key(alias)))
        if value:
            return value
    return ""


class SupabaseRest:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def get_all(self, table: str, select: str, order: str = "id.asc") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            start = len(rows)
            end = start + 999
            headers = {
                **self.headers,
                "Range-Unit": "items",
                "Range": f"{start}-{end}",
            }
            params = {"select": select}
            if order:
                params["order"] = order
            response = requests.get(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                params=params,
                timeout=60,
            )
            self.raise_for_error(response)
            chunk = response.json()
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < 1000:
                break
        return rows

    def get_staging_rows(self) -> list[dict[str, Any]]:
        return self.get_all(
            STAGING_TABLE,
            (
                "id,source_file,source_row_number,courier_id,courier_name,"
                "email,phone_number,raw_payload,imported_at"
            ),
            order="source_file.asc,source_row_number.asc",
        )

    def get_master_rows(self) -> list[dict[str, Any]]:
        return self.get_all(
            MASTER_TABLE,
            ",".join(MASTER_COLUMNS),
            order="courier_name.asc",
        )

    def patch_master(self, courier_id: int, payload: dict[str, Any]) -> None:
        response = requests.patch(
            f"{self.url}/rest/v1/{MASTER_TABLE}",
            headers={**self.headers, "Prefer": "return=minimal"},
            params={"courier_id": f"eq.{courier_id}"},
            json=payload,
            timeout=30,
        )
        self.raise_for_error(response)

    def patch_staging_courier_id(self, staging_id: int, courier_id: int) -> None:
        response = requests.patch(
            f"{self.url}/rest/v1/{STAGING_TABLE}",
            headers={**self.headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{staging_id}"},
            json={
                "courier_id": str(courier_id),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=30,
        )
        self.raise_for_error(response)

    @staticmethod
    def raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        raise RuntimeError(
            f"Supabase hiba: HTTP {response.status_code}: {response.text[:2000]}"
        )


def unique_phone_index(master_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in master_rows:
        phone = normalize_phone(row.get("phone_number"))
        if phone:
            grouped[phone].append(row)
    return {phone: rows[0] for phone, rows in grouped.items() if len(rows) == 1}


def build_master_patch(staging_row: dict[str, Any], master_row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = staging_row.get("raw_payload") or {}
    patch: dict[str, Any] = {}
    provenance: list[str] = []

    for field, aliases in BILLING_ALIASES.items():
        value = first_raw_value(raw_payload, aliases)
        if field == "tax_number":
            value = normalize_tax_number(value)
        current = clean_text(master_row.get(field))
        if value and value != current:
            patch[field] = value
            provenance.append(field)

    for field in ("email", "phone_number"):
        if clean_text(master_row.get(field)):
            continue
        value = clean_text(staging_row.get(field))
        if value:
            patch[field] = value
            provenance.append(field)

    if patch:
        patch["billing_data_source"] = (
            f"{STAGING_TABLE}:{staging_row.get('source_file')}:"
            f"{staging_row.get('source_row_number')} ({', '.join(provenance)})"
        )
        patch["billing_data_updated_at"] = datetime.now(timezone.utc).isoformat()
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()

    return patch


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
    parser.add_argument("--apply", action="store_true", help="Tenyleges master frissites.")
    parser.add_argument(
        "--write-back-id",
        action="store_true",
        help="A megtalalt courier_id-t visszairja a staging tablaba is.",
    )
    args = parser.parse_args()

    ensure_required_environment()
    supabase = SupabaseRest()
    staging_rows = supabase.get_staging_rows()
    master_rows = supabase.get_master_rows()
    phone_index = unique_phone_index(master_rows)

    updates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    no_phone: list[dict[str, Any]] = []
    no_match: list[dict[str, Any]] = []

    for staging_row in staging_rows:
        phone = normalize_phone(staging_row.get("phone_number"))
        if not phone:
            no_phone.append(staging_row)
            continue
        master_row = phone_index.get(phone)
        if not master_row:
            no_match.append(staging_row)
            continue
        patch = build_master_patch(staging_row, master_row)
        if patch:
            updates.append((staging_row, master_row, patch))

    print(f"Staging sorok: {len(staging_rows)}")
    print(f"Master futarok: {len(master_rows)}")
    print(f"Telefon alapjan frissitendo master sorok: {len(updates)}")
    print(f"Telefon nelkuli staging sorok: {len(no_phone)}")
    print(f"Telefonos, de masterben nem talalt sorok: {len(no_match)}")

    for staging_row, master_row, patch in updates[:50]:
        fields = ", ".join(patch.keys())
        print(
            f"  {master_row.get('courier_id')} | "
            f"{master_row.get('courier_name')} <- "
            f"{staging_row.get('courier_name')} | {fields}"
        )
    if len(updates) > 50:
        print(f"  ... tovabbi {len(updates) - 50} frissites")

    if not args.apply:
        print("\nDRY-RUN: nem tortent adatbazis-modositas.")
        print("Eles futtatas: python scripts/promote_courier_master_sheet_import.py --apply")
        return 0

    failures = 0
    for staging_row, master_row, patch in updates:
        courier_id = int(master_row["courier_id"])
        try:
            supabase.patch_master(courier_id, patch)
            if args.write_back_id and not clean_text(staging_row.get("courier_id")):
                supabase.patch_staging_courier_id(int(staging_row["id"]), courier_id)
        except Exception as exc:
            failures += 1
            print(
                f"HIBA: {courier_id} | {master_row.get('courier_name')} | {exc}",
                file=sys.stderr,
            )

    print(f"\nKesz. Sikeres: {len(updates) - failures}, hibas: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
