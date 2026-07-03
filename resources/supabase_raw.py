import os

import requests
import streamlit as st


def get_supabase_setting(name):
    if name in st.secrets:
        return st.secrets.get(name)

    return os.getenv(name, "")


def get_supabase_config():
    supabase_url = str(
        get_supabase_setting("SUPABASE_URL") or ""
    ).rstrip("/")
    service_role_key = str(
        get_supabase_setting("SUPABASE_SERVICE_ROLE_KEY") or ""
    )

    if not supabase_url or not service_role_key:
        return "", ""

    return supabase_url, service_role_key


@st.cache_data(show_spinner=False, ttl=300)
def read_driver_detail_raw(limit=5000):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    endpoint = (
        f"{supabase_url}/rest/v1/dsp_driver_detail_raw"
        "?select=driver_id,work_date,response_json,fetched_at"
        "&order=work_date.asc,driver_id.asc"
        f"&limit={int(limit)}"
    )
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    return response.json()


@st.cache_data(show_spinner=False, ttl=300)
def read_vehicle_assignments(limit=5000):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    endpoint = (
        f"{supabase_url}/rest/v1/dsp_vehicle_assignments"
        "?select=work_date,driver_name,shift_start,shift_end,car,license_plate,shift_type,fetched_at"
        "&order=work_date.asc,driver_name.asc,shift_start.asc"
        f"&limit={int(limit)}"
    )
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    return response.json()
