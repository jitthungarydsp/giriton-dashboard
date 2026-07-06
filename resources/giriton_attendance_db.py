from datetime import datetime
import re
from urllib.parse import urlparse

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

    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)

    if hour > 23 or minute > 59 or second > 59:
        return None

    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _supabase_host(supabase_url):
    return urlparse(supabase_url).netloc or supabase_url


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


def _count_stored_rows(supabase_url, service_role_key, work_dates):
    dates = [
        str(date)
        for date in sorted(set(work_dates))
        if str(date).strip()
    ]

    if not dates:
        return 0

    date_filter = ",".join(dates)
    endpoint = (
        f"{supabase_url}/rest/v1/giriton_attendance_raw"
        "?select=id"
        f"&source_name=eq.{SOURCE_NAME}"
        f"&work_date=in.({date_filter})"
        "&limit=10000"
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

    return len(response.json())


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

    work_dates = [
        row.get("work_date")
        for row in db_rows
    ]
    endpoint = (
        f"{supabase_url}/rest/v1/giriton_attendance_raw"
        "?on_conflict=source_name,work_date,courier_name"
    )
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=db_rows,
        timeout=60,
    )
    raise_for_supabase_error(response)

    returned_rows = response.json() if response.text.strip() else []
    stored_rows = _count_stored_rows(
        supabase_url,
        service_role_key,
        work_dates,
    )

    return {
        "rows": len(db_rows),
        "status": "ok",
        "host": _supabase_host(supabase_url),
        "dates": ",".join(sorted(set(work_dates))),
        "returned_rows": len(returned_rows),
        "stored_rows": stored_rows,
    }


def write_giriton_attendance_db(rows):
    result = upsert_giriton_attendance_rows(rows)

    if result.get("status") == "empty":
        raise RuntimeError(
            "Giriton Attendance scraper nem adott vissza sort, ezert nem irtunk DB-be."
        )

    if result.get("status") == "skipped":
        raise RuntimeError(
            "Giriton Attendance DB iras kihagyva: hianyzik a Supabase beallitas."
        )

    message = (
        "OK | Giriton_Attendance DB "
        f"status={result.get('status')} rows={result.get('rows')}"
    )

    if result.get("host"):
        message = f"{message} host={result.get('host')}"

    if result.get("dates"):
        message = f"{message} dates={result.get('dates')}"

    if result.get("returned_rows") is not None:
        message = f"{message} returned_rows={result.get('returned_rows')}"

    if result.get("stored_rows") is not None:
        message = f"{message} stored_rows={result.get('stored_rows')}"

    if result.get("error"):
        message = f"{message} error={result.get('error')}"

    print(message)
    return message


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
