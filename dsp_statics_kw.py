from datetime import datetime, timedelta

import requests

from dsp_common_kw import hu_time, local_today, parse_datetime
from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)

ATTENDANCE_BASE_URL = (
    "https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
    "fetch-attendance/JIT"
)

ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"


def minutes_between(start_value, end_value):
    start = parse_datetime(start_value)
    end = parse_datetime(end_value)

    if not start or not end:
        return ""

    return round(
        (end - start).total_seconds() / 60,
        1
    )


def format_minutes(value):
    if value == "":
        return ""

    return value


def choose_wait_minutes(available_to_registered, registered_to_assigned):
    if (
        available_to_registered != ""
        and available_to_registered >= 0
    ):
        return available_to_registered

    return registered_to_assigned


def find_matching_shift(route, shifts):
    route_registered = parse_datetime(
        route.get("courierRegisteredAt")
    )
    route_assigned = parse_datetime(
        route.get("assignedAt")
    )
    route_departure = (
        parse_datetime(route.get("realDeparture"))
        or parse_datetime(route.get("plannedDeparture"))
    )

    parsed_shifts = []

    for shift in shifts:
        parsed_shifts.append({
            "raw": shift,
            "start": parse_datetime(shift.get("shiftStart")),
            "end": parse_datetime(shift.get("shiftEnd")),
            "available": parse_datetime(
                shift.get("availableForShiftSince")
            ),
        })

    for item in parsed_shifts:
        available = item["available"]

        if not available:
            continue

        if route_registered and available == route_registered:
            return item["raw"], "available=courierRegisteredAt"

        if route_assigned and available == route_assigned:
            return item["raw"], "available=assignedAt"

    if route_departure:
        for item in parsed_shifts:
            start = item["start"]
            end = item["end"]

            if start and end and start <= route_departure <= end:
                return item["raw"], "routeDepartureInShift"

    candidates = []

    for item in parsed_shifts:
        available = item["available"]

        if not available:
            continue

        distances = []

        if route_registered:
            distances.append(
                abs(
                    (
                        route_registered - available
                    ).total_seconds()
                )
            )

        if route_assigned:
            distances.append(
                abs(
                    (
                        route_assigned - available
                    ).total_seconds()
                )
            )

        if distances:
            candidates.append(
                (
                    min(distances),
                    item["raw"]
                )
            )

    if candidates:
        return sorted(
            candidates,
            key=lambda item: item[0]
        )[0][1], "closestAvailable"

    if shifts:
        return shifts[0], "firstShiftFallback"

    return {}, ""


def fetch_attendance_for_date(work_date):
    url = (
        f"{ATTENDANCE_BASE_URL}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    response = requests.get(
        url,
        timeout=60
    )
    response.raise_for_status()

    return response.json()


def build_attendance_route_stat_rows_for_date(work_date):
    data = fetch_attendance_for_date(work_date)
    rows = []

    for courier in data.get("couriers", []):
        shifts = courier.get("shifts", [])
        routes = courier.get("routes", [])

        for route in routes:
            shift, match_source = find_matching_shift(
                route,
                shifts
            )

            available = shift.get(
                "availableForShiftSince",
                ""
            )
            wait_available_to_registered = minutes_between(
                available,
                route.get("courierRegisteredAt")
            )
            wait_registered_to_assigned = minutes_between(
                route.get("courierRegisteredAt"),
                route.get("assignedAt")
            )

            rows.append([
                work_date,
                courier.get("courierId", ""),
                courier.get("courierName", ""),
                courier.get("warehouseName", ""),
                shift.get("shiftId", ""),
                shift.get("shiftName", ""),
                hu_time(shift.get("shiftStart", "")),
                hu_time(shift.get("shiftEnd", "")),
                hu_time(available),
                route.get("routeId", ""),
                hu_time(route.get("courierRegisteredAt", "")),
                hu_time(route.get("assignedAt", "")),
                hu_time(route.get("plannedDeparture", "")),
                hu_time(route.get("realDeparture", "")),
                hu_time(route.get("plannedReturn", "")),
                hu_time(route.get("realReturn", "")),
                format_minutes(
                    choose_wait_minutes(
                        wait_available_to_registered,
                        wait_registered_to_assigned
                    )
                ),
                format_minutes(
                    wait_available_to_registered
                ),
                format_minutes(
                    wait_registered_to_assigned
                ),
                format_minutes(
                    minutes_between(
                        route.get("plannedDeparture"),
                        route.get("realDeparture")
                    )
                ),
                format_minutes(
                    minutes_between(
                        route.get("plannedReturn"),
                        route.get("realReturn")
                    )
                ),
                format_minutes(
                    minutes_between(
                        route.get("realDeparture"),
                        route.get("realReturn")
                    )
                ),
                match_source,
            ])

    return rows


def create_attendance_route_statistics(start_date=None, end_date=None):
    try:
        ws_stats = spreadsheet.worksheet(
            "DSP_Attendance_Route_Stats"
        )
    except:
        ws_stats = spreadsheet.add_worksheet(
            title="DSP_Attendance_Route_Stats",
            rows=50000,
            cols=30
        )

    today = local_today()

    if start_date:
        current = datetime.strptime(
            str(start_date),
            "%Y-%m-%d"
        ).date()
    else:
        current = today.replace(day=1)

    if end_date:
        last_day = datetime.strptime(
            str(end_date),
            "%Y-%m-%d"
        ).date()
    else:
        last_day = today

    rows = [[
        "date",
        "courierId",
        "courierName",
        "warehouseName",
        "shiftId",
        "shiftName",
        "shiftStart",
        "shiftEnd",
        "availableForShiftSince",
        "routeId",
        "courierRegisteredAt",
        "assignedAt",
        "plannedDeparture",
        "realDeparture",
        "plannedReturn",
        "realReturn",
        "wait_minutes",
        "wait_available_to_registered_minutes",
        "wait_registered_to_assigned_minutes",
        "departure_diff_minutes",
        "return_diff_minutes",
        "real_route_minutes",
        "match_source",
    ]]

    while current <= last_day:
        work_date = current.strftime("%Y-%m-%d")

        print(
            f"DSP_ATTENDANCE_ROUTE_DATE={work_date}"
        )

        try:
            daily_rows = build_attendance_route_stat_rows_for_date(
                work_date
            )

            rows.extend(daily_rows)

            print(
                f"  -> {len(daily_rows)} route sor"
            )
        except Exception as e:
            print(
                f"HIBA {work_date}: {e}"
            )

        current += timedelta(days=1)

    ws_stats.clear()
    ws_stats.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} attendance route statisztika feltoltve."
    )

    return "ATTENDANCE_ROUTE_STATS_OK"

def create_daily_statistics():

    ws_orders = spreadsheet.worksheet(
        "DSP_Orders"
    )

    try:

        ws_stats = spreadsheet.worksheet(
            "DSP_Daily_Stats"
        )

    except:

        ws_stats = spreadsheet.add_worksheet(
            title="DSP_Daily_Stats",
            rows=1000,
            cols=20
        )

    values = ws_orders.get_all_values()

    if len(values) < 2:
        return "NINCS_ADAT"

    headers = values[0]

    idx = {
        name: pos
        for pos, name in enumerate(headers)
    }

    daily_stats = {}

    for row in values[1:]:

        try:

            datum = row[
                idx["date"]
            ].strip()

            courier_id = row[
                idx["courierId"]
            ].strip()

            delivered = int(
                row[
                    idx["numDeliveredOrders"]
                ] or 0
            )

            if datum not in daily_stats:

                daily_stats[datum] = {
                    "couriers": set(),
                    "delivered": 0
                }

            daily_stats[datum]["couriers"].add(
                courier_id
            )

            daily_stats[datum]["delivered"] += (
                delivered
            )

        except Exception as e:

            print(
                f"HIBA: {e}"
            )

    rows = [[
        "date",
        "courier_count",
        "numDeliveredOrders",
        "avgDeliveredOrdersPerCourier"
    ]]

    for datum in sorted(
        daily_stats.keys()
    ):

        courier_count = len(
            daily_stats[datum][
                "couriers"
            ]
        )

        delivered = daily_stats[datum][
            "delivered"
        ]

        avg_delivered = 0

        if courier_count > 0:

            avg_delivered = round(
                delivered / courier_count,
                2
            )

        rows.append([
            datum,
            courier_count,
            delivered,
            avg_delivered
        ])

    ws_stats.clear()

    ws_stats.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} nap feldolgozva."
    )

    return "STAT_OK"

def create_driver_statistics():

    ws_orders = spreadsheet.worksheet(
        "DSP_Orders"
    )

    try:

        ws_stats = spreadsheet.worksheet(
            "DSP_Daily_Stat_Drivers"
        )

    except:

        ws_stats = spreadsheet.add_worksheet(
            title="DSP_Daily_Stat_Drivers",
            rows=50000,
            cols=20
        )

    values = ws_orders.get_all_values()

    if len(values) < 2:
        return "NINCS_ADAT"

    headers = values[0]

    idx = {
        name: pos
        for pos, name in enumerate(headers)
    }

    stats = {}

    for row in values[1:]:

        try:

            datum = row[
                idx["date"]
            ].strip()

            courier_id = row[
                idx["courierId"]
            ].strip()

            route_id = row[
                idx["routeId"]
            ].strip()

            delivered = int(
                row[
                    idx["numDeliveredOrders"]
                ] or 0
            )

            key = (
                datum,
                courier_id
            )

            if key not in stats:

                stats[key] = {
                    "routes": set(),
                    "delivered": 0
                }

            if route_id:

                stats[key]["routes"].add(
                    route_id
                )

            stats[key]["delivered"] += (
                delivered
            )

        except Exception as e:

            print(
                f"HIBA: {e}"
            )

    rows = [[
        "date",
        "courierId",
        "numDeliveredOrders",
        "route_count"
    ]]

    for key in sorted(stats.keys()):

        datum = key[0]
        courier_id = key[1]

        rows.append([
            datum,
            courier_id,
            stats[key]["delivered"],
            len(
                stats[key]["routes"]
            )
        ])

    ws_stats.clear()

    ws_stats.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} futár statisztika feltöltve."
    )

    return "STAT_OK"

def calculate_arrival_status():

    ws = spreadsheet.worksheet(
        "DSP_Order_Customers"
    )

    values = ws.get_all_values()

    if len(values) < 2:
        return "NINCS_ADAT"

    headers = values[0]

    idx = {
        name: pos
        for pos, name in enumerate(headers)
    }

    # oszlopok létrehozása ha még nincsenek

    if "arrival_status" not in headers:

        ws.update_cell(
            1,
            len(headers) + 1,
            "arrival_status"
        )

        ws.update_cell(
            1,
            len(headers) + 2,
            "arrival_diff_minutes"
        )

        headers.append(
            "arrival_status"
        )

        headers.append(
            "arrival_diff_minutes"
        )

        idx = {
            name: pos
            for pos, name in enumerate(headers)
        }

    updates = []

    for row_number, row in enumerate(
        values[1:],
        start=2
    ):

        try:

            status = ""
            diff = ""

            real_arrival = row[
                idx["realArrivalTime"]
            ]

            if real_arrival:

                deliver_since = parse_datetime(
                    row[
                        idx["deliverSince"]
                    ]
                )

                deliver_till = parse_datetime(
                    row[
                        idx["deliverTill"]
                    ]
                )

                real_arrival = parse_datetime(
                    real_arrival
                )

                if not deliver_since or not deliver_till or not real_arrival:
                    raise ValueError("Missing arrival time value")

                if (
                    deliver_since
                    <= real_arrival
                    <= deliver_till
                ):

                    status = "OK"
                    diff = 0

                elif real_arrival < deliver_since:

                    minutes = round(
                        (
                            deliver_since -
                            real_arrival
                        ).total_seconds() / 60,
                        1
                    )

                    status = "EARLY"
                    diff = -minutes

                else:

                    minutes = round(
                        (
                            real_arrival -
                            deliver_till
                        ).total_seconds() / 60,
                        1
                    )

                    status = "LATE"
                    diff = minutes

            updates.append([
                status,
                diff
            ])

        except Exception as e:

            print(
                f"HIBA sor {row_number}: {e}"
            )

            updates.append([
                "ERROR",
                ""
            ])

    start_col = len(headers) - 1

    range_name = (
        f"{chr(64 + start_col)}2:"
        f"{chr(65 + start_col)}"
        f"{len(values)}"
    )

    ws.update(
        range_name,
        updates
    )

    print(
        f"{len(updates)} sor feldolgozva."
    )

    return "ARRIVAL_STATUS_OK"

from datetime import datetime


def create_driver_summary():

    ws_drivers = spreadsheet.worksheet(
        "DSP_Drivers"
    )

    ws_orders = spreadsheet.worksheet(
        "DSP_Orders"
    )

    try:

        ws_summary = spreadsheet.worksheet(
            "DSP_Driver_Summary"
        )

    except:

        ws_summary = spreadsheet.add_worksheet(
            title="DSP_Driver_Summary",
            rows=5000,
            cols=30
        )

    drivers = ws_drivers.get_all_values()
    orders = ws_orders.get_all_values()

    driver_headers = drivers[0]
    order_headers = orders[0]

    driver_idx = {
        name: pos
        for pos, name in enumerate(driver_headers)
    }

    order_idx = {
        name: pos
        for pos, name in enumerate(order_headers)
    }

    summary = {}

    # ----------------------------------------
    # Futárok összegyűjtése
    # ----------------------------------------

    for row in drivers[1:]:

        try:

            driver_id = row[
                driver_idx["driver_id"]
            ].strip()

            if not driver_id:
                continue

            if driver_id not in summary:

                summary[driver_id] = {

                    "name": row[
                        driver_idx["name"]
                    ],

                    "warehouse": row[
                        driver_idx["warehouse_name"]
                    ],

                    "monday": 0,
                    "tuesday": 0,
                    "wednesday": 0,
                    "thursday": 0,
                    "friday": 0,
                    "saturday": 0,
                    "sunday": 0,

                    "monday_routes": 0,
                    "tuesday_routes": 0,
                    "wednesday_routes": 0,
                    "thursday_routes": 0,
                    "friday_routes": 0,
                    "saturday_routes": 0,
                    "sunday_routes": 0,
                    "weekly_income": 0
                }

        except Exception as e:

            print(e)

    # ----------------------------------------
    # DSP_Orders feldolgozása
    # ----------------------------------------

    for row in orders[1:]:

        try:

            courier_id = row[
                order_idx["courierId"]
            ].strip()

            if courier_id not in summary:
                continue

            datum = row[
                order_idx["date"]
            ].strip()

            delivered = int(
                row[
                    order_idx["numDeliveredOrders"]
                ] or 0
            )

            weekday = datetime.strptime(
                datum,
                "%Y-%m-%d"
            ).weekday()

            if weekday == 0:

                summary[courier_id]["monday"] += delivered
                summary[courier_id]["monday_routes"] += 1

            elif weekday == 1:

                summary[courier_id]["tuesday"] += delivered
                summary[courier_id]["tuesday_routes"] += 1

            elif weekday == 2:

                summary[courier_id]["wednesday"] += delivered
                summary[courier_id]["wednesday_routes"] += 1

            elif weekday == 3:

                summary[courier_id]["thursday"] += delivered
                summary[courier_id]["thursday_routes"] += 1

            elif weekday == 4:

                summary[courier_id]["friday"] += delivered
                summary[courier_id]["friday_routes"] += 1

            elif weekday == 5:

                summary[courier_id]["saturday"] += delivered
                summary[courier_id]["saturday_routes"] += 1

            elif weekday == 6:

                summary[courier_id]["sunday"] += delivered
                summary[courier_id]["sunday_routes"] += 1

        except Exception as e:

            print(e)

    rows = [[
        "driver_id",
        "name",
        "warehouse_name",

        "monday_delivered",
        "monday_routes",

        "tuesday_delivered",
        "tuesday_routes",

        "wednesday_delivered",
        "wednesday_routes",

        "thursday_delivered",
        "thursday_routes",

        "friday_delivered",
        "friday_routes",

        "saturday_delivered",
        "saturday_routes",

        "sunday_delivered",
        "sunday_routes"
    ]]

    for driver_id in sorted(summary.keys()):

        data = summary[driver_id]
        weekly_income = (

            data["monday_routes"] * 13000 +

            data["tuesday_routes"] * 11000 +

            data["wednesday_routes"] * 11000 +

            data["thursday_routes"] * 13000 +

            data["friday_routes"] * 13000 +

            data["saturday_routes"] * 13000 +

            data["sunday_routes"] * 11000

        )

        rows.append([

            driver_id,
            data["name"],
            data["warehouse"],

            data["monday"],
            data["monday_routes"],

            data["tuesday"],
            data["tuesday_routes"],

            data["wednesday"],
            data["wednesday_routes"],

            data["thursday"],
            data["thursday_routes"],

            data["friday"],
            data["friday_routes"],

            data["saturday"],
            data["saturday_routes"],

            data["sunday"],
            data["sunday_routes"],

                

        ])

    ws_summary.clear()

    ws_summary.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} futár összesítve."
    )

    return "DRIVER_SUMMARY_OK"
