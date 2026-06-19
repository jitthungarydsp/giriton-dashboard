import streamlit as st

PASSWORD = "JIT2026"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 DSP Bejelentkezés")

    password = st.text_input(
        "Jelszó",
        type="password"
    )

    if st.button("Belépés"):

        if password == PASSWORD:

            st.session_state.logged_in = True
            st.rerun()

        else:

            st.error(
                "Hibás jelszó!"
            )

    st.stop()

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

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

# -------------------------
# Segéd
# -------------------------

@st.cache_data(ttl=60)
def load_sheet(sheet_name):

    ws = spreadsheet.worksheet(sheet_name)

    data = ws.get_all_records()

    return pd.DataFrame(data)

# -------------------------
# UI
# -------------------------

st.set_page_config(
    page_title="DSP Search",
    layout="wide"
)

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

# -------------------------
# Keresés
# -------------------------

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