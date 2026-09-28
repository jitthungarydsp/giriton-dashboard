from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.giriton_auto_booking import (  # noqa: E402
    ROBOTLOG_HEADER,
    ROBOTLOG_SHEET_STATUSES,
    _legacy_candidate_serial,
    _format_robotlog_shift,
    _format_robotlog_timestamp,
    _normalize_warehouse,
    _robotlog_spreadsheet_id,
    _robotlog_worksheet_name,
    _robotlog_action_type,
    clean,
    read_giriton_booking_log,
)
from resources.google_auth import SCOPES, load_service_account_info, resolve_service_account_file  # noqa: E402


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def sheets_session() -> AuthorizedSession:
    service_account_info = load_service_account_info()
    if service_account_info:
        credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    else:
        service_account_file = resolve_service_account_file()
        if not service_account_file:
            raise FileNotFoundError("Google service account nincs beállítva.")
        credentials = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
    return AuthorizedSession(credentials)


def values_url(spreadsheet_id: str, range_name: str, suffix: str = "") -> str:
    return f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{quote(range_name, safe='')}{suffix}"


def raise_for_google_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    body = response.text[:1000]
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {body}")


def robotlog_keys(session: AuthorizedSession, spreadsheet_id: str, worksheet_name: str) -> set[tuple[str, str]]:
    response = session.get(
        values_url(spreadsheet_id, f"{worksheet_name}!C:E"),
        timeout=30,
    )
    raise_for_google_response(response, "ROBOTLOG key read")
    values = (response.json() or {}).get("values") or []
    if not values:
        header_response = session.put(
            values_url(spreadsheet_id, f"{worksheet_name}!A1:E1"),
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [ROBOTLOG_HEADER]},
            timeout=30,
        )
        raise_for_google_response(header_response, "ROBOTLOG header write")
        return set()

    keys: set[tuple[str, str]] = set()
    for row in values[1:]:
        serial = clean(row[2]) if len(row) >= 3 else ""
        if serial:
            action_type = clean(row[0]) if row else "FOGLALÁS"
            keys.add((action_type or "FOGLALÁS", serial))
    return keys


def append_robotlog_rows(
    session: AuthorizedSession,
    spreadsheet_id: str,
    worksheet_name: str,
    rows: list[list[str]],
    *,
    batch_size: int = 500,
) -> int:
    written = 0
    for start in range(0, len(rows), max(int(batch_size), 1)):
        batch = rows[start:start + max(int(batch_size), 1)]
        response = session.post(
            values_url(spreadsheet_id, f"{worksheet_name}!A:E", ":append"),
            params={
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
            },
            json={"values": batch},
            timeout=60,
        )
        raise_for_google_response(response, "ROBOTLOG batch append")
        written += len(batch)
    return written


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

    spreadsheet_id = _robotlog_spreadsheet_id()
    worksheet_name = _robotlog_worksheet_name()
    session = sheets_session()
    existing_keys = robotlog_keys(session, spreadsheet_id, worksheet_name)
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

    written = append_robotlog_rows(session, spreadsheet_id, worksheet_name, rows)
    print(f"ROBOTLOG_SYNC_WRITTEN={written}")
    return len(success_df), written


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
