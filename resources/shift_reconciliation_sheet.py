import time

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread

from resources.muszakpro_sheet import (
    open_sheet,
    normalize_name,
    normalize_time,
)


WORKSHEET_NAME = "Muszak_Ellenorzes"
MISSING_API_WORKSHEET_NAME = "CourierDB_JITT_API_Hianyzo"
GIRITON_LOG_WORKSHEET_NAME = "Giriton_Log"
FOGLALASOK_LOG_WORKSHEET_NAME = "Foglalasok_Log"
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
    "courier_id",
]

MISSING_API_HEADER = [
    "name",
    "email",
    "warehouse",
    "dates",
    "shifts",
    "sources",
    "reason",
    "updated_at",
]


def row_value(row, index):
    if index >= len(row):
        return ""

    return row[index]


def with_retries(callback, attempts=3, delay_seconds=2):
    last_error = None

    for attempt in range(attempts):
        try:
            return callback()
        except Exception as exc:
            last_error = exc

            if attempt == attempts - 1:
                break

            time.sleep(delay_seconds * (attempt + 1))

    raise last_error


def make_match_key(work_date, email, warehouse, start, name="", courier_id=""):
    courier_id = str(courier_id or "").strip()
    email = str(email or "").strip().casefold()
    name = normalize_name(name)
    person = courier_id or email or name

    return "|".join(
        [
            str(work_date or "").strip(),
            person,
            str(warehouse or "").strip().casefold(),
            normalize_time(start),
        ]
    )


def normalize_serial(value):
    serial = str(value or "").strip()

    if not serial or "NINCS_ID" in serial:
        return ""

    return serial


def header_map(header):
    return {
        normalize_name(column): index
        for index, column in enumerate(header)
    }


def column_index(header, *names):
    indexes = header_map(header)

    for name in names:
        index = indexes.get(
            normalize_name(name)
        )

        if index is not None:
            return index

    return None


def row_column(row, index):
    if index is None or index >= len(row):
        return ""

    return str(row[index] or "").strip()


def read_worksheet_values(spreadsheet, sheet_name):
    try:
        return spreadsheet.worksheet(sheet_name).get_all_values()
    except gspread.WorksheetNotFound:
        return []


def read_giriton_keyed_records(spreadsheet, work_date):
    rows = read_worksheet_values(
        spreadsheet,
        GIRITON_LOG_WORKSHEET_NAME,
    )

    if rows:
        header = rows[0]
        serial_index = column_index(header, "sorszam")
        date_index = column_index(header, "datum")
        id_index = column_index(header, "courier_id")
        name_index = column_index(header, "nev", "name")
        email_index = column_index(header, "email")
        warehouse_index = column_index(header, "raktar", "raktár", "warehouse")
        start_index = column_index(header, "kezdes", "kezdés", "start")
        end_index = column_index(header, "vege", "vége", "end")

        records = []

        for row in rows[1:]:
            serial = normalize_serial(
                row_column(row, serial_index)
            )

            if not serial:
                continue

            record_date = row_column(row, date_index)

            if record_date != work_date:
                continue

            records.append(
                {
                    "serial": serial,
                    "work_date": record_date,
                    "courier_id": row_column(row, id_index),
                    "name": row_column(row, name_index),
                    "email": row_column(row, email_index).casefold(),
                    "warehouse": row_column(row, warehouse_index),
                    "start": normalize_time(row_column(row, start_index)),
                    "end": normalize_time(row_column(row, end_index)),
                }
            )

        return records

    rows = read_worksheet_values(
        spreadsheet,
        "Giriton",
    )

    if not rows:
        return []

    header = rows[0]
    date_index = column_index(header, "datum", "work_date")
    start_index = column_index(header, "kezdes", "kezdés", "start")
    end_index = column_index(header, "vege", "vége", "end")
    warehouse_index = column_index(header, "raktar", "raktár", "warehouse")
    name_index = column_index(header, "nev", "név", "name")
    email_index = column_index(header, "email")
    serial_index = column_index(header, "sorszam")
    id_index = column_index(header, "courier_id")
    status_index = column_index(header, "statusz", "status")
    records = []

    for row in rows[1:]:
        serial = normalize_serial(
            row_column(row, serial_index)
        )

        if not serial:
            continue

        record_date = row_column(row, date_index)

        if record_date != work_date:
            continue

        status = row_column(row, status_index).upper()

        if status == "URES":
            continue

        records.append(
            {
                "serial": serial,
                "work_date": record_date,
                "courier_id": row_column(row, id_index),
                "name": row_column(row, name_index),
                "email": row_column(row, email_index).casefold(),
                "warehouse": row_column(row, warehouse_index),
                "start": normalize_time(row_column(row, start_index)),
                "end": normalize_time(row_column(row, end_index)),
            }
        )

    return records


def read_foglalasok_keyed_records(spreadsheet, work_date):
    rows = read_worksheet_values(
        spreadsheet,
        FOGLALASOK_LOG_WORKSHEET_NAME,
    )

    if rows:
        header = rows[0]
        serial_index = column_index(header, "sorszam")
        date_index = column_index(header, "datum")
        id_index = column_index(header, "courier_id")
        name_index = column_index(header, "nev", "name")
        email_index = column_index(header, "email")
        warehouse_index = column_index(header, "raktar", "raktár", "warehouse")
        start_index = column_index(header, "kezdes", "kezdés", "start")
        code_index = column_index(header, "foglalasi_kod", "foglalási kód", "code")
        records = []

        for row in rows[1:]:
            serial = normalize_serial(
                row_column(row, serial_index)
            )

            if not serial:
                continue

            record_date = row_column(row, date_index)

            if record_date != work_date:
                continue

            records.append(
                {
                    "serial": serial,
                    "work_date": record_date,
                    "courier_id": row_column(row, id_index),
                    "name": row_column(row, name_index),
                    "email": row_column(row, email_index).casefold(),
                    "warehouse": row_column(row, warehouse_index),
                    "start": normalize_time(row_column(row, start_index)),
                    "code": row_column(row, code_index),
                }
            )

        return records

    rows = read_worksheet_values(
        spreadsheet,
        "Foglalasok",
    )

    if not rows:
        return []

    header = rows[0]
    date_index = column_index(header, "Dátum", "datum")
    email_index = column_index(header, "Email")
    shift_index = column_index(header, "Műszak", "muszak")
    warehouse_index = column_index(header, "Raktár", "raktar")
    code_index = column_index(header, "Foglalási kód", "foglalasi kod")
    id_index = column_index(header, "courier_id")
    name_index = column_index(header, "nev", "name")
    serial_index = column_index(header, "sorszam")
    records = []

    for row in rows[1:]:
        serial = normalize_serial(
            row_column(row, serial_index)
        )

        if not serial:
            continue

        record_date = row_column(row, date_index)

        if record_date != work_date:
            continue

        shift = row_column(row, shift_index)
        start = shift.split("_", 1)[1] if "_" in shift else ""

        records.append(
            {
                "serial": serial,
                "work_date": record_date,
                "courier_id": row_column(row, id_index),
                "name": row_column(row, name_index),
                "email": row_column(row, email_index).casefold(),
                "warehouse": row_column(row, warehouse_index),
                "start": normalize_time(start),
                "code": row_column(row, code_index),
            }
        )

    return records


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


def missing_api_record_to_row(record):
    return [
        record.get(column, "")
        for column in MISSING_API_HEADER
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
    spreadsheet = open_sheet()
    giriton_records = {
        record["serial"]: record
        for record in read_giriton_keyed_records(
            spreadsheet,
            work_date,
        )
        if record.get("serial")
    }
    foglalas_records = {
        record["serial"]: record
        for record in read_foglalasok_keyed_records(
            spreadsheet,
            work_date,
        )
        if record.get("serial")
    }
    records = []

    for serial in sorted(
        set(giriton_records) | set(foglalas_records)
    ):
        giriton_record = giriton_records.get(
            serial,
            {},
        )
        foglalas_record = foglalas_records.get(
            serial,
            {},
        )
        source = giriton_record or foglalas_record
        has_giriton = bool(giriton_record)
        has_muszakpro = bool(foglalas_record)
        missing = []

        if not has_giriton:
            missing.append("Giriton")

        if not has_muszakpro:
            missing.append("MuszakPro")

        records.append(
            {
                "work_date": source.get("work_date", ""),
                "name": source.get("name", ""),
                "email": source.get("email", ""),
                "warehouse": source.get("warehouse", ""),
                "start": normalize_time(source.get("start")),
                "end": normalize_time(giriton_record.get("end", "")),
                "giriton": "OK" if has_giriton else "-",
                "muszakpro": "OK" if has_muszakpro else "-",
                "missing": ", ".join(missing),
                "giriton_check": "GIRITON_OK" if has_giriton else "",
                "muszakpro_code": foglalas_record.get("code", ""),
                "updated_at": updated_at,
                "match_key": serial,
                "courier_id": source.get("courier_id", ""),
            }
        )

    return sorted(
        records,
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


def get_or_create_missing_api_worksheet(spreadsheet):
    try:
        worksheet = spreadsheet.worksheet(
            MISSING_API_WORKSHEET_NAME
        )
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=MISSING_API_WORKSHEET_NAME,
            rows=1000,
            cols=len(MISSING_API_HEADER),
        )

    values = worksheet.get_all_values()

    if not values:
        with_retries(
            lambda: worksheet.update("A1", [MISSING_API_HEADER])
        )

    return worksheet


def build_missing_api_records(records):
    updated_at = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")
    grouped = {}

    for record in records:
        if str(record.get("courier_id", "")).strip():
            continue

        name = str(record.get("name", "")).strip()
        email = str(record.get("email", "")).strip().casefold()

        if not name and not email:
            continue

        key = (
            email,
            normalize_name(name),
        )
        item = grouped.setdefault(
            key,
            {
                "name": name,
                "email": email,
                "warehouse": set(),
                "dates": set(),
                "shifts": set(),
                "sources": set(),
                "reason": "Nincs courier_id a CourierDB_JITT/API törzsben",
                "updated_at": updated_at,
            },
        )

        if record.get("warehouse"):
            item["warehouse"].add(
                str(record.get("warehouse"))
            )

        if record.get("work_date"):
            item["dates"].add(
                str(record.get("work_date"))
            )

        if record.get("start"):
            item["shifts"].add(
                f"{record.get('work_date', '')} {record.get('warehouse', '')} {record.get('start', '')}"
            )

        if record.get("giriton") == "OK":
            item["sources"].add("Giriton")

        if record.get("muszakpro") == "OK":
            item["sources"].add("MuszakPro")

    return [
        {
            "name": item["name"],
            "email": item["email"],
            "warehouse": ", ".join(
                sorted(item["warehouse"])
            ),
            "dates": ", ".join(
                sorted(item["dates"])
            ),
            "shifts": " | ".join(
                sorted(item["shifts"])
            ),
            "sources": ", ".join(
                sorted(item["sources"])
            ),
            "reason": item["reason"],
            "updated_at": item["updated_at"],
        }
        for item in sorted(
            grouped.values(),
            key=lambda value: (
                normalize_name(value["name"]),
                value["email"],
            ),
        )
    ]


def write_missing_api_sheet(spreadsheet, records):
    missing_records = build_missing_api_records(records)
    worksheet = get_or_create_missing_api_worksheet(
        spreadsheet
    )
    rows = [
        MISSING_API_HEADER,
        *[
            missing_api_record_to_row(record)
            for record in missing_records
        ],
    ]

    with_retries(
        worksheet.clear
    )
    with_retries(
        lambda: worksheet.update("A1", rows)
    )

    return len(missing_records)


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
        daily_records = with_retries(
            lambda work_date=work_date: build_records_for_date(work_date),
            attempts=3,
            delay_seconds=3,
        )
        records.extend(daily_records)

    spreadsheet = open_sheet()
    worksheet = get_or_create_worksheet(spreadsheet)
    with_retries(
        worksheet.clear
    )
    with_retries(
        lambda: worksheet.update("A1", records_to_rows(records))
    )
    write_missing_api_sheet(
        spreadsheet,
        records,
    )

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
