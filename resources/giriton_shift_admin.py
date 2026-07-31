from datetime import date, datetime, timedelta
from pathlib import Path
import os
import platform
import subprocess
from uuid import uuid4

import pandas as pd
import requests

from resources.giriton_shifts_db import read_giriton_shifts_raw
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_EXPORT_ROBOT = PROJECT_ROOT / "giriton_raw_export_github.robot"
DELETE_ROBOT = PROJECT_ROOT / "giriton_shift_delete_github.robot"
ADMIN_LOG_TABLE = "ops_giriton_shift_admin_log"


def clean(value):
    return str(value or "").strip()


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


def normalize_courier_id(value):
    text = clean(value)
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def can_run_robot_locally():
    if os.getenv("ALLOW_STREAMLIT_ROBOT_RUN") == "true":
        return True
    system = platform.system().lower()
    project_text = str(PROJECT_ROOT).replace("\\", "/")
    return not (system == "linux" and project_text.startswith("/home/appuser"))


def next_days_window(days=10):
    start = date.today()
    return start, start + timedelta(days=max(int(days), 1) - 1)


def read_next_giriton_shifts(days=10):
    start, end = next_days_window(days)
    return read_giriton_shifts_raw(start_date=start, end_date=end, limit=20000)


def filter_booked_shift_rows(df):
    if df is None or df.empty:
        return pd.DataFrame()
    rows = df.copy()
    if "status" in rows.columns:
        rows = rows[rows["status"].astype(str).str.upper() != "URES"]
    if "courier_name" in rows.columns:
        rows = rows[
            ~rows["courier_name"].astype(str).str.upper().isin(["URES", "(NONE)", ""])
        ]
    return rows


def serial_from_row(row):
    return clean(row.get("serial"))


def raw_export_command(start_date=None, days=10):
    command = [
        "robot",
        "--variable",
        f"RUN_START_DATE:{clean(start_date)}",
        "--variable",
        f"DAYS_TO_SYNC:{int(days)}",
        str(RAW_EXPORT_ROBOT),
    ]
    return command


def delete_command(serial="", work_date="", warehouse="", shift_start="", courier_id="", courier_name=""):
    return [
        "robot",
        "--variable",
        f"DELETE_SERIAL:{clean(serial)}",
        "--variable",
        f"DELETE_WORK_DATE:{clean(work_date)}",
        "--variable",
        f"DELETE_WAREHOUSE:{clean(warehouse).upper()}",
        "--variable",
        f"DELETE_SHIFT_START:{normalize_time(shift_start)}",
        "--variable",
        f"DELETE_COURIER_ID:{normalize_courier_id(courier_id)}",
        "--variable",
        f"DELETE_COURIER_NAME:{clean(courier_name)}",
        str(DELETE_ROBOT),
    ]


def command_text(command):
    return " ".join(f'"{item}"' if " " in str(item) else str(item) for item in command)


def run_command(command, timeout=60 * 60):
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _headers():
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


def log_admin_action(action, status, actor="", payload=None, message=""):
    supabase_url, headers = _headers()
    row = {
        "id": str(uuid4()),
        "source_name": "giriton-admin-page",
        "action": clean(action),
        "status": clean(status),
        "actor": clean(actor),
        "message": clean(message),
        "payload": payload or {},
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if not supabase_url:
        return "SKIPPED_NO_SUPABASE"
    response = requests.post(
        f"{supabase_url}/rest/v1/{ADMIN_LOG_TABLE}",
        headers=headers,
        json=[row],
        timeout=30,
    )
    if _is_missing_table_response(response):
        return "SKIPPED_MISSING_TABLE"
    raise_for_supabase_error(response)
    return "OK"


def read_admin_action_log(limit=500):
    supabase_url, headers = _headers()
    if not supabase_url:
        return pd.DataFrame()
    params = {
        "select": "created_at,actor,action,status,message,payload",
        "order": "created_at.desc",
        "limit": str(int(limit)),
    }
    response = requests.get(
        f"{supabase_url}/rest/v1/{ADMIN_LOG_TABLE}",
        headers=headers,
        params=params,
        timeout=30,
    )
    if _is_missing_table_response(response):
        return pd.DataFrame()
    raise_for_supabase_error(response)
    return pd.DataFrame(response.json())
