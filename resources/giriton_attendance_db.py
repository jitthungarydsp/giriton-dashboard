from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


SOURCE_NAME = "giriton-attendance-robot"


def _clean(value):
    return str(value or "").strip()


def _normalize_time(value):
    text = _clean(value)

    if not text:
        return None

    if len(text) == 5:
        return f"{text}:00"

    return text


def _build_db_rows(rows):
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    db_rows = []

    for row in rows or []:
        values = list(row) + [""] * 7
        work_date = _clean(values[0])
        courier_name = _clean(values[1])

        if not work_date or not courier_name:
            continue

        db_rows.append({
            "source_name": SOURCE_NAME,
            "work_date": work_date,
            "courier_name": courier_name,
            "shift_text": _clean(values[2]),
            "activity_status": _clean(values[3]),
            "checkin_start": _normalize_time(values[4]),
            "checkin_end": _normalize_time(values[5]),
            "raw_details": _clean(values[6]),
            "response_json": {
                "work_date": work_date,
                "courier_name": courier_name,
                "shift": _clean(values[2]),
                "activity": _clean(values[3]),
                "checkin_start": _clean(values[4]),
                "checkin_end": _clean(values[5]),
                "raw_details": _clean(values[6]),
            },
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
        })

    return db_rows


def upsert_giriton_attendance_rows(rows):
    db_rows = _build_db_rows(rows)

    if not db_rows:
        return {
            "rows": 0,
            "status": "empty",
        }

    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return {
            "rows": len(db_rows),
            "status": "skipped",
            "error": "missing_supabase_config",
        }

    endpoint = (
        f"{supabase_url}/rest/v1/giriton_attendance_raw"
        "?on_conflict=source_name,work_date,courier_name"
    )
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=db_rows,
        timeout=60,
    )
    raise_for_supabase_error(response)

    return {
        "rows": len(db_rows),
        "status": "ok",
    }


@st.cache_data(show_spinner=False, ttl=300)
def read_giriton_attendance_raw(start_date=None, end_date=None, limit=5000):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    filters = [
        (
            "select=work_date,courier_name,shift_text,activity_status,"
            "checkin_start,checkin_end,raw_details,fetched_at,updated_at"
        ),
        "order=work_date.desc,courier_name.asc",
        f"limit={int(limit)}",
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
        f"{supabase_url}/rest/v1/giriton_attendance_raw"
        f"?{'&'.join(filters)}"
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
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
