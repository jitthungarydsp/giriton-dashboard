import json
import base64
import hashlib
import hmac
import secrets
import time
import streamlit as st

from resources.security import hash_password, verify_password

#from streamlit_cookies_manager import EncryptedCookieManager

COOKIE_NAME = "dsp_token"
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


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


def _token_secret(user):
    password_hash = str(user.get("passwordHash") or user.get("password") or "")

    try:
        app_secret = st.secrets.get("AUTH_TOKEN_SECRET", "")
    except Exception:
        app_secret = ""

    return f"{password_hash}|{app_secret}".encode("utf-8")


def _sign_token_payload(payload, user):
    return hmac.new(
        _token_secret(user),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_token(payload, signature):
    raw = f"{payload}.{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_token(token):
    try:
        raw = base64.urlsafe_b64decode(
            str(token).encode("ascii")
        ).decode("utf-8")
        payload, signature = raw.rsplit(".", 1)
        return payload, signature
    except Exception:
        return "", ""


def save_token(username):
    data = load_users()

    for user in data["users"]:
        if user["username"] == username:
            payload = f"{username}|{int(time.time())}"
            signature = _sign_token_payload(payload, user)
            return _encode_token(payload, signature)

    return ""


def login_by_token(
    token
):

    if not token:
        return None

    payload, signature = _decode_token(token)
    data = load_users()

    if payload and signature:
        try:
            username, issued_at = payload.rsplit("|", 1)
            issued_at = int(issued_at)
        except ValueError:
            return None

        if time.time() - issued_at > TOKEN_TTL_SECONDS:
            return None

        for user in data["users"]:
            if (
                user["username"] == username
                and user.get("active", True)
            ):
                expected = _sign_token_payload(payload, user)

                if hmac.compare_digest(expected, signature):
                    return user

        return None

    for user in data["users"]:
        if (
            user.get("token") == token
            and user.get("active", True)
        ):
            return user

    return None


def logout(
    username
):
    return None

def login_screen():

    if "user" in st.session_state:
        return

    token = st.query_params.get(
        COOKIE_NAME,
        ""
    )
    token_user = login_by_token(
        token
    )

    if token_user:
        st.session_state["user"] = token_user
        st.rerun()

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

            st.query_params[COOKIE_NAME] = token

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

        if COOKIE_NAME in st.query_params:
            del st.query_params[COOKIE_NAME]

        st.rerun()
