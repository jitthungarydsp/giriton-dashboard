import os
from datetime import datetime
from zoneinfo import ZoneInfo

from resources.google_auth import get_client


DEFAULT_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
WORKSHEET_NAME = "Today_Shifts_Log"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "work_date",
    "logged_at",
    "name",
    "warehouse",
    "shift_start",
    "shift_end",
    "muszakpro",
    "giriton",
    "checked_in",
    "checkin_time",
    "current_plate",
    "suggested_plate",
    "email_sent",
]


def get_spreadsheet_id():
    return os.getenv(
        "TODAY_SHIFT_LOG_SPREADSHEET_ID",
        DEFAULT_SPREADSHEET_ID,
    )


def get_or_create_worksheet(spreadsheet):
    import gspread

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(HEADER),
        )

    values = worksheet.get_all_values()

    if not values:
        worksheet.update(
            "A1",
            [HEADER],
        )

    return worksheet


def bool_text(value):
    return "igen" if value else "nem"


def row_key(record):
    return (
        str(record.get("work_date", "")),
        str(record.get("name", "")),
        str(record.get("shift_start", "")),
    )


def records_to_rows(records):
    return [
        HEADER,
        *[
            [
                record.get(column, "")
                for column in HEADER
            ]
            for record in records
        ],
    ]


def build_log_records(work_date, rows):
    logged_at = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")

    return [
        {
            "work_date": work_date,
            "logged_at": logged_at,
            "name": row.get("name", ""),
            "warehouse": row.get("warehouse", ""),
            "shift_start": row.get("start", ""),
            "shift_end": row.get("end", ""),
            "muszakpro": bool_text(row.get("_has_muszakpro")),
            "giriton": bool_text(row.get("_has_giriton")),
            "checked_in": bool_text(row.get("_is_checked_in")),
            "checkin_time": row.get("checkin_time", ""),
            "current_plate": row.get("current_plate", ""),
            "suggested_plate": row.get("suggested_plate", ""),
            "email_sent": bool_text(row.get("_email_sent")),
        }
        for row in rows
    ]


def write_today_shift_log(work_date, rows):
    client = get_client()
    spreadsheet = client.open_by_key(
        get_spreadsheet_id()
    )
    worksheet = get_or_create_worksheet(
        spreadsheet
    )

    existing_records = worksheet.get_all_records()
    existing_by_key = {
        row_key(record): record
        for record in existing_records
    }

    for record in build_log_records(
        work_date,
        rows,
    ):
        existing_by_key[row_key(record)] = record

    records = sorted(
        existing_by_key.values(),
        key=lambda record: (
            str(record.get("work_date", "")),
            str(record.get("name", "")),
            str(record.get("shift_start", "")),
        ),
    )

    worksheet.clear()
    worksheet.update(
        "A1",
        records_to_rows(records),
    )

    return len(rows)
