import os
from datetime import datetime
from zoneinfo import ZoneInfo

from resources.google_auth import (
    get_client,
    get_service_account_email,
)
DEFAULT_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
WORKSHEET_NAME = "Alert_Log"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "work_date",
    "first_seen_at",
    "last_seen_at",
    "driver_id",
    "driver_name",
    "route_id",
    "issue_type",
    "issue",
    "value",
    "status",
    "warehouse",
    "license_plate",
    "occurrences",
]


def get_spreadsheet_id():
    return os.getenv(
        "ALERT_LOG_SPREADSHEET_ID",
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


def record_key(record):
    return (
        str(record.get("work_date", "")),
        str(record.get("driver_id", "")),
        str(record.get("route_id", "")),
        str(record.get("issue_type", "")),
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


def write_alert_logs(alert_records):
    if not alert_records:
        return "NO_ALERTS"

    client = get_client()
    spreadsheet = client.open_by_key(
        get_spreadsheet_id()
    )
    worksheet = get_or_create_worksheet(
        spreadsheet
    )

    existing_records = worksheet.get_all_records()
    existing_by_key = {
        record_key(record): record
        for record in existing_records
    }

    now = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")

    for record in alert_records:
        key = record_key(record)
        existing = existing_by_key.get(key)

        if existing:
            occurrences = existing.get(
                "occurrences",
                1,
            )

            try:
                occurrences = int(occurrences)
            except (TypeError, ValueError):
                occurrences = 1

            existing.update(record)
            existing["first_seen_at"] = existing.get(
                "first_seen_at",
                now,
            )
            existing["last_seen_at"] = now
            existing["occurrences"] = occurrences + 1
            existing_by_key[key] = existing
        else:
            record["first_seen_at"] = now
            record["last_seen_at"] = now
            record["occurrences"] = 1
            existing_by_key[key] = record

    records = sorted(
        existing_by_key.values(),
        key=lambda record: (
            str(record.get("work_date", "")),
            str(record.get("driver_name", "")),
            str(record.get("issue_type", "")),
        ),
    )

    worksheet.clear()
    worksheet.update(
        "A1",
        records_to_rows(records),
    )

    return "OK"
