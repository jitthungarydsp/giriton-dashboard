import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from google_client import open_spreadsheet


SOURCE_SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
TARGET_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"

SOURCE_FOGLALASOK_SHEET = "Foglalasok"
TARGET_FOGLALASOK_SHEET = "Foglalasok"
GIRITON_RAW_SHEET = "Giriton"
GIRITON_ATTENDANCE_SHEET = "Giriton_Attendance"
COURIER_LOGIN_STATS_SHEET = "Futar_Bejelentkezes_Statisztika"


source_spreadsheet = open_spreadsheet(SOURCE_SPREADSHEET_ID)
target_spreadsheet = open_spreadsheet(TARGET_SPREADSHEET_ID)


def _get_or_create_worksheet(spreadsheet, title, rows=1000, cols=30):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(
            title=title,
            rows=rows,
            cols=cols,
        )


def _update_from_a1(ws, values):
    ws.clear()
    if values:
        ws.update(
            "A1",
            values,
            value_input_option="USER_ENTERED",
        )


def copy_foglalasok():
    source_ws = source_spreadsheet.worksheet(SOURCE_FOGLALASOK_SHEET)
    values = source_ws.get_all_values()

    target_ws = _get_or_create_worksheet(
        target_spreadsheet,
        TARGET_FOGLALASOK_SHEET,
        rows=max(len(values) + 100, 1000),
        cols=max((len(row) for row in values), default=20),
    )

    _update_from_a1(target_ws, values)
    return len(values)


def write_giriton_raw(rows):
    ws = _get_or_create_worksheet(
        target_spreadsheet,
        GIRITON_RAW_SHEET,
        rows=max(len(rows) + 100, 1000),
        cols=12,
    )

    output = [[
        "datum",
        "kezdes",
        "vege",
        "raktar",
        "foglaltsag",
        "foglalt",
        "maximum",
        "nev",
    ]]
    output.extend(rows)

    _update_from_a1(ws, output)
    return len(rows)


def write_giriton_attendance(rows):
    ws = _get_or_create_worksheet(
        target_spreadsheet,
        GIRITON_ATTENDANCE_SHEET,
        rows=max(len(rows) + 100, 1000),
        cols=10,
    )

    output = [[
        "datum",
        "nev",
        "muszak",
        "statusz",
        "bejelentkezes_kezdete",
        "bejelentkezes_vege",
        "raw_details",
    ]]
    output.extend(rows)

    _update_from_a1(ws, output)
    return len(rows)


def _format_sheet_date(date_value):
    return f"{date_value[5:7]}.{date_value[8:10]}."


def _sort_shift_key(value):
    try:
        time_part = value.split("_", 1)[1]
        hour, minute = time_part.split(":", 1)
        return int(hour), int(minute)
    except Exception:
        return 99, 99


def write_open_shift_matrices(rows):
    warehouses = [
        ("BUD1", "BUD1_PROD2.0"),
        ("BUD2", "BUD2_PROD2.0"),
    ]
    summaries = []

    for warehouse, sheet_name in warehouses:
        ws = _get_or_create_worksheet(
            target_spreadsheet,
            sheet_name,
            rows=300,
            cols=40,
        )

        matrix = {}
        dates = sorted(set(row[0] for row in rows if row[3] == warehouse))

        for row in rows:
            if row[3] != warehouse:
                continue

            datum = row[0]
            kezdes = row[1]

            try:
                foglalt = int(row[5])
                maximum = int(row[6])
                szabad = max(maximum - foglalt, 0)
            except (TypeError, ValueError):
                szabad = 0

            shift = f"{warehouse}_{kezdes}"
            matrix.setdefault(shift, {})
            matrix[shift][datum] = szabad

        header = ["muszak neve", "", ""]
        for work_date in dates:
            header.append(_format_sheet_date(work_date))

        output = [header]

        for shift in sorted(matrix.keys(), key=_sort_shift_key):
            output_row = [shift, "", ""]
            for work_date in dates:
                output_row.append(matrix[shift].get(work_date, 0))
            output.append(output_row)

        output.append(["Befoglalt muszakok"])

        ws.clear()
        ws.update(
            "A4",
            output,
            value_input_option="USER_ENTERED",
        )

        summaries.append(
            f"{sheet_name}: shifts={len(matrix)}, dates={len(dates)}, rows={len(output)}"
        )

    return summaries


def write_raw_export(rows):
    if not rows:
        raise ValueError("Nincs feldolgozhato Giriton sor.")

    copied_foglalasok_rows = copy_foglalasok()
    giriton_rows = write_giriton_raw(rows)
    matrix_summaries = write_open_shift_matrices(rows)

    result = (
        "OK | "
        f"Foglalasok copied={copied_foglalasok_rows} | "
        f"Giriton rows={giriton_rows} | "
        + " | ".join(matrix_summaries)
    )
    print(result)
    return result


def write_attendance_export(rows):
    attendance_rows = write_giriton_attendance(rows)
    result = f"OK | Giriton_Attendance rows={attendance_rows}"
    print(result)
    return result


def _parse_time(value):
    value = str(value or "").strip()
    if not value:
        return None

    for fmt in ["%H:%M:%S", "%H:%M"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    return None


def _worked_hours(start_value, end_value):
    start = _parse_time(start_value)
    end = _parse_time(end_value)

    if not start or not end:
        return ""

    if end < start:
        end = end + timedelta(days=1)

    hours = (end - start).total_seconds() / 3600
    return round(hours, 2)


def _read_sheet_records(sheet_name):
    try:
        ws = target_spreadsheet.worksheet(sheet_name)
    except Exception:
        return []

    values = ws.get_all_values()
    if not values:
        return []

    header = values[0]
    records = []

    for row in values[1:]:
        record = {}
        for index, column in enumerate(header):
            record[column] = row[index] if index < len(row) else ""
        records.append(record)

    return records


def build_courier_login_stats():
    giriton_records = _read_sheet_records(GIRITON_RAW_SHEET)
    attendance_records = _read_sheet_records(GIRITON_ATTENDANCE_SHEET)

    planned_counts = defaultdict(int)

    for record in giriton_records:
        name = str(record.get("nev", "")).strip()
        work_date = str(record.get("datum", "")).strip()

        if not name or name == "URES" or re.fullmatch(r"\d+\s+persons?", name, re.I) or not work_date:
            continue

        planned_counts[(work_date, name)] += 1

    attendance_by_key = {}

    for record in attendance_records:
        name = str(record.get("nev", "")).strip()
        work_date = str(record.get("datum", "")).strip()

        if not name or re.fullmatch(r"\d+\s+persons?", name, re.I) or not work_date:
            continue

        attendance_by_key[(work_date, name)] = record

    all_keys = sorted(
        set(planned_counts.keys()) | set(attendance_by_key.keys()),
        key=lambda item: (item[0], item[1].casefold()),
    )

    output = [[
        "datum",
        "futar_nev",
        "tervezett_muszak_db_giriton",
        "bejelentkezes_kezdete",
        "bejelentkezes_vege",
        "ledolgozott_ora",
        "attendance_statusz",
        "attendance_muszak",
    ]]

    for work_date, name in all_keys:
        attendance = attendance_by_key.get((work_date, name), {})
        planned_count = planned_counts.get((work_date, name), 0)
        attendance_status = attendance.get("statusz", "")

        if planned_count == 0 and attendance_status == "Didn't come":
            continue

        checkin_start = attendance.get("bejelentkezes_kezdete", "")
        checkin_end = attendance.get("bejelentkezes_vege", "")

        output.append([
            work_date,
            name,
            planned_count,
            checkin_start,
            checkin_end,
            _worked_hours(checkin_start, checkin_end),
            attendance_status,
            attendance.get("muszak", ""),
        ])

    ws = _get_or_create_worksheet(
        target_spreadsheet,
        COURIER_LOGIN_STATS_SHEET,
        rows=max(len(output) + 100, 1000),
        cols=len(output[0]),
    )
    _update_from_a1(ws, output)

    result = f"OK | {COURIER_LOGIN_STATS_SHEET} rows={len(output) - 1}"
    print(result)
    return result
