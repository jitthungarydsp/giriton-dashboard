import streamlit as st
import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
from datetime import datetime

from streamlit_autorefresh import st_autorefresh


USERS = {
    "balazs": {
        "password": "1234",
        "driver_name": "Varecza Roland"
    },

    "fonok": {
        "password": "JIT2026",
        "driver_name": None
    }
}

# ---------------------------------
# LOGIN
# ---------------------------------

if "logged_in" not in st.session_state:

    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 DSP Bejelentkezés")

    username = st.text_input(
        "Felhasználónév"
    )

    password = st.text_input(
        "Jelszó",
        type="password"
    )

    if st.button("Belépés"):

        if (
            username in USERS
            and USERS[username]["password"] == password
        ):

            st.session_state.logged_in = True

            st.session_state.user = username

            st.session_state.driver_name = (
                USERS[username]["driver_name"]
            )

            st.rerun()

        else:

            st.error(
                "Hibás felhasználónév vagy jelszó"
            )

    st.stop()

@st.cache_data(ttl=30)
@st.cache_data(ttl=30)
def load_driver_details(driver_id):

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    url = (
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-drivers-detail/{driver_id}/{today}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    )

    response = requests.get(
        url,
        timeout=30
    )

    return response.json()
@st.cache_data(ttl=30)
def load_loading_data():

    url = (
        "https://uftplslamjbbhlozsygo.supabase.co/functions/v1/departure-dashboard"
    )

    payload = {
        "id": "JIT",
        "organizationId":
        "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    return response.json()
# ---------------------------------
# BELÉPVE
# ---------------------------------

st.sidebar.success(
    f"Belépve: {st.session_state.user}"
)
    
import requests
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------------
# Google Sheet kapcsolat
# ---------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)

# ---------------------------------
# Belépés
# ---------------------------------

USERS = {
    "balazs": "1234",
    "fonok": "JIT2026"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 DSP Bejelentkezés")

    username = st.text_input(
        "Felhasználónév"
    )

    password = st.text_input(
        "Jelszó",
        type="password"
    )

    if st.button("Belépés"):

        if (
            username in USERS
            and USERS[username] == password
        ):

            st.session_state.logged_in = True
            st.session_state.user = username

            st.rerun()

        else:

            st.error(
                "Hibás felhasználónév vagy jelszó"
            )

    st.stop()

# ---------------------------------
# Segéd
# ---------------------------------

@st.cache_data(ttl=60)
def load_sheet(sheet_name):

    ws = spreadsheet.worksheet(sheet_name)

    data = ws.get_all_records()

    return pd.DataFrame(data)
@st.cache_data(ttl=30)
def load_live_drivers():

    url = (
        "https://uftplslamjbbhlozsygo.supabase.co/"
        "functions/v1/fetch-drivers"
        "?id=JIT"
        "&organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
        "&departureDelayThreshold=10"
    )

    response = requests.get(
        url,
        timeout=30
    )

    return response.json()

# ---------------------------------
# Oldal beállítás
# ---------------------------------

st.set_page_config(
    page_title="DSP Dashboard",
    layout="wide"
)

st.sidebar.success(
    f"Belépve: {st.session_state.user}"
)

if st.sidebar.button(
    "Kijelentkezés",
    key="logout_button"
):

    st.session_state.logged_in = False

    st.rerun()

page = st.sidebar.radio(
    "Menü",
    [
        "🔍 Kereső",
        "🚚 Futár Dashboard",
        "🗺️ Aktuális útvonal",
        "📊 Admin Dashboard",
        "🗺️ Élő futártérkép",
        "🔄 Sheet újratöltése",
        "📦 Rakodási infók"
    ]
)

# ---------------------------------
# KERESŐ
# ---------------------------------

if page == "🔍 Kereső":

    st.title("🚚 DSP Kereső")

    sheet_name = st.selectbox(
        "Tábla",
        [
            "DSP_Drivers",
            "DSP_Driver_Summary",
            "DSP_Orders",
            "DSP_Order_Customers"
        ]
    )

    search_text = st.text_input(
        "Keresés (ID vagy név)"
    )

    df = load_sheet(sheet_name)

    if search_text:

        mask = df.astype(str).apply(
            lambda col: col.str.contains(
                search_text,
                case=False,
                na=False
            )
        ).any(axis=1)

        result = df[mask]

        st.success(
            f"{len(result)} találat"
        )

        st.dataframe(
            result,
            use_container_width=True
        )

    else:

        st.dataframe(
            df.head(100),
            use_container_width=True
        )
# ---------------------------------
# ÉLŐ FUTÁRTÉRKÉP
# ---------------------------------

elif page == "🗺️ Élő futártérkép":

    st.title("🗺️ Élő Futártérkép")

    st.caption(
        f"🔄 Utolsó frissítés: {datetime.now().strftime('%H:%M:%S')}"
    )

    st.markdown("""
    🟢 Időben

    🟡 1-10 perc késés

    🔴 10+ perc késés
    """)

    try:

        url = (
            "https://uftplslamjbbhlozsygo.supabase.co/"
            "functions/v1/fetch-drivers"
            "?id=JIT"
            "&organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
            "&departureDelayThreshold=50"
        )

        data = load_live_drivers()

        rows = []

        for driver in data["drivers"]:

            try:

                rows.append({

                    "name":
                    driver["personal_info"]["name"],

                    "lat":
                    driver["route"]["current_position"]["latitude"],

                    "lon":
                    driver["route"]["current_position"]["longitude"],

                    "state":
                    driver["status"]["current_state"],

                    "delay":
                    driver["status"]["delay_minutes"],

                    "license_plate":
                    driver.get("vehicle", {}).get(
                        "license_plate",
                        ""
                    ),

                    "temperature":
                    driver.get("vehicle", {}).get(
                        "temperature",
                        None
                    )

                })

            except:
                pass

        if len(rows) == 0:

            st.warning(
                "Nincs aktív futár."
            )

            st.stop()

        df = pd.DataFrame(rows)

        # -------------------------
        # Színezés
        # -------------------------

        def get_color(delay):

            try:

                delay = float(delay)

                if delay <= 0:

                    return [0, 200, 0]

                elif delay <= 10:

                    return [255, 165, 0]

                else:

                    return [255, 0, 0]

            except:

                return [0, 0, 255]

        df["color"] = df["delay"].apply(
            get_color
        )

        st.success(
            f"{len(df)} aktív futár"
        )

        # -------------------------
        # Futár pontok
        # -------------------------

        point_layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius=300,
            pickable=True
        )

        # -------------------------
        # Futár nevek
        # -------------------------


        # -------------------------
        # Kamera
        # -------------------------

        view_state = pdk.ViewState(
            latitude=df["lat"].mean(),
            longitude=df["lon"].mean(),
            zoom=10,
            pitch=0
        )

        tooltip = {
            "html": """
            <b>{name}</b><br/>
            Állapot: {state}<br/>
            Késés: {delay} perc
            """,
            "style": {
                "backgroundColor": "steelblue",
                "color": "white"
            }
        }

        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=view_state,
                layers=[
                    point_layer
                ],
                tooltip=tooltip
            )
        )

        st.subheader(
            "🚚 Aktív futárok"
        )

        st.dataframe(
            df[
                [
                    "name",
                    "license_plate",
                    "temperature",
                    "state",
                    "delay"
                ]
            ],
            use_container_width=True
        )

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )
# ---------------------------------
# FUTÁR DASHBOARD
# ---------------------------------

elif page == "🚚 Futár Dashboard":

    st.title("🚚 Futár Dashboard")

    df = load_sheet(
        "DSP_Driver_Summary"
    )

    driver_name = st.text_input(
        "Futár neve",
        value="Gurzó Balázs"
    )

    result = df[
        df["name"].astype(str).str.contains(
            driver_name,
            case=False,
            na=False
        )
    ]

    if result.empty:

        st.warning(
            "Nincs találat."
        )

    else:

        row = result.iloc[0]

        total_orders = (
            row["monday_delivered"] +
            row["tuesday_delivered"] +
            row["wednesday_delivered"] +
            row["thursday_delivered"] +
            row["friday_delivered"] +
            row["saturday_delivered"] +
            row["sunday_delivered"]
        )

        total_routes = (
            row["monday_routes"] +
            row["tuesday_routes"] +
            row["wednesday_routes"] +
            row["thursday_routes"] +
            row["friday_routes"] +
            row["saturday_routes"] +
            row["sunday_routes"]
        )

        income = (
            row["monday_routes"] * 13000 +
            row["tuesday_routes"] * 11000 +
            row["wednesday_routes"] * 11000 +
            row["thursday_routes"] * 13000 +
            row["friday_routes"] * 13000 +
            row["saturday_routes"] * 13000 +
            row["sunday_routes"] * 11000
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "📦 Heti rendelések",
            int(total_orders)
        )

        col2.metric(
            "🚚 Heti körök",
            int(total_routes)
        )

        col3.metric(
            "💰 Heti bevétel",
            f"{income:,.0f} Ft"
        )

        st.divider()

        chart_df = pd.DataFrame({

            "Nap": [
                "Hétfő",
                "Kedd",
                "Szerda",
                "Csütörtök",
                "Péntek",
                "Szombat",
                "Vasárnap"
            ],

            "Rendelések": [
                row["monday_delivered"],
                row["tuesday_delivered"],
                row["wednesday_delivered"],
                row["thursday_delivered"],
                row["friday_delivered"],
                row["saturday_delivered"],
                row["sunday_delivered"]
            ]

        })

        st.subheader(
            "📦 Rendelések naponta"
        )

        st.bar_chart(
            chart_df.set_index(
                "Nap"
            )
        )

        routes_df = pd.DataFrame({

            "Nap": [
                "Hétfő",
                "Kedd",
                "Szerda",
                "Csütörtök",
                "Péntek",
                "Szombat",
                "Vasárnap"
            ],

            "Körök": [
                row["monday_routes"],
                row["tuesday_routes"],
                row["wednesday_routes"],
                row["thursday_routes"],
                row["friday_routes"],
                row["saturday_routes"],
                row["sunday_routes"]
            ]

        })

        st.subheader(
            "🚚 Körök naponta"
        )

        st.bar_chart(
            routes_df.set_index(
                "Nap"
            )
        )

        st.subheader(
            "📋 Heti összesítés"
        )

        st.dataframe(
            result,
            use_container_width=True
        )
# ---------------------------------
# AKTUÁLIS ÚTVONAL
# ---------------------------------

elif page == "🚚 Aktuális útvonal":

    from streamlit_autorefresh import st_autorefresh
    from datetime import datetime

    st_autorefresh(
        interval=30000,
        key="live_route_refresh"
    )

    st.title("🚚 Aktuális útvonal")

    try:

        data = load_live_drivers()

        active_drivers = []

        for driver in data.get(
            "drivers",
            []
        ):

            try:

                if (
                    driver.get(
                        "status",
                        {}
                    ).get(
                        "current_state"
                    )
                    == "Delivering"
                ):

                    active_drivers.append(
                        driver[
                            "personal_info"
                        ][
                            "name"
                        ]
                    )

            except:
                pass

        if not active_drivers:

            st.warning(
                "Nincs aktív futár."
            )

            st.stop()

        selected_driver = st.selectbox(
            "🚚 Aktív futár",
            sorted(
                active_drivers
            )
        )

        selected = None

        for driver in data.get(
            "drivers",
            []
        ):

            try:

                if (
                    driver[
                        "personal_info"
                    ][
                        "name"
                    ]
                    == selected_driver
                ):

                    selected = driver
                    break

            except:
                pass

        if not selected:

            st.stop()

        # -------------------------
        # KPI KÁRTYÁK
        # -------------------------

        col1, col2, col3, col4 = st.columns(4)

        with col1:

            st.metric(
                "🚚 Futár",
                selected[
                    "personal_info"
                ][
                    "name"
                ]
            )

        with col2:

            st.metric(
                "🌡️ Hőmérséklet",
                str(
                    selected[
                        "vehicle"
                    ].get(
                        "temperature",
                        "-"
                    )
                )
                + " °C"
            )

        with col3:

            st.metric(
                "📍 Állapot",
                selected[
                    "status"
                ].get(
                    "current_state",
                    "-"
                )
            )

        with col4:

            st.metric(
                "⏱️ Késés",
                str(
                    selected[
                        "status"
                    ].get(
                        "delay_minutes",
                        0
                    )
                )
                + " perc"
            )

        # -------------------------
        # KM STATISZTIKA
        # -------------------------

        stats = (
            selected
            .get(
                "route",
                {}
            )
            .get(
                "statistics",
                {}
            )
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "🚚 Megtett km",
                round(
                    stats.get(
                        "distance_covered_km",
                        0
                    ),
                    1
                )
            )

        with col2:

            st.metric(
                "🗺️ Teljes km",
                round(
                    stats.get(
                        "total_distance_km",
                        0
                    ),
                    1
                )
            )

        with col3:

            st.metric(
                "📍 Hátralévő km",
                round(
                    stats.get(
                        "total_distance_km",
                        0
                    )
                    -
                    stats.get(
                        "distance_covered_km",
                        0
                    ),
                    1
                )
            )

        st.divider()

        st.subheader(
            "📦 Következő stop"
        )

        st.info(
            selected[
                "status"
            ].get(
                "next_stop",
                "Nincs aktív stop"
            )
        )

        # -------------------------
        # ROUTE RÉSZLETEK
        # -------------------------

        driver_id = selected.get(
            "driver_id"
        )

        today = datetime.now().strftime(
            "%Y-%m-%d"
        )

        detail = load_driver_details(
            driver_id,
            today
        )

        routes = detail.get(
            "routes",
            []
        )

        if routes:

            current_route = routes[-1]

            st.divider()

            st.subheader(
                f"🗺️ Route #{current_route.get('id')}"
            )

            st.success(
                f"""
📦 Rendelések:
{current_route.get('numDeliveredOrders',0)}
/
{current_route.get('numTotalOrders',0)}

⚠️ Becsült késések:
{current_route.get('numDelayedOrdersEstimate',0)}
"""
            )

            checkpoints = current_route.get(
                "checkpoints",
                []
            )

            checkpoints = sorted(
                checkpoints,
                key=lambda x:
                x.get(
                    "position",
                    0
                )
            )

            for stop in checkpoints:

                if stop.get(
                    "realArrivalTime"
                ):

                    icon = "✅"

                elif stop.get(
                    "estimatedArrivalTime"
                ):

                    icon = "🟡"

                else:

                    icon = "⚪"

                st.markdown(
                    f"""
### {icon} {stop.get('position')}. stop

🏠 {stop.get('address','')}

📦 Order:
{stop.get('orderId','')}

⏰ Tervezett:
{stop.get('plannedArrivalTime','')}

🚚 Becsült:
{stop.get('estimatedArrivalTime','')}

✅ Tényleges:
{stop.get('realArrivalTime','')}
"""
                )

                st.divider()

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )

 # ---------------------------------
# RAKODÁSI INFÓK
# ---------------------------------

elif page == "📦 Rakodási infók":

    st_autorefresh(
        interval=30000,
        key="loading_dashboard_refresh"
    )

    st.title("📦 Rakodási infók")

    try:

        data = load_loading_data()

        routes = data.get(
            "routes",
            []
            )

        # -------------------------
        # RAKODÓ FUTÁROK
        # -------------------------

        st.subheader(
            "🚚 Rakodó futárok"
        )

        loading_rows = []

        for r in routes:

            # ---------------------------------
            # Csak ténylegesen rakodó futárok
            # ---------------------------------

            if not r.get(
                "platform_section_mark"
            ):
                continue

            if (
                len(
                    r.get(
                        "dry_carriage_and_parking",
                        []
                    )
                ) == 0
                and
                len(
                    r.get(
                        "cooled_carriage_and_parking",
                        []
                    )
                ) == 0
            ):
                continue

            if r.get(
                "minutes_to_departure",
                0
            ) <= 0:
                continue

            dry = "\n".join([

                f"{x['trolley_ean']} → {x['parking_spot_ean']}"

                for x in r.get(
                    "dry_carriage_and_parking",
                    []
                )

            ])

            cooled = "\n".join([

                f"{x['trolley_ean']} → {x['parking_spot_ean']}"

                for x in r.get(
                    "cooled_carriage_and_parking",
                    []
                )

            ])

            loading_rows.append({

                "Platform":
                r.get(
                    "platform_section_mark",
                    "-"
                ),

                "🌡️":
                str(
                    r.get(
                        "temperature",
                        {}
                    ).get(
                        "temperature",
                        "-"
                    )
                ) + "°C",

                "Route ID":
                r.get(
                    "route_id",
                    ""
                ),

                "Futár":
                r.get(
                    "courier_name",
                    ""
                ),

                "📦":
                r.get(
                    "orders_in_route",
                    0
                ),

                "Nem szkennelt zsák":
                r.get(
                    "not_scanned_bag_eans",
                    0
                ),

                "Nem szkennelt rendelés":
                r.get(
                    "not_scanned_orders",
                    0
                ),

                "Száraz kocsik":
                dry,

                "Hűtött kocsik":
                cooled,

                "Indulásig":
                f"{r.get('minutes_to_departure', 0)} min",

                "Rakodásig":
                f"{r.get('minutes_to_loading', 0)} min",

                "Alert":
                r.get(
                    "alert_level",
                    ""
                )

            })
        if loading_rows:

            df = pd.DataFrame(
                loading_rows
            )

            st.dataframe(
                df,
                use_container_width=True,
                height=450
            )

        else:

            st.info(
                "Nincs rakodó futár."
            )

        # -------------------------
        # WAITING - NOT YET ASSIGNED
        # -------------------------

        st.divider()

        st.subheader(
            "⏳ Waiting – not yet assigned"
        )

        waiting_rows = []

        for courier in data.get(
            "couriers_without_route",
            []
        ):

            waiting_rows.append({

                "Futár":
                courier.get(
                    "courier_name",
                    ""
                ),

                "🌡️ Hőmérséklet":
                courier.get(
                    "temperature",
                    {}
                ).get(
                    "temperature",
                    "-"
                )

            })

        if waiting_rows:

            st.dataframe(
                pd.DataFrame(
                    waiting_rows
                ),
                use_container_width=True,
                height=300
            )

        else:

            st.success(
                "Nincs várakozó futár."
            )

        st.caption(
            "🔄 Automatikus frissítés: 30 mp"
        )

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )