import streamlit as st

from resources.courier_master_db import read_courier_master
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


def user_courier_id(user):
    return normalize_courier_id(
        user.get("courierId")
        or user.get("courier_id")
        or ""
    )


def find_user(username):
    clean_username = normalize_text(username)
    if not clean_username:
        return None

    users = load_users().get("users", [])
    for user in users:
        if normalize_text(user.get("username")) == clean_username:
            return user

    return None


@st.cache_data(show_spinner=False, ttl=300)
def courier_email_lookup():
    courier_master = read_courier_master()
    if courier_master is None or courier_master.empty:
        return {}, {}

    by_id = {}
    by_name = {}
    for _, row in courier_master.iterrows():
        row_data = row.to_dict()
        email = str(
            row_data.get("email")
            or row_data.get("billing_email")
            or ""
        ).strip()
        if not email:
            continue

        courier_id = normalize_courier_id(row_data.get("courier_id"))
        courier_name = normalize_text(row_data.get("courier_name"))
        if courier_id:
            by_id[courier_id] = email
        if courier_name:
            by_name[courier_name] = email

    return by_id, by_name


def find_registered_email(user):
    by_id, by_name = courier_email_lookup()
    courier_id = user_courier_id(user)
    if courier_id and by_id.get(courier_id):
        return by_id[courier_id]

    username = normalize_text(user.get("username"))
    return by_name.get(username, "")


st.title("🔐 Jelszó emlékeztető")
st.caption("A rendszer a regisztrált e-mail címre küldi ki a belépési adatokat.")

with st.form("password_reminder_form"):
    username = st.text_input("Felhasználónév")
    submitted = st.form_submit_button(
        "Jelszóemlékeztető küldése e-mailben",
        use_container_width=True,
    )


if submitted:
    user = find_user(username)
    if not user:
        st.error("Nem találtam ilyen felhasználónevet.")
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

    recipient = find_registered_email(user)
    if not recipient:
        st.error(
            "Ehhez a felhasználóhoz nem találtam regisztrált e-mail címet "
            "a courier_master táblában."
        )
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
        "A jelszóemlékeztetőt elküldtük a regisztrált e-mail címre: "
        f"{result.get('recipient')}"
    )

