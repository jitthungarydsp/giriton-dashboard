import argparse
import calendar
import sys
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

from resources.foglalasok_db import read_foglalasok_raw, shift_start
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DSP_ID = "JIT"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
RAW_TABLE = "raw_fetch_attendance_shifts"
COMPARISON_TABLE = "ops_attendance_muszakpro_comparison"


def clean(value):
    return str(value or "").strip()


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


def db_time(value):
    text = normalize_time(value)

    if not text:
        return None

    if len(text) == 4:
        text = f"0{text}"

    if len(text) == 5:
        return f"{text}:00"

    return text


def normalize_warehouse(value):
    text = clean(value).upper()

    if "BUD1" in text or text == "1":
        return "BUD1"

    if "BUD2" in text or text == "2":
        return "BUD2"

    return text


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


def make_match_key(work_date, courier_id, email, courier_name, warehouse, start):
    person = clean(courier_id) or clean(email).casefold() or clean(courier_name).casefold()

    return "|".join([
        clean(work_date),
        person,
        normalize_warehouse(warehouse).casefold(),
        normalize_time(start),
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

            match_key = make_match_key(
                work_date_text,
                courier_id,
                "",
                courier_name,
                warehouse,
                start_text,
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

    rows = []

    for _, row in df.iterrows():
        work_date_text = clean(row.get("work_date"))[:10]
        shift_text = clean(row.get("shift_text"))
        start = shift_start(shift_text)
        courier_id = optional_int(row.get("courier_id"))
        email = clean(row.get("email")).casefold()
        courier_name = clean(row.get("courier_name"))
        warehouse = normalize_warehouse(row.get("warehouse"))

        if not work_date_text or not start:
            continue

        match_key = make_match_key(
            work_date_text,
            courier_id,
            email,
            courier_name,
            warehouse,
            start,
        )
        rows.append({
            "match_key": match_key,
            "work_date": work_date_text,
            "courier_id": courier_id,
            "courier_name": courier_name,
            "email": email,
            "warehouse": warehouse,
            "shift_start": start,
            "shift_text": shift_text,
            "booking_code": clean(row.get("booking_code")),
        })

    return rows


def build_comparison_rows(collection_id, attendance_rows, muszakpro_rows):
    attendance_by_key = {
        row["match_key"]: row
        for row in attendance_rows
    }
    muszakpro_by_key = {
        row["match_key"]: row
        for row in muszakpro_rows
    }
    output = []

    for match_key in sorted(set(attendance_by_key) | set(muszakpro_by_key)):
        attendance = attendance_by_key.get(match_key, {})
        muszakpro = muszakpro_by_key.get(match_key, {})
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
        comparison_rows = build_comparison_rows(
            collection_id,
            attendance_rows,
            muszakpro_rows,
        )
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
