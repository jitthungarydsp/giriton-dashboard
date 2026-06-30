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
    show_profile_page,
)
from resources.auth import (
    login_screen,
    logout_button,
)
from page.admin import (
    show_admin_page,
)
from page.today_couriers import (
    show_today_couriers_page,
)
from page.today_shifts import (
    show_today_shifts_page,
)
from page.live_map import (
    show_live_map_page,
)
from page.waiting_couriers import (
    show_waiting_couriers_page,
)
from page.statistics import (
    show_statistics_page,
)


login_screen()

if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]

st.sidebar.success(
    f"👤 {user['username']}"
)
st.sidebar.info(
    f"Jogosultság: {user['role']}"
)
logout_button()

if user["role"] == "admin":
    menu = [
        "Admin",
        "Mai futárok",
        "Mai műszakok",
        "Várakozó futárok",
        "Live Map",
        "Profil",
    ]
else:
    menu = [
        "Mai futárok",
        "Mai műszakok",
        "Várakozó futárok",
        "Live Map",
        "Profil",
    ]

if "Statisztika" not in menu:
    menu.insert(
        max(len(menu) - 1, 0),
        "Statisztika",
    )

page = st.sidebar.radio(
    "Menü",
    menu,
)

if page == "Live Map":
    st_autorefresh(
        interval=30 * 1000,
        key="live_map_auto_refresh",
    )
    st.sidebar.caption(
        "Live Map automatikus frissítés: 30 mp"
    )
else:
    if st.sidebar.button(
        "Frissítés",
        use_container_width=True,
    ):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state["manual_refresh_requested"] = True
        st.session_state["manual_refresh_counter"] = (
            st.session_state.get(
                "manual_refresh_counter",
                0,
            )
            + 1
        )
        st.rerun()

    st_autorefresh(
        interval=5 * 60 * 1000,
        key=f"{page}_auto_refresh",
    )
    st.sidebar.caption(
        "Automatikus frissítés: 5 perc"
    )

if page == "Admin":
    show_admin_page()
elif page == "Mai futárok":
    show_today_couriers_page()
elif page == "Mai műszakok":
    show_today_shifts_page()
elif page == "Live Map":
    show_live_map_page()
elif page == "Várakozó futárok":
    show_waiting_couriers_page()
elif page == "Statisztika":
    show_statistics_page()
elif page == "Trainer":
    st.title(
        "Trainer felület"
    )
    st.info(
        "Fejlesztés alatt"
    )
elif page == "Saját adatok":
    st.title(
        "Saját adatok"
    )
    st.info(
        "Fejlesztés alatt"
    )
elif page == "Profil":
    show_profile_page()
