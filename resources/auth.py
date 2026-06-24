import json
import secrets
import streamlit as st

from resources.security import hash_password, verify_password

#from streamlit_cookies_manager import EncryptedCookieManager

COOKIE_NAME = "dsp_token"


def load_users():

    with open(
        "data/users.json",
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def save_users(data):

    with open(
        "data/users.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


def authenticate(
    username,
    password
):

    data = load_users()

    for user in data["users"]:
        if (
            user["username"] != username
            or
            not user.get(
                "active",
                True
            )
        ):
            continue

        password_hash = user.get(
            "passwordHash"
        )

        if password_hash and verify_password(
            password,
            password_hash
        ):

            return user

        if user.get(
            "password"
        ) == password:

            user["passwordHash"] = hash_password(
                password
            )

            user.pop(
                "password",
                None
            )

            save_users(
                data
            )

            return user

    return None


def create_token():

    return secrets.token_hex(
        32
    )


def save_token(
    username
):

    data = load_users()

    token = create_token()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["token"] = token

            break

    save_users(
        data
    )

    return token


def login_by_token(
    token
):

    if not token:
        return None

    data = load_users()

    for user in data["users"]:

        if (
            user.get(
                "token"
            )
            ==
            token
        ):

            return user

    return None


def logout(
    username
):

    data = load_users()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["token"] = ""

    save_users(
        data
    )

def login_screen():

    if "user" in st.session_state:
        return

    st.title("🔐 Bejelentkezés")

    username = st.text_input(
        "Felhasználónév"
    )

    password = st.text_input(
        "Jelszó",
        type="password"
    )

    if st.button("Belépés"):

        user = authenticate(
            username,
            password
        )

        if user:

            st.session_state["user"] = user

            token = save_token(
                username
            )

            st.success(
                "Sikeres belépés"
            )

            st.rerun()

        else:

            st.error(
                "Hibás felhasználónév vagy jelszó"
            )


def logout_button():

    if st.sidebar.button(
        "🚪 Kilépés"
    ):

        logout(
            st.session_state["user"]["username"]
        )

        del st.session_state["user"]

        st.rerun()
