import requests
import gspread
from dsp_common_kw import hu_time
from google.oauth2.service_account import Credentials
from datetime import datetime


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    r"C:\Giriton\giriton-dashboard\girition-a89bab5e91bc.json",
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
    "numDelayedOrdersEstimate",

    "waitForRouteMinutes",
    "waitForLoadingMinutes",
    "totalWaitMinutes"
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
                wait_route = ""
                wait_loading = ""
                wait_total = ""

                try:

                    registered = datetime.fromisoformat(
                        route.get("courierRegisteredAt").replace("Z", "+00:00")
                    )

                    assigned = datetime.fromisoformat(
                        route.get("assignedAt").replace("Z", "+00:00")
                    )

                    loading = datetime.fromisoformat(
                        route.get("loadingTime").replace("Z", "+00:00")
                    )

                    departure = datetime.fromisoformat(
                        route.get("realDeparture").replace("Z", "+00:00")
                    )

                    wait_route = round(
                        (assigned - registered).total_seconds() / 60
                    )

                    wait_loading = round(
                        (loading - assigned).total_seconds() / 60
                    )

                    wait_total = round(
                        (departure - registered).total_seconds() / 60
                    )

                except:
                    pass

                rows.append([
                    courier_id,
                    datum,
                    warehouse,
                    route.get("id"),
                    route.get("id"),
                    hu_time(route.get("courierRegisteredAt")),
                    hu_time(route.get("createdAt")),
                    hu_time(route.get("assignedAt")),
                    hu_time(route.get("loadingTime")),
                    hu_time(route.get("plannedDeparture")),
                    hu_time(route.get("realDeparture")),
                    hu_time(route.get("plannedReturn")),
                    hu_time(route.get("realReturn")),
                    route.get("status"),
                    route.get("numTotalOrders"),
                    route.get("numDeliveredOrders"),
                    route.get("numDelayedOrdersSlot"),
                    route.get("numDelayedOrdersPlan"),
                    route.get("numDelayedOrdersEstimate"),
                    wait_route,
                    wait_loading,
                    wait_total
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