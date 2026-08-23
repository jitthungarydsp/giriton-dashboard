from datetime import datetime
import re
from zoneinfo import ZoneInfo

import requests

from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
TABLE_NAME = "ops_shift_comparison"
NEXT_5_DAY_VIEW_NAME = "vw_courier_next_5_day_shifts"


def clean(value):
    return str(value or "").strip()


def db_time(value):
    text = clean(value)

    if not text:
        return None

    match = re.search(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\b", text)

    if not match:
        return None

    text = f"{match.group(1)}:{match.group(2)}"
    parts = text.split(":")

    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
        except ValueError:
            return text

    return text


def optional_int(value):
    text = clean(value)

    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def get_headers():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    return supabase_url, {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def build_db_rows(records):
    updated_at = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat(timespec="seconds")
    rows = []

    for record in records:
        comparison_key = clean(
            record.get("match_key")
        )

        if not comparison_key:
            continue

        work_date = clean(
            record.get("work_date")
        )

        if not work_date:
            continue

        row = {
            "comparison_key": comparison_key,
            "work_date": work_date,
            "courier_id": optional_int(record.get("courier_id")),
            "courier_name": clean(record.get("name")),
            "email": clean(record.get("email")).casefold(),
            "warehouse": clean(record.get("warehouse")),
            "shift_start": db_time(record.get("start")),
            "shift_end": db_time(record.get("end")),
            "giriton_status": clean(record.get("giriton")) or "-",
            "muszakpro_status": clean(record.get("muszakpro")) or "-",
            "missing_source": clean(record.get("missing")),
            "giriton_check": clean(record.get("giriton_check")),
            "muszakpro_booking_code": clean(record.get("muszakpro_code")),
            "source_summary": {
                "giriton": clean(record.get("giriton")) or "-",
                "muszakpro": clean(record.get("muszakpro")) or "-",
                "missing": clean(record.get("missing")),
                "giriton_check": clean(record.get("giriton_check")),
                "muszakpro_code": clean(record.get("muszakpro_code")),
            },
            "updated_at": updated_at,
        }
        rows.append(row)

    return rows


def upsert_shift_comparison_rows(records):
    db_rows = build_db_rows(
        records
    )

    if not db_rows:
        return {
            "rows": 0,
            "status": "empty",
        }

    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/{TABLE_NAME}"
        "?on_conflict=comparison_key"
    )
    headers = {
        **headers,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    for index in range(0, len(db_rows), 500):
        response = requests.post(
            endpoint,
            headers=headers,
            json=db_rows[index:index + 500],
            timeout=60,
        )
        raise_for_supabase_error(response)

    return {
        "rows": len(db_rows),
        "status": "ok",
    }


def delete_shift_comparison_range(start_date, end_date):
    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/{TABLE_NAME}"
        f"?work_date=gte.{start_date}&work_date=lte.{end_date}"
    )
    headers = {
        **headers,
        "Prefer": "return=minimal",
    }
    response = requests.delete(
        endpoint,
        headers=headers,
        timeout=60,
    )
    raise_for_supabase_error(response)

    return {
        "status": "ok",
        "start_date": str(start_date),
        "end_date": str(end_date),
    }


def read_shift_comparison_records(start_date=None, end_date=None, courier_id=None, limit=5000):
    supabase_url, headers = get_headers()
    filters = [
        (
            "select=work_date,courier_id,courier_name,email,warehouse,"
            "shift_start,shift_end,giriton_status,muszakpro_status,"
            "missing_source,giriton_check,muszakpro_booking_code,updated_at"
        ),
        "order=work_date.asc,shift_start.asc,courier_name.asc",
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

    if courier_id not in [None, ""]:
        filters.append(
            f"courier_id=eq.{int(courier_id)}"
        )

    endpoint = (
        f"{supabase_url}/rest/v1/{TABLE_NAME}"
        f"?{'&'.join(filters)}"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    raise_for_supabase_error(response)

    return response.json()


def read_next_5_day_shift_comparison(courier_id=None, limit=500):
    supabase_url, headers = get_headers()
    filters = [
        (
            "select=work_date,courier_id,courier_name,email,warehouse,"
            "shift_start,shift_end,giriton_status,muszakpro_status,"
            "missing_source,giriton_check,muszakpro_booking_code,updated_at"
        ),
        "order=work_date.asc,shift_start.asc,courier_name.asc",
        f"limit={int(limit)}",
    ]

    if courier_id not in [None, ""]:
        filters.append(
            f"courier_id=eq.{int(courier_id)}"
        )

    endpoint = (
        f"{supabase_url}/rest/v1/{NEXT_5_DAY_VIEW_NAME}"
        f"?{'&'.join(filters)}"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    raise_for_supabase_error(response)

    return response.json()
