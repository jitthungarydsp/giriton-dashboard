from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

from resources.api import load_drivers
from resources.google_auth import get_client
from resources.muszakpro_sheet import (
    get_spreadsheet_id,
    normalize_name,
)


WORKSHEET_NAME = "CourierDB_JITT"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "courier_id",
    "name",
    "email",
    "phone",
    "warehouse",
    "source",
    "active",
    "updated_at",
    "notes",
]


def normalize_id(value):
    text = str(value or "").strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def normalize_email(value):
    return str(value or "").strip().casefold()


def row_value(row, index):
    if index >= len(row):
        return ""

    return row[index]


def open_spreadsheet():
    client = get_client()
    return client.open_by_key(
        get_spreadsheet_id()
    )


def get_or_create_worksheet():
    spreadsheet = open_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(HEADER) + 10,
        )
        worksheet.update("A1", [HEADER])
        return worksheet

    values = worksheet.get_all_values()

    if not values:
        worksheet.update("A1", [HEADER])
        return worksheet

    current_header = values[0]
    missing_columns = [
        column
        for column in HEADER
        if column not in current_header
    ]

    if missing_columns:
        worksheet.update(
            "A1",
            [
                [
                    *current_header,
                    *missing_columns,
                ]
            ],
        )

    return worksheet


def read_courier_db_records():
    worksheet = get_or_create_worksheet()
    rows = worksheet.get_all_values()

    if not rows:
        return []

    header = rows[0]
    records = []

    for row in rows[1:]:
        record = {
            column: row_value(row, index)
            for index, column in enumerate(header)
        }
        courier_id = normalize_id(
            record.get("courier_id")
        )

        if courier_id:
            record["courier_id"] = courier_id
            records.append(record)

    return records


def build_courier_lookup(records=None):
    records = records if records is not None else read_courier_db_records()
    by_id = {}
    by_email = {}
    by_name = {}

    for record in records:
        courier_id = normalize_id(
            record.get("courier_id")
        )

        if not courier_id:
            continue

        normalized_record = dict(record)
        normalized_record["courier_id"] = courier_id
        email = normalize_email(
            normalized_record.get("email")
        )
        name = normalize_name(
            normalized_record.get("name")
        )

        by_id[courier_id] = normalized_record

        if email:
            by_email[email] = normalized_record

        if name:
            by_name.setdefault(
                name,
                normalized_record,
            )

    return {
        "by_id": by_id,
        "by_email": by_email,
        "by_name": by_name,
    }


def resolve_courier_id(email="", name="", courier_id="", lookup=None):
    courier_id = normalize_id(courier_id)

    if courier_id:
        return courier_id

    lookup = lookup or build_courier_lookup()
    email = normalize_email(email)
    name = normalize_name(name)

    if email and email in lookup["by_email"]:
        return lookup["by_email"][email].get("courier_id", "")

    if name and name in lookup["by_name"]:
        return lookup["by_name"][name].get("courier_id", "")

    return ""


def row_from_record(record, header):
    return [
        record.get(column, "")
        for column in header
    ]


def upsert_couriers(records):
    worksheet = get_or_create_worksheet()
    values = worksheet.get_all_values()
    header = values[0] if values else HEADER
    existing = {}
    ordered_ids = []

    for row in values[1:]:
        record = {
            column: row_value(row, index)
            for index, column in enumerate(header)
        }
        courier_id = normalize_id(
            record.get("courier_id")
        )

        if courier_id:
            record["courier_id"] = courier_id
            existing[courier_id] = record
            ordered_ids.append(courier_id)

    updated_at = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")

    for record in records:
        courier_id = normalize_id(
            record.get("courier_id")
        )

        if not courier_id:
            continue

        target = existing.setdefault(
            courier_id,
            {"courier_id": courier_id},
        )

        if courier_id not in ordered_ids:
            ordered_ids.append(courier_id)

        for column in HEADER:
            if column in ["courier_id", "updated_at"]:
                continue

            value = record.get(column, "")

            if value not in [None, ""]:
                target[column] = value

        target["updated_at"] = updated_at

    rows = [
        header,
        *[
            row_from_record(
                existing[courier_id],
                header,
            )
            for courier_id in sorted(
                set(ordered_ids),
                key=lambda value: (
                    normalize_name(
                        existing[value].get("name")
                    ),
                    value,
                ),
            )
        ],
    ]

    worksheet.clear()
    worksheet.update("A1", rows)

    return {
        "updated": len(records),
        "total": len(rows) - 1,
    }


def driver_to_courier_record(driver):
    personal_info = driver.get("personal_info", {}) or {}

    return {
        "courier_id": normalize_id(
            driver.get("driver_id")
        ),
        "name": personal_info.get("name", ""),
        "email": normalize_email(
            personal_info.get("contact_email", "")
        ),
        "phone": personal_info.get("contact_number", ""),
        "warehouse": personal_info.get("warehouse_name", ""),
        "source": "fetch-drivers",
        "active": str(
            driver.get("active", "")
        ),
    }


def sync_courier_db_from_drivers():
    data = load_drivers()
    drivers = data.get("drivers", []) if isinstance(data, dict) else []
    records = [
        driver_to_courier_record(driver)
        for driver in drivers
    ]

    return upsert_couriers(records)
