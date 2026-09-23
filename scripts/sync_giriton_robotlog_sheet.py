from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.giriton_auto_booking import (  # noqa: E402
    ROBOTLOG_HEADER,
    ROBOTLOG_SHEET_STATUSES,
    _legacy_candidate_serial,
    _format_robotlog_shift,
    _format_robotlog_timestamp,
    _get_or_create_robotlog_worksheet,
    _normalize_warehouse,
    _robotlog_spreadsheet_id,
    _robotlog_action_type,
    clean,
    read_giriton_booking_log,
)
from resources.google_auth import get_client  # noqa: E402


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def robotlog_keys(worksheet) -> set[tuple[str, str]]:
    values = worksheet.get_all_values()
    if not values:
        worksheet.update(
            "A1",
            [ROBOTLOG_HEADER],
            value_input_option="USER_ENTERED",
        )
        return set()

    keys: set[tuple[str, str]] = set()
    for row in values[1:]:
        if len(row) >= 5 and clean(row[4]):
            action_type = clean(row[2]) if len(row) >= 3 else "FOGLALÁS"
            keys.add((action_type or "FOGLALÁS", clean(row[4])))
    return keys


def robotlog_key_from_log(log_row: dict) -> tuple[str, str]:
    candidate = {
        "work_date": clean(log_row.get("work_date")),
        "warehouse": _normalize_warehouse(log_row.get("warehouse")),
        "shift_start": clean(log_row.get("shift_start")),
        "shift_text": clean(log_row.get("shift_text")),
        "courier_id": clean(log_row.get("courier_id")),
        "serial": clean(log_row.get("serial")),
    }
    return (
        _robotlog_action_type(log_row.get("status")),
        _legacy_candidate_serial(candidate),
    )


def row_from_log(log_row: dict) -> list[str]:
    candidate = {
        "work_date": clean(log_row.get("work_date")),
        "warehouse": _normalize_warehouse(log_row.get("warehouse")),
        "shift_start": clean(log_row.get("shift_start")),
        "shift_text": clean(log_row.get("shift_text")),
        "email": clean(log_row.get("email")).casefold(),
        "courier_id": clean(log_row.get("courier_id")),
        "serial": clean(log_row.get("serial")),
    }
    return [
        _format_robotlog_timestamp(),
        candidate["email"],
        _robotlog_action_type(log_row.get("status")),
        (
            f"Dátum: {candidate['work_date']}, "
            f"Műszak: {_format_robotlog_shift(candidate)}, "
            f"Raktár: {candidate['warehouse']}"
        ),
        _legacy_candidate_serial(candidate),
    ]


def sync_robotlog_sheet(start_date: date, end_date: date, *, limit: int, dry_run: bool) -> tuple[int, int]:
    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=limit,
    )
    if log_df.empty:
        print("ROBOTLOG_SYNC source_rows=0 missing=0 written=0")
        return 0, 0

    required_columns = {"serial", "status"}
    if not required_columns.issubset(log_df.columns):
        print("ROBOTLOG_SYNC source_rows=0 missing=0 written=0 reason=missing_columns")
        return 0, 0

    success_df = log_df[
        log_df["status"].fillna("").astype(str).str.strip().isin(ROBOTLOG_SHEET_STATUSES)
        & log_df["serial"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if success_df.empty:
        print(f"ROBOTLOG_SYNC source_rows={len(log_df)} missing=0 written=0")
        return 0, 0

    worksheet = _get_or_create_robotlog_worksheet(
        get_client().open_by_key(_robotlog_spreadsheet_id())
    )
    existing_keys = robotlog_keys(worksheet)
    missing_df = success_df[
        ~success_df.apply(
            lambda row: robotlog_key_from_log(row.to_dict()) in existing_keys,
            axis=1,
        )
    ].copy()

    if missing_df.empty:
        print(
            "ROBOTLOG_SYNC "
            f"source_rows={len(success_df)} missing=0 written=0"
        )
        return len(success_df), 0

    rows = [row_from_log(row) for row in missing_df.to_dict("records")]
    print(
        "ROBOTLOG_SYNC "
        f"source_rows={len(success_df)} missing={len(rows)} dry_run={dry_run}"
    )
    if dry_run:
        for row in rows:
            print(f"ROBOTLOG_SYNC_DRY_RUN row={row}")
        return len(success_df), 0

    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"ROBOTLOG_SYNC_WRITTEN={len(rows)}")
    return len(success_df), len(rows)


def main() -> None:
    today = datetime.now(BUDAPEST_TZ).date()
    parser = argparse.ArgumentParser(
        description="Sikeres Giriton auto booking logok pótlása a Google Sheet ROBOTLOG fülre."
    )
    parser.add_argument("--start-date", default="", help="Kezdő nap YYYY-MM-DD. Alap: ma.")
    parser.add_argument("--end-date", default="", help="Záró nap YYYY-MM-DD. Alap: start-date.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today)
    end_date = parse_date(args.end_date, start_date)
    sync_robotlog_sheet(
        start_date,
        end_date,
        limit=max(int(args.limit), 1),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
