import streamlit as st

USERS = {
    "balazs": "1234",
    "fonok": "JIT2026",
    "diszpecser": "admin123"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 Bejelentkezés")

    username = st.text_input("Felhasználónév")
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

if st.sidebar.button("Kijelentkezés"):

    st.session_state.logged_in = False

    st.rerun()

page = st.sidebar.radio(
    "Menü",
    [
        "🔍 Kereső",
        "🚚 Futár Dashboard",
        "🗺️ Aktuális útvonal",
        "📊 Admin Dashboard"
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

elif page == "🗺️ Aktuális útvonal":

    st.title("🗺️ Aktuális útvonal")

    orders_df = load_sheet(
        "DSP_Orders"
    )

    customers_df = load_sheet(
        "DSP_Order_Customers"
    )

    route_id = st.text_input(
        "Route ID"
    )

    if route_id:

        route_df = customers_df[
            customers_df["routeId"].astype(str)
            == str(route_id)
        ]

        if route_df.empty:

            st.warning(
                "Nincs ilyen Route."
            )

        else:

            route_df = route_df.sort_values(
                "position"
            )

            order_row = orders_df[
                orders_df["routeId"].astype(str)
                == str(route_id)
            ]

            planned_return = ""

            if not order_row.empty:

                planned_return = (
                    order_row.iloc[0]
                    .get(
                        "plannedReturn",
                        ""
                    )
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

                eta = stop.get(
                    "estimatedArrivalTime",
                    ""
                )

                real_arrival = stop.get(
                    "realArrivalTime",
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

⏰ ETA: {eta}
"""
                )

                st.divider()

            st.success(
                f"""
🏢 Vissza a depóba

⏰ Várható visszaérkezés:
{planned_return}
"""
            )
             
# ---------------------------------
# ADMIN DASHBOARD
# ---------------------------------

elif page == "📊 Admin Dashboard":

    st.title("📊 Admin Dashboard")

    st.info(
        "Hamarosan..."
    )