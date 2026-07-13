import argparse
from datetime import datetime
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from google_client import open_spreadsheet
from resources.foglalasok_db import SOURCE_SPREADSHEET_ID
from resources.muszakpro_db import (
    CAPACITY_SOURCE_NAME,
    CAPACITY_TABLE,
    clean,
    get_headers,
    normalize_time,
    optional_int,
)
from resources.supabase_raw import raise_for_supabase_error


BEO_SHEET_NAME = "beo"


def parse_sheet_date(value):
    text = clean(value)

    if not text:
        return ""

    for pattern in [
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y.%m.%d.",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d.%m.%Y.",
        "%m/%d/%Y",
    ]:
        try:
            return datetime.strptime(
                text,
                pattern,
            ).date().isoformat()
        except ValueError:
            pass

    if len(text) >= 10 and text[4] in [".", "-"]:
        return text[:10].replace(".", "-")

    return ""


def build_capacity_rows(values):
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows = []

    for source_row, row in enumerate(values[1:], start=2):
        cells = list(row) + [""] * 8
        work_date = parse_sheet_date(
            cells[0]
        )
        shift_text = normalize_time(
            cells[1]
        )
        warehouse = clean(
            cells[5]
        ) or "BUD1"

        if not work_date or not shift_text:
            continue

        limit_count = optional_int(
            cells[2],
            0,
        )
        booked_count = optional_int(
            cells[3],
            0,
        )
        active_raw = clean(
            cells[4]
        )
        active = active_raw not in ["0", "FALSE", "false", "NEM", "nem"]
        slack_quota = optional_int(
            cells[6],
            0,
        )

        rows.append({
            "source_name": CAPACITY_SOURCE_NAME,
            "source_row": source_row,
            "work_date": work_date,
            "shift_text": shift_text,
            "warehouse": warehouse,
            "limit_count": limit_count,
            "booked_count": booked_count,
            "active": active,
            "slack_quota": slack_quota,
            "response_json": {
                "source_row": source_row,
                "raw": row,
            },
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
        })

    return rows


def load_values_from_sheet(spreadsheet_id):
    spreadsheet = open_spreadsheet(
        spreadsheet_id
    )
    worksheet = spreadsheet.worksheet(
        BEO_SHEET_NAME
    )
    return worksheet.get_all_values()


def upsert_capacity_rows(rows):
    if not rows:
        return {
            "rows": 0,
            "status": "empty",
        }

    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/{CAPACITY_TABLE}"
        "?on_conflict=source_name,work_date,shift_text,warehouse"
    )
    headers = {
        **headers,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    for index in range(0, len(rows), 500):
        response = requests.post(
            endpoint,
            headers=headers,
            json=rows[index:index + 500],
            timeout=60,
        )
        raise_for_supabase_error(response)

    return {
        "rows": len(rows),
        "status": "ok",
    }


def main():
    parser = argparse.ArgumentParser(
        description="MuszakPro beo kapacitasok feltoltese Supabase DB-be."
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=SOURCE_SPREADSHEET_ID,
        help="Forras Google Spreadsheet ID. Alapertelmezett: regi MuszakPro munkafuzet.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak beolvassa es normalizalja, DB-be nem ir.",
    )
    args = parser.parse_args()

    values = load_values_from_sheet(
        args.spreadsheet_id
    )
    rows = build_capacity_rows(
        values
    )

    print(
        f"beo sheet sorok: {max(len(values) - 1, 0)}"
    )
    print(
        f"DB-re elokeszitett kapacitas sorok: {len(rows)}"
    )

    if rows:
        sample = rows[0]
        print(
            f"MINTA {sample.get('work_date')} {sample.get('warehouse')} "
            f"{sample.get('shift_text')} limit={sample.get('limit_count')} "
            f"booked={sample.get('booked_count')}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    result = upsert_capacity_rows(
        rows
    )
    print(
        f"DB feltoltes: {result}"
    )


if __name__ == "__main__":
    main()
