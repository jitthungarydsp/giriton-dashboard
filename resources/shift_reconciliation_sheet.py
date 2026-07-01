from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread

from resources.muszakpro_sheet import (
    build_foglalas_lookup,
    foglalas_key,
    open_sheet,
    read_foglalasok_records,
    read_giriton_email_name_lookup,
    read_giriton_records,
    normalize_name,
    normalize_time,
)


WORKSHEET_NAME = "Muszak_Ellenorzes"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "work_date",
    "name",
    "email",
    "warehouse",
    "start",
    "end",
    "giriton",
    "muszakpro",
    "missing",
    "giriton_check",
    "muszakpro_code",
    "updated_at",
    "match_key",
]


def row_value(row, index):
    if index >= len(row):
        return ""

    return row[index]


def make_match_key(work_date, email, warehouse, start, name=""):
    email = str(email or "").strip().casefold()
    name = normalize_name(name)
    person = email or name

    return "|".join(
        [
            str(work_date or "").strip(),
            person,
            str(warehouse or "").strip().casefold(),
            normalize_time(start),
        ]
    )


def is_time_shift_start(value):
    parts = str(value or "").strip().split(":")

    if len(parts) < 2:
        return False

    try:
        int(parts[0])
        int(parts[1])
    except ValueError:
        return False

    return True


def is_courier_shift(record):
    warehouse = str(
        record.get("warehouse", "")
    ).strip().upper()

    return (
        warehouse in ["BUD1", "BUD2", "BUDAPEST"]
        and is_time_shift_start(record.get("start"))
    )


def get_or_create_worksheet(spreadsheet):
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=3000,
            cols=len(HEADER),
        )

    values = worksheet.get_all_values()

    if not values:
        worksheet.update("A1", [HEADER])

    return worksheet


def record_to_row(record):
    return [
        record.get(column, "")
        for column in HEADER
    ]


def row_to_record(row):
    return {
        column: row_value(row, index)
        for index, column in enumerate(HEADER)
    }


def build_records_for_date(work_date):
    updated_at = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")
    email_name_lookup = read_giriton_email_name_lookup()
    giriton_records = read_giriton_records(work_date)
    foglalas_records = read_foglalasok_records(work_date)
    foglalas_lookup = build_foglalas_lookup(foglalas_records)
    records_by_key = {}

    for record in giriton_records:
        if not is_courier_shift(record):
            continue

        email = str(record.get("email", "")).strip().casefold()
        name = str(record.get("name", "")).strip()
        key = make_match_key(
            record.get("work_date"),
            email,
            record.get("warehouse"),
            record.get("start"),
            name,
        )
        foglalas_record = foglalas_lookup.get(
            foglalas_key(
                email,
                record.get("warehouse"),
                record.get("start"),
            ),
            {},
        )
        has_muszakpro = bool(foglalas_record)
        missing = [] if has_muszakpro else ["MuszakPro"]

        records_by_key[key] = {
            "work_date": record.get("work_date", ""),
            "name": name,
            "email": email,
            "warehouse": record.get("warehouse", ""),
            "start": normalize_time(record.get("start")),
            "end": normalize_time(record.get("end")),
            "giriton": "OK",
            "muszakpro": "OK" if has_muszakpro else "-",
            "missing": ", ".join(missing),
            "giriton_check": record.get("check", ""),
            "muszakpro_code": foglalas_record.get("code", ""),
            "updated_at": updated_at,
            "match_key": key,
        }

    for record in foglalas_records:
        if not is_courier_shift(record):
            continue

        email = str(record.get("email", "")).strip().casefold()
        name = email_name_lookup.get(email, email)
        key = make_match_key(
            record.get("work_date"),
            email,
            record.get("warehouse"),
            record.get("start"),
            name,
        )

        if key in records_by_key:
            continue

        records_by_key[key] = {
            "work_date": record.get("work_date", ""),
            "name": name,
            "email": email,
            "warehouse": record.get("warehouse", ""),
            "start": normalize_time(record.get("start")),
            "end": "",
            "giriton": "-",
            "muszakpro": "OK",
            "missing": "Giriton",
            "giriton_check": "",
            "muszakpro_code": record.get("code", ""),
            "updated_at": updated_at,
            "match_key": key,
        }

    return sorted(
        records_by_key.values(),
        key=lambda record: (
            record.get("work_date", ""),
            normalize_name(record.get("name", "")),
            normalize_time(record.get("start", "")),
        ),
    )


def records_to_rows(records):
    return [
        HEADER,
        *[
            record_to_row(record)
            for record in records
        ],
    ]


def rebuild_shift_reconciliation(start_date=None, days=10):
    if start_date is None:
        start = datetime.now(LOCAL_TIMEZONE).date()
    elif isinstance(start_date, str):
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = start_date

    records = []

    for offset in range(days):
        work_date = (
            start + timedelta(days=offset)
        ).isoformat()
        records.extend(
            build_records_for_date(work_date)
        )

    spreadsheet = open_sheet()
    worksheet = get_or_create_worksheet(spreadsheet)
    worksheet.clear()
    worksheet.update("A1", records_to_rows(records))

    return records


def read_shift_reconciliation_records(work_date):
    spreadsheet = open_sheet()
    worksheet = get_or_create_worksheet(spreadsheet)
    rows = worksheet.get_all_values()
    records = [
        row_to_record(row)
        for row in rows[1:]
        if row_value(row, 0) == work_date
    ]

    if records:
        return records

    rebuild_shift_reconciliation(
        start_date=work_date,
        days=1,
    )
    rows = worksheet.get_all_values()

    return [
        row_to_record(row)
        for row in rows[1:]
        if row_value(row, 0) == work_date
    ]


def read_shift_reconciliation_records_for_dates(work_dates):
    wanted_dates = {
        str(work_date)
        for work_date in work_dates
        if str(work_date or "").strip()
    }

    if not wanted_dates:
        return []

    spreadsheet = open_sheet()
    worksheet = get_or_create_worksheet(spreadsheet)
    rows = worksheet.get_all_values()

    return [
        row_to_record(row)
        for row in rows[1:]
        if row_value(row, 0) in wanted_dates
    ]
