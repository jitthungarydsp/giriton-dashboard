import os

from resources.google_auth import get_client


DEFAULT_SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
GIRITON_WORKSHEET_NAME = "Giriton"
FOGLALASOK_WORKSHEET_NAME = "Foglalasok"


def get_spreadsheet_id():
    return os.getenv(
        "MUSZAKPRO_SPREADSHEET_ID",
        DEFAULT_SPREADSHEET_ID,
    )


def get_giriton_worksheet_name():
    return os.getenv(
        "GIRITON_SHIFTS_WORKSHEET_NAME",
        GIRITON_WORKSHEET_NAME,
    )


def get_foglalasok_worksheet_name():
    return os.getenv(
        "MUSZAKPRO_FOGLALASOK_WORKSHEET_NAME",
        FOGLALASOK_WORKSHEET_NAME,
    )


def normalize_name(value):
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def normalize_time(value):
    text = str(value or "").strip()

    if not text:
        return ""

    parts = text.split(":")

    if len(parts) >= 2:
        try:
            return f"{int(parts[0])}:{int(parts[1]):02d}"
        except ValueError:
            return text

    return text


def record_key(name, start):
    return (
        normalize_name(name),
        normalize_time(start),
    )


def row_value(row, index):
    if index >= len(row):
        return ""

    return row[index]


def row_to_record(row):
    return {
        "work_date": row_value(row, 0),
        "start": normalize_time(row_value(row, 1)),
        "end": normalize_time(row_value(row, 2)),
        "warehouse": row_value(row, 3),
        "name": row_value(row, 7),
        "email": row_value(row, 8),
        "check": row_value(row, 10),
    }


def foglalas_row_to_record(row):
    shift = row_value(row, 3)
    warehouse = row_value(row, 4)
    start = shift.split("_", 1)[1] if "_" in shift else ""

    return {
        "created_at": row_value(row, 0),
        "work_date": row_value(row, 1),
        "email": row_value(row, 2),
        "shift": shift,
        "warehouse": warehouse,
        "start": normalize_time(start),
        "code": row_value(row, 5),
    }


def open_sheet():
    client = get_client()
    return client.open_by_key(
        get_spreadsheet_id()
    )


def read_giriton_records(work_date):
    spreadsheet = open_sheet()
    worksheet = spreadsheet.worksheet(
        get_giriton_worksheet_name()
    )
    rows = worksheet.get_all_values()
    records = []

    for row in rows:
        record = row_to_record(row)

        if (
            record["work_date"] == work_date
            and record["name"]
            and record["name"] != "ÜRES"
        ):
            records.append(record)

    return records


def read_foglalasok_records(work_date):
    spreadsheet = open_sheet()
    worksheet = spreadsheet.worksheet(
        get_foglalasok_worksheet_name()
    )
    rows = worksheet.get_all_values()
    records = []

    for row in rows:
        record = foglalas_row_to_record(row)

        if record["work_date"] == work_date and record["email"]:
            records.append(record)

    return records


def build_giriton_lookup(records):
    return {
        record_key(
            record.get("name"),
            record.get("start"),
        ): record
        for record in records
    }


def foglalas_key(email, warehouse, start):
    return (
        str(email or "").strip().casefold(),
        str(warehouse or "").strip().casefold(),
        normalize_time(start),
    )


def build_foglalas_lookup(records):
    return {
        foglalas_key(
            record.get("email"),
            record.get("warehouse"),
            record.get("start"),
        ): record
        for record in records
    }
