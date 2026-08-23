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
from page.order_statistics import (
    show_order_statistics_page,
)
from page.invoice_summary import (
    show_invoice_summary_page,
)
from page.monthly_invoice_tasks import (
    show_monthly_invoice_tasks_page,
)
from page.amount_reconciliation import show_amount_reconciliation_page
from page.dsp_route_explanations import (
    show_dsp_route_explanations_page,
)
from page.courier_dashboard import (
    show_courier_dashboard_page,
)
from page.robots import (
    show_robots_page,
)
from page.db_probe import (
    show_db_probe_page,
)
from page.couriers import (
    show_couriers_page,
)
from page.giriton_attendance_db import (
    show_giriton_attendance_db_page,
)
from page.giriton_shifts_db import (
    show_giriton_shifts_db_page,
)
from page.foglalasok_db import (
    show_foglalasok_db_page,
)
from page.giriton_auto_booking import (
    show_giriton_auto_booking_page,
)
from page.foglalas_streamlit import (
    show_foglalas_streamlit_page,
)
from page.jitt_muszak import (
    show_jitt_muszak_page,
)
from page.settings import (
    show_settings_page,
)
from page.bonus_malus import show_bonus_malus_page


login_screen()

if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]

if user.get("role") == "user":
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
    padding-left: 1rem;
    padding-right: 1rem;
}
</style>
""",
        unsafe_allow_html=True,
    )
    st_autorefresh(
        interval=5 * 60 * 1000,
        key="courier_card_auto_refresh",
    )
    show_courier_dashboard_page()
    st.stop()

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
        "Beállítások",
        "Robotok",
        "DB proba",
        "JITT muszak admin",
        "Giriton Auto Booking",
        "Foglalás egyeztetés",
        "Giriton muszakok DB",
        "Foglalasok DB",
        "Giriton Attendance DB",
        "Performance magyarazat",
        "Elszamolas",
        "Havi feladatok",
        "Összeg ellenőrzés",
        "Bónusz / Málusz",
        "Futárok",
        "Mai futárok",
        "Kifli kártya",
        "Mai műszakok",
        "Várakozó futárok",
        "Live Map",
        "Profil",
    ]
elif user["role"] == "coordinator":
    menu = ["Bónusz / Málusz"]
else:
    menu = [
        "Mai futárok",
        "Kifli kártya",
        "Mai műszakok",
        "Várakozó futárok",
        "Live Map",
        "Profil",
    ]

if user["role"] != "coordinator" and "Statisztika" not in menu:
    menu.insert(
        max(len(menu) - 1, 0),
        "Statisztika",
    )

if user["role"] != "coordinator" and "Megrendeles statisztika" not in menu:
    menu.insert(
        max(len(menu) - 1, 0),
        "Megrendeles statisztika",
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
elif page == "Beállítások":
    show_settings_page()
elif page == "Robotok":
    show_robots_page()
elif page == "DB proba":
    show_db_probe_page()
elif page == "JITT muszak admin":
    show_jitt_muszak_page()
elif page == "Giriton Auto Booking":
    show_giriton_auto_booking_page()
elif page == "Foglalás egyeztetés":
    show_foglalas_streamlit_page()
elif page == "Giriton muszakok DB":
    show_giriton_shifts_db_page()
elif page == "Foglalasok DB":
    show_foglalasok_db_page()
elif page == "Giriton Attendance DB":
    show_giriton_attendance_db_page()
elif page in ["Futárok", "FutĂˇrok"]:
    show_couriers_page()
elif page == "Mai futárok":
    show_today_couriers_page()
elif page == "Kifli kártya":
    show_courier_dashboard_page()
elif page == "Mai műszakok":
    show_today_shifts_page()
elif page == "Live Map":
    show_live_map_page()
elif page == "Várakozó futárok":
    show_waiting_couriers_page()
elif page == "Statisztika":
    show_statistics_page()
elif page == "Megrendeles statisztika":
    show_order_statistics_page()
elif page == "Elszamolas":
    show_invoice_summary_page()
elif page == "Havi feladatok":
    show_monthly_invoice_tasks_page()
elif page == "Összeg ellenőrzés":
    show_amount_reconciliation_page()
elif page == "Bónusz / Málusz":
    show_bonus_malus_page()
elif page == "Performance magyarazat":
    show_dsp_route_explanations_page()
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
