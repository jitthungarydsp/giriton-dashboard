import pandas as pd
import streamlit as st

from resource.users import (
    load_users,
    create_user,
    reset_password,
    update_role,
    toggle_active
)


def show_admin_page():

    user = st.session_state.user

    if (
        user["role"]
        !=
        "admin"
    ):

        st.error(
            "Nincs jogosultságod!"
        )

        st.stop()

    st.title(
        "👑 Admin"
    )

    data = load_users()

    users = data["users"]

    # ------------------
    # User lista
    # ------------------

    st.subheader(
        "👥 Felhasználók"
    )

    df = pd.DataFrame(
        users
    )

    st.dataframe(
        df,
        use_container_width=True,
        height=400
    )

    st.divider()

    # ------------------
    # Új user
    # ------------------

    st.subheader(
        "➕ Új felhasználó"
    )

    with st.form(
        "new_user"
    ):

        username = st.text_input(
            "Felhasználónév"
        )

        courier_id = st.number_input(
            "Courier ID",
            step=1
        )

        role = st.selectbox(
            "Role",
            [
                "user",
                "trainer",
                "admin"
            ]
        )

        submitted = st.form_submit_button(
            "Létrehozás"
        )

        if submitted:

            password = create_user(
                username,
                courier_id,
                role
            )

            st.success(
                f"Jelszó: {password}"
            )

            st.rerun()

    st.divider()

    # ------------------
    # User kezelés
    # ------------------

    st.subheader(
        "⚙️ Felhasználó kezelése"
    )

    selected_user = st.selectbox(

        "Felhasználó",

        [
            u["username"]
            for u in users
        ]
    )

    selected_data = next(

        u

        for u in users

        if (
            u["username"]
            ==
            selected_user
        )
    )

    col1, col2, col3 = st.columns(
        3
    )

    with col1:

        new_role = st.selectbox(

            "Jogosultság",

            [
                "user",
                "trainer",
                "admin"
            ],

            index=[
                "user",
                "trainer",
                "admin"
            ].index(
                selected_data[
                    "role"
                ]
            )
        )

        if st.button(
            "Jogosultság mentése"
        ):

            update_role(
                selected_user,
                new_role
            )

            st.success(
                "Mentve"
            )

            st.rerun()

    with col2:

        if st.button(
            "🔑 Jelszó reset"
        ):

            password = reset_password(
                selected_user
            )

            st.success(
                f"Új jelszó: {password}"
            )

    with col3:

        active = st.checkbox(

            "Aktív",

            value=
            selected_data.get(
                "active",
                True
            )
        )

        if st.button(
            "Aktív állapot mentése"
        ):

            toggle_active(
                selected_user,
                active
            )

            st.success(
                "Mentve"
            )

            st.rerun()