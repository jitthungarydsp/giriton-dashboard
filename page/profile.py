import streamlit as st
import pandas as pd
from dsp_common_kw  import  hu_time

from resources.api import (
    load_attendance,
    load_driver_details,
    load_departure_dashboard
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

    if user["role"] == "user":

        selected_courier = visible_couriers[0] if visible_couriers else None

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
        
        departure_data = load_departure_dashboard()

    departure_routes = departure_data.get("routes", [])

    courier_status = {}

    for route in departure_routes:

        courier_id = route.get("courier_id")

        delayed = route.get(
            "numDelayedOrdersEstimate",
            0
        )

        temperature = (
            route.get(
                "temperature",
                {}
            ).get(
                "temperature"
            )
        )

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
        selected_courier = st.selectbox(

            "🚚 Futár",

            filtered,

            format_func=lambda x:
                f"{x.get('courierName')} "
                f"({x.get('courierId')})  "
                f"{courier_status.get(x.get('courierId'), '🟢')}"

        )
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

    routes = driver_data.get(
        "routes",
        []
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
