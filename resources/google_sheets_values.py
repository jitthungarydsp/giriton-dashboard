from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from resources.google_auth import SCOPES, load_service_account_info, resolve_service_account_file


SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def sheets_session() -> AuthorizedSession:
    service_account_info = load_service_account_info()
    if service_account_info:
        credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    else:
        service_account_file = resolve_service_account_file()
        if not service_account_file:
            raise FileNotFoundError("Google service account nincs beállítva.")
        credentials = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
    return AuthorizedSession(credentials)


def values_url(spreadsheet_id: str, range_name: str, suffix: str = "") -> str:
    return f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{quote(range_name, safe='')}{suffix}"


def spreadsheet_url(spreadsheet_id: str, suffix: str) -> str:
    return f"{SHEETS_API_BASE}/{spreadsheet_id}{suffix}"


def raise_for_google_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {response.text[:1000]}")


def replace_sheet_values_by_id(spreadsheet_id: str, sheet_id: int, values: list[list[Any]]) -> None:
    session = sheets_session()
    row_count = max(len(values), 1)
    column_count = max((len(row) for row in values), default=1)
    clear_response = session.post(
        spreadsheet_url(spreadsheet_id, "/values:batchClearByDataFilter"),
        json={"dataFilters": [{"gridRange": {"sheetId": int(sheet_id)}}]},
        timeout=60,
    )
    raise_for_google_response(clear_response, "Google Sheets batch clear")

    update_response = session.post(
        spreadsheet_url(spreadsheet_id, "/values:batchUpdateByDataFilter"),
        json={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "dataFilter": {
                        "gridRange": {
                            "sheetId": int(sheet_id),
                            "startRowIndex": 0,
                            "startColumnIndex": 0,
                            "endRowIndex": row_count,
                            "endColumnIndex": column_count,
                        }
                    },
                    "majorDimension": "ROWS",
                    "values": values,
                }
            ],
        },
        timeout=120,
    )
    raise_for_google_response(update_response, "Google Sheets batch update")


def append_values(spreadsheet_id: str, range_name: str, values: list[list[Any]], batch_size: int = 500) -> int:
    session = sheets_session()
    written = 0
    chunk_size = max(int(batch_size), 1)
    for start in range(0, len(values), chunk_size):
        batch = values[start:start + chunk_size]
        response = session.post(
            values_url(spreadsheet_id, range_name, ":append"),
            params={
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
            },
            json={"values": batch},
            timeout=60,
        )
        raise_for_google_response(response, "Google Sheets append")
        written += len(batch)
    return written
