import streamlit as st
import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
from datetime import datetime

from datetime import datetime


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

# ---------------------------------
# AKTUÁLIS ÚTVONAL
# ---------------------------------

elif page == "🚚 Aktuális útvonal":

    st.title("🚚 Aktuális útvonal")

    try:

        data = load_live_drivers()

        driver_names = []

        for driver in data["drivers"]:

            try:

                driver_names.append(
                    driver["personal_info"]["name"]
                )

            except:
                pass

        selected_driver = st.selectbox(
            "🔍 Futár keresése",
            sorted(driver_names)
        )

        selected = None

        for driver in data["drivers"]:

            try:

                if (
                    driver["personal_info"]["name"]
                    == selected_driver
                ):

                    selected = driver
                    break

            except:
                pass

        if selected:

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "🚚 Futár",
                    selected["personal_info"]["name"]
                )

                st.metric(
                    "🚗 Rendszám",
                    selected["vehicle"].get(
                        "license_plate",
                        "-"
                    )
                )

                st.metric(
                    "🌡️ Hőmérséklet",
                    str(
                        selected["vehicle"].get(
                            "temperature",
                            "-"
                        )
                    )
                    + " °C"
                )

            with col2:

                st.metric(
                    "📍 Állapot",
                    selected["status"].get(
                        "current_state",
                        "-"
                    )
                )

                st.metric(
                    "⏱️ Késés",
                    str(
                        selected["status"].get(
                            "delay_minutes",
                            0
                        )
                    )
                    + " perc"
                )

                st.metric(
                    "🏢 Depó",
                    selected["personal_info"].get(
                        "warehouse_name",
                        "-"
                    )
                )

            st.subheader(
                "📦 Következő stop"
            )

            st.write(
                selected["status"].get(
                    "next_stop",
                    "Nincs aktív stop"
                )
            )

            st.subheader(
                "🔎 Teljes JSON"
            )

            st.json(selected)

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )

    st.title("🗺️ Aktuális útvonal")

    driver_name = st.session_state.get(
        "driver_name"
    )

    if not driver_name:

        st.error(
            "Nincs futár hozzárendelve."
        )

        st.stop()

    drivers_df = load_sheet(
        "DSP_Drivers"
    )

    orders_df = load_sheet(
        "DSP_Orders"
    )

    customers_df = load_sheet(
        "DSP_Order_Customers"
    )

    driver_row = drivers_df[
        drivers_df["name"]
        .astype(str)
        .str.contains(
            driver_name,
            case=False,
            na=False
        )
    ]

    if driver_row.empty:

        st.error(
            "Futár nem található."
        )

        st.stop()

    driver_id = str(
        driver_row.iloc[0]["driver_id"]
    )

    driver_orders = orders_df[
        orders_df["courierId"]
        .astype(str)
        == driver_id
    ]

    if driver_orders.empty:

        st.warning(
            "Nincs útvonal."
        )

        st.stop()

    route_id = str(
        driver_orders.iloc[-1]["routeId"]
    )

    st.success(
        f"""
🚚 Futár: {driver_name}

🆔 Driver ID: {driver_id}

🗺️ Route ID: {route_id}
"""
    )

    route_df = customers_df[
        customers_df["routeId"]
        .astype(str)
        == route_id
    ]

    if route_df.empty:

        st.warning(
            "Ehhez a route-hoz nincs állomás."
        )

        st.stop()

    route_df = route_df.sort_values(
        "position"
    )

    order_row = driver_orders[
        driver_orders["routeId"]
        .astype(str)
        == route_id
    ]

    planned_return = ""
    real_return = ""

    if not order_row.empty:

        planned_return = order_row.iloc[0].get(
            "plannedReturn",
            ""
        )

        real_return = order_row.iloc[0].get(
            "realReturn",
            ""
        )

    st.success(
        "🏢 DEPÓ"
    )

    for _, stop in route_df.iterrows():

        position = stop.get(
            "position",
            ""
        )

        order_id = stop.get(
            "orderId",
            ""
        )

        address = stop.get(
            "address",
            ""
        )

        deliver_since = stop.get(
            "deliverSince",
            ""
        )

        deliver_till = stop.get(
            "deliverTill",
            ""
        )

        planned_arrival = stop.get(
            "plannedArrivalTime",
            ""
        )

        estimated_arrival = stop.get(
            "estimatedArrivalTime",
            ""
        )

        real_arrival = stop.get(
            "realArrivalTime",
            ""
        )

        real_departure = stop.get(
            "realDepartureTime",
            ""
        )

        arrival_status = stop.get(
            "arrival_status",
            ""
        )

        status_icon = "⚪"

        if str(real_arrival).strip():

            status_icon = "✅"

        st.markdown(
            f"""
### {status_icon} {position}. állomás

📦 Order: {order_id}

🏠 {address}

🕐 Időablak:
{deliver_since} → {deliver_till}

⏰ Tervezett érkezés:
{planned_arrival}

🚚 Várható érkezés:
{estimated_arrival}

✅ Tényleges érkezés:
{real_arrival}

🚪 Tényleges indulás:
{real_departure}

📊 Érkezés minősítése:
{arrival_status}
"""
        )

        st.divider()

    st.success(
        f"""
🏢 VISSZA A DEPÓBA

⏰ Tervezett visszaérkezés:
{planned_return}

🚚 Tényleges visszaérkezés:
{real_return}
"""
    )
             
# ---------------------------------
# ADMIN Futtaás mai nap
# ---------------------------------

if st.button("🔄 Sheet újratöltése"):
    st.cache_data.clear()
    st.rerun()
# ---------------------------------
# RAKODÁSI INFÓK
# ---------------------------------

elif page == "📦 Rakodási infók":

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

                "Futár":
                r.get(
                    "courier_name",
                    ""
                ),
                "Route ID":
                r.get(
                    "route_id",
                    ""
                ),

                "🌡️":
                r.get(
                    "temperature",
                    {}
                ).get(
                    "temperature",
                    "-"
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

                "Platform":
                r.get(
                    "platform_section_mark",
                    "-"
                ),

                "Száraz kocsik":
                dry,

                "Hűtött kocsik":
                cooled,

                "Indulásig":
                f"{r.get('minutes_to_departure',0)} perc",

                "Rakodásig":
                f"{r.get('minutes_to_loading',0)} perc",

                "Alert":
                r.get(
                    "alert_level",
                    ""
                )

            })
        loading_rows.sort(
            key=lambda x: int(x["Platform"])
            if str(x["Platform"]).isdigit()
            else 999
        )
        if loading_rows:

            st.dataframe(
                pd.DataFrame(
                    loading_rows
                ),
                use_container_width=True,
                height=450
            )

        else:

            st.info(
                "Nincs rakodó futár."
            )

        # -------------------------
        # VÁRAKOZÓ FUTÁROK
        # -------------------------

        st.divider()

        st.subheader(
            "⏳ Várakozó futárok"
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

                "Hőmérséklet":
                courier.get(
                    "temperature",
                    {}
                ).get(
                    "temperature",
                    "-"
                ),

                "Tiltva":
                courier.get(
                    "temperature_block",
                    "-"
                )

            })

        if waiting_rows:

            st.dataframe(
                pd.DataFrame(
                    waiting_rows
                ),
                use_container_width=True
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
    # ---------------------------------
# RAKODÁSI INFÓK
# ---------------------------------

elif page == "📦 Rakodási infók":

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

                "Futár":
                r.get(
                    "courier_name",
                    ""
                ),

                "🌡️":
                r.get(
                    "temperature",
                    {}
                ).get(
                    "temperature",
                    "-"
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

                "Platform":
                r.get(
                    "platform_section_mark",
                    "-"
                ),

                "Száraz kocsik":
                dry,

                "Hűtött kocsik":
                cooled,

                "Indulásig":
                f"{r.get('minutes_to_departure',0)} perc",

                "Rakodásig":
                f"{r.get('minutes_to_loading',0)} perc",

                "Alert":
                r.get(
                    "alert_level",
                    ""
                )

            })

        if loading_rows:

            st.dataframe(
                pd.DataFrame(
                    loading_rows
                ),
                use_container_width=True,
                height=450
            )

        else:

            st.info(
                "Nincs rakodó futár."
            )

        # -------------------------
        # VÁRAKOZÓ FUTÁROK
        # -------------------------

        st.divider()

        st.subheader(
            "⏳ Várakozó futárok"
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

                "Hőmérséklet":
                courier.get(
                    "temperature",
                    {}
                ).get(
                    "temperature",
                    "-"
                ),

                "Tiltva":
                courier.get(
                    "temperature_block",
                    "-"
                )

            })

        if waiting_rows:

            st.dataframe(
                pd.DataFrame(
                    waiting_rows
                ),
                use_container_width=True
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
# -------------------------
# ROUTE RÉSZLETEK API-BÓL
# -------------------------

st.divider()

st.subheader(
    "🚚 Route részletek API-ból"
)

route_options = {
    f"{r['route_id']} - {r['courier_name']}": (
        r["courier_id"],
        r["route_id"]
    )
    for r in routes
}

selected_route = st.selectbox(
    "Route kiválasztása",
    list(route_options.keys())
)

if selected_route:

    courier_id, route_id = route_options[
        selected_route
    ]

    try:

        detail = load_driver_details(
            courier_id
        )

        if (
            "routes" in detail
            and len(detail["routes"]) > 0
        ):

            route = detail["routes"][-1]

            st.success(
                f"""
🚚 Route ID: {route['id']}

📦 Összes rendelés: {route['numTotalOrders']}

✅ Kiszállítva: {route['numDeliveredOrders']}

⏰ Tervezett indulás:
{route['plannedDeparture']}

🚚 Tényleges indulás:
{route['realDeparture']}

🏢 Tervezett visszaérkezés:
{route['plannedReturn']}

🚚 Tényleges visszaérkezés:
{route['realReturn']}
"""
            )

            checkpoints = route.get(
                "checkpoints",
                []
            )

            st.subheader(
                f"📍 Címek ({len(checkpoints)})"
            )

            for stop in checkpoints:

                status_icon = "🚚"

                if str(
                    stop.get(
                        "realArrivalTime",
                        ""
                    )
                ).strip():

                    status_icon = "✅"

                real_arrival = (
                    stop.get(
                        "realArrivalTime",
                        ""
                    )
                    or "-"
                )

                real_departure = (
                    stop.get(
                        "realDepartureTime",
                        ""
                    )
                    or "-"
                )

                st.markdown(
                    f"""
### {status_icon} {stop['position']}. cím

🏠 **{stop['address']}**

📦 Order ID:
{stop['orderId']}

🕐 Időablak:
{stop['deliverSince'][11:16]} → {stop['deliverTill'][11:16]}

⏰ Tervezett érkezés:
{stop['plannedArrivalTime'][11:16]}

🚚 Várható érkezés:
{stop['estimatedArrivalTime'][11:16]}

✅ Tényleges érkezés:
{real_arrival[:16] if real_arrival != '-' else '-'}

🚪 Tényleges távozás:
{real_departure[:16] if real_departure != '-' else '-'}
"""
                )

                st.divider()

        else:

            st.warning(
                "Nincs route adat."
            )

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )