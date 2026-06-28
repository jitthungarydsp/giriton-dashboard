import json
import os

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LOCAL_SERVICE_ACCOUNT_FILE = "girition-a89bab5e91bc.json"
WINDOWS_SERVICE_ACCOUNT_FILE = r"C:\Giriton\giriton-dashboard\girition-a89bab5e91bc.json"


def _load_service_account_info():
    env_json = os.getenv("GIRITON_GOOGLE_CREDENTIALS_JSON")

    if env_json:
        data = json.loads(env_json)
        data["private_key"] = data["private_key"].replace("\\n", "\n")
        return data

    configured_path = os.getenv("GIRITON_GOOGLE_CREDENTIALS")

    for path in [
        configured_path,
        LOCAL_SERVICE_ACCOUNT_FILE,
        WINDOWS_SERVICE_ACCOUNT_FILE,
    ]:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    raise FileNotFoundError(
        "Google service account nincs beállítva. "
        "GitHub Actionsben add meg a GIRITON_GOOGLE_CREDENTIALS_JSON secretet."
    )


def open_spreadsheet(spreadsheet_id):
    creds = Credentials.from_service_account_info(
        _load_service_account_info(),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)

    return client.open_by_key(spreadsheet_id)
