import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from google_client import open_spreadsheet
from resources.dsp_dashboard_statistics import SPREADSHEET_ID as TARGET_SPREADSHEET_ID
from resources.source_sheet_sync import SOURCE_SPREADSHEET_ID


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "courier-master-sync"


def get_required_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value.rstrip("/")


def build_fetch_drivers_url():
    return (
        f"{KIFLI_API_BASE_URL}/"
        f"fetch-drivers"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )


def fetch_drivers():
    url = build_fetch_drivers_url()
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return url, response.status_code, response.json()


def clean_text(value):
    return str(value or "").strip()


def normalize_email(value):
    return clean_text(value).casefold()


def normalize_name(value):
    return " ".join(
        clean_text(value).casefold().split()
    )


def row_value(row, index):
    if index is None or index >= len(row):
        return ""

    return clean_text(row[index])


def header_index(header, aliases):
    normalized = {
        normalize_name(value): index
        for index, value in enumerate(header)
    }

    for alias in aliases:
        index = normalized.get(
            normalize_name(alias)
        )

        if index is not None:
            return index

    return None


def merge_record(records, courier_id, data):
    if courier_id in [None, ""]:
        return

    courier_id = int(courier_id)
    current = records.setdefault(
        courier_id,
        {
            "courier_id": courier_id,
            "courier_name": "",
            "phone_number": "",
            "email": "",
            "warehouse_name": "",
            "active": None,
            "response_json": {},
        },
    )

    for key in [
        "courier_name",
        "phone_number",
        "email",
        "warehouse_name",
    ]:
        value = clean_text(
            data.get(key)
        )

        if value:
            current[key] = value

    if data.get("active") is not None:
        current["active"] = bool(
            data.get("active")
        )

    if data.get("response_json"):
        current["response_json"] = data.get("response_json")


def read_sheet_values(spreadsheet_id, sheet_name):
    try:
        return open_spreadsheet(
            spreadsheet_id
        ).worksheet(sheet_name).get_all_values()
    except Exception:
        return []


def build_api_records(response_json, records):
    for driver in response_json.get("drivers", []) or []:
        courier_id = driver.get("driver_id")
        personal_info = driver.get("personal_info") or {}

        merge_record(
            records,
            courier_id,
            {
                "courier_name": personal_info.get("name"),
                "phone_number": personal_info.get("contact_number"),
                "email": personal_info.get("contact_email"),
                "warehouse_name": personal_info.get("warehouse_name"),
                "active": driver.get("active"),
                "response_json": driver,
            },
        )


def build_dsp_driver_records(records):
    rows = read_sheet_values(
        TARGET_SPREADSHEET_ID,
        "DSP_Drivers",
    )

    if not rows:
        return

    header = rows[0]
    id_index = header_index(
        header,
        ["driver_id", "courier_id", "Courier ID", "ID"],
    )
    name_index = header_index(
        header,
        ["name", "nev", "név", "courier_name"],
    )
    email_index = header_index(
        header,
        ["contact_email", "email", "e-mail"],
    )
    phone_index = header_index(
        header,
        ["contact_number", "phone", "telefon", "telefonszam", "telefonszám"],
    )
    warehouse_index = header_index(
        header,
        ["warehouse_name", "warehouse", "raktar", "raktár"],
    )

    for row in rows[1:]:
        courier_id = row_value(
            row,
            id_index,
        )

        if not courier_id:
            continue

        merge_record(
            records,
            courier_id,
            {
                "courier_name": row_value(row, name_index),
                "phone_number": row_value(row, phone_index),
                "email": row_value(row, email_index),
                "warehouse_name": row_value(row, warehouse_index),
            },
        )


def build_user_sheet_records(records):
    rows = read_sheet_values(
        SOURCE_SPREADSHEET_ID,
        "Felhasznalok",
    )
    by_email = {
        normalize_email(record.get("email")): courier_id
        for courier_id, record in records.items()
        if normalize_email(record.get("email"))
    }
    by_name = {
        normalize_name(record.get("courier_name")): courier_id
        for courier_id, record in records.items()
        if normalize_name(record.get("courier_name"))
    }

    for row in rows:
        for name_index, email_index in [
            (0, 3),
            (6, 7),
            (10, 11),
        ]:
            name = row_value(
                row,
                name_index,
            )
            email = row_value(
                row,
                email_index,
            )

            if not name or normalize_name(name) in ["nev", "név"]:
                continue

            courier_id = (
                by_email.get(normalize_email(email))
                or by_name.get(normalize_name(name))
            )

            if not courier_id:
                continue

            merge_record(
                records,
                courier_id,
                {
                    "courier_name": name,
                    "email": email,
                },
            )


def records_to_rows(records):
    rows = []
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    for record in records.values():
        if not record.get("courier_name"):
            continue

        rows.append({
            "courier_id": int(record.get("courier_id")),
            "courier_name": clean_text(record.get("courier_name")),
            "phone_number": clean_text(record.get("phone_number")),
            "email": clean_text(record.get("email")),
            "warehouse_name": clean_text(record.get("warehouse_name")),
            "source_name": SOURCE_NAME,
            "organization_id": ORGANIZATION_ID,
            "dsp_id": DSP_ID,
            "active": record.get("active"),
            "response_json": record.get("response_json") or {},
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
        })

    return sorted(
        rows,
        key=lambda item: (
            item.get("courier_name") or "",
            item.get("courier_id") or 0,
        ),
    )


def build_rows(response_json):
    records = {}
    build_api_records(
        response_json,
        records,
    )
    build_dsp_driver_records(
        records,
    )
    build_user_sheet_records(
        records,
    )

    return records_to_rows(
        records
    )


def sync_courier_master(dry_run=False):
    _url, status_code, response_json = fetch_drivers()
    rows = build_rows(
        response_json
    )

    result = {
        "api_status": status_code,
        "rows": len(rows),
        "dry_run": dry_run,
    }

    if not dry_run:
        upsert_rows(
            rows
        )

    return result


def upsert_rows(rows):
    if not rows:
        return

    supabase_url = get_required_env("SUPABASE_URL")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?on_conflict=courier_id"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=60,
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Courier master feltoltes Supabase DB-be."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak API-t hiv, DB-be nem ir.",
    )
    args = parser.parse_args()
    _url, status_code, response_json = fetch_drivers()
    rows = build_rows(
        response_json
    )

    print(
        f"API status: {status_code}"
    )
    print(
        f"Courier master sorok: {len(rows)}"
    )

    for row in rows[:5]:
        print(
            f"MINTA #{row['courier_id']} {row['courier_name']} "
            f"{row['warehouse_name']} {row['phone_number']}"
        )

    if args.dry_run:
        print(
            "DRY RUN, DB iras kihagyva."
        )
        return

    upsert_rows(
        rows
    )
    print(
        f"DB feltoltes: {len(rows)} sor"
    )


if __name__ == "__main__":
    main()
