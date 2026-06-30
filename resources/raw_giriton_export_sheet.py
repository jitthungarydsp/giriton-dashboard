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
CHANGE_LOG_SHEET = "Valtozasok"
SNAPSHOT_PREFIX = "_snapshot_"


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


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_cell(value):
    return str(value or "").strip()


def _normalize_row(row):
    return [
        _normalize_cell(value)
        for value in row
    ]


def _row_signature(row):
    return " | ".join(_normalize_row(row))


def _get_snapshot_sheet_name(sheet_name):
    return f"{SNAPSHOT_PREFIX}{sheet_name}"[:100]


def _read_snapshot(sheet_name):
    snapshot_ws = _get_or_create_worksheet(
        target_spreadsheet,
        _get_snapshot_sheet_name(sheet_name),
        rows=1000,
        cols=30,
    )

    return snapshot_ws.get_all_values()


def _write_snapshot(sheet_name, values):
    snapshot_ws = _get_or_create_worksheet(
        target_spreadsheet,
        _get_snapshot_sheet_name(sheet_name),
        rows=max(len(values) + 100, 1000),
        cols=max((len(row) for row in values), default=20),
    )

    _update_from_a1(snapshot_ws, values)


def _append_change_rows(change_rows):
    if not change_rows:
        return 0

    ws = _get_or_create_worksheet(
        target_spreadsheet,
        CHANGE_LOG_SHEET,
        rows=50000,
        cols=10,
    )

    values = ws.get_all_values()
    header = [
        "timestamp",
        "sheet",
        "change_type",
        "key",
        "field",
        "old_value",
        "new_value",
    ]

    if not values:
        ws.update(
            "A1",
            [header],
            value_input_option="USER_ENTERED",
        )

    ws.append_rows(
        change_rows,
        value_input_option="USER_ENTERED",
    )

    return len(change_rows)


def _diff_rowset(sheet_name, old_values, new_values, key_columns=None):
    if not old_values and not new_values:
        return []

    timestamp = _now_text()
    old_header = old_values[0] if old_values else []
    new_header = new_values[0] if new_values else []
    header = new_header or old_header

    if key_columns is None:
        key_columns = []

    def make_key(row, row_number):
        normalized = _normalize_row(row)
        if key_columns:
            parts = []
            for column in key_columns:
                if column < len(normalized):
                    parts.append(normalized[column])
            key = " | ".join(parts).strip()
            if key:
                return key

        return _row_signature(row) or f"row:{row_number}"

    old_map = {}
    new_map = {}

    for index, row in enumerate(old_values[1:], start=2):
        old_map[make_key(row, index)] = _normalize_row(row)

    for index, row in enumerate(new_values[1:], start=2):
        new_map[make_key(row, index)] = _normalize_row(row)

    changes = []

    for key in sorted(set(new_map) - set(old_map)):
        changes.append([
            timestamp,
            sheet_name,
            "ADDED",
            key,
            "",
            "",
            _row_signature(new_map[key]),
        ])

    for key in sorted(set(old_map) - set(new_map)):
        changes.append([
            timestamp,
            sheet_name,
            "REMOVED",
            key,
            "",
            _row_signature(old_map[key]),
            "",
        ])

    for key in sorted(set(old_map) & set(new_map)):
        old_row = old_map[key]
        new_row = new_map[key]
        max_len = max(len(old_row), len(new_row), len(header))

        for index in range(max_len):
            old_value = old_row[index] if index < len(old_row) else ""
            new_value = new_row[index] if index < len(new_row) else ""

            if old_value == new_value:
                continue

            field = header[index] if index < len(header) else f"col_{index + 1}"
            changes.append([
                timestamp,
                sheet_name,
                "CHANGED",
                key,
                field,
                old_value,
                new_value,
            ])

    return changes


def _diff_matrix(sheet_name, old_values, new_values):
    if not old_values and not new_values:
        return []

    timestamp = _now_text()

    def matrix_cells(values):
        if not values:
            return {}

        header = values[0]
        cells = {}

        for row in values[1:]:
            if not row:
                continue

            shift_name = _normalize_cell(row[0])

            if not shift_name or shift_name == "Befoglalt muszakok":
                continue

            for index in range(3, len(header)):
                date_text = _normalize_cell(header[index])

                if not date_text:
                    continue

                value = _normalize_cell(row[index] if index < len(row) else "")
                cells[(shift_name, date_text)] = value

        return cells

    old_cells = matrix_cells(old_values)
    new_cells = matrix_cells(new_values)
    changes = []

    for key in sorted(set(old_cells) | set(new_cells)):
        old_value = old_cells.get(key, "")
        new_value = new_cells.get(key, "")

        if old_value == new_value:
            continue

        shift_name, date_text = key
        changes.append([
            timestamp,
            sheet_name,
            "CHANGED",
            shift_name,
            date_text,
            old_value,
            new_value,
        ])

    return changes


def _log_sheet_changes(sheet_name, new_values, key_columns=None, matrix=False):
    old_values = _read_snapshot(sheet_name)

    if matrix:
        change_rows = _diff_matrix(
            sheet_name,
            old_values,
            new_values,
        )
    else:
        change_rows = _diff_rowset(
            sheet_name,
            old_values,
            new_values,
            key_columns=key_columns,
        )

    written = _append_change_rows(change_rows)
    _write_snapshot(sheet_name, new_values)
    return written


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
    changes = _log_sheet_changes(
        TARGET_FOGLALASOK_SHEET,
        values,
    )
    return len(values), changes


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
    changes = _log_sheet_changes(
        GIRITON_RAW_SHEET,
        output,
        key_columns=[0, 1, 2, 3, 7],
    )
    return len(rows), changes


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

        changes = _log_sheet_changes(
            sheet_name,
            output,
            matrix=True,
        )

        summaries.append(
            f"{sheet_name}: shifts={len(matrix)}, dates={len(dates)}, rows={len(output)}, changes={changes}"
        )

    return summaries


def write_raw_export(rows):
    if not rows:
        raise ValueError("Nincs feldolgozhato Giriton sor.")

    copied_foglalasok_rows, foglalasok_changes = copy_foglalasok()
    giriton_rows, giriton_changes = write_giriton_raw(rows)
    matrix_summaries = write_open_shift_matrices(rows)

    result = (
        "OK | "
        f"Foglalasok copied={copied_foglalasok_rows}, changes={foglalasok_changes} | "
        f"Giriton rows={giriton_rows}, changes={giriton_changes} | "
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
