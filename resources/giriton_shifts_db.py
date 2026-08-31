import os
from datetime import datetime
import re
import unicodedata

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


SOURCE_NAME = "giriton-shifts-robot"
MIN_ROWS_PER_WORK_DATE = 80


def clean(value):
    return str(value or "").strip()


def clean_courier_name(value):
    text = clean(value)
    if not text:
        return ""
    text = re.sub(r"^\s*Subscribed users\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*Applicants\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def normalize_name(value):
    text = unicodedata.normalize("NFKD", clean_courier_name(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def courier_id_from_text(value):
    match = re.search(r"\b(\d{4,5})\b", clean_courier_name(value))
    return match.group(1) if match else ""


def name_without_courier_id(value):
    return normalize_name(
        re.sub(r"\b\d{4,5}\b", " ", clean(value))
    )


def courier_name_pattern(value):
    tokens = name_without_courier_id(value).split()
    if len(tokens) < 2:
        return ""
    separator = r"(?:\s+\d{4,5})?\s+"
    return r"\b" + separator.join(re.escape(token) for token in tokens) + r"\b"


def lookup_courier_names(courier_lookup):
    names = set()
    for courier in (courier_lookup or {}).values():
        name = clean(courier.get("name"))
        if name and len(name_without_courier_id(name).split()) >= 2:
            names.add(name)
    return sorted(names, key=lambda name: len(name_without_courier_id(name)), reverse=True)


def split_courier_names_by_lookup(value, courier_lookup):
    text = clean_courier_name(value)
    normalized_text = normalize_name(text)
    if not normalized_text or not courier_lookup:
        return []

    matches = []
    seen = set()
    for courier_name in lookup_courier_names(courier_lookup):
        pattern = courier_name_pattern(courier_name)
        if not pattern:
            continue
        for match in re.finditer(pattern, normalized_text):
            match_key = (match.start(), match.end(), courier_name)
            if match_key in seen:
                continue
            seen.add(match_key)
            matches.append((match.start(), match.end(), courier_name))

    if len(matches) < 2:
        return []

    selected = []
    occupied = []
    for start, end, courier_name in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied):
            continue
        selected.append((start, end, courier_name))
        occupied.append((start, end))

    selected = sorted(selected)
    if len(selected) < 2:
        return []

    return [courier_name for _start, _end, courier_name in selected]


def split_courier_names(value, courier_lookup=None):
    text = clean_courier_name(value)
    if not text:
        return []
    text = re.sub(r"^\s*Subscribed users\s*:\s*", "", text, flags=re.IGNORECASE)
    parts = [
        part.strip()
        for part in re.split(r"\s*[,;|]\s*", text)
        if part.strip()
    ]
    if len(parts) == 1:
        lookup_parts = split_courier_names_by_lookup(parts[0], courier_lookup)
        if lookup_parts:
            return lookup_parts
    return parts or [text]


def is_empty_name(value):
    return normalize_name(value) in {"", "ures", "üres", "Ăśres", "(none)"}


def normalize_time(value):
    text = clean(value)

    if not text:
        return ""

    parts = text.split(":")

    if len(parts) >= 2:
        try:
            return f"{int(parts[0])}:{int(parts[1]):02d}"
        except ValueError:
            return text

    return text


def db_time(value):
    text = normalize_time(value)

    if not text:
        return None

    if len(text) == 4:
        text = f"0{text}"

    if len(text) == 5:
        return f"{text}:00"

    return text


def optional_int(value):
    text = clean(value)

    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def month_day(work_date):
    text = clean(work_date)

    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%m/%d")
    except ValueError:
        if len(text) >= 10:
            return f"{text[5:7]}/{text[8:10]}"

    return text


def shift_serial(work_date, courier_id, warehouse, start):
    if courier_id in [None, ""]:
        return ""

    return "_".join([
        month_day(work_date),
        str(courier_id).strip(),
        clean(warehouse),
        normalize_time(start),
    ])


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


def read_courier_lookup():
    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?select=courier_id,courier_name,email"
        "&limit=5000"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    raise_for_supabase_error(response)
    lookup = {}

    for row in response.json():
        name = normalize_name(row.get("courier_name"))
        courier_id = clean(row.get("courier_id"))
        courier = {
            "courier_id": row.get("courier_id"),
            "email": clean(row.get("email")).casefold(),
            "name": clean(row.get("courier_name")),
        }

        if name:
            lookup[name] = courier
        clean_name_without_id = name_without_courier_id(row.get("courier_name"))
        if clean_name_without_id:
            lookup[clean_name_without_id] = courier
        if courier_id:
            lookup[f"id:{courier_id}"] = courier

    return lookup


def find_courier(courier_name, courier_lookup):
    courier_id = courier_id_from_text(courier_name)
    if courier_id:
        driver = courier_lookup.get(f"id:{courier_id}")
        if driver:
            return driver

    for key in {
        normalize_name(courier_name),
        name_without_courier_id(courier_name),
    }:
        if key and key in courier_lookup:
            return courier_lookup[key]

    return {}


def build_db_rows(rows, courier_lookup=None):
    if courier_lookup is None:
        try:
            courier_lookup = read_courier_lookup()
        except Exception:
            courier_lookup = {}

    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    db_rows = []

    for row in rows or []:
        values = list(row) + [""] * 12
        work_date = clean(values[0])
        start = normalize_time(values[1])
        end = normalize_time(values[2])
        warehouse = clean(values[3])
        occupancy = clean(values[4])

        if len(row) >= 12:
            booked = clean(values[5])
            maximum = clean(values[6])
            courier_name = clean(values[7])
            enriched_email = clean(values[8]).casefold()
            enriched_serial = clean(values[9])
            enriched_status = clean(values[10])
            enriched_courier_id = clean(values[11])
        elif len(row) >= 8:
            booked = clean(values[5])
            maximum = clean(values[6])
            courier_name = clean(values[7])
            enriched_email = ""
            enriched_serial = ""
            enriched_status = ""
            enriched_courier_id = ""
        else:
            booked = ""
            maximum = ""
            courier_name = clean(values[5])
            enriched_email = ""
            enriched_serial = ""
            enriched_status = ""
            enriched_courier_id = ""

        if not work_date or not start or not courier_name:
            continue

        if is_empty_name(courier_name):
            courier_names = ["URES"]
        else:
            courier_names = split_courier_names(courier_name, courier_lookup)

        for current_courier_name in courier_names:
            if is_empty_name(current_courier_name):
                current_courier_name = "URES"
                driver = {}
                status = "URES"
            else:
                driver = find_courier(
                    current_courier_name,
                    courier_lookup,
                )
                status = "GIRITON_OK"

            courier_id = (
                enriched_courier_id
                or courier_id_from_text(current_courier_name)
                or driver.get("courier_id")
            )
            email = enriched_email or driver.get("email", "")
            serial = enriched_serial or shift_serial(
                work_date,
                courier_id,
                warehouse,
                start,
            )
            status = enriched_status or status
            response_json = {
                "work_date": work_date,
                "start": start,
                "end": end,
                "warehouse": warehouse,
                "occupancy": occupancy,
                "booked": booked,
                "maximum": maximum,
                "courier_name": current_courier_name,
                "source_courier_name": courier_name,
                "email": email,
                "courier_id": courier_id,
                "serial": serial,
                "status": status,
            }

            db_rows.append({
                "source_name": SOURCE_NAME,
                "work_date": work_date,
                "start_time": db_time(start),
                "end_time": db_time(end),
                "warehouse": warehouse,
                "occupancy": occupancy,
                "booked": optional_int(booked),
                "maximum": optional_int(maximum),
                "courier_name": current_courier_name,
                "email": email,
                "courier_id": optional_int(courier_id),
                "serial": serial,
                "status": status,
                "response_json": response_json,
                "fetched_at": fetched_at,
                "updated_at": fetched_at,
            })

    return db_rows


def delete_existing_shift_dates(db_rows):
    work_dates = sorted(
        {
            clean(row.get("work_date"))
            for row in db_rows or []
            if clean(row.get("work_date"))
        }
    )
    if not work_dates:
        return {
            "rows": 0,
            "status": "empty",
        }

    supabase_url, headers = get_headers()
    headers = {
        **headers,
        "Prefer": "return=minimal",
    }

    deleted_dates = 0
    for work_date in work_dates:
        endpoint = (
            f"{supabase_url}/rest/v1/giriton_shifts_raw"
            f"?source_name=eq.{SOURCE_NAME}"
            f"&work_date=eq.{work_date}"
        )
        response = requests.delete(
            endpoint,
            headers=headers,
            timeout=60,
        )
        raise_for_supabase_error(response)
        deleted_dates += 1

    return {
        "rows": deleted_dates,
        "status": "ok",
        "dates": work_dates,
    }


def min_rows_per_work_date():
    value = clean(os.getenv("GIRITON_RAW_MIN_ROWS_PER_DAY"))
    if not value:
        return MIN_ROWS_PER_WORK_DATE
    try:
        return max(int(value), 0)
    except ValueError:
        return MIN_ROWS_PER_WORK_DATE


def validate_complete_shift_export(db_rows):
    minimum_rows = min_rows_per_work_date()
    if minimum_rows <= 0:
        return

    counts = {}
    for row in db_rows:
        work_date = clean(row.get("work_date"))
        if work_date:
            counts[work_date] = counts.get(work_date, 0) + 1

    incomplete = {
        work_date: count
        for work_date, count in counts.items()
        if count < minimum_rows
    }
    if not incomplete:
        return

    details = ", ".join(
        f"{work_date}: {count} sor"
        for work_date, count in sorted(incomplete.items())
    )
    raise RuntimeError(
        "GIRITON_RAW_EXPORT_INCOMPLETE_DAY "
        f"minimum={minimum_rows} "
        f"found={details}. "
        "A DB frissítés leállt, hogy a részleges Giriton lista ne írja felül a jó adatokat."
    )


def upsert_giriton_shift_rows(rows):
    db_rows = build_db_rows(rows)

    if not db_rows:
        return {
            "rows": 0,
            "status": "empty",
        }

    validate_complete_shift_export(db_rows)

    supabase_url, headers = get_headers()
    delete_result = delete_existing_shift_dates(db_rows)
    endpoint = (
        f"{supabase_url}/rest/v1/giriton_shifts_raw"
        "?on_conflict=source_name,work_date,warehouse,start_time,courier_name"
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
        "replaced_dates": delete_result.get("rows", 0),
    }


@st.cache_data(show_spinner=False, ttl=300)
def read_giriton_shifts_raw(start_date=None, end_date=None, limit=5000):
    supabase_url, headers = get_headers()
    filters = [
        (
            "select=work_date,start_time,end_time,warehouse,occupancy,booked,"
            "maximum,courier_name,email,courier_id,serial,status,fetched_at"
        ),
        "order=work_date.desc,start_time.asc,courier_name.asc",
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
        f"{supabase_url}/rest/v1/giriton_shifts_raw"
        f"?{'&'.join(filters)}"
    )
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


def read_giriton_shift_records(work_date):
    df = read_giriton_shifts_raw(
        start_date=work_date,
        end_date=work_date,
        limit=10000,
    )

    if df.empty:
        return []

    records = []

    for _, row in df.iterrows():
        if clean(row.get("status")).upper() == "URES":
            continue

        courier_id = clean(row.get("courier_id"))
        courier_name = clean(row.get("courier_name"))
        email = clean(row.get("email")).casefold()
        serial = clean(row.get("serial")) or shift_serial(
            row.get("work_date"),
            courier_id,
            row.get("warehouse"),
            row.get("start_time"),
        )

        if not serial and not (courier_id or email or courier_name):
            continue

        records.append({
            "serial": serial,
            "work_date": clean(row.get("work_date")),
            "courier_id": courier_id,
            "name": courier_name,
            "email": email,
            "warehouse": clean(row.get("warehouse")),
            "start": normalize_time(row.get("start_time")),
            "end": normalize_time(row.get("end_time")),
        })

    return records
