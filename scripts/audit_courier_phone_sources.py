#!/usr/bin/env python3
"""
Audit where courier phone numbers are available and how many staged Sheet rows
can be matched by phone.

Sources checked:
  - live fetch-drivers API
  - public.courier_master
  - public.courier_master_sheet_import
  - public.dsp_drivers_live_raw / public.raw_dsp_live_drivers, if present

Run without Supabase env to check only the live API:
    python scripts/audit_courier_phone_sources.py

Run with Supabase env to include DB tables:
    python scripts/audit_courier_phone_sources.py --export-csv data/phone_source_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from collections import defaultdict
from typing import Any

import requests


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", clean_text(value))
    if digits.startswith("0036"):
        digits = "36" + digits[4:]
    elif digits.startswith("06"):
        digits = "36" + digits[2:]
    elif len(digits) == 9 and digits.startswith(("20", "30", "31", "50", "70")):
        digits = "36" + digits
    return digits


def fetch_live_drivers() -> list[dict[str, Any]]:
    url = (
        f"{KIFLI_API_BASE_URL}/fetch-drivers"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    payload = response.json()
    rows: list[dict[str, Any]] = []
    for driver in payload.get("drivers", []) or []:
        personal = driver.get("personal_info") or {}
        rows.append(
            {
                "source": "api:fetch-drivers",
                "courier_id": clean_text(driver.get("driver_id")),
                "courier_name": clean_text(personal.get("name")),
                "phone_number": clean_text(personal.get("contact_number")),
                "email": clean_text(personal.get("contact_email")),
            }
        )
    return rows


class SupabaseRest:
    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.enabled = bool(self.url and self.key)
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def get_all(
        self,
        table: str,
        select: str,
        *,
        order: str = "",
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        rows: list[dict[str, Any]] = []
        while len(rows) < limit:
            start = len(rows)
            end = min(start + 999, limit - 1)
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
            if is_missing_table_response(response):
                return []
            response.raise_for_status()
            chunk = response.json()
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < (end - start + 1):
                break
        return rows


def is_missing_table_response(response: requests.Response) -> bool:
    if response.status_code not in (400, 404):
        return False
    text = response.text.lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "pgrst205" in text
    )


def rows_from_courier_master(supabase: SupabaseRest) -> list[dict[str, Any]]:
    rows = supabase.get_all(
        "courier_master",
        "courier_id,courier_name,phone_number,email",
        order="courier_name.asc",
        limit=10000,
    )
    return [
        {
            "source": "db:courier_master",
            "courier_id": clean_text(row.get("courier_id")),
            "courier_name": clean_text(row.get("courier_name")),
            "phone_number": clean_text(row.get("phone_number")),
            "email": clean_text(row.get("email")),
        }
        for row in rows
    ]


def rows_from_sheet_import(supabase: SupabaseRest) -> list[dict[str, Any]]:
    rows = supabase.get_all(
        "courier_master_sheet_import",
        "id,courier_id,courier_name,phone_number,email,source_file,source_row_number",
        order="source_file.asc,source_row_number.asc",
        limit=20000,
    )
    return [
        {
            "source": "db:courier_master_sheet_import",
            "courier_id": clean_text(row.get("courier_id")),
            "courier_name": clean_text(row.get("courier_name")),
            "phone_number": clean_text(row.get("phone_number")),
            "email": clean_text(row.get("email")),
            "source_row": f"{row.get('source_file')}:{row.get('source_row_number')}",
        }
        for row in rows
    ]


PHONE_KEYS = {"phone", "phone_number", "contact_number", "mobile", "telefon", "telefonszam"}


def find_phone_values(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "", str(key).casefold())
            if normalized_key in PHONE_KEYS:
                phone = clean_text(value)
                if phone:
                    values.append(phone)
            values.extend(find_phone_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(find_phone_values(item))
    return values


def rows_from_raw_live_table(supabase: SupabaseRest, table_name: str) -> list[dict[str, Any]]:
    rows = supabase.get_all(
        table_name,
        "driver_id,response_json,fetched_at",
        order="fetched_at.desc",
        limit=10000,
    )
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        payload = row.get("response_json") or {}
        phones = find_phone_values(payload)
        personal = payload.get("personal_info") if isinstance(payload, dict) else {}
        courier_id = clean_text(row.get("driver_id") or payload.get("driver_id") if isinstance(payload, dict) else "")
        courier_name = clean_text((personal or {}).get("name") if isinstance(personal, dict) else "")
        email = clean_text((personal or {}).get("contact_email") if isinstance(personal, dict) else "")
        for phone in phones:
            key = (courier_id, normalize_phone(phone))
            if key in seen:
                continue
            seen.add(key)
            output.append(
                {
                    "source": f"db:{table_name}",
                    "courier_id": courier_id,
                    "courier_name": courier_name,
                    "phone_number": phone,
                    "email": email,
                }
            )
    return output


def summarize(rows: list[dict[str, Any]]) -> None:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)

    for source, source_rows in sorted(by_source.items()):
        with_phone = [row for row in source_rows if normalize_phone(row.get("phone_number"))]
        unique_phones = {normalize_phone(row.get("phone_number")) for row in with_phone}
        print(
            f"{source}: rows={len(source_rows)}, "
            f"with_phone={len(with_phone)}, unique_phone={len(unique_phones)}"
        )


def print_staging_matches(rows: list[dict[str, Any]]) -> None:
    staging = [row for row in rows if row["source"] == "db:courier_master_sheet_import"]
    other = [row for row in rows if row["source"] != "db:courier_master_sheet_import"]
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in other:
        phone = normalize_phone(row.get("phone_number"))
        if phone:
            index[phone].append(row)

    matched = 0
    ambiguous = 0
    missing = 0
    for row in staging:
        phone = normalize_phone(row.get("phone_number"))
        if not phone:
            missing += 1
            continue
        hits = index.get(phone, [])
        if len(hits) == 1:
            matched += 1
        elif len(hits) > 1:
            ambiguous += 1
        else:
            missing += 1

    if staging:
        print("\nStaging telefon match mas forrasok alapjan:")
        print(f"  egyertelmu talalat: {matched}")
        print(f"  tobbes talalat: {ambiguous}")
        print(f"  nincs talalat / nincs telefon: {missing}")


def export_csv(path: str, rows: list[dict[str, Any]]) -> None:
    fields = ["source", "courier_id", "courier_name", "phone_number", "email", "source_row"]
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-csv", help="Telefonforras audit export CSV fajl.")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    try:
        rows.extend(fetch_live_drivers())
    except Exception as exc:
        print(f"api:fetch-drivers hiba: {exc}")

    supabase = SupabaseRest()
    if supabase.enabled:
        rows.extend(rows_from_courier_master(supabase))
        rows.extend(rows_from_sheet_import(supabase))
        for table in ("dsp_drivers_live_raw", "raw_dsp_live_drivers"):
            rows.extend(rows_from_raw_live_table(supabase, table))
    else:
        print("Supabase env nincs beallitva, csak az API forras futott.")

    summarize(rows)
    print_staging_matches(rows)

    if args.export_csv:
        export_csv(args.export_csv, rows)
        print(f"\nExport kesz: {args.export_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
