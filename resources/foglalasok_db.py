from datetime import datetime
import re
import unicodedata

import pandas as pd
import requests
import streamlit as st

from google_client import open_spreadsheet
from resources.source_sheet_sync import SOURCE_SPREADSHEET_ID
from resources.supabase_raw import (
    format_date_filter,
    get_supabase_config,
    raise_for_supabase_error,
)


SOURCE_NAME = "google-sheet-foglalasok"
FOGLALASOK_SHEET_NAME = "Foglalasok"
ID_SHEET_NAME = "ID"
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
    return re.sub(r"\s+", "", clean(value).casefold())


def normalize_name(value):
    text = unicodedata.normalize("NFKD", clean(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def courier_id_from_text(value):
    match = re.search(r"\b(\d{4,5})\b", clean(value))
    return match.group(1) if match else ""


def name_without_courier_id(value):
    return normalize_name(re.sub(r"\b\d{4,5}\b", " ", clean(value)))


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
        try:
            number = float(text)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
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
    lookup = {
        "by_email": {},
        "by_id": {},
        "by_name": {},
    }

    for row in response.json():
        email = normalize_email(row.get("email"))
        courier_id = clean(row.get("courier_id"))
        courier_name = clean(row.get("courier_name"))
        courier = {
            "courier_id": courier_id,
            "courier_name": courier_name,
            "email": email,
        }

        if email:
            lookup["by_email"][email] = courier
        if courier_id:
            lookup["by_id"][courier_id] = courier
        for name_key in {
            normalize_name(courier_name),
            name_without_courier_id(courier_name),
        }:
            if name_key:
                lookup["by_name"][name_key] = courier

    return lookup


def get_or_create_id_worksheet():
    spreadsheet = open_spreadsheet(SOURCE_SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(ID_SHEET_NAME)
    except Exception:
        return spreadsheet.add_worksheet(
            title=ID_SHEET_NAME,
            rows=5000,
            cols=5,
        )


def read_courier_lookup_from_id_sheet():
    try:
        worksheet = get_or_create_id_worksheet()
        values = worksheet.get_all_values()
    except Exception:
        return {"by_email": {}, "by_id": {}, "by_name": {}}

    if not values:
        return {"by_email": {}, "by_id": {}, "by_name": {}}

    header = [normalize_header(value) for value in values[0]]

    def header_index(*names):
        normalized_names = {normalize_header(name) for name in names}
        for index, column in enumerate(header):
            if column in normalized_names:
                return index
        return None

    id_index = header_index("courier_id", "futar id", "futár id", "id")
    name_index = header_index("courier_name", "nev", "név", "name")
    email_index = header_index("email", "e-mail", "email cim", "e-mail cím")

    lookup = {"by_email": {}, "by_id": {}, "by_name": {}}
    for row in values[1:]:
        email = (
            normalize_email(row[email_index])
            if email_index is not None and email_index < len(row)
            else ""
        )
        courier_id = clean(row[id_index] if id_index is not None and id_index < len(row) else "")
        courier_name = clean(row[name_index] if name_index is not None and name_index < len(row) else "")
        courier = {
            "courier_id": courier_id,
            "courier_name": courier_name,
            "email": email,
        }
        if email:
            lookup["by_email"][email] = courier
        if courier_id:
            lookup["by_id"][courier_id] = courier
        for name_key in {
            normalize_name(courier_name),
            name_without_courier_id(courier_name),
        }:
            if name_key:
                lookup["by_name"][name_key] = courier

    return lookup


def merge_courier_lookups(*lookups):
    merged = {"by_email": {}, "by_id": {}, "by_name": {}}
    for lookup in lookups:
        if not lookup:
            continue
        by_email = lookup.get("by_email", lookup)
        for email, courier in by_email.items():
            normalized_email = normalize_email(email)
            if normalized_email:
                merged["by_email"][normalized_email] = courier
        for courier_id, courier in lookup.get("by_id", {}).items():
            courier_id = clean(courier_id)
            if courier_id:
                merged["by_id"][courier_id] = courier
        for name_key, courier in lookup.get("by_name", {}).items():
            name_key = normalize_name(name_key)
            if name_key:
                merged["by_name"][name_key] = courier
    return merged


def read_combined_courier_lookup():
    db_lookup = read_courier_lookup()
    sheet_lookup = read_courier_lookup_from_id_sheet()
    return merge_courier_lookups(db_lookup, sheet_lookup)


def _add_courier_export_row(rows_by_key, courier):
    courier_id = clean(courier.get("courier_id"))
    courier_name = clean(courier.get("courier_name"))
    email = normalize_email(courier.get("email"))
    key = courier_id or email or normalize_name(courier_name)
    if not key:
        return

    current = rows_by_key.get(key, {})
    rows_by_key[key] = {
        "courier_id": courier_id or clean(current.get("courier_id")),
        "courier_name": courier_name or clean(current.get("courier_name")),
        "email": email or normalize_email(current.get("email")),
    }


def export_courier_master_to_id_sheet():
    supabase_url, headers = get_headers()
    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?select=courier_id,courier_name,email"
        "&order=courier_name.asc,courier_id.asc"
        "&limit=5000"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )
    raise_for_supabase_error(response)

    worksheet = get_or_create_id_worksheet()
    existing_lookup = read_courier_lookup_from_id_sheet()
    rows_by_key = {}

    for row in response.json():
        _add_courier_export_row(
            rows_by_key,
            {
                "courier_id": clean(row.get("courier_id")),
                "courier_name": clean(row.get("courier_name")),
                "email": normalize_email(row.get("email")),
            },
        )

    for lookup in [
        existing_lookup.get("by_id", {}),
        existing_lookup.get("by_email", {}),
        existing_lookup.get("by_name", {}),
    ]:
        for courier in lookup.values():
            _add_courier_export_row(rows_by_key, courier)

    values = [["courier_id", "courier_name", "email"]]
    for row in sorted(
        rows_by_key.values(),
        key=lambda item: (
            clean(item.get("courier_name")).casefold(),
            clean(item.get("courier_id")),
        ),
    ):
        values.append([
            clean(row.get("courier_id")),
            clean(row.get("courier_name")),
            normalize_email(row.get("email")),
        ])

    worksheet.clear()
    worksheet.update("A1", values)
    return {"rows": max(len(values) - 1, 0), "sheet": ID_SHEET_NAME}


def read_courier_lookup_by_email():
    return read_courier_lookup().get("by_email", {})


def find_courier_for_booking(row, courier_lookup):
    if not courier_lookup:
        return {}

    if "by_email" not in courier_lookup:
        email = normalize_email(row.get("email"))
        return courier_lookup.get(email, {})

    email = normalize_email(row.get("email"))
    if email and email in courier_lookup["by_email"]:
        return courier_lookup["by_email"][email]

    courier_id = clean(row.get("courier_id")) or courier_id_from_text(row.get("courier_name"))
    if courier_id and courier_id in courier_lookup.get("by_id", {}):
        return courier_lookup["by_id"][courier_id]

    for name_key in {
        normalize_name(row.get("courier_name")),
        name_without_courier_id(row.get("courier_name")),
    }:
        if name_key and name_key in courier_lookup.get("by_name", {}):
            return courier_lookup["by_name"][name_key]

    return {}


def enrich_bookings_from_courier_master(df):
    if df.empty:
        return df

    try:
        courier_lookup = read_combined_courier_lookup()
    except Exception:
        return df

    if not courier_lookup:
        return df

    enriched = df.copy()

    if "courier_id" not in enriched.columns:
        enriched["courier_id"] = ""
    if "courier_name" not in enriched.columns:
        enriched["courier_name"] = ""
    if "serial" not in enriched.columns:
        enriched["serial"] = ""

    for index, row in enriched.iterrows():
        courier = find_courier_for_booking(row, courier_lookup)
        if not courier:
            continue

        current_id = clean(row.get("courier_id"))
        current_name = clean(row.get("courier_name"))

        if not current_id:
            enriched.at[index, "courier_id"] = clean(courier.get("courier_id"))
        if not current_name:
            enriched.at[index, "courier_name"] = courier.get("courier_name")
        if not clean(row.get("serial")):
            courier_id = clean(row.get("courier_id")) or clean(courier.get("courier_id"))
            enriched.at[index, "serial"] = shift_serial(
                row.get("work_date"),
                courier_id,
                row.get("warehouse"),
                shift_start(row.get("shift_text")),
            )

    return enriched


def backfill_booking_couriers_from_master(limit=5000):
    supabase_url, headers = get_headers()
    courier_lookup = read_combined_courier_lookup()
    if not courier_lookup:
        return {"checked": 0, "updated": 0}

    checked = 0
    updated = 0

    for table_name in FOGLALASOK_TABLE_CANDIDATES:
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            "?select=id,email,courier_id,courier_name,serial,work_date,shift_text,warehouse,booking_code,response_json"
            "&order=work_date.desc,shift_text.asc,email.asc"
            f"&limit={int(limit)}"
        )
        response = requests.get(endpoint, headers=headers, timeout=60)
        if is_missing_table_response(response):
            continue

        raise_for_supabase_error(response)
        rows = response.json()
        checked += len(rows)

        for row in rows:
            courier = find_courier_for_booking(row, courier_lookup)
            row_id = clean(row.get("id"))
            if not row_id:
                continue
            if not courier:
                if not clean(row.get("courier_id")):
                    print(
                        "FOGLALASOK_COURIER_BACKFILL_NO_MASTER_MATCH "
                        f"table={table_name} "
                        f"row_id={row_id} "
                        f"email={clean(row.get('email')) or '-'} "
                        f"raw_name={clean(row.get('courier_name')) or '-'} "
                        f"work_date={clean(row.get('work_date')) or '-'} "
                        f"shift={clean(row.get('shift_text')) or '-'} "
                        f"booking_code={clean(row.get('booking_code')) or '-'}"
                    )
                continue

            update_payload = {}
            if not clean(row.get("courier_id")):
                resolved_courier_id = optional_int(courier.get("courier_id"))
                if resolved_courier_id is None:
                    print(
                        "FOGLALASOK_COURIER_BACKFILL_MISSING_ID "
                        f"table={table_name} "
                        f"row_id={row_id} "
                        f"email={clean(row.get('email')) or '-'} "
                        f"raw_name={clean(row.get('courier_name')) or '-'} "
                        f"matched_name={clean(courier.get('courier_name')) or '-'} "
                        f"work_date={clean(row.get('work_date')) or '-'} "
                        f"shift={clean(row.get('shift_text')) or '-'} "
                        f"booking_code={clean(row.get('booking_code')) or '-'}"
                    )
                else:
                    update_payload["courier_id"] = resolved_courier_id
            if not clean(row.get("courier_name")):
                update_payload["courier_name"] = clean(courier.get("courier_name"))
            if not clean(row.get("serial")):
                courier_id = clean(row.get("courier_id")) or clean(courier.get("courier_id"))
                if courier_id:
                    update_payload["serial"] = shift_serial(
                        row.get("work_date"),
                        courier_id,
                        row.get("warehouse"),
                        shift_start(row.get("shift_text")),
                    )
                else:
                    print(
                        "FOGLALASOK_SERIAL_BACKFILL_MISSING_ID "
                        f"table={table_name} "
                        f"row_id={row_id} "
                        f"email={clean(row.get('email')) or '-'} "
                        f"raw_name={clean(row.get('courier_name')) or '-'} "
                        f"matched_name={clean(courier.get('courier_name')) or '-'} "
                        f"work_date={clean(row.get('work_date')) or '-'} "
                        f"shift={clean(row.get('shift_text')) or '-'} "
                        f"booking_code={clean(row.get('booking_code')) or '-'}"
                    )
            if not update_payload:
                continue

            update_response = requests.patch(
                f"{supabase_url}/rest/v1/{table_name}?id=eq.{row_id}",
                headers={**headers, "Prefer": "return=minimal"},
                json=update_payload,
                timeout=60,
            )
            raise_for_supabase_error(update_response)
            updated += 1

    return {"checked": checked, "updated": updated}


def build_db_rows(values, courier_lookup=None):
    if courier_lookup is None:
        try:
            courier_lookup = read_combined_courier_lookup()
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
    compact_email_headerless = (
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

    if compact_email_headerless:
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
            "courier_id": None,
            "courier_name": None,
            "serial": None,
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
            "courier_id": None,
            "courier_name": None,
            "serial": None,
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
    if courier_id_index is None:
        courier_id_index = default_indexes["courier_id"]
    courier_name_index = header_index("nev", "név", "name", "courier_name", "futar", "futár")
    if courier_name_index is None:
        courier_name_index = default_indexes["courier_name"]
    serial_index = header_index("sorszam", "serial")
    if serial_index is None:
        serial_index = default_indexes["serial"]

    for source_row, row in enumerate(data_rows, start=first_source_row):
        cells = list(row) + [""] * 12
        timestamp_text = timestamp_cell(cells)
        work_date = work_date_cell(cells)
        email = normalize_email(email_cell(cells))
        shift_text = shift_text_cell(cells)
        warehouse = warehouse_cell(cells)
        booking_code = booking_code_cell(cells)

        if not work_date or not shift_text:
            continue

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
        lookup_row = {
            "email": email,
            "courier_id": enriched_courier_id,
            "courier_name": enriched_courier_name,
            "shift_text": shift_text,
            "warehouse": warehouse,
            "booking_code": booking_code,
            "serial": enriched_serial,
            "response_json": cells,
        }
        driver = find_courier_for_booking(lookup_row, courier_lookup)
        courier_id = enriched_courier_id or driver.get("courier_id")
        courier_name = enriched_courier_name or driver.get("courier_name", "")
        if not email and not courier_id:
            continue
        row_email = email or f"courier-id:{clean(courier_id)}"
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
            "email": row_email,
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
                "email": row_email,
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
