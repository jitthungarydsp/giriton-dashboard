from datetime import datetime, timedelta
from pathlib import Path
import os
import sys
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.foglalasok_db import (
    clean,
    normalize_time,
    read_foglalasok_raw,
    shift_start,
)
from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
LOG_TABLE = "ops_giriton_auto_booking_log"
ROBOTLOG_SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
ROBOTLOG_WORKSHEET_GID = "1456041177"
ROBOTLOG_WORKSHEET_NAME = "ROBOTLOG"
ROBOTLOG_HEADER = [
    "Időpont",
    "Email",
    "Típus",
    "Részletek",
    "Serial",
]
ROBOTLOG_SUCCESS_STATUSES = {
    "COURIER_ADDED",
    "COURIER_ADDED_UNVERIFIED",
    "ALREADY_BOOKED",
}


def _today_budapest():
    return datetime.now(BUDAPEST_TZ).date()


def _parse_date(value):
    text = clean(value)

    if not text:
        return None

    return datetime.strptime(text, "%Y-%m-%d").date()


def _format_giriton_date(value):
    work_date = _parse_date(value)

    if not work_date:
        return ""

    return work_date.strftime("%d/%m/%Y")


def _normalize_warehouse(value):
    text = clean(value).upper()

    if "BUD1" in text:
        return "BUD1"

    if "BUD2" in text:
        return "BUD2"

    return clean(value)


def _candidate_key(row):
    return (
        clean(row.get("work_date")),
        _normalize_warehouse(row.get("warehouse")),
        normalize_time(row.get("shift_start")),
        clean(row.get("courier_name")).casefold(),
        clean(row.get("email")).casefold(),
    )


def _matches_filter(candidate, serial="", courier_id="", email="", warehouse="", shift_start=""):
    serial = clean(serial)
    courier_id = clean(courier_id)
    email = clean(email).casefold()
    warehouse = _normalize_warehouse(warehouse)
    shift_start = normalize_time(shift_start)

    if serial and clean(candidate.get("serial")) != serial:
        return False

    if courier_id and clean(candidate.get("courier_id")) != courier_id:
        return False

    if email and clean(candidate.get("email")).casefold() != email:
        return False

    if warehouse and _normalize_warehouse(candidate.get("warehouse")) != warehouse:
        return False

    if shift_start and not serial and normalize_time(candidate.get("shift_start")) != shift_start:
        return False

    return True


def _build_candidate(row):
    shift_text = clean(row.get("shift_text"))
    start = shift_start(shift_text)
    work_date = clean(row.get("work_date"))

    return {
        "work_date": work_date,
        "giriton_date": _format_giriton_date(work_date),
        "warehouse": _normalize_warehouse(row.get("warehouse")),
        "shift_text": shift_text,
        "shift_start": normalize_time(start),
        "booking_code": clean(row.get("booking_code")),
        "courier_id": clean(row.get("courier_id")),
        "courier_name": clean(row.get("courier_name")),
        "email": clean(row.get("email")).casefold(),
        "serial": clean(row.get("serial")),
    }


def get_t_plus_booking_candidates(
    days_ahead=0,
    horizon_days=1,
    start_date="",
    end_date="",
    limit=10000,
    serial="",
    courier_id="",
    email="",
    warehouse="",
    shift_start_filter="",
):
    """Return Foglalasok rows that the Giriton auto-booking robot should process."""

    if start_date:
        from_date = _parse_date(start_date)
    else:
        from_date = _today_budapest() + timedelta(days=int(days_ahead))

    if end_date:
        to_date = _parse_date(end_date)
    else:
        to_date = from_date + timedelta(days=max(int(horizon_days), 1) - 1)

    df = read_foglalasok_raw(
        start_date=from_date.isoformat(),
        end_date=to_date.isoformat(),
        limit=int(limit),
    )

    if df.empty:
        return []

    candidates = []
    seen = set()

    for row in df.to_dict("records"):
        candidate = _build_candidate(row)

        if not candidate["work_date"]:
            continue

        if not candidate["shift_start"]:
            continue

        if not candidate["warehouse"]:
            continue

        if not candidate["courier_id"] and not candidate["courier_name"]:
            continue

        if not _matches_filter(
            candidate,
            serial=serial,
            courier_id=courier_id,
            email=email,
            warehouse=warehouse,
            shift_start=shift_start_filter,
        ):
            continue

        target_shift_start = normalize_time(shift_start_filter)
        if serial and target_shift_start:
            candidate["shift_start"] = target_shift_start
            candidate["shift_text"] = f"{candidate['warehouse']}_{target_shift_start}"

        key = _candidate_key(candidate)

        if key in seen:
            continue

        seen.add(key)
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            item["work_date"],
            item["warehouse"],
            item["shift_start"],
            item["courier_name"].casefold(),
            item["email"],
        )
    )

    return candidates


def build_screenshot_name(candidate, step):
    candidate = candidate or {}
    step = clean(step) or "screenshot"
    parts = [
        clean(candidate.get("work_date")),
        clean(candidate.get("warehouse")),
        clean(candidate.get("shift_start")).replace(":", ""),
        clean(candidate.get("courier_id")) or clean(candidate.get("courier_name")),
        step,
        datetime.utcnow().strftime("%Y%m%d%H%M%S"),
    ]
    raw_name = "_".join(part for part in parts if part)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_name).strip("._")

    return f"{safe_name or 'giriton_auto_booking'}.png"


def _robotlog_spreadsheet_id():
    return os.getenv("GIRITON_ROBOTLOG_SPREADSHEET_ID", ROBOTLOG_SPREADSHEET_ID)


def _robotlog_worksheet_gid():
    return os.getenv("GIRITON_ROBOTLOG_WORKSHEET_GID", ROBOTLOG_WORKSHEET_GID)


def _robotlog_worksheet_name():
    return os.getenv("GIRITON_ROBOTLOG_WORKSHEET", ROBOTLOG_WORKSHEET_NAME)


def _get_or_create_robotlog_worksheet(spreadsheet):
    import gspread

    worksheet_gid = clean(_robotlog_worksheet_gid())
    if worksheet_gid.isdigit():
        try:
            worksheet = spreadsheet.get_worksheet_by_id(int(worksheet_gid))
            if worksheet is not None:
                return worksheet
        except Exception:
            pass

    worksheet_name = _robotlog_worksheet_name()
    try:
        return spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(ROBOTLOG_HEADER),
        )


def _format_robotlog_timestamp():
    return datetime.now(BUDAPEST_TZ).strftime("%Y.%m.%d. %H:%M:%S")


def _format_robotlog_shift(candidate):
    warehouse = _normalize_warehouse(candidate.get("warehouse"))
    shift_start_value = normalize_time(candidate.get("shift_start"))
    if warehouse and shift_start_value:
        return f"{warehouse}_{shift_start_value}"
    return clean(candidate.get("shift_text"))


def _append_success_robotlog(candidate, status):
    if clean(status) not in ROBOTLOG_SUCCESS_STATUSES:
        return "SKIPPED_STATUS"

    from resources.google_auth import get_client

    candidate = candidate or {}
    worksheet = _get_or_create_robotlog_worksheet(
        get_client().open_by_key(_robotlog_spreadsheet_id())
    )
    values = worksheet.get_all_values()

    if not values:
        worksheet.update(
            "A1",
            [ROBOTLOG_HEADER],
            value_input_option="USER_ENTERED",
        )

    work_date = clean(candidate.get("work_date"))
    warehouse = _normalize_warehouse(candidate.get("warehouse"))
    row = [
        _format_robotlog_timestamp(),
        clean(candidate.get("email")).casefold(),
        "FOGLALÁS",
        f"Dátum: {work_date}, Műszak: {_format_robotlog_shift(candidate)}, Raktár: {warehouse}",
        clean(candidate.get("serial")),
    ]
    worksheet.append_row(
        row,
        value_input_option="USER_ENTERED",
    )

    return "OK"


def log_success_robotlog_write(candidate, status):
    """Write the successful booking row to the ROBOTLOG sheet and return a visible result."""

    try:
        result = _append_success_robotlog(candidate, status)
    except Exception as exc:
        result = f"ERROR:{str(exc).replace(chr(10), ' ')[:300]}"

    print(f"GIRITON_ROBOTLOG_WRITE status={clean(status)} result={result}")
    return result


def _supabase_headers():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return "", {}

    return supabase_url.rstrip("/"), {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _is_missing_table_response(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()
    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def log_giriton_booking_result(candidate, status, message=""):
    """Append one auto-booking robot result row to Supabase when the log table exists."""

    candidate = candidate or {}
    supabase_url, headers = _supabase_headers()

    if not supabase_url:
        print(
            "GIRITON_AUTO_BOOK_LOG_SKIPPED missing Supabase config "
            f"status={status} message={message}"
        )
        return "SKIPPED_NO_SUPABASE"

    now_utc = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    row = {
        "id": str(uuid4()),
        "source_name": "giriton-auto-booking-robot",
        "work_date": clean(candidate.get("work_date")) or None,
        "courier_id": int(candidate["courier_id"]) if clean(candidate.get("courier_id")).isdigit() else None,
        "courier_name": clean(candidate.get("courier_name")),
        "email": clean(candidate.get("email")).casefold(),
        "warehouse": clean(candidate.get("warehouse")),
        "shift_text": clean(candidate.get("shift_text")),
        "shift_start": clean(candidate.get("shift_start")),
        "booking_code": clean(candidate.get("booking_code")),
        "serial": clean(candidate.get("serial")),
        "status": clean(status),
        "message": clean(message),
        "response_json": candidate,
        "created_at": now_utc,
    }
    endpoint = f"{supabase_url}/rest/v1/{LOG_TABLE}"
    response = requests.post(
        endpoint,
        headers=headers,
        json=[row],
        timeout=30,
    )

    if _is_missing_table_response(response):
        print(
            f"GIRITON_AUTO_BOOK_LOG_TABLE_MISSING status={status} message={message}"
        )
        return "SKIPPED_MISSING_TABLE"

    raise_for_supabase_error(response)

    return "OK"


def read_giriton_booking_log(start_date="", end_date="", limit=500):
    supabase_url, headers = _supabase_headers()

    if not supabase_url:
        return pd.DataFrame()

    params = {
        "select": (
            "created_at,work_date,courier_id,courier_name,email,warehouse,"
            "shift_text,shift_start,booking_code,serial,status,message"
        ),
        "order": "created_at.desc",
        "limit": str(int(limit)),
    }

    if start_date:
        params["work_date"] = f"gte.{clean(start_date)}"

    if end_date:
        params["work_date"] = f"lte.{clean(end_date)}"

    response = requests.get(
        f"{supabase_url}/rest/v1/{LOG_TABLE}",
        headers=headers,
        params=params,
        timeout=30,
    )

    if _is_missing_table_response(response):
        return pd.DataFrame()

    raise_for_supabase_error(response)
    return pd.DataFrame(response.json())


def latest_log_by_serial(log_df):
    if log_df is None or log_df.empty or "serial" not in log_df.columns:
        return {}

    rows = log_df.copy()
    rows["serial"] = rows["serial"].fillna("").astype(str)
    rows = rows[rows["serial"] != ""]

    if "created_at" in rows.columns:
        rows = rows.sort_values("created_at", ascending=False)

    latest = {}

    for row in rows.to_dict("records"):
        serial = clean(row.get("serial"))

        if serial and serial not in latest:
            latest[serial] = row

    return latest
