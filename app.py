import streamlit as st

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

# -------------------
# Bejelentkezés
# -------------------

login_screen()

if "user" not in st.session_state:

    st.stop()

user = st.session_state["user"]
selected_courier_id
selected_name = user.get("username")

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

    st.divider()

    st.subheader("Aktív futárok")

    active_couriers = []

    for courier in couriers:

        active_couriers.append({

            "id": courier.get("courierId"),
            "name": courier.get("courierName")

        })

    selected = st.selectbox(

        "🚚 Futár",

        options=active_couriers,

        format_func=lambda x:
        f"{x['name']} ({x['id']})"

    )

    selected_courier_id = selected["id"]
    selected_name = selected["name"]