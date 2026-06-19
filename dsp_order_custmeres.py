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


def load_order_customers():

    ws_drivers = spreadsheet.worksheet("DSP_Drivers")

    try:
        ws_customers = spreadsheet.worksheet(
            "DSP_Order_Customers"
        )
    except:
        ws_customers = spreadsheet.add_worksheet(
            title="DSP_Order_Customers",
            rows=100000,
            cols=30
        )

    drivers = ws_drivers.get_all_values()

    rows = [[
        "courierId",
        "date",
        "routeId",
        "id",
        "orderId",
        "position",
        "latitude",
        "longitude",
        "address",
        "deliverSince",
        "deliverTill",
        "plannedArrivalTime",
        "estimatedArrivalTime",
        "realArrivalTime",
        "plannedDepartureTime",
        "estimatedDepartureTime",
        "realDepartureTime"
    ]]

    for row in drivers[1:]:

        try:

            datum = row[0]
            driver_id = row[1]

            print(
                f"Driver: {driver_id} - {datum}"
            )

            url = (
                f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
                f"fetch-drivers-detail/{driver_id}/{datum}"
                f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
            )

            response = requests.get(url)

            data = response.json()

            courier_id = data.get(
                "courier-id"
            )

            for route in data.get(
                "routes",
                []
            ):

                route_id = route.get(
                    "id"
                )

                for checkpoint in route.get(
                    "checkpoints",
                    []
                ):

                    rows.append([
                        courier_id,
                        datum,
                        route_id,
                        checkpoint.get("id"),
                        checkpoint.get("orderId"),
                        checkpoint.get("position"),
                        checkpoint.get("latitude"),
                        checkpoint.get("longitude"),
                        checkpoint.get("address"),
                        checkpoint.get("deliverSince"),
                        checkpoint.get("deliverTill"),
                        checkpoint.get("plannedArrivalTime"),
                        checkpoint.get("estimatedArrivalTime"),
                        checkpoint.get("realArrivalTime"),
                        checkpoint.get("plannedDepartureTime"),
                        checkpoint.get("estimatedDepartureTime"),
                        checkpoint.get("realDepartureTime")
                    ])

        except Exception as e:

            print(
                f"HIBA {driver_id} {datum}: {e}"
            )

    ws_customers.clear()

    ws_customers.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} checkpoint feltöltve."
    )

    return "OK"