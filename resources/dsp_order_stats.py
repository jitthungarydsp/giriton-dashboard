import json
import os

import pandas as pd


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


def resolve_service_account_file():
    configured_path = os.getenv("GIRITON_GOOGLE_CREDENTIALS")

    if configured_path:
        return configured_path

    if os.path.exists(DEFAULT_SERVICE_ACCOUNT_FILE):
        return DEFAULT_SERVICE_ACCOUNT_FILE

    return LOCAL_SERVICE_ACCOUNT_FILE


def get_spreadsheet_id():
    return os.getenv(
        "DSP_STATS_SPREADSHEET_ID",
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


def read_worksheet_records(sheet_name):
    client = get_client()
    spreadsheet = client.open_by_key(
        get_spreadsheet_id()
    )
    worksheet = spreadsheet.worksheet(
        sheet_name
    )

    return worksheet.get_all_records()


def normalize_id(value):
    if value in [None, ""]:
        return ""

    value = str(value).strip()

    if value.endswith(".0"):
        value = value[:-2]

    return value


def to_number(series):
    return pd.to_numeric(
        series,
        errors="coerce",
    ).fillna(0)


def load_order_data():
    orders = pd.DataFrame(
        read_worksheet_records("DSP_Orders")
    )
    customers = pd.DataFrame(
        read_worksheet_records("DSP_Order_Customers")
    )

    if not orders.empty:
        orders["courierId"] = orders["courierId"].apply(normalize_id)
        orders["routeId"] = orders["routeId"].apply(normalize_id)
        orders["id"] = orders["id"].apply(normalize_id)

        for column in [
            "numTotalOrders",
            "numDeliveredOrders",
            "numDelayedOrdersSlot",
            "numDelayedOrdersPlan",
            "numDelayedOrdersEstimate",
            "waitForRouteMinutes",
            "waitForLoadingMinutes",
            "totalWaitMinutes",
            "routeCreationMinutes",
            "loadingAfterCreationMinutes",
            "assignmentToLoadingMinutes",
            "departureDelayMinutes",
            "plannedTourMinutes",
            "realTourMinutes",
            "returnDelayMinutes",
        ]:
            if column in orders.columns:
                orders[column] = to_number(orders[column])

    if not customers.empty:
        customers["courierId"] = customers["courierId"].apply(normalize_id)
        customers["routeId"] = customers["routeId"].apply(normalize_id)
        customers["id"] = customers["id"].apply(normalize_id)

    return orders, customers


def filter_courier_data(orders, customers, courier_id):
    courier_id = normalize_id(courier_id)

    if not orders.empty:
        orders = orders[
            orders["courierId"] == courier_id
        ].copy()

    if not customers.empty:
        customers = customers[
            customers["courierId"] == courier_id
        ].copy()

    return orders, customers


def get_route_order_row(orders, route_id):
    if orders.empty:
        return {}

    route_id = normalize_id(route_id)
    matching = orders[
        (orders["routeId"] == route_id)
        |
        (orders["id"] == route_id)
    ]

    if matching.empty:
        return {}

    return matching.iloc[0].to_dict()


def get_route_customers(customers, route_id):
    if customers.empty:
        return customers

    route_id = normalize_id(route_id)

    return customers[
        customers["routeId"] == route_id
    ].copy()


def build_courier_summary(orders, customers):
    if orders.empty:
        return {
            "routes": 0,
            "total_orders": 0,
            "delivered_orders": 0,
            "customer_addresses": 0,
            "avg_delivered_per_route": 0,
        }

    routes = orders["routeId"].nunique()
    delivered = orders.get(
        "numDeliveredOrders",
        pd.Series(dtype=float),
    ).sum()
    total = orders.get(
        "numTotalOrders",
        pd.Series(dtype=float),
    ).sum()
    customer_addresses = (
        customers["id"].nunique()
        if not customers.empty and "id" in customers.columns
        else 0
    )

    return {
        "routes": int(routes),
        "total_orders": int(total),
        "delivered_orders": int(delivered),
        "customer_addresses": int(customer_addresses),
        "avg_delivered_per_route": delivered / routes if routes else 0,
    }
