import requests
from dsp_common_kw import hu_time
from datetime import datetime
from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)

# KPI DEFINITIONS
#
# routeCreationMinutes
# createdAt - courierRegisteredAt
# Megmutatja mennyi idő telt el a futár bejelentkezése és a túra elkészülése között.
#
# loadingAfterCreationMinutes
# loadingTime - createdAt
# Túra elkészülésétől rakodásig eltelt idő.
#
# departureDelayMinutes
# realDeparture - plannedDeparture
# Indulási csúszás percben.
#
# plannedTourMinutes
# plannedReturn - plannedDeparture
# Tervezett túrahossz.
#
# realTourMinutes
# realReturn - realDeparture
# Valós túrahossz.
#
# returnDelayMinutes
# realReturn - plannedReturn
# Visszaérkezési eltérés.
#
# routeType
# EXPRESS <= 90 perc
# NORMAL <= 120 perc
# EXTRA > 120 perc
#
# comment
# Emberi olvasható KPI összefoglaló.

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
    "totalWaitMinutes",
    "routeCreationMinutes",
    "loadingAfterCreationMinutes",
    "assignmentToLoadingMinutes",
    "departureDelayMinutes",
    "plannedTourMinutes",
    "realTourMinutes",
    "returnDelayMinutes",
    "comment"
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

                    created = datetime.fromisoformat(
                        route.get("createdAt").replace("Z", "+00:00")
                    )

                    assigned = datetime.fromisoformat(
                        route.get("assignedAt").replace("Z", "+00:00")
                    )

                    loading = datetime.fromisoformat(
                        route.get("loadingTime").replace("Z", "+00:00")
                    )

                    planned_departure = datetime.fromisoformat(
                        route.get("plannedDeparture").replace("Z", "+00:00")
                    )

                    real_departure = datetime.fromisoformat(
                        route.get("realDeparture").replace("Z", "+00:00")
                    )

                    planned_return = datetime.fromisoformat(
                        route.get("plannedReturn").replace("Z", "+00:00")
                    )

                    real_return = datetime.fromisoformat(
                        route.get("realReturn").replace("Z", "+00:00")
                    )

                    wait_route = round(
                        (assigned - registered).total_seconds() / 60
                    )

                    wait_loading = round(
                        (loading - assigned).total_seconds() / 60
                    )

                    wait_total = round(
                        (real_departure - registered).total_seconds() / 60
                    )

                    route_creation_minutes = round(
                        (created - registered).total_seconds() / 60
                    )

                    loading_after_creation_minutes = round(
                        (loading - created).total_seconds() / 60
                    )

                    assignment_to_loading_minutes = round(
                        (loading - assigned).total_seconds() / 60
                    )

                    departure_delay_minutes = round(
                        (real_departure - planned_departure).total_seconds() / 60
                    )

                    planned_tour_minutes = round(
                        (planned_return - planned_departure).total_seconds() / 60
                    )

                    real_tour_minutes = round(
                        (real_return - real_departure).total_seconds() / 60
                    )

                    return_delay_minutes = round(
                        (real_return - planned_return).total_seconds() / 60
                    )

                    comments = []

                    if route_creation_minutes > 0:

                        comments.append(
                            f"Raktári késés: a túra {route_creation_minutes} perccel a futár bejelentkezése után készült el."
                        )

                    comments.append(
                        f"Rakodás kezdete {loading_after_creation_minutes} perccel a túra elkészülése után történt."
                    )

                    comments.append(
                        f"Kiosztás és rakodás között {assignment_to_loading_minutes} perc telt el."
                    )

                    if departure_delay_minutes > 0:

                        comments.append(
                            f"A futár {departure_delay_minutes} perc késéssel indult a tervezetthez képest."
                        )

                    else:

                        comments.append(
                            "A futár időben vagy a tervezettnél korábban indult."
                        )

                    comments.append(
                        f"A tervezett túrahossz {planned_tour_minutes} perc volt."
                    )

                    comments.append(
                        f"A valós túrahossz {real_tour_minutes} perc volt."
                    )

                    if return_delay_minutes > 0:

                        comments.append(
                            f"A futár {return_delay_minutes} perc késéssel érkezett vissza."
                        )

                    else:

                        comments.append(
                            "A futár időben vagy a tervezettnél korábban érkezett vissza."
                        )

                    comment = " | ".join(comments)

                except Exception:

                    wait_route = ""
                    wait_loading = ""
                    wait_total = ""

                    route_creation_minutes = ""
                    loading_after_creation_minutes = ""
                    assignment_to_loading_minutes = ""

                    departure_delay_minutes = ""
                    planned_tour_minutes = ""
                    real_tour_minutes = ""
                    return_delay_minutes = ""

                    comment = ""

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
                    wait_total,
                    route_creation_minutes,
                    loading_after_creation_minutes,
                    assignment_to_loading_minutes,
                    departure_delay_minutes,
                    planned_tour_minutes,
                    real_tour_minutes,
                    return_delay_minutes,
                    comment
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
