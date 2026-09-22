#!/usr/bin/env python3
"""Export Courier Hub courier identity rows to the ROBOTID Google Sheet."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google_client import open_spreadsheet  # noqa: E402
from resources.supabase_raw import (  # noqa: E402
    get_supabase_config,
    raise_for_supabase_error,
)


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 2086200160
VIEW_NAME = "vw_courier_hub_courier_identity"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "Frissítve",
    "JITT belső azonosító",
    "courierId",
    "Raktár",
    "Azonosító nélküli név",
    "name JSON",
    "phone",
    "email",
    "giritonPersonId",
    "registeredSince",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_identity_rows(limit: int = 10000) -> list[dict[str, Any]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")

    response = requests.get(
        f"{supabase_url}/rest/v1/{VIEW_NAME}",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params={
            "select": (
                "jitt_internal_id,courier_id,warehouse_code,"
                "name_without_identifier,name_json,phone_number,email,"
                "giriton_person_id,registered_since,registered_since_date,last_seen_at"
            ),
            "order": "warehouse_code.asc,name_without_identifier.asc,courier_id.asc",
            "limit": str(int(limit)),
        },
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def row_to_sheet_row(row: dict[str, Any], exported_at: str) -> list[Any]:
    return [
        exported_at,
        clean_text(row.get("jitt_internal_id")),
        row.get("courier_id") or "",
        clean_text(row.get("warehouse_code")),
        clean_text(row.get("name_without_identifier")),
        clean_text(row.get("name_json")),
        clean_text(row.get("phone_number")),
        clean_text(row.get("email")),
        clean_text(row.get("giriton_person_id")),
        clean_text(row.get("registered_since")),
    ]


def export_robot_id(dry_run: bool = False) -> int:
    rows = read_identity_rows()
    if dry_run:
        return len(rows)

    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    values = [
        HEADER,
        *[
            row_to_sheet_row(row, exported_at)
            for row in rows
        ],
    ]
    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    worksheet = spreadsheet.get_worksheet_by_id(WORKSHEET_GID)
    if worksheet is None:
        raise RuntimeError(f"Nem található worksheet gid={WORKSHEET_GID}.")

    worksheet.clear()
    worksheet.update(
        range_name="A1",
        values=values,
    )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = export_robot_id(dry_run=args.dry_run)
    print(
        f"COURIER_HUB_ROBOT_ID_SHEET rows={rows} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
