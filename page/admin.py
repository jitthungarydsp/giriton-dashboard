import pandas as pd
import streamlit as st

from resources.users import (
    load_users,
    create_user,
    reset_password,
    update_role,
    toggle_active,
    update_trainer,
    delete_user
)

def show_admin_page():

    st.title(
        "👑 Admin"
    )

    data = load_users()

    users = data["users"]

    st.subheader(
        "👥 Felhasználók"
    )

    df = pd.DataFrame(
        users
    )

    st.dataframe(
        df,
        use_container_width=True,
        height=500
    )

    st.divider()

    st.subheader(
        "➕ Új felhasználó"
    )

    with st.form(
        "new_user"
    ):

        username = st.text_input(
            "Név"
        )

        courier_id = st.number_input(
            "Courier ID",
            step=1
        )

        role = st.selectbox(

            "Jogosultság",

            [
                "user",
                "trainer",
                "admin"
            ]
        )

        trainer = st.text_input(
            "Trainer"
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

            update_trainer(
                username,
                trainer
            )

            st.success(
                f"Jelszó: {password}"
            )

            st.rerun()

    st.divider()

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

    col1, col2 = st.columns(
        2
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

        trainer = st.text_input(

            "Trainer",

            value=
            selected_data.get(
                "trainer",
                ""
            )
        )

        active = st.checkbox(

            "Aktív",

            value=
            selected_data.get(
                "active",
                True
            )
        )

        if st.button(
            "💾 Mentés"
        ):

            update_role(
                selected_user,
                new_role
            )

            update_trainer(
                selected_user,
                trainer
            )

            toggle_active(
                selected_user,
                active
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

        st.divider()

        if st.button(
            "🗑️ Felhasználó törlése"
        ):

            delete_user(
                selected_user
            )

            st.success(
                "Felhasználó törölve"
            )

            st.rerun()
####################################

