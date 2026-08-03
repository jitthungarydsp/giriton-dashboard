#!/usr/bin/env python3
"""Import Google Sheet bonus/malus rows into settlement courier adjustments.

Default source:
https://docs.google.com/spreadsheets/d/1G58HK2dyefsIOOBEZIlI9gDuAiFCe4zKHNgPYg3OiXM/edit?gid=629006360
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.google_auth import get_client
from resources.supabase_raw import get_supabase_config


DEFAULT_SHEET_ID = "1G58HK2dyefsIOOBEZIlI9gDuAiFCe4zKHNgPYg3OiXM"
DEFAULT_GID = 629006360
SOURCE_PREFIX = "google_bonus_malus"


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def slug(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "empty"


def money_int(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    text = text.replace("\xa0", "").replace(" ", "").replace("Ft", "").replace("ft", "")
    text = text.replace(",", ".")
    try:
        return int(round(float(text)))
    except ValueError:
        digits = re.sub(r"[^0-9.-]", "", text)
        return int(round(float(digits))) if digits else 0


def parse_sheet_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    patterns = [
        "%Y.%m.%d. %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d.",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def supabase_headers(prefer: str = "", schema: str = "settlement") -> dict[str, str]:
    _url, key = get_supabase_config()
    key = key.strip()
    if not key:
        raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY setting.")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def raise_for_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {response.text[:2000]}")


def supabase_url() -> str:
    url, _key = get_supabase_config()
    url = url.rstrip("/")
    if not url:
        raise RuntimeError("Missing SUPABASE_URL setting.")
    return url


def read_courier_master() -> dict[str, dict[str, str]]:
    response = requests.get(
        f"{supabase_url()}/rest/v1/courier_master",
        headers=supabase_headers(schema="public"),
        params={
            "select": "courier_id,courier_name,active",
            "limit": "10000",
        },
        timeout=60,
    )
    raise_for_response(response, "courier_master")
    by_name: dict[str, dict[str, str]] = {}
    for row in response.json() or []:
        courier_id = str(row.get("courier_id") or "").strip()
        courier_name = str(row.get("courier_name") or "").strip()
        if courier_id and courier_name:
            by_name[normalize_text(courier_name)] = {
                "courier_id": courier_id,
                "courier_name": courier_name,
            }
    return by_name


def worksheet_by_gid(sheet_id: str, gid: int):
    spreadsheet = get_client().open_by_key(sheet_id)
    for worksheet in spreadsheet.worksheets():
        if int(worksheet.id) == int(gid):
            return worksheet
    raise RuntimeError(f"Nincs worksheet ezzel a gid-del: {gid}")


def rows_from_sheet(sheet_id: str, gid: int) -> list[dict[str, Any]]:
    worksheet = worksheet_by_gid(sheet_id, gid)
    values = worksheet.get_all_values()
    result: list[dict[str, Any]] = []
    for row_number, row in enumerate(values[1:], start=2):
        padded = row + [""] * (8 - len(row))
        occurred_at = parse_sheet_datetime(padded[0])
        name = str(padded[1] or "").strip()
        raw_type = str(padded[2] or "").strip()
        reason = str(padded[3] or "").strip()
        malus = money_int(padded[4])
        bonus = money_int(padded[5])
        recorded_by = str(padded[6] or "").strip()
        transaction_id = str(padded[7] or "").strip()
        if not occurred_at or not name:
            continue
        if bonus <= 0 and malus <= 0:
            continue
        if bonus > 0:
            result.append({
                "row_number": row_number,
                "effective_date": occurred_at.date(),
                "courier_name": name,
                "adjustment_type": "bonus",
                "amount_huf": bonus,
                "note": reason,
                "recorded_by": recorded_by,
                "transaction_id": transaction_id,
                "raw_type": raw_type,
            })
        if malus > 0:
            result.append({
                "row_number": row_number,
                "effective_date": occurred_at.date(),
                "courier_name": name,
                "adjustment_type": "malus",
                "amount_huf": malus,
                "note": reason,
                "recorded_by": recorded_by,
                "transaction_id": transaction_id,
                "raw_type": raw_type,
            })
    return result


def source_key(sheet_id: str, gid: int, row: dict[str, Any]) -> str:
    transaction = slug(row.get("transaction_id") or f"row-{row.get('row_number')}")
    return ":".join([
        SOURCE_PREFIX,
        sheet_id,
        str(gid),
        transaction,
        slug(row.get("courier_name")),
        str(row.get("effective_date")),
        str(row.get("adjustment_type")),
        str(row.get("amount_huf")),
    ])


def existing_adjustments() -> dict[str, dict[str, Any]]:
    response = requests.get(
        f"{supabase_url()}/rest/v1/courier_settlement_adjustment",
        headers=supabase_headers(),
        params={
            "select": "id,source_key",
            "source_key": f"like.{SOURCE_PREFIX}:%",
            "limit": "10000",
        },
        timeout=60,
    )
    raise_for_response(response, "courier_settlement_adjustment existing")
    return {
        str(row.get("source_key") or ""): row
        for row in response.json() or []
        if str(row.get("source_key") or "")
    }


def adjustment_payload(row: dict[str, Any], courier: dict[str, str], key: str) -> dict[str, Any]:
    effective = row["effective_date"]
    valid_to = month_end(effective)
    note_parts = [str(row.get("note") or "").strip()]
    if row.get("transaction_id"):
        note_parts.append(f"Tranzakcio: {row['transaction_id']}")
    if row.get("raw_type"):
        note_parts.append(f"Sheet tipus: {row['raw_type']}")
    return {
        "session_id": None,
        "courier_id": courier["courier_id"],
        "adjustment_type": row["adjustment_type"],
        "amount_huf": int(row["amount_huf"]),
        "effective_date": effective.isoformat(),
        "valid_from": effective.isoformat(),
        "valid_to": valid_to.isoformat(),
        "source_key": key,
        "note": " | ".join(part for part in note_parts if part) or None,
        "is_active": True,
        "deleted_at": None,
        "deleted_by": None,
        "created_by": str(row.get("recorded_by") or "google-sheet"),
        "updated_at": datetime.utcnow().isoformat(),
    }


def insert_adjustment(payload: dict[str, Any]) -> None:
    response = requests.post(
        f"{supabase_url()}/rest/v1/courier_settlement_adjustment",
        headers=supabase_headers("return=minimal"),
        json=payload,
        timeout=60,
    )
    raise_for_response(response, "courier_settlement_adjustment insert")


def update_adjustment(row_id: str, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload.pop("created_by", None)
    response = requests.patch(
        f"{supabase_url()}/rest/v1/courier_settlement_adjustment",
        headers=supabase_headers("return=minimal"),
        params={"id": f"eq.{row_id}"},
        json=payload,
        timeout=60,
    )
    raise_for_response(response, "courier_settlement_adjustment update")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--gid", type=int, default=DEFAULT_GID)
    parser.add_argument("--from-date", help="Inclusive YYYY-MM-DD filter.")
    parser.add_argument("--to-date", help="Inclusive YYYY-MM-DD filter.")
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    to_date = date.fromisoformat(args.to_date) if args.to_date else None

    couriers = read_courier_master()
    sheet_rows = rows_from_sheet(args.sheet_id, args.gid)
    if from_date:
        sheet_rows = [row for row in sheet_rows if row["effective_date"] >= from_date]
    if to_date:
        sheet_rows = [row for row in sheet_rows if row["effective_date"] <= to_date]
    existing = existing_adjustments()

    prepared: list[tuple[str, dict[str, Any]]] = []
    unmatched: list[str] = []
    skipped = 0
    for row in sheet_rows:
        courier = couriers.get(normalize_text(row["courier_name"]))
        if not courier:
            unmatched.append(f"{row['row_number']}: {row['courier_name']}")
            continue
        key = source_key(args.sheet_id, args.gid, row)
        payload = adjustment_payload(row, courier, key)
        prepared.append((key, payload))

    inserted = 0
    updated = 0
    if args.apply:
        for key, payload in prepared:
            current = existing.get(key)
            if current and current.get("id"):
                update_adjustment(str(current["id"]), payload)
                updated += 1
            else:
                insert_adjustment(payload)
                inserted += 1
    else:
        inserted = sum(1 for key, _payload in prepared if key not in existing)
        updated = sum(1 for key, _payload in prepared if key in existing)

    skipped = len(sheet_rows) - len(prepared)
    print("Google bonus/malus import")
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    print(f"Sheet rows with amount: {len(sheet_rows)}")
    print(f"Prepared: {len(prepared)} | insert: {inserted} | update: {updated} | unmatched/skipped: {skipped}")
    if unmatched:
        print("Unmatched couriers:")
        for item in unmatched[:50]:
            print(f"  - {item}")
        if len(unmatched) > 50:
            print(f"  ... +{len(unmatched) - 50} tovabbi")
        return 2 if args.apply else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
