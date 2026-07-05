import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from google_client import open_spreadsheet
from resources.giriton_shifts_db import (
    build_db_rows,
    upsert_giriton_shift_rows,
)


TARGET_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
GIRITON_SHEET_NAME = "Giriton"


def load_rows_from_sheet():
    spreadsheet = open_spreadsheet(
        TARGET_SPREADSHEET_ID
    )
    worksheet = spreadsheet.worksheet(
        GIRITON_SHEET_NAME
    )
    values = worksheet.get_all_values()

    if not values:
        return []

    rows = []

    for row in values[1:]:
        if not any(str(cell or "").strip() for cell in row):
            continue

        cells = list(row) + [""] * 8
        rows.append([
            cells[0],
            cells[1],
            cells[2],
            cells[3],
            cells[4],
            cells[5],
            cells[6],
            cells[7],
        ])

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Meglevo Giriton sheet feltoltes Supabase giriton_shifts_raw tablaba."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak beolvassa es normalizalja, DB-be nem ir.",
    )
    args = parser.parse_args()

    rows = load_rows_from_sheet()
    db_rows = build_db_rows(
        rows
    )

    print(
        f"Giriton sheet sorok: {len(rows)}"
    )
    print(
        f"DB-re elokeszitett sorok: {len(db_rows)}"
    )

    if db_rows:
        sample = db_rows[0]
        print(
            f"MINTA {sample.get('work_date')} {sample.get('warehouse')} "
            f"{sample.get('start_time')} {sample.get('courier_name')} "
            f"#{sample.get('courier_id') or ''}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    result = upsert_giriton_shift_rows(
        rows
    )
    print(
        f"DB feltoltes: {result}"
    )


if __name__ == "__main__":
    main()
