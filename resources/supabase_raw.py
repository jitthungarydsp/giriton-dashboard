import os

import requests
import streamlit as st


def raise_for_supabase_error(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()

        if detail:
            raise requests.HTTPError(
                f"{exc}; Supabase valasz: {detail[:1000]}",
                response=response,
            ) from exc

        raise


def get_supabase_setting(name):
    try:
        if name in st.secrets:
            return st.secrets.get(name)
    except Exception:
        pass

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


def format_date_filter(value):
    if not value:
        return ""

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


@st.cache_data(show_spinner=False, ttl=300)
def read_driver_detail_raw(start_date=None, end_date=None, limit=10000, page_size=250):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    filters = [
        "select=driver_id,work_date,response_json,fetched_at",
        "order=work_date.asc,driver_id.asc",
    ]
    start_date_text = format_date_filter(start_date)
    end_date_text = format_date_filter(end_date)

    if start_date_text:
        filters.append(
            f"work_date=gte.{start_date_text}"
        )

    if end_date_text:
        filters.append(
            f"work_date=lte.{end_date_text}"
        )

    endpoint = (
        f"{supabase_url}/rest/v1/dsp_driver_detail_raw"
        f"?{'&'.join(filters)}"
    )
    rows = []
    total_limit = int(limit)
    chunk_size = max(
        min(int(page_size), 1000),
        1,
    )

    while len(rows) < total_limit:
        range_start = len(rows)
        range_end = min(
            range_start + chunk_size - 1,
            total_limit - 1,
        )
        headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Range-Unit": "items",
            "Range": f"{range_start}-{range_end}",
        }

        response = requests.get(
            endpoint,
            headers=headers,
            timeout=60,
        )
        raise_for_supabase_error(response)

        chunk = response.json()

        if not chunk:
            break

        rows.extend(
            chunk
        )

        if len(chunk) < (range_end - range_start + 1):
            break

    return rows


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
    raise_for_supabase_error(response)

    return response.json()
