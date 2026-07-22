import time

import pandas as pd
import streamlit as st

from resources.courier_db_sheet import (
    sync_courier_db_from_drivers,
    upsert_couriers,
    )
from resources.courier_master_db import read_courier_master
from resources.email_sender import send_login_credentials, validate_email
from resources.users import (
    build_courier_master_sync_preview,
    load_users,
    create_user,
    reset_password,
    sync_users_from_courier_master,
    update_role,
    toggle_active,
    update_trainer,
    delete_user,
)


def normalize_courier_id(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_email_lookup():
    courier_master_df = read_courier_master()
    if courier_master_df is None or courier_master_df.empty:
        return {}
    if "courier_id" not in courier_master_df.columns:
        return {}

    lookup = {}
    for _, row in courier_master_df.iterrows():
        courier_id = normalize_courier_id(row.get("courier_id"))
        if not courier_id:
            continue
        email = str(row.get("email") or row.get("billing_email") or "").strip()
        lookup[courier_id] = email
    return lookup


def get_user_courier_id(user):
    return normalize_courier_id(
        user.get("courierId") or user.get("courier_id") or ""
    )


def get_existing_password(user):
    return str(user.get("password") or "").strip()


def get_courier_email(user, email_lookup):
    return str(email_lookup.get(get_user_courier_id(user)) or "").strip()


def send_existing_credentials(user, recipient_email):
    username = str(user.get("username") or "").strip()
    password = get_existing_password(user)

    if not username:
        raise ValueError("Hiányzik a felhasználónév.")
    if not password:
        raise ValueError(
            "Nincs olvasható password mező a users.json fájlban. "
            "A passwordHash értékből a jelszó nem állítható vissza."
        )

    recipient_email = validate_email(recipient_email)
    return send_login_credentials(recipient_email, username, password)


def show_admin_page():
    st.title("👑 Admin")

    created_user = st.session_state.pop("admin_created_user", None)
    if created_user:
        st.success(
            f"Felhasználó létrehozva: {created_user['username']} | "
            f"Jelszó: {created_user['password']}"
        )

    data = load_users()
    users = data.get("users", [])

    st.subheader("👥 Felhasználók")

    show_passwords = st.toggle(
        "Jelszavak megjelenítése",
        value=False,
        help="Csak adminisztrációs célra használd.",
    )

    display_users = []
    for user in users:
        display_user = user.copy()

        if not show_passwords:
            if display_user.get("password"):
                display_user["password"] = "••••••••"
            if display_user.get("passwordHash"):
                display_user["passwordHash"] = "beállítva"

        if display_user.get("token"):
            display_user["token"] = "aktív"

        display_users.append(display_user)

    st.dataframe(
        pd.DataFrame(display_users),
        use_container_width=True,
        height=500,
        hide_index=True,
    )

    st.divider()
    st.subheader("🔄 users.json frissítése a courier_master alapján")

    st.caption(
        "A courier_id alapján frissíti a users.json fájlt. "
        "Az admin jogosultságú felhasználók és Bagoly Zoltán változatlanok maradnak. "
        "A többi meglévő felhasználó új jelszót kap."
    )

    try:
        courier_master_for_sync = read_courier_master()
    except Exception as exc:
        courier_master_for_sync = pd.DataFrame()
        st.error(f"A courier_master nem olvasható: {exc}")

    if not courier_master_for_sync.empty:
        courier_rows = courier_master_for_sync.to_dict("records")
        sync_preview = build_courier_master_sync_preview(courier_rows)
        sync_preview_df = pd.DataFrame(sync_preview)

        if not sync_preview_df.empty:
            action_counts = sync_preview_df["action"].value_counts().to_dict()
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Új", action_counts.get("Új felhasználó", 0))
            p2.metric(
                "Reset + frissítés",
                action_counts.get("Frissítés + jelszó reset", 0),
            )
            p3.metric(
                "Védett",
                action_counts.get("Védett – változatlan", 0),
            )
            p4.metric("Összes", len(sync_preview_df))

            with st.expander("Szinkron előnézet", expanded=False):
                st.dataframe(
                    sync_preview_df,
                    use_container_width=True,
                    hide_index=True,
                )

        confirm_sync = st.checkbox(
            "Megerősítem a users.json frissítését és a nem védett felhasználók jelszó-resetjét.",
            key="confirm_users_json_sync",
        )

        if st.button(
            "users.json frissítése",
            type="primary",
            disabled=not confirm_sync,
        ):
            try:
                result = sync_users_from_courier_master(
                    courier_rows,
                    reset_existing=True,
                )
                st.session_state["last_users_sync_passwords"] = result.get(
                    "passwords",
                    [],
                )
                st.success(
                    "Frissítés kész. "
                    f"Új: {result['created']}, "
                    f"frissített: {result['updated']}, "
                    f"resetelt: {result['reset']}, "
                    f"védett: {result['protected']}, "
                    f"kihagyott: {result['skipped']}."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"A users.json frissítése sikertelen: {exc}")

    generated_passwords = st.session_state.get(
        "last_users_sync_passwords",
        [],
    )

    if generated_passwords:
        with st.expander(
            "Legutóbbi szinkronban generált jelszavak",
            expanded=True,
        ):
            show_generated_passwords = st.toggle(
                "Generált jelszavak megjelenítése",
                value=False,
                key="show_generated_passwords",
            )
            generated_df = pd.DataFrame(generated_passwords)

            if (
                not show_generated_passwords
                and "password" in generated_df.columns
            ):
                generated_df["password"] = "••••••••"

            st.dataframe(
                generated_df,
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "Jelszólista elrejtése",
                key="clear_generated_passwords",
            ):
                st.session_state.pop(
                    "last_users_sync_passwords",
                    None,
                )
                st.rerun()

    st.divider()
    st.subheader("🚚 CourierDB_JITT törzsadat")
    st.caption(
        "ID, név, e-mail, telefonszám és raktár frissítése a DSP driver API-ból. "
        "A courier_id lesz a biztos azonosító."
    )

    if st.button("CourierDB_JITT frissítése"):
        try:
            result = sync_courier_db_from_drivers()
            load_courier_email_lookup.clear()
            st.success(
                f"CourierDB_JITT frissítve: {result['updated']} API rekord, "
                f"összesen {result['total']} futár."
            )
        except Exception as exc:
            st.error(f"CourierDB_JITT frissítés sikertelen: {exc}")

    st.divider()
    st.subheader("➕ Új felhasználó")

    with st.form("new_user"):
        username = st.text_input("Név")
        courier_id = st.number_input("Courier ID", step=1)
        email = st.text_input("E-mail cím")
        phone = st.text_input("Telefonszám")
        role = st.selectbox("Jogosultság", ["user", "trainer", "coordinator", "admin"])
        trainer = st.text_input("Trainer")
        submitted = st.form_submit_button("Létrehozás")

        if submitted:
            try:
                password = create_user(username, int(courier_id), role, trainer)
                try:
                    upsert_couriers(
                        [{
                            "courier_id": int(courier_id),
                            "name": username,
                            "email": email,
                            "phone": phone,
                            "source": "admin",
                            "active": "True",
                        }]
                    )
                    load_courier_email_lookup.clear()
                except Exception as exc:
                    st.warning(
                        "A felhasználó elkészült, de a CourierDB_JITT "
                        f"frissítés nem sikerült: {exc}"
                    )

                st.session_state["admin_created_user"] = {
                    "username": username,
                    "password": password,
                }
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    try:
        email_lookup = load_courier_email_lookup()
    except Exception as exc:
        email_lookup = {}
        st.error(f"A courier_master e-mail címei nem tölthetők be: {exc}")

    st.divider()
    st.subheader("📨 Tömeges belépési adatok kiküldése")
    st.caption(
        "Az aktív felhasználók users.json fájlban tárolt jelenlegi jelszavát küldi ki. "
        "Nem generál új jelszót."
    )

    active_users = [u for u in users if bool(u.get("active", True))]
    bulk_candidates = []
    missing_email_users = []
    missing_password_users = []

    for user in active_users:
        email_address = get_courier_email(user, email_lookup)
        password = get_existing_password(user)

        if not email_address:
            missing_email_users.append(str(user.get("username") or "Ismeretlen"))
            continue
        if not password:
            missing_password_users.append(str(user.get("username") or "Ismeretlen"))
            continue

        bulk_candidates.append({"user": user, "email": email_address})

    c1, c2, c3 = st.columns(3)
    c1.metric("Aktív felhasználó", len(active_users))
    c2.metric("Küldhető", len(bulk_candidates))
    c3.metric(
        "Kihagyandó",
        len(missing_email_users) + len(missing_password_users),
    )

    with st.expander("Tömeges küldés ellenőrzése", expanded=False):
        preview = []
        for item in bulk_candidates:
            preview.append({
                "Felhasználó": item["user"].get("username"),
                "Courier ID": get_user_courier_id(item["user"]),
                "E-mail": item["email"],
                "Küldhető": "Igen",
            })
        for name in missing_email_users:
            preview.append({
                "Felhasználó": name,
                "Courier ID": "",
                "E-mail": "",
                "Küldhető": "Nem – nincs e-mail",
            })
        for name in missing_password_users:
            preview.append({
                "Felhasználó": name,
                "Courier ID": "",
                "E-mail": "",
                "Küldhető": "Nem – nincs olvasható jelszó",
            })
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

    bulk_confirm = st.checkbox(
        f"Megerősítem {len(bulk_candidates)} belépési e-mail kiküldését.",
        key="bulk_credentials_confirm",
    )

    if st.button(
        "📨 Belépési adatok kiküldése mindenkinek",
        type="primary",
        disabled=not bulk_confirm or not bulk_candidates,
    ):
        sent_count = 0
        failed_rows = []
        progress = st.progress(0)
        status_box = st.empty()

        for index, item in enumerate(bulk_candidates, start=1):
            user = item["user"]
            recipient = item["email"]
            username_value = str(user.get("username") or "").strip()
            status_box.write(f"Küldés: {username_value} → {recipient}")

            try:
                send_existing_credentials(user, recipient)
                sent_count += 1
            except Exception as exc:
                failed_rows.append({
                    "Felhasználó": username_value,
                    "E-mail": recipient,
                    "Hiba": str(exc),
                })

            progress.progress(index / len(bulk_candidates))
            time.sleep(0.15)

        status_box.empty()
        st.success(
            f"Tömeges küldés kész. Elküldve: {sent_count}, "
            f"hibás: {len(failed_rows)}, "
            f"kihagyva: {len(missing_email_users) + len(missing_password_users)}."
        )

        if failed_rows:
            st.dataframe(
                pd.DataFrame(failed_rows),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    st.subheader("⚙️ Felhasználó kezelése")

    if not users:
        st.info("Még nincs kezelhető felhasználó.")
        return

    selected_user = st.selectbox(
        "Felhasználó",
        [u["username"] for u in users],
    )
    selected_data = next(
        u for u in users if u["username"] == selected_user
    )

    col1, col2 = st.columns(2)

    with col1:
        roles = ["user", "trainer", "coordinator", "admin"]
        current_role = selected_data.get("role", "user")
        if current_role not in roles:
            current_role = "user"

        new_role = st.selectbox(
            "Jogosultság",
            roles,
            index=roles.index(current_role),
        )
        trainer = st.text_input(
            "Trainer",
            value=selected_data.get("trainer", ""),
        )
        active = st.checkbox(
            "Aktív",
            value=selected_data.get("active", True),
        )

        if st.button("💾 Mentés"):
            update_role(selected_user, new_role)
            update_trainer(selected_user, trainer)
            toggle_active(selected_user, active)
            st.success("Mentve")
            st.rerun()

    with col2:
        st.markdown("**Belépési adatok küldése**")

        selected_password = get_existing_password(selected_data)
        show_selected_password = st.toggle(
            "Jelszó megjelenítése",
            value=False,
            key=f"show_selected_password_{selected_user}",
        )
        st.text_input(
            "Jelenlegi jelszó",
            value=(
                selected_password
                if show_selected_password
                else "••••••••"
            ),
            disabled=True,
            key=f"selected_password_{selected_user}_{show_selected_password}",
        )

        selected_courier_id = get_user_courier_id(selected_data)
        default_email = get_courier_email(selected_data, email_lookup)
        existing_password = get_existing_password(selected_data)

        if not selected_courier_id:
            st.warning("Ehhez a felhasználóhoz nincs Courier ID beállítva.")
        if not default_email:
            st.warning("Ehhez a futárhoz nincs e-mail-cím a courier_master táblában.")
        if not existing_password:
            st.warning(
                "Ehhez a felhasználóhoz nincs olvasható password mező a users.json fájlban."
            )

        with st.form(f"send_login_credentials_form_{selected_user}"):
            recipient_email = st.text_input(
                "Futár e-mail-címe",
                value=default_email,
                key=f"admin_credential_email_{selected_courier_id or selected_user}",
            )
            confirm_send = st.checkbox(
                "Megerősítem a jelenlegi belépési adatok kiküldését.",
                key=f"confirm_credentials_send_{selected_user}",
            )
            send_credentials = st.form_submit_button(
                "Belépési adatok elküldése",
                type="primary",
                disabled=not bool(existing_password),
            )

        if send_credentials:
            if not confirm_send:
                st.error("A kiküldést jóvá kell hagyni.")
            else:
                try:
                    result = send_existing_credentials(
                        selected_data,
                        recipient_email,
                    )
                    st.success(
                        "A jelenlegi belépési adatok elküldve ide: "
                        f"{result['recipient']}"
                    )
                except Exception as exc:
                    st.error(f"A levélküldés sikertelen: {exc}")

        st.divider()

        if st.button("🔑 Jelszó reset"):
            password = reset_password(selected_user)
            st.success(f"Új jelszó: {password}")
            st.info(
                "A reset után az új jelszót külön küldd ki a "
                "„Belépési adatok elküldése” gombbal."
            )

        st.divider()

        delete_confirm = st.checkbox(
            "Megerősítem a felhasználó törlését.",
            key=f"delete_user_confirm_{selected_user}",
        )

        if st.button(
            "🗑️ Felhasználó törlése",
            disabled=not delete_confirm,
        ):
            delete_user(selected_user)
            st.success("Felhasználó törölve")
            st.rerun()
