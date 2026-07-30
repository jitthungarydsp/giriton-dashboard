import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from resources.shift_comparison_db import (
    delete_shift_comparison_range,
    upsert_shift_comparison_rows,
)
from resources.shift_reconciliation_sheet import (
    LOCAL_TIMEZONE,
    build_records_for_date,
)


def parse_start_date(value):
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()

    return datetime.now(LOCAL_TIMEZONE).date()


def collect_records(start_date, days):
    records = []

    for offset in range(days):
        work_date = (
            start_date + timedelta(days=offset)
        ).isoformat()
        daily_records = build_records_for_date(
            work_date
        )
        records.extend(
            daily_records
        )
        print(
            f"{work_date}: {len(daily_records)} sor"
        )

    return records


def main():
    parser = argparse.ArgumentParser(
        description="MuszakPro vs Giriton osszehasonlitas feltoltese Supabase DB-be."
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Elso nap YYYY-MM-DD formatumban. Alapertelmezes: mai nap.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="Hany napot epitsen ujra.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak kiirja az eredmenyt, DB-be nem ir.",
    )
    args = parser.parse_args()

    start_date = parse_start_date(
        args.start_date
    )
    records = collect_records(
        start_date,
        max(args.days, 1),
    )

    print(
        f"SHIFT_COMPARISON_ROWS={len(records)}"
    )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    end_date = start_date + timedelta(days=max(args.days, 1) - 1)
    delete_result = delete_shift_comparison_range(
        start_date,
        end_date,
    )
    print(
        f"SHIFT_COMPARISON_DELETE={delete_result.get('status')} "
        f"{delete_result.get('start_date')}..{delete_result.get('end_date')}"
    )

    result = upsert_shift_comparison_rows(
        records
    )
    print(
        f"SHIFT_COMPARISON_DB={result.get('status')} rows={result.get('rows')}"
    )


if __name__ == "__main__":
    main()
