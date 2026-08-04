#!/usr/bin/env python3
"""Google Form Idobelyeg -> courier_master.work_start_date sync.

Dry-run alapbol:
    python scripts/sync_courier_work_start_dates.py

Mentes:
    python scripts/sync_courier_work_start_dates.py --apply

Meglevo work_start_date felulirasa:
    python scripts/sync_courier_work_start_dates.py --apply --overwrite
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resources.google_auth import get_client
from resources.supabase_raw import get_supabase_config


SHEETS = [
    {
        "spreadsheet_id": "1dHzIpTMwSud2oCXbuLUsUHmCgMwHaa1O75e7kUmLiKo",
        "worksheet_gid": 2146041807,
        "source": "google_form_new",
        "priority": 200,
    },
    {
        "spreadsheet_id": "14H9c5InkUbWlMMkbFVXYQay4UMiYo0opu4wk8rXHWvY",
        "worksheet_gid": 237983567,
        "source": "google_form_legacy",
        "priority": 100,
    },
]


@dataclass(frozen=True)
class SourceRecord:
    source: str
    spreadsheet_id: str
    worksheet_gid: int
    row_number: int
    timestamp_date: date
    timestamp_raw: str
    courier_id: str
    courier_name: str
    email: str
    phone: str


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.casefold() in {"nan", "none", "null", "#ref!", "n/a"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = text.split(".", 1)[0]
    return re.sub(r"\D+", "", text)


def parse_timestamp_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    for date_format in ("%Y.%m.%d. %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        parsed = pd.to_datetime(text, format=date_format, errors="coerce")
        if not pd.isna(parsed):
            return parsed.date()
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def supabase_config() -> tuple[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    return url.rstrip("/"), key


def supabase_headers(prefer: str = "") -> dict[str, str]:
    _url, key = supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def raise_for_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {response.text[:2000]}")


def find_column(headers: list[str], predicates: list[Any]) -> int | None:
    normalized = [normalize_text(header) for header in headers]
    for predicate in predicates:
        for index, value in enumerate(normalized):
            if predicate(value):
                return index
    return None


def cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return clean_text(row[index])


def read_sheet_records(config: dict[str, Any]) -> list[SourceRecord]:
    worksheet = get_client().open_by_key(config["spreadsheet_id"]).get_worksheet_by_id(config["worksheet_gid"])
    values = worksheet.get_all_values()
    if not values:
        return []

    header_index = next(
        (
            index
            for index, row in enumerate(values[:20])
            if any(normalize_text(cell_value) in {"idobelyeg", "timestamp", "kezdo idopont"} for cell_value in row)
        ),
        0,
    )
    headers = values[header_index]
    timestamp_index = find_column(headers, [
        lambda value: value == "idobelyeg",
        lambda value: value == "timestamp",
        lambda value: value == "kezdo idopont",
    ])
    courier_id_index = find_column(headers, [
        lambda value: value in {"courier id", "futar id", "futar azonosito", "usernumber", "id"},
    ])
    name_index = find_column(headers, [
        lambda value: "vezeteknev" in value and "keresztnev" in value and "anyja" not in value,
        lambda value: value in {"nev", "teljes nev", "futar neve"},
        lambda value: "teljes neve" in value,
        lambda value: "alairo" in value and "nev" in value,
    ])
    email_index = find_column(headers, [
        lambda value: value in {"e mail cim", "e mail", "email"},
        lambda value: "mail" in value,
    ])
    phone_index = find_column(headers, [
        lambda value: "telefonszam" in value or value == "telefon",
    ])
    status_index = find_column(headers, [
        lambda value: value == "statusza" or value == "statusz",
    ])

    records: list[SourceRecord] = []
    for row_number, row in enumerate(values[header_index + 1 :], start=header_index + 2):
        timestamp_raw = cell(row, timestamp_index)
        timestamp_date = parse_timestamp_date(timestamp_raw)
        if not timestamp_date:
            continue
        status_key = normalize_text(cell(row, status_index))
        if "duplik" in status_key:
            continue
        record = SourceRecord(
            source=str(config["source"]),
            spreadsheet_id=str(config["spreadsheet_id"]),
            worksheet_gid=int(config["worksheet_gid"]),
            row_number=row_number,
            timestamp_date=timestamp_date,
            timestamp_raw=timestamp_raw,
            courier_id=normalize_courier_id(cell(row, courier_id_index)),
            courier_name=clean_text(cell(row, name_index)),
            email=normalize_email(cell(row, email_index)),
            phone=normalize_phone(cell(row, phone_index)),
        )
        if any([record.courier_id, record.courier_name, record.email, record.phone]):
            records.append(record)
    return records


def read_source_records() -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for config in SHEETS:
        records.extend(read_sheet_records(config))
    return records


def read_courier_master() -> list[dict[str, Any]]:
    url, _key = supabase_config()
    response = requests.get(
        f"{url}/rest/v1/courier_master",
        headers=supabase_headers(),
        params={
            "select": "courier_id,courier_name,email,billing_email,phone_number,work_start_date",
            "limit": "20000",
        },
        timeout=60,
    )
    raise_for_response(response, "courier_master")
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("A courier_master valasza nem lista.")
    return payload


def unique_index(rows: list[dict[str, Any]], value_getter: Any) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = value_getter(row)
        if key:
            grouped[key].append(row)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def build_indexes(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "id": unique_index(rows, lambda row: normalize_courier_id(row.get("courier_id"))),
        "email": unique_index(rows, lambda row: normalize_email(row.get("email"))),
        "billing_email": unique_index(rows, lambda row: normalize_email(row.get("billing_email"))),
        "phone": unique_index(rows, lambda row: normalize_phone(row.get("phone_number"))),
        "name": unique_index(rows, lambda row: normalize_text(row.get("courier_name"))),
    }


def match_courier(record: SourceRecord, indexes: dict[str, dict[str, dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    if record.courier_id and record.courier_id in indexes["id"]:
        return indexes["id"][record.courier_id], "courier_id"
    if record.email and record.email in indexes["email"]:
        return indexes["email"][record.email], "email"
    if record.email and record.email in indexes["billing_email"]:
        return indexes["billing_email"][record.email], "billing_email"
    if record.phone and record.phone in indexes["phone"]:
        return indexes["phone"][record.phone], "phone"
    name_key = normalize_text(record.courier_name)
    if name_key and name_key in indexes["name"]:
        return indexes["name"][name_key], "name"
    return None, ""


def choose_record(records: list[SourceRecord], prefer: str) -> SourceRecord:
    reverse = prefer == "latest"
    return sorted(records, key=lambda item: (item.timestamp_date, item.source, item.row_number), reverse=reverse)[0]


def build_updates(records: list[SourceRecord], couriers: list[dict[str, Any]], prefer: str, overwrite: bool) -> tuple[list[dict[str, Any]], list[SourceRecord]]:
    indexes = build_indexes(couriers)
    by_courier: dict[str, list[SourceRecord]] = defaultdict(list)
    unmatched: list[SourceRecord] = []

    for record in records:
        courier, _match_method = match_courier(record, indexes)
        if not courier:
            unmatched.append(record)
            continue
        courier_id = normalize_courier_id(courier.get("courier_id"))
        if courier_id:
            by_courier[courier_id].append(record)

    courier_by_id = {
        normalize_courier_id(row.get("courier_id")): row
        for row in couriers
        if normalize_courier_id(row.get("courier_id"))
    }
    updates: list[dict[str, Any]] = []
    for courier_id, candidate_records in sorted(by_courier.items()):
        courier = courier_by_id.get(courier_id) or {}
        selected = choose_record(candidate_records, prefer)
        current_date = clean_text(courier.get("work_start_date"))
        selected_date = selected.timestamp_date.isoformat()
        if current_date and current_date[:10] == selected_date:
            continue
        if current_date and not overwrite:
            continue
        updates.append(
            {
                "courier_id": courier_id,
                "courier_name": clean_text(courier.get("courier_name")),
                "current_work_start_date": current_date[:10] if current_date else "",
                "new_work_start_date": selected_date,
                "source": selected.source,
                "source_row": selected.row_number,
                "source_timestamp": selected.timestamp_raw,
                "candidate_count": len(candidate_records),
            }
        )
    return updates, unmatched


def apply_updates(updates: list[dict[str, Any]]) -> int:
    url, _key = supabase_config()
    written = 0
    for update in updates:
        payload = {
            "work_start_date": update["new_work_start_date"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        response = requests.patch(
            f"{url}/rest/v1/courier_master",
            headers=supabase_headers("return=minimal"),
            params={"courier_id": f"eq.{update['courier_id']}"},
            json=payload,
            timeout=30,
        )
        raise_for_response(response, f"courier_master update {update['courier_id']}")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Form Idobelyeg -> courier_master.work_start_date")
    parser.add_argument("--apply", action="store_true", help="Ment Supabase-be. Enelkul csak dry-run.")
    parser.add_argument("--overwrite", action="store_true", help="Meglevo work_start_date felulirasa.")
    parser.add_argument("--prefer", choices=["earliest", "latest"], default="earliest", help="Tobb forras eseten melyik Idobelyeg legyen a nyertes.")
    args = parser.parse_args()

    records = read_source_records()
    couriers = read_courier_master()
    updates, unmatched = build_updates(records, couriers, args.prefer, args.overwrite)

    print("Jogviszony kezdet sync")
    print(f"Forras sorok Idobelyeggel: {len(records)}")
    print(f"Courier master sorok: {len(couriers)}")
    print(f"Nem parositott forras sorok: {len(unmatched)}")
    print(f"Frissitendo courier_master sorok: {len(updates)}")
    if updates:
        print("Minta frissitesek:")
        for update in updates[:20]:
            print(
                f"  {update['courier_id']} | {update['courier_name']} | "
                f"{update['current_work_start_date'] or '-'} -> {update['new_work_start_date']} | "
                f"{update['source']} row={update['source_row']}"
            )
    if not args.apply:
        print("DRY-RUN: menteshez add meg: --apply")
        return 0
    written = apply_updates(updates)
    print(f"OK: frissitett courier_master sorok: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
