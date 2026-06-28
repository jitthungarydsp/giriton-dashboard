import requests
from dsp_common_kw import hu_time
from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
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
                        hu_time(checkpoint.get("deliverSince")),
                        hu_time(checkpoint.get("deliverTill")),
                        hu_time(checkpoint.get("plannedArrivalTime")),
                        hu_time(checkpoint.get("estimatedArrivalTime")),
                        hu_time(checkpoint.get("realArrivalTime")),
                        hu_time(checkpoint.get("plannedDepartureTime")),
                        hu_time(checkpoint.get("estimatedDepartureTime")),
                        hu_time(checkpoint.get("realDepartureTime"))
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
