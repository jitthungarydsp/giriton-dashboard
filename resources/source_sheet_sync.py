from google_client import open_spreadsheet
from resources.dsp_dashboard_statistics import SPREADSHEET_ID as TARGET_SPREADSHEET_ID


SOURCE_SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
SHEETS_TO_COPY = [
    "Foglalasok",
    "Felhasznalok",
]


def get_or_create_worksheet(spreadsheet, title, rows=1000, cols=30):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(
            title=title,
            rows=rows,
            cols=cols,
        )


def copy_values(source_ws, target_ws, values):
    target_ws.clear()

    if values:
        target_ws.update(
            "A1",
            values,
        )


def sync_source_sheets():
    source_spreadsheet = open_spreadsheet(
        SOURCE_SPREADSHEET_ID
    )
    target_spreadsheet = open_spreadsheet(
        TARGET_SPREADSHEET_ID
    )
    result = {}

    for sheet_name in SHEETS_TO_COPY:
        source_ws = source_spreadsheet.worksheet(
            sheet_name
        )
        values = source_ws.get_all_values()
        max_cols = max(
            (len(row) for row in values),
            default=30,
        )
        target_ws = get_or_create_worksheet(
            target_spreadsheet,
            sheet_name,
            rows=max(len(values) + 100, 1000),
            cols=max(max_cols, 30),
        )
        copy_values(
            source_ws,
            target_ws,
            values,
        )
        result[sheet_name] = len(values)

    return result
