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
from resources.foglalasok_db import (
    FOGLALASOK_SHEET_NAME,
    SOURCE_SPREADSHEET_ID,
    build_db_rows,
    upsert_foglalasok_rows,
)


def load_values_from_sheet():
    spreadsheet = open_spreadsheet(
        SOURCE_SPREADSHEET_ID
    )
    worksheet = spreadsheet.worksheet(
        FOGLALASOK_SHEET_NAME
    )
    return worksheet.get_all_values()


def main():
    parser = argparse.ArgumentParser(
        description="Foglalasok Google Sheet feltoltes Supabase DB-be."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak beolvassa es normalizalja, DB-be nem ir.",
    )
    args = parser.parse_args()

    values = load_values_from_sheet()
    rows = build_db_rows(
        values
    )

    print(
        f"Foglalasok sheet sorok: {max(len(values) - 1, 0)}"
    )
    print(
        f"DB-re elokeszitett sorok: {len(rows)}"
    )

    if rows:
        sample = rows[0]
        print(
            f"MINTA {sample.get('work_date')} {sample.get('shift_text')} "
            f"{sample.get('email')} #{sample.get('courier_id') or ''}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    result = upsert_foglalasok_rows(
        values
    )
    print(
        f"DB feltoltes: {result}"
    )


if __name__ == "__main__":
    main()
