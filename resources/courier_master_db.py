import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?select=courier_id,courier_name,phone_number,email,warehouse_name,active,fetched_at,updated_at"
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
