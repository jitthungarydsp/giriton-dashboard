import os
import re
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SERVICE_ACCOUNT_FILE = os.getenv(
    "GIRITON_GOOGLE_CREDENTIALS",
    r"C:\Giriton\giriton-dashboard\girition-a89bab5e91bc.json",
)

KIFLI_SYNC_SPREADSHEET_ID = os.getenv(
    "KIFLI_SYNC_SPREADSHEET_ID",
    "1yWO5bBWpXPNuOhoE58m2amZmOW_Bp65qLBibgovKtao",
)

WAREHOUSE_SHEETS = {
    "BUD1": "BUD1_PROD2.0",
    "BUD2": "BUD2_PROD2.0",
}

STOP_ROW_LABEL = "Befoglalt műszakok"
def get_client():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    return gspread.authorize(creds)


def normalize_shift_time(value):
    value = str(value).strip()

    if not value:
        return value

    hour, minute = value.split(":", 1)

    return f"{int(hour)}:{minute.zfill(2)}"


def format_sheet_date(value):
    parsed = datetime.strptime(
        str(value).strip(),
        "%Y-%m-%d",
    )

    return parsed.strftime("%m.%d.")


def parse_limit(value):
    value = str(value).strip()

    if not value:
        return ""

    if "/" in value:
        value = value.split("/")[-1]

    match = re.search(r"\d+", value)

    if not match:
        return ""

    return int(match.group(0))


def get_or_create_worksheet(spreadsheet, title):
    import gspread

    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title,
            rows=200,
            cols=60,
        )


def build_sheet_rows(rows, warehouse):
    dates = []
    shifts = []
    values_by_shift_and_date = {}

    for row in rows:
        if len(row) < 5:
            continue

        date_value = row[0]
        start_time = row[1]
        row_warehouse = row[3]
        limit_value = row[4]

        if str(row_warehouse).strip() != warehouse:
            continue

        date_header = format_sheet_date(date_value)
        shift_name = f"{warehouse}_{normalize_shift_time(start_time)}"
        limit = parse_limit(limit_value)

        if date_header not in dates:
            dates.append(date_header)

        if shift_name not in shifts:
            shifts.append(shift_name)

        values_by_shift_and_date[
            (shift_name, date_header)
        ] = limit

    shifts.sort()

    output = [
        ["Műszak szinkron", "", *dates],
        ["Műszak neve", "", *dates],
    ]

    for shift_name in shifts:
        output.append(
            [
                shift_name,
                "",
                *[
                    values_by_shift_and_date.get(
                        (shift_name, date_header),
                        "",
                    )
                    for date_header in dates
                ],
            ]
        )

    output.append(
        [
            STOP_ROW_LABEL,
            "(A kód itt megáll)",
            *["" for _ in dates],
        ]
    )

    return output


def write_kifli_sync(rows):
    client = get_client()

    spreadsheet = client.open_by_key(
        KIFLI_SYNC_SPREADSHEET_ID
    )

    results = []

    for warehouse, sheet_name in WAREHOUSE_SHEETS.items():
        worksheet = get_or_create_worksheet(
            spreadsheet,
            sheet_name,
        )

        output = build_sheet_rows(
            rows,
            warehouse,
        )

        worksheet.clear()
        worksheet.update(
            "A1",
            output,
        )

        results.append(
            f"{sheet_name}: {len(output) - 3} muszak"
        )

    return "OK - " + ", ".join(results)
