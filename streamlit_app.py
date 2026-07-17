import streamlit as st

from resources.auth import login_screen, logout_button
from page.invoice_summary import show_invoice_summary_page

st.set_page_config(
    page_title="JITT Elszámolás",
    layout="wide",
)

login_screen()

if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]

st.sidebar.success(f"👤 {user['username']}")
st.sidebar.info(f"Jogosultság: {user['role']}")
logout_button()

st.title("📄 Elszámolás")

show_invoice_summary_page()