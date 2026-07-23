import streamlit as st


from page.new_invoice_summary_page import show_new_invoice_summary_page
from page.invoice_summary import show_invoice_summary_page
from page.monthly_invoice_tasks import show_monthly_invoice_tasks_page
from page.monthly_invoice_editor import (
    show_monthly_invoice_editor_page,
    show_monthly_tig_editor_page,
)
from resources.auth import login_screen, logout_button
from page.bonus_malus import show_bonus_malus_page
from page.compensation_settings import show_compensation_configuration_page
from page.amount_reconciliation import show_amount_reconciliation_page


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

if user.get("role") == "coordinator":
    settlement_menu = ["Bónusz / Málusz"]
else:
    settlement_menu = [
        "Elszámolás",
        "Havi feladatok",
        "Havi számla",
        "Havi TIG",
        "Összeg ellenőrzés",
        "Konfiguráció",
        "Bónusz / Málusz",
        "Biztosítás / Céltartalék",
        "Új Elszámolási oldal"
    ]

selected_page = st.sidebar.radio(
    "Menü",
    settlement_menu,
)




# ==========================================================
# OLDALAK BETÖLTÉSE
# ==========================================================

if selected_page == "Elszámolás":
    show_invoice_summary_page()

elif selected_page == "Havi feladatok":
    show_monthly_invoice_tasks_page()

elif selected_page == "Havi számla":
    show_monthly_invoice_editor_page()

elif selected_page == "Havi TIG":
    show_monthly_tig_editor_page()

elif selected_page == "Összeg ellenőrzés":
    show_amount_reconciliation_page()

elif selected_page == "Konfiguráció":
    show_compensation_configuration_page()

elif selected_page == "Bónusz / Málusz":
    show_bonus_malus_page()

elif selected_page == "Biztosítás / Céltartalék":
    show_insurance_reserve_page()

elif selected_page == "Új Elszámolási oldal":
    show_new_invoice_summary_page()

else:
    st.error("A kiválasztott oldal nem található.")
