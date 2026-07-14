import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


PERFORMANCE_TABLE = "stg_jitt_invoice_performance_couriers"
PERFORMANCE_COLUMNS = [
    "warehouse_id",
    "warehouse_code",
    "date_from",
    "date_to",
    "courier_id",
    "courier_name",
    "shifts",
    "orders",
    "delayed",
    "delay_percent",
    "late_percent",
    "no_show_percent",
    "compliance_bad_percent",
    "compliance_score_percent",
    "delay_level",
    "compliance_level",
]


def format_date_filter(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value or "")


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_hub_performance_rows(start_date, end_date, courier_id="", warehouse=""):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    warehouse_id = {
        "BUD1": "1",
        "BUD2": "2",
    }.get(str(warehouse or "").strip().upper())

    params = {
        "select": ",".join(PERFORMANCE_COLUMNS),
        "date_from": f"lte.{format_date_filter(end_date)}",
        "date_to": f"gte.{format_date_filter(start_date)}",
        "order": "date_from.asc,warehouse_id.asc,courier_id.asc",
        "limit": "1000",
    }

    courier_id = str(courier_id or "").strip()
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"

    if warehouse_id:
        params["warehouse_id"] = f"eq.{warehouse_id}"

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    response = requests.get(
        f"{supabase_url}/rest/v1/{PERFORMANCE_TABLE}",
        headers=headers,
        params=params,
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def summarize_courier_hub_performance(performance_df):
    if performance_df.empty:
        return {}

    df = performance_df.copy()

    for column in [
        "shifts",
        "orders",
        "delayed",
        "delay_percent",
        "late_percent",
        "no_show_percent",
        "compliance_bad_percent",
        "compliance_score_percent",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    shifts = int(df.get("shifts", pd.Series(dtype=float)).fillna(0).sum())
    orders = int(df.get("orders", pd.Series(dtype=float)).fillna(0).sum())
    delayed = int(df.get("delayed", pd.Series(dtype=float)).fillna(0).sum())
    delay_percent = (delayed / orders * 100) if orders else 0

    def weighted_percent(column, weight_column):
        if column not in df.columns or weight_column not in df.columns:
            return 0

        valid = df[[column, weight_column]].dropna()

        if valid.empty or valid[weight_column].sum() == 0:
            return 0

        return (
            valid[column].mul(valid[weight_column]).sum()
            / valid[weight_column].sum()
        )

    late_percent = weighted_percent("late_percent", "shifts")
    no_show_percent = weighted_percent("no_show_percent", "shifts")
    compliance_bad_percent = (0.7 * no_show_percent) + (0.3 * late_percent)

    return {
        "shifts": shifts,
        "orders": orders,
        "delayed": delayed,
        "delay_percent": delay_percent,
        "late_percent": late_percent,
        "no_show_percent": no_show_percent,
        "compliance_bad_percent": compliance_bad_percent,
        "compliance_score_percent": 100 - compliance_bad_percent,
    }
