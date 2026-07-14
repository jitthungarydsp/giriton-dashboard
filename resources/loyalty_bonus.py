from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from resources.google_auth import get_client


LOYALTY_EFFECTIVE_FROM = date(2026, 6, 1)
COURIER_SHEETS = [
    ("14H9c5InkUbWlMMkbFVXYQay4UMiYo0opu4wk8rXHWvY", 237983567),
    ("1dHzIpTMwSud2oCXbuLUsUHmCgMwHaa1O75e7kUmLiKo", 2146041807),
]


def _key(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _column(headers, predicates):
    normalized = [_key(value) for value in headers]
    for predicate in predicates:
        for index, value in enumerate(normalized):
            if predicate(value):
                return index
    return None


def _cell(row, index):
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _parse_sheet(spreadsheet_id, worksheet_gid):
    worksheet = get_client().open_by_key(spreadsheet_id).get_worksheet_by_id(worksheet_gid)
    values = worksheet.get_all_values()
    if not values:
        return []
    header_index = next((i for i, row in enumerate(values[:15]) if any(_key(c) == "kezdo idopont" for c in row) and any("nev" in _key(c) for c in row)), 0)
    headers = values[header_index]
    name_index = _column(headers, [
        lambda v: "vezeteknev" in v and "keresztnev" in v and "anyja" not in v,
        lambda v: v in {"nev", "teljes nev", "futar neve"},
        lambda v: "teljes nev" in v,
    ])
    start_index = _column(headers, [lambda v: v == "kezdo idopont", lambda v: v == "idobelyeg"])
    status_index = _column(headers, [lambda v: v == "statusza"])
    trainer1_index = _column(headers, [lambda v: v == "oktato t1"])
    trainer2_index = _column(headers, [lambda v: v == "oktato t2"])
    rows = []
    for row_number, row in enumerate(values[header_index + 1:], start=header_index + 2):
        name = _cell(row, name_index)
        if not name:
            continue
        status = _cell(row, status_index)
        status_key = _key(status)
        if "duplik" in status_key:
            continue
        rows.append({
            "driver_name": name,
            "start_date": pd.to_datetime(_cell(row, start_index), dayfirst=True, errors="coerce"),
            "employment_status": status,
            "is_active": status_index is None or status_key in {"", "aktiv", "active"},
            "is_notice_period": "felmond" in status_key,
            "trainer_t1": _cell(row, trainer1_index),
            "trainer_t2": _cell(row, trainer2_index),
            "source_sheet_id": spreadsheet_id,
            "source_row": row_number,
        })
    return rows


@st.cache_data(show_spinner=False, ttl=900)
def read_loyalty_profiles():
    rows, errors = [], []
    for spreadsheet_id, worksheet_gid in COURIER_SHEETS:
        try:
            rows.extend(_parse_sheet(spreadsheet_id, worksheet_gid))
        except Exception as exc:
            errors.append(f"{spreadsheet_id}: {exc}")
    if not rows:
        if errors:
            raise RuntimeError("; ".join(errors))
        return pd.DataFrame()
    profiles = pd.DataFrame(rows)
    profiles["driver_match_key"] = profiles["driver_name"].map(_key)
    profiles = profiles.sort_values(["driver_match_key", "is_active", "start_date", "source_row"], ascending=[True, False, False, False], kind="stable")
    profiles = profiles.drop_duplicates("driver_match_key", keep="first").reset_index(drop=True)
    profiles.attrs["load_errors"] = errors
    return profiles
