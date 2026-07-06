import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


DISCORD_ROUTE_COLUMNS = [
    "courier_id",
    "courier_name",
    "route_id",
    "order_id",
    "assigned_at",
    "planned_departure",
    "planned_return",
    "notified_at",
]


@st.cache_data(show_spinner=False, ttl=300)
def read_latest_discord_route(courier_id):
    supabase_url, service_role_key = get_supabase_config()
    courier_id = str(courier_id or "").strip()

    if not supabase_url or not service_role_key or not courier_id:
        return {}

    endpoint = (
        f"{supabase_url}/rest/v1/discord_route_notifications"
        "?select="
        f"{','.join(DISCORD_ROUTE_COLUMNS)}"
        f"&courier_id=eq.{courier_id}"
        "&order=notified_at.desc"
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
        return {}

    return rows[0]


@st.cache_data(show_spinner=False, ttl=300)
def read_discord_routes_for_courier(courier_id, limit=20):
    supabase_url, service_role_key = get_supabase_config()
    courier_id = str(courier_id or "").strip()

    if not supabase_url or not service_role_key or not courier_id:
        return pd.DataFrame(columns=DISCORD_ROUTE_COLUMNS)

    endpoint = (
        f"{supabase_url}/rest/v1/discord_route_notifications"
        "?select="
        f"{','.join(DISCORD_ROUTE_COLUMNS)}"
        f"&courier_id=eq.{courier_id}"
        "&order=notified_at.desc"
        f"&limit={int(limit)}"
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
        return pd.DataFrame(columns=DISCORD_ROUTE_COLUMNS)

    return pd.DataFrame(rows)
