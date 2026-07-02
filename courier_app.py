import streamlit as st
from streamlit_autorefresh import st_autorefresh

from page.courier_dashboard import show_courier_dashboard_page
from resources.auth import login_screen


st.set_page_config(
    page_title="Kifli futar kartya",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
[data-testid="stSidebar"] {
    display: none;
}
[data-testid="collapsedControl"] {
    display: none;
}
.block-container {
    max-width: none;
    padding: 1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

login_screen()

if "user" not in st.session_state:
    st.stop()

st_autorefresh(
    interval=5 * 60 * 1000,
    key="courier_app_auto_refresh",
)

show_courier_dashboard_page()
