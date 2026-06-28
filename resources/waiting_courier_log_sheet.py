import os
from datetime import datetime
from zoneinfo import ZoneInfo

from resources.google_auth import get_client


DEFAULT_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
WORKSHEET_NAME = "Waiting_Courier_Log"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "work_date",
    "driver_id",
    "driver_name",
    "warehouse",
    "shift_id",
    "shift_name",
    "waiting_since",
    "waiting_since_local",
    "first_seen_at",
    "last_seen_at",
    "left_queue_at",
    "waiting_minutes",
    "temperature",
    "last_measurement",
    "temperature_block",
    "status",
]


def get_spreadsheet_id():
    return os.getenv(
        "WAITING_LOG_SPREADSHEET_ID",
        DEFAULT_SPREADSHEET_ID,
    )


def local_now():
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)


def now_text():
    return local_now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return local_now().strftime("%Y-%m-%d")


def parse_datetime(value):
    if value in [None, ""]:
        return None

    text = str(value)

    for date_format in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))

        if parsed.tzinfo:
            parsed = parsed.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)

        return parsed
    except ValueError:
        return None


def minutes_between(start_value, end_value):
    start = parse_datetime(start_value)
    end = parse_datetime(end_value)

    if not start or not end:
        return ""

    return max(int((end - start).total_seconds() // 60), 0)


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
        worksheet.update("A1", [HEADER])

    return worksheet


def normalize_record(record):
    return {
        column: record.get(column, "")
        for column in HEADER
    }


def record_key(record):
    return (
        str(record.get("work_date", "")),
        str(record.get("driver_id", "")),
        str(record.get("shift_id", "")),
        str(record.get("waiting_since", "")),
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


def sync_waiting_courier_log(waiting_records):
    client = get_client()
    spreadsheet = client.open_by_key(get_spreadsheet_id())
    worksheet = get_or_create_worksheet(spreadsheet)

    existing_records = [
        normalize_record(record)
        for record in worksheet.get_all_records()
    ]
    existing_by_key = {
        record_key(record): record
        for record in existing_records
    }

    current_time = now_text()
    current_date = today_text()
    normalized_waiting_records = [
        normalize_record(record)
        for record in waiting_records
    ]
    current_keys = {
        record_key(record)
        for record in normalized_waiting_records
    }

    for key, record in list(existing_by_key.items()):
        if (
            str(record.get("work_date", "")) == current_date
            and str(record.get("status", "")) == "active"
            and key not in current_keys
        ):
            record["status"] = "closed"
            record["left_queue_at"] = current_time
            record["waiting_minutes"] = minutes_between(
                record.get("waiting_since") or record.get("first_seen_at"),
                current_time,
            )
            existing_by_key[key] = record

    for record in normalized_waiting_records:
        key = record_key(record)
        existing = existing_by_key.get(key, {})
        merged = normalize_record({**existing, **record})
        merged["first_seen_at"] = existing.get("first_seen_at") or current_time
        merged["last_seen_at"] = current_time
        merged["left_queue_at"] = ""
        merged["status"] = "active"
        merged["waiting_minutes"] = minutes_between(
            merged.get("waiting_since") or merged.get("first_seen_at"),
            current_time,
        )
        existing_by_key[key] = merged

    records = sorted(
        existing_by_key.values(),
        key=lambda record: (
            str(record.get("work_date", "")),
            str(record.get("driver_name", "")),
            str(record.get("status", "")),
            str(record.get("shift_id", "")),
        ),
    )

    worksheet.clear()
    worksheet.update("A1", records_to_rows(records))

    return "OK"
