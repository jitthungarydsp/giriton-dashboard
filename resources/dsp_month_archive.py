import gspread

from google_client import open_spreadsheet


SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"

ARCHIVE_SHEETS = [
    ("DSP_Drivers", "DSP_Drivers_Archive", "date"),
    ("DSP_Orders", "DSP_Orders_Archive", "date"),
    ("DSP_Order_Customers", "DSP_Order_Customers_Archive", "date"),
    ("DSP_Attendance_Route_Stats", "DSP_Attendance_Route_Stats_Archive", "date"),
    ("DSP_Earning_Estimate", "DSP_Earning_Estimate_Archive", "date"),
]


def get_spreadsheet():
    return open_spreadsheet(SPREADSHEET_ID)


def get_or_create_worksheet(spreadsheet, title, rows=1000, cols=30):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title,
            rows=rows,
            cols=cols,
        )


def month_from_date(value):
    text = str(value or "").strip()

    if len(text) < 7:
        return ""

    return text[:7]


def header_index(header, column):
    for index, name in enumerate(header):
        if str(name).strip() == column:
            return index

    return None


def read_values(spreadsheet, sheet_name):
    try:
        return spreadsheet.worksheet(sheet_name).get_all_values()
    except gspread.WorksheetNotFound:
        return []


def archive_sheet_month(spreadsheet, source_name, archive_name, date_column):
    source_values = read_values(
        spreadsheet,
        source_name,
    )

    if len(source_values) < 2:
        return {
            "source": source_name,
            "archive": archive_name,
            "rows": 0,
            "skipped": True,
        }

    header = source_values[0]
    date_index = header_index(header, date_column)

    if date_index is None:
        return {
            "source": source_name,
            "archive": archive_name,
            "rows": 0,
            "skipped": True,
            "reason": f"Hianyzik a datum oszlop: {date_column}",
        }

    months = {
        month_from_date(row[date_index] if date_index < len(row) else "")
        for row in source_values[1:]
    }
    months.discard("")

    if not months:
        return {
            "source": source_name,
            "archive": archive_name,
            "rows": 0,
            "skipped": True,
            "reason": "Nincs archivahato honap.",
        }

    archive_ws = get_or_create_worksheet(
        spreadsheet,
        archive_name,
        rows=max(len(source_values) + 1000, 1000),
        cols=max(len(header) + 5, 20),
    )
    archive_values = archive_ws.get_all_values()
    preserved_rows = []

    if archive_values:
        archive_header = archive_values[0]
        archive_date_index = header_index(
            archive_header,
            date_column,
        )

        if archive_date_index is not None:
            for row in archive_values[1:]:
                archive_month = month_from_date(
                    row[archive_date_index]
                    if archive_date_index < len(row)
                    else ""
                )

                if archive_month not in months:
                    preserved_rows.append(row)

    output = [
        header,
        *preserved_rows,
        *source_values[1:],
    ]
    archive_ws.clear()
    archive_ws.update(
        "A1",
        output,
    )

    return {
        "source": source_name,
        "archive": archive_name,
        "months": sorted(months),
        "rows": len(source_values) - 1,
    }


def archive_current_dsp_months():
    spreadsheet = get_spreadsheet()
    results = []

    for source_name, archive_name, date_column in ARCHIVE_SHEETS:
        results.append(
            archive_sheet_month(
                spreadsheet,
                source_name,
                archive_name,
                date_column,
            )
        )

    return results
