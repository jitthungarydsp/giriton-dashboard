from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


TABLE_NAME = "ops_shift_start_parameters"


def clean(value) -> str:
    return str(value or "").strip()


def _headers():
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )
    return supabase_url, {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def _is_missing_table(response) -> bool:
    if response.status_code not in (400, 404):
        return False
    text = response.text.lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


@st.cache_data(show_spinner=False, ttl=300)
def read_shift_start_parameters(active_only: bool = True) -> pd.DataFrame:
    supabase_url, headers = _headers()
    params = {
        "select": (
            "warehouse,shift_code,shift_kind,route_count,start_time,end_time,"
            "paid_duration,break_duration,is_active"
        ),
        "order": "warehouse.asc,start_time.asc,shift_code.asc",
        "limit": "10000",
    }
    if active_only:
        params["is_active"] = "eq.true"

    response = requests.get(
        f"{supabase_url}/rest/v1/{TABLE_NAME}",
        headers=headers,
        params=params,
        timeout=60,
    )
    if _is_missing_table(response):
        return pd.DataFrame()

    raise_for_supabase_error(response)
    rows = response.json()
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
