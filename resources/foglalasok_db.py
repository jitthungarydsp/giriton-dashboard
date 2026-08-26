from datetime import datetime
import re
import unicodedata

import pandas as pd
import requests
import streamlit as st

from resources.source_sheet_sync import SOURCE_SPREADSHEET_ID
from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


SOURCE_NAME = "google-sheet-foglalasok"
FOGLALASOK_SHEET_NAME = "Foglalasok"
FOGLALASOK_TABLE_CANDIDATES = [
    "raw_muszakpro_bookings",
    "foglalasok_raw",
]


def clean(value):
    return str(value or "").strip()


def normalize_header(value):
    text = clean(value).casefold()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_email(value):
    return clean(value).casefold()


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


def looks_like_date(value):
    text = clean(value)
    if not text:
        return False
    try:
        datetime.strptime(text[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def looks_like_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean(value)))


def shift_start(shift_text):
    text = clean(shift_text)

    match = re.search(r"(\d{1,2}:\d{2})", text)

    if match:
        return normalize_time(match.group(1))

    return ""


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


def resolve_foglalasok_table(supabase_url, headers):
    for table_name in FOGLALASOK_TABLE_CANDIDATES:
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            "?select=id&limit=1"
        )
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=30,
        )

        if is_missing_table_response(response):
            continue

        raise_for_supabase_error(response)
        return table_name

    return "foglalasok_raw"


def read_courier_lookup_by_email():
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
        email = normalize_email(row.get("email"))

        if email:
            lookup[email] = {
                "courier_id": row.get("courier_id"),
                "courier_name": clean(row.get("courier_name")),
            }

    return lookup


def enrich_bookings_from_courier_master(df):
    if df.empty or "email" not in df.columns:
        return df

    try:
        courier_lookup = read_courier_lookup_by_email()
    except Exception:
        return df

    if not courier_lookup:
        return df

    enriched = df.copy()

    if "courier_id" not in enriched.columns:
        enriched["courier_id"] = ""
    if "courier_name" not in enriched.columns:
        enriched["courier_name"] = ""

    for index, row in enriched.iterrows():
        email = normalize_email(row.get("email"))
        courier = courier_lookup.get(email)
        if not courier:
            continue

        current_id = clean(row.get("courier_id"))
        current_name = clean(row.get("courier_name"))

        if not current_id:
            enriched.at[index, "courier_id"] = clean(courier.get("courier_id"))
        if not current_name:
            enriched.at[index, "courier_name"] = courier.get("courier_name")

    return enriched


def build_db_rows(values, courier_lookup=None):
    if courier_lookup is None:
        try:
            courier_lookup = read_courier_lookup_by_email()
        except Exception:
            courier_lookup = {}

    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows = []
    raw_header = list(values[0] if values else [])
    header = [
        normalize_header(value)
        for value in raw_header
    ]
    known_headers = {
        "timestamp", "idopont", "createdat", "rogzitve", "workdate", "datum",
        "date", "nap", "email", "emailcim", "mail", "shifttext", "muszak",
        "shift", "muszakpro", "warehouse", "raktar", "depo", "bookingcode",
        "kod", "code", "foglalasikod", "adminrecorder", "admin", "rogzito",
        "giritonuploaded", "rendszerellenorzes", "systemcheck", "legacykey",
        "kulcs", "key", "courierid", "nev", "name", "couriername", "futar",
        "sorszam", "serial",
    }
    has_header = bool(set(header) & known_headers)
    compact_headerless = (
        not has_header
        and len(raw_header) >= 4
        and looks_like_date(raw_header[0])
        and looks_like_email(raw_header[1])
    )

    def header_index(*names):
        if not has_header:
            return None
        normalized_names = {
            normalize_header(name)
            for name in names
        }

        for index, column in enumerate(header):
            if column in normalized_names:
                return index

        return None

    def cell_by_header(default_index, *names):
        index = header_index(*names)
        if index is None:
            index = default_index
        return lambda cells: clean(cells[index]) if index is not None and index < len(cells) else ""

    if compact_headerless:
        default_indexes = {
            "timestamp": None,
            "work_date": 0,
            "email": 1,
            "shift_text": 2,
            "warehouse": 3,
            "booking_code": 4,
            "admin_recorder": 5,
            "giriton_uploaded": 6,
            "system_check": 7,
            "legacy_key": 8,
        }
        data_rows = values
        first_source_row = 1
    else:
        default_indexes = {
            "timestamp": 0,
            "work_date": 1,
            "email": 2,
            "shift_text": 3,
            "warehouse": 4,
            "booking_code": 5,
            "admin_recorder": 6,
            "giriton_uploaded": 7,
            "system_check": 8,
            "legacy_key": 10,
        }
        data_rows = values[1:] if has_header else values
        first_source_row = 2 if has_header else 1

    timestamp_cell = cell_by_header(default_indexes["timestamp"], "timestamp", "idopont", "időpont", "created_at", "rogzitve", "rögzítve")
    work_date_cell = cell_by_header(default_indexes["work_date"], "work_date", "datum", "dátum", "date", "nap")
    email_cell = cell_by_header(default_indexes["email"], "email", "e-mail", "email cim", "e-mail cím", "mail")
    shift_text_cell = cell_by_header(default_indexes["shift_text"], "shift_text", "muszak", "műszak", "shift", "muszakpro", "műszakpro")
    warehouse_cell = cell_by_header(default_indexes["warehouse"], "warehouse", "raktar", "raktár", "depo", "depó")
    booking_code_cell = cell_by_header(default_indexes["booking_code"], "booking_code", "booking code", "kod", "kód", "code", "foglalasi kod", "foglalási kód")
    admin_recorder_cell = cell_by_header(default_indexes["admin_recorder"], "admin_recorder", "admin", "rogzito", "rögzítő")
    giriton_uploaded_cell = cell_by_header(default_indexes["giriton_uploaded"], "giriton_uploaded", "giriton feltoltve", "giriton feltöltve")
    system_check_cell = cell_by_header(default_indexes["system_check"], "system_check", "rendszer ellenorzes", "rendszer ellenőrzés")
    legacy_key_cell = cell_by_header(default_indexes["legacy_key"], "legacy_key", "kulcs", "key")
    courier_id_index = header_index("courier_id")
    courier_name_index = header_index("nev", "név", "name", "courier_name", "futar", "futár")
    serial_index = header_index("sorszam", "serial")

    for source_row, row in enumerate(data_rows, start=first_source_row):
        cells = list(row) + [""] * 12
        timestamp_text = timestamp_cell(cells)
        work_date = work_date_cell(cells)
        email = normalize_email(email_cell(cells))
        shift_text = shift_text_cell(cells)
        warehouse = warehouse_cell(cells)
        booking_code = booking_code_cell(cells)

        if not work_date or not email or not shift_text:
            continue

        driver = courier_lookup.get(
            email,
            {},
        )
        enriched_courier_id = (
            clean(cells[courier_id_index])
            if courier_id_index is not None and courier_id_index < len(cells)
            else ""
        )
        enriched_courier_name = (
            clean(cells[courier_name_index])
            if courier_name_index is not None and courier_name_index < len(cells)
            else ""
        )
        enriched_serial = (
            clean(cells[serial_index])
            if serial_index is not None and serial_index < len(cells)
            else ""
        )
        courier_id = enriched_courier_id or driver.get("courier_id")
        courier_name = enriched_courier_name or driver.get("courier_name", "")
        start = shift_start(
            shift_text
        )
        serial = enriched_serial or shift_serial(
            work_date,
            courier_id,
            warehouse,
            start,
        )

        rows.append({
            "source_name": SOURCE_NAME,
            "source_row": source_row,
            "timestamp_text": timestamp_text,
            "work_date": work_date,
            "email": email,
            "shift_text": shift_text,
            "warehouse": warehouse,
            "booking_code": booking_code,
            "admin_recorder": admin_recorder_cell(cells),
            "giriton_uploaded": giriton_uploaded_cell(cells),
            "system_check": system_check_cell(cells),
            "legacy_key": legacy_key_cell(cells),
            "courier_id": optional_int(courier_id),
            "courier_name": courier_name,
            "serial": serial,
            "response_json": {
                "source_row": source_row,
                "timestamp_text": timestamp_text,
                "work_date": work_date,
                "email": email,
                "shift_text": shift_text,
                "warehouse": warehouse,
                "booking_code": booking_code,
                "admin_recorder": admin_recorder_cell(cells),
                "giriton_uploaded": giriton_uploaded_cell(cells),
                "system_check": system_check_cell(cells),
                "legacy_key": legacy_key_cell(cells),
                "courier_id": courier_id,
                "courier_name": courier_name,
                "serial": serial,
            },
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
        })

    return rows


def upsert_foglalasok_rows(values):
    db_rows = build_db_rows(
        values
    )

    if not db_rows:
        return {
            "rows": 0,
            "status": "empty",
        }

    supabase_url, headers = get_headers()
    table_name = resolve_foglalasok_table(
        supabase_url,
        headers,
    )
    delete_endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?id=not.is.null"
    )
    delete_headers = {
        **headers,
        "Prefer": "return=minimal",
    }
    delete_response = requests.delete(
        delete_endpoint,
        headers=delete_headers,
        timeout=60,
    )
    raise_for_supabase_error(delete_response)

    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?on_conflict=source_name,work_date,email,shift_text,booking_code"
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


@st.cache_data(show_spinner=False, ttl=300)
def read_foglalasok_raw(start_date=None, end_date=None, limit=10000):
    supabase_url, headers = get_headers()
    base_select = (
        "work_date,email,shift_text,warehouse,booking_code,"
        "courier_id,courier_name,serial,fetched_at"
    )
    select_fields = f"{base_select},status,cancelled_at"

    def build_filters(select_text):
        filters = [
            f"select={select_text}",
            "order=work_date.desc,shift_text.asc,email.asc",
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

        return filters

    rows = []

    for table_name in FOGLALASOK_TABLE_CANDIDATES:
        filters = build_filters(
            select_fields
        )
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            f"?{'&'.join(filters)}"
        )
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=60,
        )

        if is_missing_table_response(response):
            continue

        if response.status_code == 400 and "status" in response.text.lower():
            filters = build_filters(
                base_select
            )
            endpoint = (
                f"{supabase_url}/rest/v1/{table_name}"
                f"?{'&'.join(filters)}"
            )
            response = requests.get(
                endpoint,
                headers=headers,
                timeout=60,
            )

        raise_for_supabase_error(response)
        rows.extend(response.json())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    dedupe_columns = [
        column
        for column in [
            "work_date",
            "email",
            "shift_text",
            "warehouse",
            "booking_code",
            "courier_id",
        ]
        if column in df.columns
    ]
    if dedupe_columns:
        df = df.drop_duplicates(subset=dedupe_columns, keep="first")

    if len(df) > int(limit):
        df = df.head(int(limit))

    if "status" in df.columns:
        df = df[
            df["status"].fillna("ACTIVE").astype(str).str.upper() != "CANCELLED"
        ]

    return enrich_bookings_from_courier_master(df)

@st.cache_data(show_spinner=False, ttl=300)
def read_muszakpro_events(start_date=None, end_date=None, limit=1000):
    supabase_url, headers = get_headers()
    filters = [
        (
            "select=created_at,action_type,work_date,email,shift_text,"
            "warehouse,booking_code,actor_email"
        ),
        "order=created_at.desc",
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
        f"{supabase_url}/rest/v1/ops_muszakpro_events"
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

    return pd.DataFrame(rows)


def read_foglalasok_records(work_date):
    df = read_foglalasok_raw(
        start_date=work_date,
        end_date=work_date,
        limit=10000,
    )

    if df.empty:
        return []

    records = []

    for _, row in df.iterrows():
        serial = clean(row.get("serial"))

        if not serial:
            continue

        shift = clean(row.get("shift_text"))

        records.append({
            "serial": serial,
            "work_date": clean(row.get("work_date")),
            "courier_id": clean(row.get("courier_id")),
            "name": clean(row.get("courier_name")),
            "email": normalize_email(row.get("email")),
            "warehouse": clean(row.get("warehouse")),
            "start": shift_start(shift),
            "code": clean(row.get("booking_code")),
        })

    return records
