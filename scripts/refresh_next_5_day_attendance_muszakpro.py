import argparse
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from resources.foglalasok_db import (
    backfill_booking_couriers_from_master,
    build_db_rows,
    export_courier_master_to_id_sheet,
    upsert_foglalasok_rows,
)
from scripts.cleanup_attendance_muszakpro_comparison import (
    TABLES as COMPARISON_TABLES,
    delete_collection,
    select_collections,
)
from scripts.collect_attendance_muszakpro_comparison import (
    COMPARISON_TABLE,
    LOCAL_TIMEZONE,
    RAW_TABLE,
    build_comparison_rows,
    clean,
    date_range,
    fetch_attendance,
    insert_rows,
    parse_attendance_shift_rows,
    read_muszakpro_rows,
)
from scripts.load_foglalasok_raw import load_values_from_sheet


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Kovetkezo napok fetch-attendance vs MuszakPro frissitese egyben: "
            "Foglalasok raw sync, regi collection takaritas, uj osszehasonlitas."
        )
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Elso nap YYYY-MM-DD formatumban. Alapertelmezes: mai nap.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Hany napot frissitsen. Alapertelmezes: 5.",
    )
    parser.add_argument(
        "--debug-email",
        default="",
        help="Kiirja az adott email MuszakPro sorait es a hozza talalt nevet.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak beolvas es kiir, DB-be nem ir es nem torol.",
    )
    return parser.parse_args()


def resolve_work_dates(start_date_text, days):
    if start_date_text:
        start_date = datetime.strptime(
            start_date_text,
            "%Y-%m-%d",
        ).date()
    else:
        start_date = datetime.now(LOCAL_TIMEZONE).date()

    end_date = start_date + timedelta(days=max(days, 1) - 1)
    return list(
        date_range(
            start_date,
            end_date,
        )
    )


def sync_foglalasok_raw(dry_run=False):
    if dry_run:
        print("DRY RUN, ID ful frissites kihagyva.")
    else:
        id_sheet_result = export_courier_master_to_id_sheet()
        print(
            "ID ful frissites: "
            f"sheet={id_sheet_result.get('sheet')} "
            f"rows={id_sheet_result.get('rows', 0)}"
        )

    values = load_values_from_sheet()
    rows = build_db_rows(
        values
    )

    print(
        f"Foglalasok sheet sorok: {max(len(values) - 1, 0)}"
    )
    print(
        f"Foglalasok DB-re elokeszitett sorok: {len(rows)}"
    )

    if dry_run:
        print("DRY RUN, Foglalasok raw DB iras kihagyva.")
        return

    result = upsert_foglalasok_rows(
        values
    )
    print(
        f"Foglalasok raw DB feltoltes: {result}"
    )

    backfill_result = backfill_booking_couriers_from_master()
    print(
        "Foglalasok futartorzzs backfill: "
        f"checked={backfill_result.get('checked', 0)} "
        f"updated={backfill_result.get('updated', 0)}"
    )


def cleanup_existing_collections(work_dates, dry_run=False):
    for work_date in work_dates:
        collections = select_collections(
            work_date.isoformat()
        )
        collection_ids = [
            collection["collection_id"]
            for collection in collections
            if collection.get("collection_id")
        ]

        print(
            f"{work_date.isoformat()}: torlendo regi collectionok={len(collection_ids)}"
        )

        for collection in collections:
            print(
                f"  DELETE {collection.get('collection_id')} {collection.get('collected_at')}"
            )

        if dry_run:
            continue

        for collection_id in collection_ids:
            for table_name in COMPARISON_TABLES:
                delete_collection(
                    table_name,
                    collection_id,
                )


def collect_comparison(work_dates, debug_email="", dry_run=False):
    collection_id = str(
        uuid.uuid4()
    )
    collected_at = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat(timespec="seconds")
    all_attendance_rows = []
    all_comparison_rows = []
    debug_email = clean(
        debug_email
    ).casefold()

    print(
        f"UJ_COLLECTION_ID={collection_id}"
    )

    for work_date in work_dates:
        request_url, status_code, payload = fetch_attendance(
            work_date
        )
        attendance_rows = parse_attendance_shift_rows(
            collection_id,
            work_date,
            request_url,
            status_code,
            payload,
        )
        muszakpro_rows = read_muszakpro_rows(
            work_date
        )

        if debug_email:
            print(
                f"\nDEBUG_EMAIL={debug_email} DATE={work_date.isoformat()}"
            )

            for row in muszakpro_rows:
                if clean(row.get("email")).casefold() == debug_email:
                    print(
                        "MUSZAKPRO "
                        f"courier_id={row.get('courier_id')} "
                        f"courier_name={row.get('courier_name')} "
                        f"email={row.get('email')} "
                        f"warehouse={row.get('warehouse')} "
                        f"shift_text={row.get('shift_text')} "
                        f"key={row.get('match_key')}"
                    )

        comparison_rows = build_comparison_rows(
            collection_id,
            attendance_rows,
            muszakpro_rows,
        )

        for row in attendance_rows:
            row["collected_at"] = collected_at

        for row in comparison_rows:
            row["collected_at"] = collected_at

        all_attendance_rows.extend(
            attendance_rows
        )
        all_comparison_rows.extend(
            comparison_rows
        )
        print(
            f"{work_date.isoformat()}: attendance={len(attendance_rows)}, "
            f"muszakpro={len(muszakpro_rows)}, comparison={len(comparison_rows)}"
        )

    if dry_run:
        print("DRY RUN, uj osszehasonlitas DB iras kihagyva.")
        return

    raw_inserted = insert_rows(
        RAW_TABLE,
        all_attendance_rows,
    )
    comparison_inserted = insert_rows(
        COMPARISON_TABLE,
        all_comparison_rows,
    )
    print(
        f"DB_INSERT raw={raw_inserted}, comparison={comparison_inserted}"
    )


def main():
    args = parse_args()
    work_dates = resolve_work_dates(
        args.start_date,
        args.days,
    )
    print(
        "Frissites napok: "
        + ", ".join(work_date.isoformat() for work_date in work_dates)
    )

    sync_foglalasok_raw(
        dry_run=args.dry_run
    )
    cleanup_existing_collections(
        work_dates,
        dry_run=args.dry_run,
    )
    collect_comparison(
        work_dates,
        debug_email=args.debug_email,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
