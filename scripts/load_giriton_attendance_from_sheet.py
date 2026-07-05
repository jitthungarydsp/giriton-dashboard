import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from google_client import open_spreadsheet
from resources.giriton_attendance_db import upsert_giriton_attendance_rows


TARGET_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
GIRITON_ATTENDANCE_SHEET = "Giriton_Attendance"


def load_rows_from_sheet():
    spreadsheet = open_spreadsheet(
        TARGET_SPREADSHEET_ID
    )
    worksheet = spreadsheet.worksheet(
        GIRITON_ATTENDANCE_SHEET
    )
    values = worksheet.get_all_values()

    if not values:
        return []

    return [
        row
        for row in values[1:]
        if any(str(cell or "").strip() for cell in row)
    ]


def main():
    rows = load_rows_from_sheet()
    result = upsert_giriton_attendance_rows(
        rows
    )
    print(
        f"Giriton_Attendance sheet sorok: {len(rows)}"
    )
    print(
        f"DB feltoltes: {result}"
    )


if __name__ == "__main__":
    main()
