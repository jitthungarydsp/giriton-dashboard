import re

import streamlit as st

from resources.courier_master_db import read_courier_master
from resources.courier_db_sheet import read_courier_db_records
from resources.email_sender import send_login_credentials
from resources.users import load_users


st.set_page_config(
    page_title="Jelszó emlékeztető",
    page_icon="🔐",
    layout="centered",
)


def normalize_text(value):
    return str(value or "").strip().casefold()


def normalize_courier_id(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def is_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value or "").strip()))


def record_email(record):
    for key in [
        "email",
        "billing_email",
        "credentialEmail",
        "credential_email",
        "contact_email",
        "mail",
        "e-mail",
    ]:
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""


def user_courier_id(user):
    return normalize_courier_id(
        user.get("courierId")
        or user.get("courier_id")
        or ""
    )


@st.cache_data(show_spinner=False, ttl=300)
def load_user_rows():
    return load_users().get("users", [])


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_rows():
    rows = []
    try:
        courier_master = read_courier_master()
        if courier_master is not None and not courier_master.empty:
            rows.extend(courier_master.to_dict("records"))
    except Exception:
        pass

    try:
        rows.extend(read_courier_db_records())
    except Exception:
        pass

    return rows


def find_user_by_username(username):
    clean_username = normalize_text(username)
    if not clean_username:
        return None

    for user in load_user_rows():
        if normalize_text(user.get("username")) == clean_username:
            return user
    return None


def find_user_by_courier_id(courier_id):
    clean_id = normalize_courier_id(courier_id)
    if not clean_id:
        return None

    for user in load_user_rows():
        if user_courier_id(user) == clean_id:
            return user
    return None


def find_user_by_email(email):
    clean_email = normalize_text(email)
    if not clean_email:
        return None, ""

    for user in load_user_rows():
        user_email = normalize_text(record_email(user))
        if user_email == clean_email:
            return user, record_email(user)

    for courier in load_courier_rows():
        courier_email = normalize_text(record_email(courier))
        if courier_email != clean_email:
            continue

        user = find_user_by_courier_id(courier.get("courier_id"))
        if user:
            return user, record_email(courier)

        courier_name = normalize_text(courier.get("courier_name"))
        if not courier_name:
            courier_name = normalize_text(courier.get("name"))
        for candidate in load_user_rows():
            if normalize_text(candidate.get("username")) == courier_name:
                return candidate, record_email(courier)

    return None, ""


def registered_email_for_user(user):
    courier_id = user_courier_id(user)
    username = normalize_text(user.get("username"))

    for courier in load_courier_rows():
        email = record_email(courier)
        if not email:
            continue

        if courier_id and normalize_courier_id(courier.get("courier_id")) == courier_id:
            return email

        courier_name = normalize_text(courier.get("courier_name") or courier.get("name"))
        if username and courier_name == username:
            return email

    return ""


def resolve_user_and_email(identifier):
    text = str(identifier or "").strip()
    if not text:
        return None, ""

    if is_email(text):
        return find_user_by_email(text)

    user = find_user_by_username(text)
    if not user:
        return None, ""

    return user, registered_email_for_user(user)


st.title("🔐 Jelszó emlékeztető")
st.caption("Add meg a felhasználónevedet vagy a regisztrált e-mail címedet.")

st.info(
    "Ha találunk aktív felhasználót, a belépési adatokat a rendszerben rögzített "
    "saját e-mail címedre küldjük ki."
)

with st.form("password_reminder_form"):
    identifier = st.text_input("Felhasználónév vagy e-mail cím")
    submitted = st.form_submit_button(
        "Belépési adatok elküldése",
        use_container_width=True,
    )


if submitted:
    user, recipient = resolve_user_and_email(identifier)

    if not user:
        st.error("Nem találtam felhasználót ezzel az adattal.")
        st.stop()

    if not bool(user.get("active", True)):
        st.error("Ez a felhasználó jelenleg inaktív.")
        st.stop()

    password = str(user.get("password") or "").strip()
    if not password:
        st.error(
            "Ehhez a felhasználóhoz nincs olvasható jelszó. "
            "A jelszó hash-ből nem visszafejthető, ezért admin jelszóreset szükséges."
        )
        st.stop()

    if not recipient:
        st.error("Nem találtam regisztrált e-mail címet ehhez a felhasználóhoz.")
        st.stop()

    try:
        result = send_login_credentials(
            recipient,
            str(user.get("username") or "").strip(),
            password,
        )
    except Exception as exc:
        st.error(f"Az e-mail küldése sikertelen: {exc}")
        st.stop()

    st.success(
        "Elküldtük a belépési adatokat a regisztrált e-mail címre: "
        f"{result.get('recipient')}"
    )
