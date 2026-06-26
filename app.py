import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Giriton Dashboard",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {
    max-width: none;
    padding-left: 1rem;
    padding-right: 1rem;
}
[data-testid="stHorizontalBlock"] {
    gap: 1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

from page.profile import (
    show_profile_page
)

from resources.auth import (
    login_screen,
    logout_button
)

from page.admin import (
    show_admin_page
)

from page.today_couriers import (
    show_today_couriers_page
)

from page.live_map import (
    show_live_map_page
)

from page.waiting_couriers import (
    show_waiting_couriers_page
)

from page.statistics import (
    show_statistics_page
)

# -------------------
# Bejelentkezés
# -------------------

login_screen()

if "user" not in st.session_state:

    st.stop()

user = st.session_state["user"]
selected_courier_id = user.get("courierId")
selected_name = user.get("username")

# -------------------
# Automatikus frissites
# -------------------

st_autorefresh(
    interval=30 * 1000,
    key="dashboard_auto_refresh"
)

# -------------------
# Sidebar
# -------------------

st.sidebar.success(
    f"👤 {user['username']}"
)

st.sidebar.info(
    f"Jogosultság: {user['role']}"
)

st.sidebar.caption(
    "Automatikus frissítés: 30 mp"
)

logout_button()

# -------------------
# Menü
# -------------------

if user["role"] == "admin":

    menu = [
        "Admin",
        "Mai futárok",
        "Várakozó futárok",
        "Live Map",
        "Profil"
    ]

else:

    menu = [
        "Mai futárok",
        "Várakozó futárok",
        "Live Map",
        "Profil"
    ]

if "Statisztika" not in menu:
    menu.insert(
        max(len(menu) - 1, 0),
        "Statisztika"
    )

page = st.sidebar.radio(
    "Menü",
    menu
)

# -------------------
# Oldalak
# -------------------

if page == "Admin":

    show_admin_page()

elif page == "Mai futárok":

    show_today_couriers_page()

elif page == "Live Map":

    show_live_map_page()

elif page == "Várakozó futárok":

    show_waiting_couriers_page()

elif page == "Statisztika":

    show_statistics_page()

elif page == "Trainer":

    st.title(
        "👨‍🏫 Trainer felület"
    )

    st.info(
        "Fejlesztés alatt"
    )

elif page == "Saját adatok":

    st.title(
        "👤 Saját adatok"
    )

    st.info(
        "Fejlesztés alatt"
    )

elif page == "Profil":

    show_profile_page()
