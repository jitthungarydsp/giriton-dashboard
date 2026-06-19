import requests
import gspread

from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    r"C:\Giriton\girition-a89bab5e91bc.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)


def load_orders():

    ws_drivers = spreadsheet.worksheet("DSP_Drivers")

    try:
        ws_orders = spreadsheet.worksheet("DSP_Orders")
    except:
        ws_orders = spreadsheet.add_worksheet(
            title="DSP_Orders",
            rows=50000,
            cols=50
        )

    drivers = ws_drivers.get_all_values()

    rows = [[
        "courierId",
        "date",
        "warehouseName",
        "routeId",
        "id",
        "courierRegisteredAt",
        "createdAt",
        "assignedAt",
        "loadingTime",
        "plannedDeparture",
        "realDeparture",
        "plannedReturn",
        "realReturn",
        "status",
        "numTotalOrders",
        "numDeliveredOrders",
        "numDelayedOrdersSlot",
        "numDelayedOrdersPlan",
        "numDelayedOrdersEstimate"
    ]]

    for row in drivers[1:]:

        try:

            datum = row[0]
            driver_id = row[1]

            url = (
                f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
                f"fetch-drivers-detail/{driver_id}/{datum}"
                f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
            )

            print(f"Lekérés: {driver_id} - {datum}")

            response = requests.get(url)
            data = response.json()

            courier_id = data.get("courier-id")
            warehouse = data.get("warehouseName")

            for route in data.get("routes", []):

                rows.append([
                    courier_id,
                    datum,
                    warehouse,
                    route.get("id"),
                    route.get("id"),
                    route.get("courierRegisteredAt"),
                    route.get("createdAt"),
                    route.get("assignedAt"),
                    route.get("loadingTime"),
                    route.get("plannedDeparture"),
                    route.get("realDeparture"),
                    route.get("plannedReturn"),
                    route.get("realReturn"),
                    route.get("status"),
                    route.get("numTotalOrders"),
                    route.get("numDeliveredOrders"),
                    route.get("numDelayedOrdersSlot"),
                    route.get("numDelayedOrdersPlan"),
                    route.get("numDelayedOrdersEstimate")
                ])

        except Exception as e:

            print(
                f"HIBA {driver_id} {datum}: {e}"
            )

    ws_orders.clear()

    ws_orders.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} sor feltöltve."
    )

    return "OK"