import argparse
import calendar
import re
import sys
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from google_client import open_spreadsheet
from resources.foglalasok_db import read_foglalasok_raw, shift_start
from resources.source_sheet_sync import SOURCE_SPREADSHEET_ID
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DSP_ID = "JIT"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
RAW_TABLE = "raw_fetch_attendance_shifts"
COMPARISON_TABLE = "ops_attendance_muszakpro_comparison"
COURIER_LOOKUP_CACHE = None
USER_SHEET_LOOKUP_CACHE = None
SHIFT_MATCH_TOLERANCE_MINUTES = 30
COURIER_TABLE_CANDIDATES = [
    "core_couriers",
    "courier_master",
]


def clean(value):
    text = str(value or "").strip()

    if text.casefold() in {"nan", "none", "null", "<na>"}:
        return ""

    return text


def optional_int(value):
    text = clean(value)

    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


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


def is_time_text(value):
    text = clean(value)
    parts = text.split(":")

    if len(parts) < 2:
        return False

    try:
        int(parts[0])
        int(parts[1])
    except ValueError:
        return False

    return True


def db_time(value):
    text = normalize_time(value)

    if not text:
        return None

    if not is_time_text(text):
        return None

    if len(text) == 4:
        text = f"0{text}"

    if len(text) == 5:
        return f"{text}:00"

    return text


def normalize_warehouse(value):
    text = clean(value).upper()

    if "BUDAPEST" in text or "BUD1" in text or text == "1":
        return "BUD1"

    if "BUD2" in text or text == "2":
        return "BUD2"

    return text


def normalize_name(value):
    text = clean(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = re.sub(
        r"\b\d{4,6}\b",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def parse_datetime(value):
    text = clean(value)

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)

    return parsed.astimezone(LOCAL_TIMEZONE)


def iso_datetime(value):
    parsed = parse_datetime(value)

    if not parsed:
        return None

    return parsed.isoformat(timespec="seconds")


def time_from_datetime(value):
    parsed = parse_datetime(value)

    if not parsed:
        return ""

    return f"{parsed.hour}:{parsed.minute:02d}"


def time_to_minutes(value):
    text = normalize_time(value)

    if not is_time_text(text):
        return None

    hour, minute = text.split(":", 1)
    return int(hour) * 60 + int(minute)


def shift_time_from_text(value):
    match = re.search(
        r"(\d{1,2}):(\d{2})",
        clean(value),
    )

    if not match:
        return ""

    return f"{int(match.group(1))}:{match.group(2)}"


def normalize_shift_name(value, warehouse="", fallback_start=""):
    text = clean(value)
    normalized_warehouse = normalize_warehouse(warehouse)
    upper_text = text.upper().replace("_", "-")

    if "BUD1" in upper_text:
        normalized_warehouse = "BUD1"
    elif "BUD2" in upper_text:
        normalized_warehouse = "BUD2"

    shift_time = shift_time_from_text(text) or normalize_time(fallback_start)

    if shift_time:
        return f"{normalized_warehouse}-{shift_time}".casefold()

    return f"{normalized_warehouse}-{text}".casefold()


def make_match_key(work_date, courier_name, shift_name):
    return "|".join([
        clean(work_date),
        normalize_name(courier_name),
        clean(shift_name).casefold(),
    ])


def make_person_day_warehouse_key(row):
    person = (
        clean(row.get("courier_id"))
        or clean(row.get("email")).casefold()
        or normalize_name(row.get("courier_name"))
    )

    return "|".join([
        clean(row.get("work_date")),
        person,
        normalize_warehouse(row.get("warehouse")).casefold(),
    ])


def legacy_match_key(work_date, courier_id, email, courier_name, warehouse, start):
    person = clean(courier_id) or clean(email).casefold() or normalize_name(courier_name)
    shift_key = normalize_time(start) if is_time_text(start) else clean(start).casefold()

    return "|".join([
        clean(work_date),
        person,
        normalize_warehouse(warehouse).casefold(),
        shift_key,
    ])


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def month_dates(month_text):
    year, month = map(int, month_text.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    for day in range(1, last_day + 1):
        yield date(year, month, day)


def build_attendance_url(work_date):
    return (
        f"{BASE_URL}/fetch-attendance/{DSP_ID}/{work_date.isoformat()}"
        f"?organizationId={ORGANIZATION_ID}"
    )


def fetch_attendance(work_date):
    url = build_attendance_url(work_date)
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()
    return url, response.status_code, response.json()


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


def read_courier_table_rows(supabase_url, headers, table_name):
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?select=courier_id,courier_name,email,billing_email"
        "&limit=5000"
    )
    response = requests.get(
        endpoint,
        headers=headers,
        timeout=60,
    )

    if response.status_code == 400 and "billing_email" in response.text:
        endpoint = (
            f"{supabase_url}/rest/v1/{table_name}"
            "?select=courier_id,courier_name,email"
            "&limit=5000"
        )
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=60,
        )

    return response


def read_courier_lookup():
    global COURIER_LOOKUP_CACHE

    if COURIER_LOOKUP_CACHE is not None:
        return COURIER_LOOKUP_CACHE

    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        COURIER_LOOKUP_CACHE = {
            "by_id": {},
            "by_email": {},
        }
        return COURIER_LOOKUP_CACHE

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    responses = []
    for table_name in COURIER_TABLE_CANDIDATES:
        response = read_courier_table_rows(
            supabase_url,
            headers,
            table_name,
        )

        if is_missing_table_response(response):
            continue

        raise_for_supabase_error(response)
        responses.append(response.json())

    if not responses:
        COURIER_LOOKUP_CACHE = {
            "by_id": {},
            "by_email": {},
        }
        return COURIER_LOOKUP_CACHE

    by_id = {}
    by_email = {}

    for rows in responses:
        for row in rows:
            courier_id = optional_int(row.get("courier_id"))
            email = clean(row.get("email")).casefold()
            billing_email = clean(row.get("billing_email")).casefold()
            item = {
                "courier_id": courier_id,
                "courier_name": clean(row.get("courier_name")),
                "email": email,
                "billing_email": billing_email,
            }

            if courier_id:
                by_id[courier_id] = {
                    **by_id.get(courier_id, {}),
                    **{
                        key: value
                        for key, value in item.items()
                        if value not in [None, ""]
                    },
                }

            if email:
                by_email[email] = item

            if billing_email:
                by_email[billing_email] = item

    COURIER_LOOKUP_CACHE = {
        "by_id": by_id,
        "by_email": by_email,
    }
    return COURIER_LOOKUP_CACHE


def row_value(row, index):
    if index is None or index >= len(row):
        return ""

    return clean(row[index])


def read_user_sheet_lookup():
    global USER_SHEET_LOOKUP_CACHE

    if USER_SHEET_LOOKUP_CACHE is not None:
        return USER_SHEET_LOOKUP_CACHE

    lookup = {
        "by_email": {},
    }

    try:
        worksheet = open_spreadsheet(
            SOURCE_SPREADSHEET_ID
        ).worksheet("Felhasznalok")
        rows = worksheet.get_all_values()
    except Exception:
        USER_SHEET_LOOKUP_CACHE = lookup
        return lookup

    for row in rows:
        for name_index, email_index in [
            (0, 3),
            (6, 7),
            (10, 11),
        ]:
            name = row_value(row, name_index)
            email = row_value(row, email_index).casefold()

            if not name or not email or "@" not in email:
                continue

            if normalize_name(name) in {"nev", "név"}:
                continue

            lookup["by_email"][email] = {
                "courier_name": name,
            }

    USER_SHEET_LOOKUP_CACHE = lookup
    return USER_SHEET_LOOKUP_CACHE


def parse_attendance_shift_rows(collection_id, work_date, request_url, status_code, payload):
    rows = []
    work_date_text = work_date.isoformat()

    for courier in payload.get("couriers", []) or []:
        courier_id = optional_int(courier.get("courierId"))
        courier_name = clean(courier.get("courierName"))
        warehouse = normalize_warehouse(
            courier.get("warehouseName")
            or courier.get("warehouse")
            or courier.get("warehouseId")
        )

        for shift in courier.get("shifts", []) or []:
            start_text = time_from_datetime(shift.get("shiftStart"))

            if not start_text:
                continue

            normalized_shift_name = normalize_shift_name(
                shift.get("shiftName"),
                warehouse,
                start_text,
            )
            match_key = make_match_key(
                work_date_text,
                courier_name,
                normalized_shift_name,
            )
            rows.append({
                "collection_id": collection_id,
                "source_name": "fetch-attendance",
                "organization_id": ORGANIZATION_ID,
                "dsp_id": DSP_ID,
                "work_date": work_date_text,
                "request_url": request_url,
                "status_code": int(status_code),
                "courier_id": courier_id,
                "courier_name": courier_name,
                "warehouse": warehouse,
                "api_shift_id": clean(shift.get("shiftId")),
                "shift_name": clean(shift.get("shiftName")),
                "normalized_shift_name": normalized_shift_name,
                "shift_start": iso_datetime(shift.get("shiftStart")),
                "shift_end": iso_datetime(shift.get("shiftEnd")),
                "available_for_shift_since": iso_datetime(
                    shift.get("availableForShiftSince")
                ),
                "match_key": match_key,
                "source_json": {
                    "courier": courier,
                    "shift": shift,
                },
            })

    return rows


def read_muszakpro_rows(work_date):
    df = read_foglalasok_raw(
        start_date=work_date.isoformat(),
        end_date=work_date.isoformat(),
        limit=20000,
    )

    if df.empty:
        return []

    rows_by_key = {}
    courier_lookup = read_courier_lookup()
    user_sheet_lookup = read_user_sheet_lookup()

    for _, row in df.iterrows():
        work_date_text = clean(row.get("work_date"))[:10]
        shift_text = clean(row.get("shift_text"))
        start = shift_start(shift_text)
        shift_key = start if is_time_text(start) else shift_text
        courier_id = optional_int(row.get("courier_id"))
        email = clean(row.get("email")).casefold()
        courier_name = clean(row.get("courier_name"))
        warehouse = normalize_warehouse(row.get("warehouse"))
        master = (
            courier_lookup["by_id"].get(courier_id)
            or courier_lookup["by_email"].get(email)
            or {}
        )
        user_sheet = user_sheet_lookup["by_email"].get(
            email,
            {},
        )
        courier_name = (
            courier_name
            or clean(master.get("courier_name"))
            or clean(user_sheet.get("courier_name"))
        )
        courier_id = courier_id or optional_int(
            master.get("courier_id")
        )
        normalized_shift_name = normalize_shift_name(
            shift_text,
            warehouse,
            start,
        )

        if not work_date_text or not shift_key or not courier_name:
            continue

        match_key = make_match_key(
            work_date_text,
            courier_name,
            normalized_shift_name,
        )
        record = {
            "match_key": match_key,
            "work_date": work_date_text,
            "courier_id": courier_id,
            "courier_name": courier_name,
            "email": email,
            "warehouse": warehouse,
            "shift_start": start,
            "shift_key": shift_key,
            "normalized_shift_name": normalized_shift_name,
            "shift_text": shift_text,
            "booking_code": clean(row.get("booking_code")),
        }
        existing = rows_by_key.get(match_key)

        if existing is None or muszakpro_row_quality(record) > muszakpro_row_quality(existing):
            rows_by_key[match_key] = record

    return list(rows_by_key.values())


def muszakpro_row_quality(row):
    return sum(
        1
        for key in [
            "courier_id",
            "courier_name",
            "email",
            "warehouse",
            "shift_start",
            "booking_code",
        ]
        if clean(row.get(key))
    )


def build_comparison_rows(collection_id, attendance_rows, muszakpro_rows):
    attendance_by_key = {
        row["match_key"]: row
        for row in attendance_rows
    }
    muszakpro_by_key = {
        row["match_key"]: row
        for row in muszakpro_rows
    }
    exact_keys = set(attendance_by_key) & set(muszakpro_by_key)
    paired_keys = [
        (
            match_key,
            attendance_by_key[match_key],
            muszakpro_by_key[match_key],
        )
        for match_key in sorted(exact_keys)
    ]
    used_attendance_keys = set(exact_keys)
    used_muszakpro_keys = set(exact_keys)

    remaining_attendance = [
        row
        for row in attendance_rows
        if row["match_key"] not in used_attendance_keys
    ]
    remaining_muszakpro = [
        row
        for row in muszakpro_rows
        if row["match_key"] not in used_muszakpro_keys
    ]

    for attendance in remaining_attendance:
        attendance_start = time_to_minutes(
            time_from_datetime(attendance.get("shift_start"))
        )

        if attendance_start is None:
            continue

        attendance_group_key = make_person_day_warehouse_key(
            attendance
        )
        best_muszakpro = None
        best_delta = None

        for muszakpro in remaining_muszakpro:
            if muszakpro["match_key"] in used_muszakpro_keys:
                continue

            if make_person_day_warehouse_key(muszakpro) != attendance_group_key:
                continue

            muszakpro_start = time_to_minutes(
                muszakpro.get("shift_start")
            )

            if muszakpro_start is None:
                continue

            delta = abs(attendance_start - muszakpro_start)

            if delta > SHIFT_MATCH_TOLERANCE_MINUTES:
                continue

            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_muszakpro = muszakpro

        if not best_muszakpro:
            continue

        paired_keys.append(
            (
                attendance["match_key"],
                attendance,
                best_muszakpro,
            )
        )
        used_attendance_keys.add(
            attendance["match_key"]
        )
        used_muszakpro_keys.add(
            best_muszakpro["match_key"]
        )

    output = []

    comparison_items = paired_keys

    for row in attendance_rows:
        if row["match_key"] not in used_attendance_keys:
            comparison_items.append(
                (
                    row["match_key"],
                    row,
                    {},
                )
            )

    for row in muszakpro_rows:
        if row["match_key"] not in used_muszakpro_keys:
            comparison_items.append(
                (
                    row["match_key"],
                    {},
                    row,
                )
            )

    for match_key, attendance, muszakpro in sorted(
        comparison_items,
        key=lambda item: item[0],
    ):
        source = attendance or muszakpro
        has_attendance = bool(attendance)
        has_muszakpro = bool(muszakpro)
        missing = []

        if not has_attendance:
            missing.append("fetch-attendance")

        if not has_muszakpro:
            missing.append("MuszakPro")

        shift_start_value = (
            time_from_datetime(attendance.get("shift_start"))
            if attendance
            else muszakpro.get("shift_start")
        )
        shift_end_value = time_from_datetime(
            attendance.get("shift_end")
        )

        output.append({
            "collection_id": collection_id,
            "work_date": source.get("work_date"),
            "match_key": match_key,
            "courier_id": optional_int(source.get("courier_id")),
            "courier_name": clean(source.get("courier_name")),
            "email": clean(muszakpro.get("email")).casefold(),
            "warehouse": normalize_warehouse(source.get("warehouse")),
            "shift_start": db_time(shift_start_value),
            "shift_end": db_time(shift_end_value),
            "attendance_status": "OK" if has_attendance else "-",
            "muszakpro_status": "OK" if has_muszakpro else "-",
            "missing_source": ", ".join(missing),
            "attendance_shift_id": clean(attendance.get("api_shift_id")),
            "attendance_shift_name": clean(attendance.get("shift_name")),
            "muszakpro_shift_text": clean(muszakpro.get("shift_text")),
            "muszakpro_booking_code": clean(muszakpro.get("booking_code")),
            "source_summary": {
                "attendance": attendance,
                "muszakpro": muszakpro,
                "missing": missing,
                "match_method": (
                    "exact"
                    if attendance and muszakpro and attendance.get("match_key") == muszakpro.get("match_key")
                    else "time_tolerance"
                    if attendance and muszakpro
                    else "unmatched"
                ),
            },
        })

    return output


def supabase_headers(extra=None):
    _supabase_url, service_role_key = get_supabase_config()

    if not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    if extra:
        headers.update(extra)

    return headers


def insert_rows(table_name, rows):
    if not rows:
        return 0

    supabase_url, _service_role_key = get_supabase_config()
    endpoint = f"{supabase_url}/rest/v1/{table_name}"
    headers = supabase_headers({
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    })

    inserted = 0

    for index in range(0, len(rows), 500):
        response = requests.post(
            endpoint,
            headers=headers,
            json=rows[index:index + 500],
            timeout=60,
        )
        raise_for_supabase_error(response)
        inserted += len(rows[index:index + 500])

    return inserted


def parse_args():
    parser = argparse.ArgumentParser(
        description="fetch-attendance API es MuszakPro DB append-only osszehasonlitas."
    )
    parser.add_argument("--month", help="Honap YYYY-MM formatumban.")
    parser.add_argument("--start-date", help="Kezdo datum YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Zaro datum YYYY-MM-DD.")
    parser.add_argument(
        "--debug-email",
        default="",
        help="Kiirja az adott email MuszakPro sorait es a hozza talalt nevet.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_dates(args):
    if args.month:
        return list(month_dates(args.month))

    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end_date = (
            datetime.strptime(args.end_date, "%Y-%m-%d").date()
            if args.end_date
            else start_date
        )
        return list(date_range(start_date, end_date))

    return [datetime.now(LOCAL_TIMEZONE).date()]


def main():
    args = parse_args()
    work_dates = resolve_dates(args)
    collection_id = str(uuid.uuid4())
    collection_collected_at = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat(timespec="seconds")
    all_attendance_rows = []
    all_comparison_rows = []

    print(f"COLLECTION_ID={collection_id}")

    for work_date in work_dates:
        request_url, status_code, payload = fetch_attendance(
            work_date
        )
        attendance_rows = parse_attendance_shift_rows(
            collection_id,
            work_date,
            request_url,
            status_code,
            payload,
        )
        muszakpro_rows = read_muszakpro_rows(
            work_date
        )

        if args.debug_email:
            debug_email = clean(args.debug_email).casefold()
            print(f"\nDEBUG_EMAIL={debug_email} DATE={work_date.isoformat()}")

            for row in muszakpro_rows:
                if clean(row.get("email")).casefold() == debug_email:
                    print(
                        "MUSZAKPRO "
                        f"courier_id={row.get('courier_id')} "
                        f"courier_name={row.get('courier_name')} "
                        f"email={row.get('email')} "
                        f"warehouse={row.get('warehouse')} "
                        f"shift_text={row.get('shift_text')} "
                        f"key={row.get('match_key')}"
                    )

        comparison_rows = build_comparison_rows(
            collection_id,
            attendance_rows,
            muszakpro_rows,
        )

        for row in attendance_rows:
            row["collected_at"] = collection_collected_at

        for row in comparison_rows:
            row["collected_at"] = collection_collected_at

        all_attendance_rows.extend(attendance_rows)
        all_comparison_rows.extend(comparison_rows)
        print(
            f"{work_date.isoformat()}: attendance={len(attendance_rows)}, "
            f"muszakpro={len(muszakpro_rows)}, comparison={len(comparison_rows)}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    raw_inserted = insert_rows(
        RAW_TABLE,
        all_attendance_rows,
    )
    comparison_inserted = insert_rows(
        COMPARISON_TABLE,
        all_comparison_rows,
    )
    print(
        f"DB_INSERT raw={raw_inserted}, comparison={comparison_inserted}"
    )


if __name__ == "__main__":
    main()
