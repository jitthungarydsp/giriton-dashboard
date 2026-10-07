import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from resources.foglalasok_db import (
    FOGLALASOK_SHEET_NAME,
    SOURCE_SPREADSHEET_ID,
    build_db_rows,
    dedupe_foglalasok_rows,
    upsert_foglalasok_rows,
)
from resources.google_sheets_values import read_sheet_values


def load_values_from_sheet():
    return read_sheet_values(
        SOURCE_SPREADSHEET_ID,
        FOGLALASOK_SHEET_NAME,
    )


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
    deduped_rows = dedupe_foglalasok_rows(
        rows
    )

    print(
        f"Foglalasok sheet sorok: {max(len(values) - 1, 0)}"
    )
    print(
        f"DB-re elokeszitett sorok: {len(rows)}"
    )
    print(
        f"DB-re kuldendo egyedi sorok: {len(deduped_rows)} "
        f"(duplikalt kulcsok: {len(rows) - len(deduped_rows)})"
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
        values,
        rows,
    )
    print(
        f"DB feltoltes: {result}"
    )


if __name__ == "__main__":
    main()
