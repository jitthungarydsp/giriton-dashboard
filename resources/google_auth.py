import json
import os


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_SERVICE_ACCOUNT_FILE = r"C:\Giriton\giriton-dashboard\girition-a89bab5e91bc.json"
LOCAL_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "girition-a89bab5e91bc.json",
)


def resolve_service_account_file():
    configured_path = os.getenv("GIRITON_GOOGLE_CREDENTIALS")

    if configured_path:
        return configured_path

    if os.path.exists(DEFAULT_SERVICE_ACCOUNT_FILE):
        return DEFAULT_SERVICE_ACCOUNT_FILE

    if os.path.exists(LOCAL_SERVICE_ACCOUNT_FILE):
        return LOCAL_SERVICE_ACCOUNT_FILE

    return ""


def load_service_account_info():
    env_json = os.getenv("GIRITON_GOOGLE_CREDENTIALS_JSON")

    if env_json:
        data = json.loads(env_json)

        if "private_key" in data:
            data["private_key"] = data["private_key"].replace("\\n", "\n")

        return data

    try:
        import streamlit as st

        if "gcp_service_account" in st.secrets:
            data = dict(st.secrets["gcp_service_account"])

            if "private_key" in data:
                data["private_key"] = data["private_key"].replace("\\n", "\n")

            return data
    except Exception:
        pass

    return None


def get_service_account_email():
    service_account_info = load_service_account_info()

    if service_account_info:
        return service_account_info.get("client_email", "")

    service_account_file = resolve_service_account_file()

    if not service_account_file:
        return ""

    try:
        with open(
            service_account_file,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        return data.get("client_email", "")
    except OSError:
        return ""


def get_client():
    import gspread
    from google.oauth2.service_account import Credentials

    service_account_info = load_service_account_info()

    if service_account_info:
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
    else:
        service_account_file = resolve_service_account_file()

        if not service_account_file:
            raise FileNotFoundError(
                "Google service account nincs beállítva. "
                "Streamlit Cloudon add meg a gcp_service_account secretet."
            )

        creds = Credentials.from_service_account_file(
            service_account_file,
            scopes=SCOPES,
        )

    return gspread.authorize(creds)
