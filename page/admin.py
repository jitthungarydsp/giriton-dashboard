import pandas as pd
import streamlit as st

from resources.courier_db_sheet import (
    sync_courier_db_from_drivers,
    upsert_couriers,
)
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

    created_user = st.session_state.pop(
        "admin_created_user",
        None,
    )

    if created_user:
        st.success(
            f"Felhasználó létrehozva: {created_user['username']} | Jelszó: {created_user['password']}"
        )

    data = load_users()

    users = data["users"]

    st.subheader(
        "👥 Felhasználók"
    )

    display_users = []

    for user in users:

        display_user = user.copy()

        if display_user.get(
            "password"
        ):
            display_user["password"] = "legacy plaintext"

        if display_user.get(
            "passwordHash"
        ):
            display_user["passwordHash"] = "set"

        if display_user.get(
            "token"
        ):
            display_user["token"] = "active"

        display_users.append(
            display_user
        )

    df = pd.DataFrame(
        display_users
    )

    st.dataframe(
        df,
        use_container_width=True,
        height=500
    )

    st.divider()

    st.subheader(
        "🚚 CourierDB_JITT törzsadat"
    )

    st.caption(
        "ID, név, e-mail, telefonszám és raktár frissítése a DSP driver API-ból. A courier_id lesz a biztos azonosító."
    )

    if st.button(
        "CourierDB_JITT frissítése"
    ):
        try:
            result = sync_courier_db_from_drivers()
            st.success(
                f"CourierDB_JITT frissítve: {result['updated']} API rekord, összesen {result['total']} futár."
            )
        except Exception as exc:
            st.error(
                f"CourierDB_JITT frissítés sikertelen: {exc}"
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

        email = st.text_input(
            "E-mail cím"
        )

        phone = st.text_input(
            "Telefonszám"
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

            try:
                password = create_user(
                    username,
                    int(courier_id),
                    role,
                    trainer,
                )
                try:
                    upsert_couriers(
                        [
                            {
                                "courier_id": int(courier_id),
                                "name": username,
                                "email": email,
                                "phone": phone,
                                "source": "admin",
                                "active": "True",
                            }
                        ]
                    )
                except Exception as exc:
                    st.warning(
                        f"A felhasználó elkészült, de a CourierDB_JITT frissítés nem sikerült: {exc}"
                    )
                st.session_state["admin_created_user"] = {
                    "username": username,
                    "password": password,
                }
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

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

