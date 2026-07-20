import streamlit as st

from page.invoice_summary import show_invoice_summary_page
from page.monthly_invoice_editor import (
    show_monthly_invoice_editor_page,
    show_monthly_tig_editor_page,
)
from resources.auth import login_screen, logout_button


st.set_page_config(
    page_title="JITT Elszámolás",
    layout="wide",
)

login_screen()

if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]

st.sidebar.success(f"Felhasználó: {user['username']}")
st.sidebar.info(f"Jogosultság: {user['role']}")
logout_button()

selected_page = st.sidebar.radio(
    "Menü",
    [
        "Elszámolás",
        "Havi számla",
        "Havi TIG",
    ],
)

if selected_page == "Havi TIG":
    show_monthly_tig_editor_page()
elif selected_page == "Havi számla":
    show_monthly_invoice_editor_page()
else:
    show_invoice_summary_page()
