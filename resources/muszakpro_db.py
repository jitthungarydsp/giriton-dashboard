from datetime import datetime
import random
import re
import string
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from resources.foglalasok_db import (
    clean,
    normalize_email,
    normalize_time,
    read_foglalasok_raw,
    shift_serial,
)
from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


BOOKING_SOURCE_NAME = "muszakpro-python"
CAPACITY_SOURCE_NAME = "google-sheet-beo"
CAPACITY_TABLE = "raw_muszakpro_shift_capacity"
EVENT_TABLE = "ops_muszakpro_events"


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


def is_missing_table_response(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def db_time(value):
    text = normalize_time(value)

    if not text:
        return None

    if len(text) == 4:
        text = f"0{text}"

    if len(text) == 5:
        return f"{text}:00"

    return text


def optional_int(value, default=0):
    text = clean(value)

    if not text:
        return default

    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return default


def shift_start(shift_text):
    text = clean(shift_text)

    if "_" in text:
        text = text.split("_", 1)[1]

    match = re.search(r"(\d{1,2})(?::(\d{2}))?", text)

    if not match:
        return ""

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)

    return f"{hour}:{minute:02d}"


def shift_minutes(shift_text):
    start = shift_start(
        shift_text
    )

    if ":" not in start:
        return None

    try:
        hour, minute = start.split(":", 1)
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def shift_end_minutes(shift_text):
    start = shift_minutes(
        shift_text
    )

    if start is None:
        return None

    text = clean(
        shift_text
    ).upper()

    if "EXP" in text:
        return start + 13 * 60

    return start + 270


def quote_filter(value):
    return quote(
        str(value or ""),
        safe="",
    )


def parse_work_date(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value or "").strip()[:10]


@st.cache_data(show_spinner=False, ttl=300)
def read_shift_capacity(start_date=None, end_date=None, limit=50000):
    supabase_url, headers = get_headers()
    filters = [
        (
            "select=id,source_name,source_row,work_date,shift_text,warehouse,"
            "limit_count,booked_count,active,slack_quota,fetched_at"
        ),
        "order=work_date.asc,warehouse.asc,shift_text.asc",
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
        f"{supabase_url}/rest/v1/{CAPACITY_TABLE}"
        f"?{'&'.join(filters)}"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )

    if is_missing_table_response(response):
        return pd.DataFrame()

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if "active" in df.columns:
        df = df[
            df["active"].fillna(True).astype(bool)
        ]

    return df


def normalize_bookings(bookings):
    if bookings.empty:
        return bookings

    df = bookings.copy()

    if "status" in df.columns:
        df = df[
            df["status"].fillna("ACTIVE").astype(str).str.upper() != "CANCELLED"
        ].copy()

    if "warehouse" not in df.columns:
        df["warehouse"] = ""

    df["warehouse_norm"] = df["warehouse"].fillna("").astype(str).str.strip().str.upper()
    df["shift_norm"] = df["shift_text"].fillna("").astype(str).map(normalize_time)
    df["email_norm"] = df["email"].fillna("").astype(str).map(normalize_email)

    return df


def build_daily_shift_view(work_date, user_email="", warehouse_filter="Mind"):
    work_date_text = parse_work_date(work_date)
    selected_date = datetime.strptime(
        work_date_text,
        "%Y-%m-%d",
    ).date()
    now = datetime.now()
    today = now.date()
    current_minutes = now.hour * 60 + now.minute
    capacity = read_shift_capacity(
        start_date=work_date_text,
        end_date=work_date_text,
    )
    bookings = read_foglalasok_raw(
        start_date=work_date_text,
        end_date=work_date_text,
        limit=50000,
    )
    bookings = normalize_bookings(
        bookings
    )
    user_email_norm = normalize_email(
        user_email
    )

    if capacity.empty:
        return pd.DataFrame()

    rows = []
    filtered_capacity = capacity.copy()
    user_intervals = []

    if user_email_norm and not bookings.empty:
        user_rows = bookings[
            bookings["email_norm"] == user_email_norm
        ]

        for _, booked_row in user_rows.iterrows():
            start_minutes = shift_minutes(
                booked_row.get("shift_text")
            )
            end_minutes = shift_end_minutes(
                booked_row.get("shift_text")
            )

            if start_minutes is not None and end_minutes is not None:
                user_intervals.append(
                    (start_minutes, end_minutes)
                )

    if warehouse_filter and warehouse_filter != "Mind":
        filtered_capacity = filtered_capacity[
            filtered_capacity["warehouse"].fillna("").astype(str).str.upper()
            == str(warehouse_filter).upper()
        ]

    for _, row in filtered_capacity.iterrows():
        shift_text = clean(row.get("shift_text"))
        warehouse = clean(row.get("warehouse")) or "BUD1"
        warehouse_norm = warehouse.upper()
        shift_norm = normalize_time(shift_text)
        shift_bookings = pd.DataFrame()

        if not bookings.empty:
            shift_bookings = bookings[
                (bookings["warehouse_norm"] == warehouse_norm)
                & (bookings["shift_norm"] == shift_norm)
            ]

        booked_count = len(shift_bookings)
        user_booking = pd.DataFrame()

        if user_email_norm and not shift_bookings.empty:
            user_booking = shift_bookings[
                shift_bookings["email_norm"] == user_email_norm
            ]

        limit_count = optional_int(
            row.get("limit_count"),
            0,
        )
        is_mine = not user_booking.empty
        booking_code = ""

        if is_mine and "booking_code" in user_booking.columns:
            booking_code = clean(
                user_booking.iloc[0].get("booking_code")
            )

        start_minutes = shift_minutes(
            shift_text
        )
        end_minutes = shift_end_minutes(
            shift_text
        )
        is_expired = False
        is_urgent = False
        conflict = False

        if selected_date < today:
            is_expired = True
        elif selected_date == today and start_minutes is not None:
            is_expired = current_minutes >= start_minutes
            is_urgent = 0 < (start_minutes - current_minutes) <= 72 * 60

        if not is_mine and start_minutes is not None and end_minutes is not None:
            for own_start, own_end in user_intervals:
                if start_minutes < own_end and end_minutes > own_start:
                    conflict = True
                    break

        rows.append({
            "work_date": work_date_text,
            "shift_text": shift_text,
            "start": shift_start(shift_text),
            "end": _minutes_to_time(end_minutes),
            "warehouse": warehouse,
            "limit_count": limit_count,
            "booked_count": booked_count,
            "free_count": max(limit_count - booked_count, 0),
            "slack_quota": optional_int(row.get("slack_quota"), 0),
            "is_mine": is_mine,
            "is_waiting": booking_code.startswith("TF-"),
            "is_expired": is_expired,
            "is_urgent": is_urgent,
            "conflict": conflict,
            "booking_code": booking_code,
            "status": "Foglalva" if is_mine else ("Betelt" if booked_count >= limit_count else "Szabad"),
        })

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    result["sort_minutes"] = result["start"].map(
        lambda value: _sort_minutes(value)
    )

    return result.sort_values(
        ["warehouse", "sort_minutes", "shift_text"],
        kind="stable",
    ).drop(
        columns=["sort_minutes"],
    )


def _sort_minutes(value):
    text = normalize_time(value)

    if ":" not in text:
        return 99999

    try:
        hour, minute = text.split(":", 1)
        return int(hour) * 60 + int(minute)
    except ValueError:
        return 99999


def _minutes_to_time(value):
    if value is None:
        return ""

    value = int(value) % (24 * 60)
    return f"{value // 60}:{value % 60:02d}"


def generate_booking_code(prefix):
    token = "".join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=5,
        )
    )
    return f"{prefix}-{token}"


def write_event(action_type, payload):
    supabase_url, headers = get_headers()
    endpoint = f"{supabase_url}/rest/v1/{EVENT_TABLE}"
    headers = {
        **headers,
        "Content-Type": "application/json",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=payload | {
            "source_name": BOOKING_SOURCE_NAME,
            "action_type": action_type,
        },
        timeout=30,
    )

    if is_missing_table_response(response):
        return

    raise_for_supabase_error(response)


def upsert_booking_row(row):
    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/raw_muszakpro_bookings"
        "?on_conflict=source_name,work_date,email,shift_text,booking_code"
    )
    headers = {
        **headers,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=[row],
        timeout=30,
    )
    raise_for_supabase_error(response)


def find_active_booking(work_date, email, shift_text, warehouse):
    supabase_url, headers = get_headers()
    filters = [
        "select=id,booking_code,status",
        f"work_date=eq.{parse_work_date(work_date)}",
        f"email=eq.{quote_filter(normalize_email(email))}",
        f"shift_text=eq.{quote_filter(clean(shift_text))}",
        f"warehouse=eq.{quote_filter(clean(warehouse))}",
        "status=neq.CANCELLED",
        "order=created_at.desc",
        "limit=1",
    ]
    endpoint = (
        f"{supabase_url}/rest/v1/raw_muszakpro_bookings"
        f"?{'&'.join(filters)}"
    )
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


def cancel_booking(work_date, email, shift_text, warehouse, actor_email=""):
    existing = find_active_booking(
        work_date,
        email,
        shift_text,
        warehouse,
    )

    if not existing:
        return {
            "ok": False,
            "message": "Nem talaltam aktiv foglalast ehhez a muszakhoz.",
        }

    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/raw_muszakpro_bookings"
        f"?id=eq.{existing['id']}"
    )
    payload = {
        "status": "CANCELLED",
        "event_type": "CANCEL",
        "cancelled_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "cancelled_by": normalize_email(actor_email),
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    response = requests.patch(
        endpoint,
        headers={
            **headers,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    raise_for_supabase_error(response)

    write_event(
        "CANCEL",
        {
            "work_date": parse_work_date(work_date),
            "email": normalize_email(email),
            "shift_text": clean(shift_text),
            "warehouse": clean(warehouse),
            "booking_code": clean(existing.get("booking_code")),
            "actor_email": normalize_email(actor_email),
            "payload": payload,
        },
    )

    return {
        "ok": True,
        "message": "Foglalas torolve.",
    }


def book_shift(work_date, email, shift_text, warehouse, actor_email="", courier=None):
    email_norm = normalize_email(email)

    if not email_norm:
        return {
            "ok": False,
            "message": "Hianyzik a futar e-mail cime.",
        }

    daily = build_daily_shift_view(
        work_date,
        user_email=email_norm,
        warehouse_filter=warehouse,
    )
    target = daily[
        (daily["shift_text"] == clean(shift_text))
        & (daily["warehouse"].str.upper() == clean(warehouse).upper())
    ]

    if target.empty:
        return {
            "ok": False,
            "message": "Ez a muszak nincs megnyitva a kapacitas tablaban.",
        }

    row = target.iloc[0]

    if bool(row.get("is_mine")):
        return {
            "ok": False,
            "message": "Erre a muszakra mar van aktiv foglalas.",
        }

    prefix = "TF" if int(row.get("booked_count") or 0) >= int(row.get("limit_count") or 0) else "OK"
    booking_code = generate_booking_code(
        prefix
    )
    courier = courier or {}
    now_text = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    courier_id = courier.get("courier_id") or courier.get("courierId")
    courier_name = clean(
        courier.get("courier_name")
        or courier.get("name")
        or courier.get("username")
    )
    start = shift_start(
        shift_text
    )

    db_row = {
        "source_name": BOOKING_SOURCE_NAME,
        "timestamp_text": now_text,
        "work_date": parse_work_date(work_date),
        "email": email_norm,
        "shift_text": clean(shift_text),
        "warehouse": clean(warehouse),
        "booking_code": booking_code,
        "admin_recorder": normalize_email(actor_email) if actor_email else "",
        "courier_id": courier_id,
        "courier_name": courier_name,
        "serial": shift_serial(
            parse_work_date(work_date),
            courier_id,
            warehouse,
            start,
        ),
        "status": "ACTIVE",
        "event_type": "BOOK",
        "response_json": {
            "source": "streamlit_muszakpro",
            "actor_email": normalize_email(actor_email),
        },
        "fetched_at": now_text,
        "updated_at": now_text,
    }
    upsert_booking_row(
        db_row
    )
    write_event(
        "BOOK",
        {
            "work_date": parse_work_date(work_date),
            "email": email_norm,
            "shift_text": clean(shift_text),
            "warehouse": clean(warehouse),
            "booking_code": booking_code,
            "actor_email": normalize_email(actor_email),
            "payload": db_row,
        },
    )

    return {
        "ok": True,
        "message": f"Foglalas rogzitve: {booking_code}",
        "booking_code": booking_code,
    }
