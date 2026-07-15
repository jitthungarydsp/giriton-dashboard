import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


SELECT_FIELDS = (
    "courier_id,courier_name,phone_number,email,warehouse_name,"
    "company_name,company_address,tax_number,"
    "bank_account_number,billing_email,"
    "active,fetched_at,updated_at"
)


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        f"?select={SELECT_FIELDS}"
        "&order=courier_name.asc,courier_id.asc"
        "&limit=5000"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=30,
    )

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master_by_id(courier_id):
    supabase_url, service_role_key = get_supabase_config()
    courier_id = str(courier_id or "").strip()

    if not supabase_url or not service_role_key or not courier_id:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        f"?select={SELECT_FIELDS}"
        f"&courier_id=eq.{courier_id}"
        "&limit=1"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=30,
    )

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)