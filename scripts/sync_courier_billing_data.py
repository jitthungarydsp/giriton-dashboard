#!/usr/bin/env python3
"""
Google Sheets -> Supabase courier_master számlázási adat szinkronizáló.

Alapértelmezésben csak előnézetet készít (dry-run).
Tényleges módosításhoz:
    python sync_courier_billing_data.py --apply

Szükséges környezeti változók:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Google hitelesítés egyik módon:
    GOOGLE_SERVICE_ACCOUNT_FILE=/utvonal/service-account.json
vagy:
    GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'

Függőségek:
    pip install gspread google-auth requests
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import gspread
import requests
from google.oauth2.service_account import Credentials


SHEETS = [
    # Az újabb adatbekérő az elsődleges forrás.
    {
        "spreadsheet_id": "1dHzIpTMwSud2oCXbuLUsUHmCgMwHaa1O75e7kUmLiKo",
        "worksheet": "adatbe_valaszok",
        "source": "google_form_2025_05",
        "priority": 200,
    },
    # Régebbi adatbekérő, csak hiányzó adatok pótlására.
    {
        "spreadsheet_id": "14H9c5InkUbWlMMkbFVXYQay4UMiYo0opu4wk8rXHWvY",
        "worksheet": "A(z) 3. lapon lévő válaszok",
        "source": "google_form_legacy_3",
        "priority": 100,
    },
]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

FIELD_ALIASES: dict[str, list[str]] = {
    "courier_id": [
        "courier_id",
        "courier_ID",
        "Courier ID",
        "Futar ID",
        "Futar azonosito",
        "USERNUMBER",
        "Usernumber",
        "ID",
        "0",
    ],
    "courier_name": [
        "1. Az Ön teljes neve: (ahogy a személyi igazolványban szerepel)",
        "Aláíró személy teljes neve",
        "Aláíró teljes neve",
    ],
    "warehouse_name": [
        "Raktar",
        "Telephely",
        "Depo",
        "warehouse_name",
    ],
    "email": [
        "E-mail-cím",
        "E-mail",
        "2. e-mail",
        "2. E-mail",
    ],
    "phone_number": [
        "2. Az Ön telefonszáma (0036-tal kezdve, szóközök nélkül!)",
        "Telefonszám",
    ],
    "company_name": [
        "Vállalkozás neve",
        "Cég neve",
        "Cégnév",
    ],
    "company_address": [
        "Vállalkozás székhelye:",
        "Cég székhelye",
    ],
    "tax_number": [
        "Vállalkozás adószáma:",
        "Cég adószáma",
    ],
    "bank_account_number": [
        "Vállalkozása bankszámla száma:",
    ],
    "billing_email": [
        "E-mail-cím",
        "E-mail",
    ],
}

TARGET_BILLING_FIELDS = (
    "company_name",
    "company_address",
    "tax_number",
    "bank_account_number",
    "billing_email",
)


@dataclass
class SourceRow:
    source: str
    priority: int
    row_number: int
    values: dict[str, str]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "#ref!", "n/a"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_name(value: Any) -> str:
    text = clean_text(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_email(value: Any) -> str:
    return clean_text(value).casefold()


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", clean_text(value))
    if digits.startswith("0036"):
        digits = "36" + digits[4:]
    elif digits.startswith("06"):
        digits = "36" + digits[2:]
    elif len(digits) == 9 and digits.startswith(("20", "30", "31", "50", "70")):
        digits = "36" + digits
    return digits


def normalize_courier_id(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = text.split(".", 1)[0]
    return re.sub(r"\D+", "", text)


def normalize_tax_number(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value)).upper()


def first_nonempty(row: dict[str, Any], aliases: Iterable[str]) -> str:
    for alias in aliases:
        value = clean_text(row.get(alias))
        if value:
            return value

    normalized_row = {
        normalize_name(header): value
        for header, value in row.items()
        if normalize_name(header)
    }
    for alias in aliases:
        value = clean_text(normalized_row.get(normalize_name(alias)))
        if value:
            return value
    return ""


def extract_source_values(row: dict[str, Any]) -> dict[str, str]:
    values = {
        field: first_nonempty(row, aliases)
        for field, aliases in FIELD_ALIASES.items()
    }
    values["courier_id"] = normalize_courier_id(values.get("courier_id"))
    values["tax_number"] = normalize_tax_number(values.get("tax_number"))
    return values


def load_google_credentials() -> Credentials:
    json_text = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    json_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    if json_text:
        try:
            info = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("A GOOGLE_SERVICE_ACCOUNT_JSON nem érvényes JSON.") from exc
        return Credentials.from_service_account_info(info, scopes=GOOGLE_SCOPES)

    if json_file:
        return Credentials.from_service_account_file(json_file, scopes=GOOGLE_SCOPES)

    raise RuntimeError(
        "Hiányzik a Google hitelesítés. Állítsd be a "
        "GOOGLE_SERVICE_ACCOUNT_FILE vagy GOOGLE_SERVICE_ACCOUNT_JSON változót."
    )


def read_google_rows() -> list[SourceRow]:
    client = gspread.authorize(load_google_credentials())
    all_rows: list[SourceRow] = []

    for config in SHEETS:
        spreadsheet = client.open_by_key(config["spreadsheet_id"])
        worksheet = spreadsheet.worksheet(config["worksheet"])
        rows = worksheet.get_all_values()

        headers = rows[0]

        records = []
        for values in rows[1:]:
            row = {}

            for i, header in enumerate(headers):
                key = header.strip()

                if not key:
                    key = f"column_{i}"

                # duplikált oszlopnevek kezelése
                if key in row:
                    n = 2
                    while f"{key}_{n}" in row:
                        n += 1
                    key = f"{key}_{n}"

                row[key] = values[i] if i < len(values) else ""

            records.append(row)

        for index, row in enumerate(records, start=2):
            values = extract_source_values(row)
            if not any(values.values()):
                continue
            all_rows.append(
                SourceRow(
                    source=config["source"],
                    priority=int(config["priority"]),
                    row_number=index,
                    values=values,
                )
            )

    return all_rows


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


def read_csv_rows(paths: list[str]) -> list[SourceRow]:
    all_rows: list[SourceRow] = []
    for path_text in paths:
        path = Path(path_text).expanduser()
        handle, reader = open_csv_dict_reader(path)
        with handle:
            for index, row in enumerate(reader, start=2):
                values = extract_source_values(dict(row))
                if not any(values.values()):
                    continue
                all_rows.append(
                    SourceRow(
                        source=f"csv:{path.name}",
                        priority=300,
                        row_number=index,
                        values=values,
                    )
                )
    return all_rows


class SupabaseRest:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
        if not self.url or not self.key:
            raise RuntimeError("Hiányos Supabase konfiguráció.")

        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def get_all_couriers(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.url}/rest/v1/courier_master",
            headers=self.headers,
            params={
                "select": (
                    "courier_id,courier_name,phone_number,email,"
                    "warehouse_name,source_name,organization_id,dsp_id,active,"
                    "company_name,company_address,tax_number,"
                    "bank_account_number,billing_email,"
                    "billing_data_source,billing_data_updated_at"
                ),
                "limit": "10000",
            },
            timeout=60,
        )
        self._raise_for_error(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Váratlan Supabase-válasz a courier_master lekérésekor.")
        return payload

    def patch_courier(self, courier_id: int, payload: dict[str, Any]) -> None:
        headers = {
            **self.headers,
            "Prefer": "return=minimal",
        }
        response = requests.patch(
            f"{self.url}/rest/v1/courier_master",
            headers=headers,
            params={"courier_id": f"eq.{courier_id}"},
            json=payload,
            timeout=30,
        )
        self._raise_for_error(response)

    def upsert_couriers(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        response = requests.post(
            f"{self.url}/rest/v1/courier_master",
            headers=headers,
            params={"on_conflict": "courier_id"},
            json=rows,
            timeout=60,
        )
        self._raise_for_error(response)

    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        body = response.text[:2000]
        raise RuntimeError(
            f"Supabase hiba: HTTP {response.status_code}: {body}"
        )


def unique_index(
    couriers: list[dict[str, Any]],
    value_getter,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for courier in couriers:
        key = value_getter(courier)
        if key:
            grouped[key].append(courier)
    return {
        key: rows[0]
        for key, rows in grouped.items()
        if len(rows) == 1
    }


def build_courier_indexes(couriers: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "id": unique_index(couriers, lambda row: normalize_courier_id(row.get("courier_id"))),
        "email": unique_index(couriers, lambda row: normalize_email(row.get("email"))),
        "phone": unique_index(couriers, lambda row: normalize_phone(row.get("phone_number"))),
        "name": unique_index(couriers, lambda row: normalize_name(row.get("courier_name"))),
    }


def match_courier(
    source: SourceRow,
    indexes: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    courier_id = normalize_courier_id(source.values.get("courier_id"))
    if courier_id and courier_id in indexes["id"]:
        return indexes["id"][courier_id], "courier_id"

    email = normalize_email(source.values.get("email"))
    if email and email in indexes["email"]:
        return indexes["email"][email], "email"

    phone = normalize_phone(source.values.get("phone_number"))
    if phone and phone in indexes["phone"]:
        return indexes["phone"][phone], "phone"

    name = normalize_name(source.values.get("courier_name"))
    if name and name in indexes["name"]:
        return indexes["name"][name], "name"

    return None, ""


def merge_candidates(
    rows: list[SourceRow],
    couriers: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], list[SourceRow]]:
    indexes = build_courier_indexes(couriers)
    matched: dict[int, list[tuple[SourceRow, str]]] = defaultdict(list)
    unmatched: list[SourceRow] = []

    for source in rows:
        courier, method = match_courier(source, indexes)
        if courier is None:
            unmatched.append(source)
            continue
        matched[int(courier["courier_id"])].append((source, method))

    result: dict[int, dict[str, Any]] = {}

    for courier_id, candidates in matched.items():
        candidates.sort(key=lambda item: item[0].priority, reverse=True)
        courier = next(row for row in couriers if int(row["courier_id"]) == courier_id)

        patch: dict[str, Any] = {}
        provenance: list[str] = []

        for field in TARGET_BILLING_FIELDS:
            # Meglévő értéket üres adattal soha nem írunk felül.
            selected_value = ""
            selected_source = ""
            for source, _method in candidates:
                candidate_value = clean_text(source.values.get(field))
                if candidate_value:
                    selected_value = candidate_value
                    selected_source = source.source
                    break

            current_value = clean_text(courier.get(field))
            if selected_value and selected_value != current_value:
                patch[field] = selected_value
                provenance.append(f"{field}:{selected_source}")

        # Az alap elérhetőségeket csak akkor pótoljuk, ha jelenleg hiányoznak.
        for field in ("email", "phone_number"):
            if clean_text(courier.get(field)):
                continue
            for source, _method in candidates:
                value = clean_text(source.values.get(field))
                if value:
                    patch[field] = value
                    provenance.append(f"{field}:{source.source}")
                    break

        if patch:
            patch["billing_data_source"] = ", ".join(sorted(set(provenance)))
            patch["billing_data_updated_at"] = datetime.now(timezone.utc).isoformat()
            result[courier_id] = {
                "courier": courier,
                "patch": patch,
                "matches": [
                    {
                        "source": source.source,
                        "row": source.row_number,
                        "method": method,
                    }
                    for source, method in candidates
                ],
            }

    return result, unmatched


def build_insert_candidates(
    unmatched: list[SourceRow],
    couriers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[SourceRow]]:
    existing_ids = {
        normalize_courier_id(courier.get("courier_id"))
        for courier in couriers
        if normalize_courier_id(courier.get("courier_id"))
    }
    by_id: dict[str, SourceRow] = {}
    skipped: list[SourceRow] = []

    for source in unmatched:
        courier_id = normalize_courier_id(source.values.get("courier_id"))
        if not courier_id or courier_id in existing_ids:
            skipped.append(source)
            continue
        current = by_id.get(courier_id)
        if current is None or source.priority > current.priority:
            by_id[courier_id] = source

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for courier_id, source in sorted(by_id.items(), key=lambda item: int(item[0])):
        values = source.values
        courier_name = clean_text(values.get("courier_name"))
        if not courier_name:
            skipped.append(source)
            continue

        row: dict[str, Any] = {
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "phone_number": clean_text(values.get("phone_number")),
            "email": clean_text(values.get("email")),
            "warehouse_name": clean_text(values.get("warehouse_name")),
            "source_name": source.source,
            "dsp_id": "JIT",
            "active": True,
            "response_json": {
                "imported_from": "sync_courier_billing_data",
                "source": source.source,
                "source_row": source.row_number,
            },
            "fetched_at": now,
            "updated_at": now,
            "billing_data_source": source.source,
            "billing_data_updated_at": now,
        }
        for field in TARGET_BILLING_FIELDS:
            value = clean_text(values.get(field))
            if value:
                row[field] = value

        rows.append(row)

    return rows, skipped


def ensure_required_environment() -> None:
    missing = [
        name
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Hiányzó környezeti változó(k): " + ", ".join(missing)
        )


def print_preview(
    updates: dict[int, dict[str, Any]],
    unmatched: list[SourceRow],
    insert_candidates: list[dict[str, Any]],
) -> None:
    print(f"\nFrissítendő futárok száma: {len(updates)}")
    for courier_id, item in sorted(updates.items()):
        courier = item["courier"]
        fields = ", ".join(item["patch"].keys())
        print(f"  {courier_id} | {courier.get('courier_name')} | {fields}")

    print(f"\nFelvetelre varo uj courier_master sorok: {len(insert_candidates)}")
    for row in insert_candidates[:50]:
        print(
            f"  {row.get('courier_id')} | "
            f"{row.get('courier_name')} | "
            f"{row.get('email')} | "
            f"{row.get('phone_number')}"
        )
    if len(insert_candidates) > 50:
        print(f"  ... tovabbi {len(insert_candidates) - 50} sor")

    print(f"\nNem párosított forrássorok száma: {len(unmatched)}")
    for source in unmatched[:50]:
        print(
            f"  {source.source}:{source.row_number} | "
            f"{source.values.get('courier_id')} | "
            f"{source.values.get('courier_name')} | "
            f"{source.values.get('email')} | "
            f"{source.values.get('phone_number')}"
        )
    if len(unmatched) > 50:
        print(f"  ... további {len(unmatched) - 50} sor")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="A frissítések tényleges mentése Supabase-be.",
    )
    parser.add_argument(
        "--insert-missing",
        action="store_true",
        help=(
            "A courier_id-val rendelkezo, de courier_masterben meg nem levo "
            "futarok felvetele. Nev alapjan nem hoz letre uj sort."
        ),
    )
    parser.add_argument(
        "--csv-file",
        action="append",
        default=[],
        help=(
            "Google auth nelkuli import helyi CSV fajlbol. Tobbszor is megadhato. "
            "Ha meg van adva, a Google Sheets olvasas kimarad."
        ),
    )
    args = parser.parse_args()

    ensure_required_environment()

    print("Google Sheets adatok olvasása...")
    source_rows = read_csv_rows(args.csv_file) if args.csv_file else read_google_rows()
    print(f"Beolvasott forrássorok: {len(source_rows)}")

    supabase = SupabaseRest()
    print("courier_master olvasása...")
    couriers = supabase.get_all_couriers()
    print(f"Beolvasott futárok: {len(couriers)}")

    updates, unmatched = merge_candidates(source_rows, couriers)
    insert_candidates, skipped_unmatched = build_insert_candidates(unmatched, couriers)
    print_preview(updates, skipped_unmatched, insert_candidates)

    if not args.apply:
        print("\nDRY-RUN: nem történt adatbázis-módosítás.")
        print("Meglevo adatok frissitese: python sync_courier_billing_data.py --apply")
        print(
            "Frissites + uj courier_id-s futarok felvetele: "
            "python sync_courier_billing_data.py --apply --insert-missing"
        )
        return 0

    success = 0
    failures = 0
    for courier_id, item in sorted(updates.items()):
        try:
            supabase.patch_courier(courier_id, item["patch"])
            success += 1
            print(f"OK: {courier_id} | {item['courier'].get('courier_name')}")
        except Exception as exc:
            failures += 1
            print(
                f"HIBA: {courier_id} | "
                f"{item['courier'].get('courier_name')} | {exc}",
                file=sys.stderr,
            )

    inserted = 0
    if args.insert_missing and insert_candidates:
        try:
            supabase.upsert_couriers(insert_candidates)
            inserted = len(insert_candidates)
            print(f"OK: uj courier_master sorok felveve: {inserted}")
        except Exception as exc:
            failures += 1
            print(f"HIBA: uj courier_master sorok felvetele sikertelen | {exc}", file=sys.stderr)
    elif insert_candidates:
        print(
            "INFO: vannak uj felveheto futarok, de az --insert-missing nincs megadva, "
            "ezert nem lettek beszurva."
        )

    print(
        f"\nOsszesites: sikeres frissites: {success}, uj felvetel: {inserted}, "
        f"hibas: {failures}, nem parositott: {len(skipped_unmatched)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
