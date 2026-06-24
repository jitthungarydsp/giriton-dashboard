import streamlit as st
import pandas as pd

from resources.api import (
    load_attendance,
    load_driver_details
)


def show_profile_page():

    st.title(
        "👤 Saját profil"
    )

    user = st.session_state["user"]

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
    # Admin
    # -------------------------

    if user["role"] == "admin":

        st.divider()

        st.subheader(
            "Aktív futárok"
        )

        active_couriers = []

        for courier in couriers:

            active_couriers.append({

                "id":
                courier.get(
                    "courierId"
                ),

                "name":
                courier.get(
                    "courierName"
                )

            })

        if not active_couriers:

            st.warning(
                "Nincs futár."
            )

            return

        selected = st.selectbox(

            "🚚 Futár",

            options=active_couriers,

            format_func=lambda x:
            f"{x['name']} ({x['id']})"

        )
        driver_data = load_driver_details(
            selected["id"]
        )

        routes = driver_data.get(
            "routes",
            []
        )

        st.write(
            f"Aktív route-ok: {len(routes)}"
        )

        for route in routes:

            with st.expander(
                f"🚚 Route {route.get('id')}"
            ):

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "Összes",
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
                    route.get(
                        "numDelayedOrdersEstimate",
                        0
                    )
                )

                c4.metric(
                    "Route ID",
                    route.get(
                        "id",
                        ""
                    )
                )

        return
    # -------------------------
    # User
    # -------------------------

    my_courier = next(

        (
            c

            for c in couriers

            if c.get(
                "courierId"
            )
            ==
            user.get(
                "courierId"
            )
        ),

        None
    )

    if not my_courier:

        st.warning(
            "Nincs aktív műszak vagy futár adat."
        )

        return

    st.divider()

    st.subheader(
        "Mai adatok"
    )

    st.write(
        f"**Név:** {my_courier.get('courierName')}"
    )

    st.write(
        f"**Courier ID:** {my_courier.get('courierId')}"
    )

    st.write(
        f"**Depó:** {my_courier.get('warehouseName')}"
    )
#############################
    driver_data = load_driver_details(
        user["courierId"]
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