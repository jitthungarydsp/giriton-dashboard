import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_SERVICE_ACCOUNT_FILE = r"C:\Giriton\giriton-dashboard\girition-a89bab5e91bc.json"
LOCAL_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "girition-a89bab5e91bc.json",
)
DEFAULT_SPREADSHEET_ID = "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
WORKSHEET_NAME = "Route_Statistics"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "work_date",
    "updated_at",
    "driver_id",
    "driver_name",
    "route_id",
    "status",
    "license_plate",
    "total_distance_km",
    "distance_covered_km",
    "parcels_delivered",
    "parcels_total",
]


def resolve_service_account_file():
    configured_path = os.getenv("GIRITON_GOOGLE_CREDENTIALS")

    if configured_path:
        return configured_path

    if os.path.exists(DEFAULT_SERVICE_ACCOUNT_FILE):
        return DEFAULT_SERVICE_ACCOUNT_FILE

    return LOCAL_SERVICE_ACCOUNT_FILE


def get_spreadsheet_id():
    return os.getenv(
        "ROUTE_STATS_SPREADSHEET_ID",
        DEFAULT_SPREADSHEET_ID,
    )


def get_service_account_email():
    try:
        with open(
            resolve_service_account_file(),
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        return data.get("client_email", "")
    except OSError:
        return ""


def get_client():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        resolve_service_account_file(),
        scopes=SCOPES,
    )

    return gspread.authorize(creds)


def get_or_create_worksheet(spreadsheet):
    import gspread

    try:
        return spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(HEADER),
        )


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current in [None, ""]:
            return default

    return current


def get_route_id(driver):
    for path in [
        ["route", "id"],
        ["route", "route_id"],
        ["route_id"],
        ["status", "route_id"],
        ["current_shift", "shift_name"],
    ]:
        value = nested_get(driver, path)

        if value:
            return value

    return ""


def build_route_statistics_records(drivers):
    updated_at = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")
    work_date = datetime.now(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d")

    records = []

    for driver in drivers:
        statistics = nested_get(
            driver,
            ["route", "statistics"],
            {},
        )

        if not isinstance(statistics, dict):
            statistics = {}

        records.append({
            "work_date": work_date,
            "updated_at": updated_at,
            "driver_id": driver.get("driver_id", ""),
            "driver_name": nested_get(driver, ["personal_info", "name"]),
            "route_id": get_route_id(driver),
            "status": nested_get(driver, ["status", "current_state"]),
            "license_plate": nested_get(driver, ["vehicle", "license_plate"]),
            "total_distance_km": statistics.get("total_distance_km", ""),
            "distance_covered_km": statistics.get("distance_covered_km", ""),
            "parcels_delivered": statistics.get("parcels_delivered", ""),
            "parcels_total": statistics.get("parcels_total", ""),
        })

    return records


def record_key(record):
    return (
        str(record.get("work_date", "")),
        str(record.get("driver_id", "")),
        str(record.get("route_id", "")),
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


def read_route_statistics():
    client = get_client()
    spreadsheet = client.open_by_key(
        get_spreadsheet_id()
    )
    worksheet = get_or_create_worksheet(
        spreadsheet
    )

    return worksheet.get_all_records()


def write_route_statistics(drivers):
    client = get_client()
    spreadsheet = client.open_by_key(
        get_spreadsheet_id()
    )
    worksheet = get_or_create_worksheet(
        spreadsheet
    )

    existing_records = worksheet.get_all_records()
    existing_by_key = {
        record_key(record): record
        for record in existing_records
    }

    for record in build_route_statistics_records(drivers):
        existing_by_key[record_key(record)] = record

    records = sorted(
        existing_by_key.values(),
        key=lambda record: (
            str(record.get("work_date", "")),
            str(record.get("driver_name", "")),
            str(record.get("route_id", "")),
        ),
    )

    worksheet.clear()
    worksheet.update(
        "A1",
        records_to_rows(records),
    )

    return "OK"
