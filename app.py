import streamlit as st
import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
from datetime import datetime
from dsp_common_kw import hu_time

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
def load_attendance():

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    url = (
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-attendance/JIT/{today}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    )

    response = requests.get(
        url,
        timeout=30
    )

    return response.json()
################################################################################################################
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
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-drivers-detail/{driver_id}/{today}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
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
        "🗺️ Élő futártérkép",
        "📦 Rakodási infók",
        "👥 Mai futárok"
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
# MAI FUTÁROK
# ---------------------------------

elif page == "👥 Mai futárok":

    from streamlit_autorefresh import st_autorefresh
    from datetime import datetime

    st_autorefresh(
        interval=30000,
        key="attendance_refresh"
    )

    st.title("👥 Mai futárok")

    try:

        data = load_attendance()

        rows = []

        for courier in data.get(
            "couriers",
            []
        ):

            routes = courier.get(
                "routes",
                []
            )

            used_routes = set()

            for shift in courier.get(
                "shifts",
                []
            ):

                available_raw = shift.get(
                    "availableForShiftSince"
                )

                available_since = hu_time(
                    available_raw
                )

                route_status = "Nem dolgozik"

                route_id = ""
                courier_registered = ""
                assigned_at = ""
                planned_departure = ""
                real_departure = ""
                planned_return = ""
                real_return = ""

                matched_route = None

                if available_raw and routes:

                    try:

                        available_dt = datetime.fromisoformat(
                            available_raw.replace(
                                "Z",
                                "+00:00"
                            )
                        )

                        closest_diff = None

                        for route in routes:

                            if route.get(
                                "routeId"
                            ) in used_routes:
                                continue

                            reg = route.get(
                                "courierRegisteredAt"
                            )

                            if not reg:

                                reg = route.get(
                                    "assignedAt"
                                )

                            if not reg:
                                continue

                            reg_dt = datetime.fromisoformat(
                                reg.replace(
                                    "Z",
                                    "+00:00"
                                )
                            )

                            diff = abs(
                                (
                                    reg_dt -
                                    available_dt
                                ).total_seconds()
                            )

                            if (
                                closest_diff is None
                                or
                                diff < closest_diff
                            ):

                                closest_diff = diff
                                matched_route = route

                    except:
                        pass

                # -------------------------
                # Talált route
                # -------------------------

                if matched_route:

                    used_routes.add(
                        matched_route.get(
                            "routeId"
                        )
                    )

                    route_status = "Kapott túrát"

                    route_id = matched_route.get(
                        "routeId"
                    )

                    courier_registered = hu_time(
                        matched_route.get(
                            "courierRegisteredAt"
                        )
                    )

                    assigned_at = hu_time(
                        matched_route.get(
                            "assignedAt"
                        )
                    )

                    planned_departure = hu_time(
                        matched_route.get(
                            "plannedDeparture"
                        )
                    )

                    real_departure = hu_time(
                        matched_route.get(
                            "realDeparture"
                        )
                    )

                    planned_return = hu_time(
                        matched_route.get(
                            "plannedReturn"
                        )
                    )

                    real_return = hu_time(
                        matched_route.get(
                            "realReturn"
                        )
                    )

                elif available_raw:

                    try:

                        available_dt = datetime.fromisoformat(
                            available_raw.replace(
                                "Z",
                                "+00:00"
                            )
                        )

                        wait_minutes = round(
                            (
                                datetime.now(
                                    available_dt.tzinfo
                                )
                                -
                                available_dt
                            ).total_seconds()
                            / 60
                        )

                        route_status = (
                            f"Vár túrára ({wait_minutes} perc)"
                        )

                    except:
                        pass

                rows.append({

                    "Név":
                    courier.get(
                        "courierName"
                    ),

                    "Courier ID":
                    courier.get(
                        "courierId"
                    ),

                    "Depó":
                    courier.get(
                        "warehouseName"
                    ),

                    "Műszak":
                    shift.get(
                        "shiftName"
                    ),

                    "Műszak kezdete":
                    hu_time(
                        shift.get(
                            "shiftStart"
                        )
                    ),

                    "Műszak vége":
                    hu_time(
                        shift.get(
                            "shiftEnd"
                        )
                    ),

                    "Elérhető":
                    available_since,

                    "Státusz":
                    route_status,

                    "Route ID":
                    route_id,

                    "Sorba állt":
                    courier_registered,

                    "Túrát kapott":
                    assigned_at,

                    "Tervezett indulás":
                    planned_departure,

                    "Tényleges indulás":
                    real_departure,

                    "Tervezett vissza":
                    planned_return,

                    "Tényleges vissza":
                    real_return

                })

        df = pd.DataFrame(
            rows
        )

        df = df.sort_values(
            by=[
                "Név",
                "Műszak kezdete"
            ]
        ).reset_index(
            drop=True
        )

        st.dataframe(
            df,
            use_container_width=True,
            height=750
        )

        st.caption(
            "🔄 Automatikus frissítés: 30 mp"
        )

    except Exception as e:

        st.error(
            f"Hiba történt: {e}"
        )