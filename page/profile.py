import streamlit as st
import pandas as pd
import altair as alt
from dsp_common_kw  import  hu_time

from resources.dsp_order_stats import (
    build_courier_summary,
    filter_courier_data,
    get_route_customers,
    get_route_order_row,
    load_order_data,
)
from resources.api import (
    load_attendance,
    load_driver_details,
    load_departure_dashboard,
    load_drivers
)


def show_profile_page():

    st.title(
        "👤 Saját profil"
    )

    user = st.session_state["user"]
    # -------------------------
    # Jogosultság
    # -------------------------

    user = st.session_state["user"]

    selected_courier_id = user.get("courierId")
    selected_name = user.get("username")

    attendance = load_attendance()

    couriers = attendance.get(
        "couriers",
        []
    )

    st.subheader(
        "Felhasználó adatai"
    )

    st.write(
        f"**Név:** {user['username']}"
    )

    st.write(
        f"**Jogosultság:** {user['role']}"
    )

    st.write(
        f"**Courier ID:** {user.get('courierId')}"
    )

    attendance = load_attendance()

    couriers = attendance.get(
        "couriers",
        []
    )
    # -------------------------
    # Látható futárok
    # -------------------------

    from resources.users import load_users

    users_data = load_users()

    portal_users = users_data["users"]

    visible_couriers = []

    if user["role"] == "admin":

        visible_couriers = couriers

    elif user["role"] == "trainer":

        trainer_name = user["username"]

        trainer_courier_ids = []

        for u in portal_users:

            if u.get("trainer") == trainer_name:

                trainer_courier_ids.append(
                    u.get("courierId")
                )

        visible_couriers = [

            c

            for c in couriers

            if c.get("courierId")
            in trainer_courier_ids

        ]

    else:

        visible_couriers = [

            c

            for c in couriers

            if c.get("courierId")
            ==
            selected_courier_id

        ]
    # -------------------------
    # User
    # -------------------------
    # -------------------------
    # Futár kiválasztása
    # -------------------------

    selected_courier = None
    departure_data = load_departure_dashboard()

    if user["role"] == "user":

        selected_courier = visible_couriers[0] if visible_couriers else None

        if not selected_courier:

            st.warning(
                "Nincs aktív műszak vagy futár adat."
            )

            return

    else:

        search = st.text_input(
            "🔍 Futár keresése"
        )

        filtered = visible_couriers

        if search:

            filtered = [

                c

                for c in visible_couriers

                if search.lower()
                in c.get(
                    "courierName",
                    ""
                ).lower()

            ]

        if not filtered:

            st.warning(
                "Nincs találat."
            )

            return
        
    departure_routes = departure_data.get("routes", [])

    courier_status = {}

    for route in departure_routes:

        courier_id = route.get("courier_id")

        delayed = route.get(
            "numDelayedOrdersEstimate",
            0
        )

        temperature = None

        if isinstance(route.get("temperature"), dict):
            temperature = route["temperature"].get("temperature")
        icons = []

        if delayed > 0:
            icons.append(f"⏰ {delayed}")

        if temperature is not None:

            if temperature < 0 or temperature > 5:
                icons.append(f"❄️ {temperature}°C")

        if len(icons) == 0:
            status = "🟢"

        elif len(icons) == 1:
            status = icons[0]

        else:
            status = "🚨 " + " | ".join(icons)

        courier_status[courier_id] = status

    if user["role"] != "user":

        selected_courier = st.selectbox(
            "🚚 Futár",

            filtered,

            key="profile_selected_courier",

            format_func=lambda x:
                f"{x.get('courierName')} "
                f"({x.get('courierId')})  "
                f"{courier_status.get(x.get('courierId'), '🟢')}"

        )
    
    selected_courier_id = selected_courier.get("courierId")
    # ----------------------------------
    # Departure Dashboard
    # ----------------------------------

    departure_data = load_departure_dashboard()

    departure_route = next(

        (

            route

            for route in departure_data.get(
                "routes",
                []
            )

            if str(route.get("courier_id"))
            ==
            str(selected_courier_id)

        ),

        None
    )

    if departure_route:

        st.divider()

        st.subheader(
            "🚚 Jármű és indulási adatok"
        )

        temperature = departure_route.get(
            "temperature",
            {}
        )

        c1, c2, c3 = st.columns(
            3
        )

        c1.metric(
            "Rendszám",
            departure_route.get(
                "licence_plate",
                "-"
            )
        )

        c2.metric(
            "Hőmérséklet",
            f"{temperature.get('temperature', '-')} °C"
        )

        c3.metric(
            "Rendelések",
            departure_route.get(
                "orders_in_route",
                0
            )
        )

        if departure_route.get(
            "platform_section_mark"
        ):

            with st.expander(
                "📦 Rakodási információk",
                expanded=True
            ):

                st.write(
                    f"**Platform:** "
                    f"{departure_route.get('platform_section_mark')}"
                )

                st.write(
                    f"**Rakodásig:** "
                    f"{departure_route.get('minutes_to_loading')} perc"
                )

                st.write(
                    f"**Indulásig:** "
                    f"{departure_route.get('minutes_to_departure')} perc"
                )

                st.write(
                    f"**Riasztás:** "
                    f"{departure_route.get('alert_level')}"
                )

                st.subheader(
                    "📦 Száraz áru"
                )

                for item in departure_route.get(
                    "dry_carriage_and_parking",
                    []
                ):

                    st.write(
                        f"{item.get('trolley_ean')} → "
                        f"{item.get('parking_spot_ean')}"
                    )

                st.subheader(
                    "❄️ Hűtött áru"
                )

                for item in departure_route.get(
                    "cooled_carriage_and_parking",
                    []
                ):

                    st.write(
                        f"{item.get('trolley_ean')} → "
                        f"{item.get('parking_spot_ean')}"
                    )

    else:

        st.info(
            "Ehhez a futárhoz most nincs departure-dashboard adat."
        )

    driver_data = load_driver_details(
        selected_courier_id
        )

    try:
        orders_df, customers_df = load_order_data()
        courier_orders_df, courier_customers_df = filter_courier_data(
            orders_df,
            customers_df,
            selected_courier_id,
        )
    except Exception as exc:
        courier_orders_df = pd.DataFrame()
        courier_customers_df = pd.DataFrame()
        st.warning(
            f"DSP order statisztika nem tölthető be: {exc}"
        )

    drivers_data = load_drivers()
    current_driver = next(
        (
            driver
            for driver in drivers_data.get(
                "drivers",
                []
            )
            if str(
                driver.get(
                    "driver_id"
                )
            )
            ==
            str(
                selected_courier_id
            )
        ),
        {}
    )

    routes = driver_data.get(
        "routes",
        []
    )

    courier_summary = build_courier_summary(
        courier_orders_df,
        courier_customers_df,
    )

    if courier_summary["routes"]:

        st.divider()

        st.subheader(
            "DSP order statisztika"
        )

        d1, d2, d3, d4 = st.columns(4)

        d1.metric(
            "Körök",
            courier_summary["routes"]
        )

        d2.metric(
            "Címek",
            courier_summary["customer_addresses"]
        )

        d3.metric(
            "Kiszállított rendelések",
            courier_summary["delivered_orders"]
        )

        d4.metric(
            "Átlag rendelés/kör",
            f"{courier_summary['avg_delivered_per_route']:.1f}"
        )

    st.write(
        f"Aktív route-ok: {len(routes)}"
    )

    for route in routes:

        delayed = route.get(
            "numDelayedOrdersEstimate",
            0
        )

        if delayed <= 0:

            status = "🟢"

        elif delayed <= 5:

            status = "🟡"

        else:

            status = "🔴"

        with st.expander(
            f"{status} Route {route.get('id')}"
        ):
            route_id = route.get(
                "id"
            )
            dsp_route = get_route_order_row(
                courier_orders_df,
                route_id,
            )
            route_customers = get_route_customers(
                courier_customers_df,
                route_id,
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Összes rendelés",
                route.get(
                    "numTotalOrders",
                    0
                )
            )

            c2.metric(
                "Kiszállított",
                route.get(
                    "numDeliveredOrders",
                    0
                )
            )

            c3.metric(
                "Késő",
                delayed
            )

            c4.metric(
                "Route ID",
                route.get(
                    "id",
                    ""
                )
            )

            st.markdown(
                f"""
**Állapot:** {status}

**Sorba állt:** {route.get('courierRegisteredAt', '-')}

**Kiosztva:** {route.get('assignedAt', '-')}

**Rakodás:** {route.get('loadingTime', '-')}

**Tervezett indulás:** {route.get('plannedDeparture', '-')}

**Valós indulás:** {route.get('realDeparture', '-')}

**Tervezett vissza:** {route.get('plannedReturn', '-')}

**Valós vissza:** {route.get('realReturn', '-')}
"""
            )

            st.divider()

            if dsp_route or not route_customers.empty:

                st.subheader(
                    "DSP kör statisztika"
                )

                delivered_orders = dsp_route.get(
                    "numDeliveredOrders",
                    0
                )
                total_orders = dsp_route.get(
                    "numTotalOrders",
                    0
                )
                customer_count = (
                    route_customers["id"].nunique()
                    if not route_customers.empty
                    and "id" in route_customers.columns
                    else 0
                )
                remaining_orders = max(
                    total_orders - delivered_orders,
                    0
                )

                k1, k2, k3, k4 = st.columns(4)

                k1.metric(
                    "Route ID",
                    route_id
                )

                k2.metric(
                    "Címek",
                    customer_count
                )

                k3.metric(
                    "Kiszállított",
                    int(delivered_orders)
                )

                k4.metric(
                    "Összes rendelés",
                    int(total_orders)
                )

                chart_df = pd.DataFrame([
                    {
                        "Típus": "Kiszállított",
                        "Darab": delivered_orders,
                    },
                    {
                        "Típus": "Hátralévő",
                        "Darab": remaining_orders,
                    },
                ])

                if chart_df["Darab"].sum() > 0:
                    chart = (
                        alt.Chart(chart_df)
                        .mark_arc(innerRadius=45)
                        .encode(
                            theta="Darab:Q",
                            color="Típus:N",
                            tooltip=["Típus:N", "Darab:Q"],
                        )
                    )

                    st.altair_chart(
                        chart,
                        use_container_width=True,
                    )

                timing_rows = []

                timing_labels = {
                    "waitForRouteMinutes": "Várakozás túrára",
                    "waitForLoadingMinutes": "Várakozás rakodásra",
                    "totalWaitMinutes": "Összes várakozás",
                    "routeCreationMinutes": "Túrakészítés",
                    "loadingAfterCreationMinutes": "Túra után rakodás",
                    "assignmentToLoadingMinutes": "Kiosztás-rakodás",
                    "departureDelayMinutes": "Indulási késés",
                    "plannedTourMinutes": "Tervezett túraidő",
                    "realTourMinutes": "Valós túraidő",
                    "returnDelayMinutes": "Visszaérkezési eltérés",
                }

                for key, label in timing_labels.items():
                    value = dsp_route.get(
                        key,
                        ""
                    )

                    if value != "":
                        timing_rows.append({
                            "Mutató": label,
                            "Perc": value,
                        })

                if timing_rows:
                    st.dataframe(
                        pd.DataFrame(timing_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                comment = dsp_route.get(
                    "comment",
                    ""
                )

                if comment:
                    st.info(
                        comment
                    )

                st.divider()

            statistics = route.get(
                "statistics",
                {}
            )

            if not statistics:
                statistics = (
                    current_driver.get(
                        "route",
                        {}
                    )
                    .get(
                        "statistics",
                        {}
                    )
                )

            if statistics:

                st.subheader(
                    "Route statisztika"
                )

                s1, s2, s3, s4 = st.columns(4)

                s1.metric(
                    "Össz. km",
                    statistics.get(
                        "total_distance_km",
                        "-"
                    )
                )

                s2.metric(
                    "Megtett km",
                    statistics.get(
                        "distance_covered_km",
                        "-"
                    )
                )

                s3.metric(
                    "Kiszállított csomag",
                    statistics.get(
                        "parcels_delivered",
                        "-"
                    )
                )

                s4.metric(
                    "Összes csomag",
                    statistics.get(
                        "parcels_total",
                        "-"
                    )
                )

                st.divider()

            checkpoint_rows = []

            for cp in route.get(
                "checkpoints",
                []
            ):

                checkpoint_rows.append({

                    "Poz":
                    cp.get(
                        "position"
                    ),

                    "Cím":
                    cp.get(
                        "address"
                    ),

                    "Időablak":
                    (
                        f"{cp.get('deliverSince', '')}"
                        " - "
                        f"{cp.get('deliverTill', '')}"
                    ),

                    "Tervezett":
                    cp.get(
                        "plannedArrivalTime"
                    ),

                    "Becsült":
                    cp.get(
                        "estimatedArrivalTime"
                    ),

                    "Valós":
                    cp.get(
                        "realArrivalTime"
                    )

                })

            if checkpoint_rows:

                st.dataframe(

                    pd.DataFrame(
                        checkpoint_rows
                    ),

                    use_container_width=True,
                    height=500

                )
