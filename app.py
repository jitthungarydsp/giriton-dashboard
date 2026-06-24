import streamlit as st

from page.profile import (
    show_profile_page
)

from resource.auth import (
    login_screen,
    logout_button
)

from page.admin import (
    show_admin_page
)

# -------------------
# Bejelentkezés
# -------------------

login_screen()

if "user" not in st.session_state:

    st.stop()

user = st.session_state["user"]

# -------------------
# Sidebar
# -------------------

st.sidebar.success(
    f"👤 {user['username']}"
)

st.sidebar.info(
    f"Jogosultság: {user['role']}"
)

logout_button()

# -------------------
# Menü
# -------------------

if user["role"] == "admin":

    menu = [
        "Admin",
        "Profil"
    ]

else:

    menu = [
        "Profil"
    ]

page = st.sidebar.radio(
    "Menü",
    menu
)

# -------------------
# Oldalak
# -------------------

if page == "Admin":

    show_admin_page()

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