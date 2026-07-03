import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


NUMERIC_COLUMNS = [
    "delivered_orders",
    "total_orders",
    "routes",
    "worked_days",
    "avg_orders_per_route",
    "avg_routes_per_workday",
    "avg_wait_minutes",
    "late_shift_count",
    "planned_shift_count",
    "avg_route_minutes",
    "avg_loading_minutes",
    "avg_planned_loading_minutes",
    "avg_real_loading_minutes",
    "total_address_count",
    "early_address_count",
    "late_address_count",
    "early_address_rate",
    "late_address_rate",
    "normal_address_count",
    "express_address_count",
    "normal_address_rate",
    "express_address_rate",
    "normal_early_address_count",
    "normal_late_address_count",
    "express_early_address_count",
    "express_late_address_count",
    "normal_late_address_rate",
    "express_late_address_rate",
    "normal_routes",
    "express_routes",
    "estimated_max_revenue",
    "avg_revenue_per_route",
    "previous_month_revenue",
]


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_card_stats(snapshot_month):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_card_stats"
        "?select=*"
        f"&snapshot_month=eq.{snapshot_month}"
        "&order=name.asc,courier_id.asc"
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

    df = pd.DataFrame(rows)

    for column in NUMERIC_COLUMNS:
        if column not in df.columns:
            df[column] = 0

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    return df
