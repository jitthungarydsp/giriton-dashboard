import streamlit as st

from page.invoice_summary import show_invoice_summary_page
from page.monthly_invoice_editor import (
    show_monthly_invoice_editor_page,
    show_monthly_tig_editor_page,
)
from page.bill_config import show_bill_config_page
from page.bill_bonus_malus import show_bonus_malus_page
from page.bill_insurance_reserve import show_insurance_reserve_page
from resources.auth import login_screen, logout_button
from page.bill_config import show_bill_config_page


st.set_page_config(
    page_title="JITT Elszámolás",
    page_icon="🧾",
    layout="wide",
)


# ==========================================================
# BEJELENTKEZÉS
# ==========================================================

login_screen()

if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]


# ==========================================================
# OLDALSÁV
# ==========================================================

st.sidebar.success(
    f"Felhasználó: {user['username']}"
)

st.sidebar.info(
    f"Jogosultság: {user['role']}"
)

logout_button()

st.sidebar.divider()

selected_page = st.sidebar.radio(
    "Menü",
    [
        "Elszámolás",
        "Havi számla",
        "Havi TIG",
        "Konfiguráció",
        "Bónusz / Málusz",
        "Biztosítás / Céltartalék",
    ],
)


# ==========================================================
# OLDALAK BETÖLTÉSE
# ==========================================================

if selected_page == "Elszámolás":
    show_invoice_summary_page()

elif selected_page == "Havi számla":
    show_monthly_invoice_editor_page()

elif selected_page == "Havi TIG":
    show_monthly_tig_editor_page()

elif selected_page == "Konfiguráció":
    show_bill_config_page()

elif selected_page == "Bónusz / Málusz":
    show_bonus_malus_page()

elif selected_page == "Biztosítás / Céltartalék":
    show_insurance_reserve_page()

else:
    st.error("A kiválasztott oldal nem található.")