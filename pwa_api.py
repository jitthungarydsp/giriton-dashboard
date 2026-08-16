import hashlib
import hmac
import base64
import json
import os
import re
import secrets
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import tomllib
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from resources.email_sender import send_login_credentials, send_message, smtp_config, validate_email
from resources.pwa_invoice_validation import MAX_INVOICE_BYTES, extract_expected_amount, validate_invoice
from resources.pwa_users_db import (
    authenticate_pwa_db_user,
    change_pwa_user_password,
    find_pwa_user_by_login,
    public_pwa_user,
    reset_pwa_user_password,
)
from resources.security import hash_password, verify_password
from resources.users import generate_password
from resources.settlement_pdf import build_tig_breakdown, build_tig_pdf

try:
    from cryptography.hazmat.primitives import serialization
except Exception:  # pragma: no cover - optional local fallback
    serialization = None


PROJECT_ROOT = Path(__file__).resolve().parent
PWA_ROOT = PROJECT_ROOT / "pwa"
USERS_FILE = PROJECT_ROOT / "data" / "users.json"
LOCAL_SESSION_SECRET_FILE = PROJECT_ROOT / ".pwa_session_secret"
LOCAL_VAPID_PRIVATE_FILE = PROJECT_ROOT / "vapid_private.pem"
SESSION_COOKIE = "giriton_pwa_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_DEVICE_PHOTO_BYTES = 8 * 1024 * 1024
MAX_DEVICE_PHOTOS = 8
DEVICE_PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
FINANCIAL_LOOKUP_CACHE_SECONDS = 60
_FINANCIAL_LOOKUP_CACHE: dict[tuple[str, str, str], tuple[float, Any]] = {}

COURIER_DETAIL_API_BASE = (
    "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
)
COURIER_DETAIL_ORGANIZATION_ID = (
    "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
)
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


class LoginRequest(BaseModel):
    username: str
    password: str


class RegistrationRequest(BaseModel):
    courier_id: str
    courier_name: str
    phone_number: str
    email: str


class PasswordResetRequest(BaseModel):
    courier_id: str
    email: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class WorkflowActionRequest(BaseModel):
    month: str
    process: str = ""


class SalaryAdvanceRequest(BaseModel):
    start_date: str
    requested_amount_huf: int
    installment_months: int
    note: str = ""


class ComplaintRequest(BaseModel):
    month: str
    action: str
    message: str
    process: str = ""


class RouteDelayAlertRequest(BaseModel):
    route_id: str | int
    order_id: str = ""
    message: str
    dispatcher_notified: bool = False
    current_address: str = ""
    current_checkpoint_position: int | None = None


class RouteNoteRequest(BaseModel):
    work_date: str
    route_id: str
    note: str = ""


class ShiftDelayAlertRequest(BaseModel):
    work_date: str
    start: str = ""
    end: str = ""
    warehouse: str = ""
    shift_name: str = ""
    booking_code: str = ""
    message: str = ""


class ShiftQueueCheckinRequest(BaseModel):
    work_date: str
    start: str = ""
    end: str = ""
    warehouse: str = ""
    shift_name: str = ""
    booking_code: str = ""
    event_type: str = "queued"


class BillingProfileUpdate(BaseModel):
    courier_id: str = ""
    courier_name: str = ""
    phone_number: str = ""
    company_name: str = ""
    company_address: str = ""
    tax_number: str = ""
    bank_account_number: str = ""
    billing_email: str = ""


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: str = ""


class CoordinatorAdjustmentRequest(BaseModel):
    kind: str
    courier_id: str
    item_id: str
    amount_huf: int
    note: str = ""
    effective_date: str


class CoordinatorAdjustmentDeleteRequest(BaseModel):
    reason: str


def load_setting(name: str) -> str:
    def clean(value: Any) -> str:
        text = str(value or "").strip()
        if (
            len(text) >= 2
            and text[0] == text[-1]
            and text[0] in {"'", '"'}
        ):
            text = text[1:-1].strip()
        return text.replace("\\n", "\n")

    value = os.getenv(name, "")
    if value:
        return clean(value)

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            settings = tomllib.load(file)
        value = (
            settings.get(name)
            or settings.get("supabase", {}).get(name)
            or settings.get("discord", {}).get(name)
            or settings.get("pwa", {}).get(name)
        )
        return clean(value)
    except Exception:
        return ""


def supabase_key_headers(key: str) -> dict[str, str]:
    """Support both legacy JWT service-role keys and the new sb_secret_ keys."""
    clean_key = str(key or "").strip()
    headers = {"apikey": clean_key}
    if clean_key and not clean_key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {clean_key}"
    return headers


def session_secret() -> bytes:
    value = load_setting("PWA_SESSION_SECRET") or load_setting("AUTH_TOKEN_SECRET")
    if not value and LOCAL_SESSION_SECRET_FILE.exists():
        value = LOCAL_SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()
    if not value:
        value = secrets.token_urlsafe(48)
        LOCAL_SESSION_SECRET_FILE.write_text(value, encoding="utf-8")
    return value.encode("utf-8")


def load_users() -> list[dict[str, Any]]:
    with USERS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file).get("users", [])


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(user.get("username") or ""),
        "courierId": str(user.get("courierId") or ""),
        "role": str(user.get("role") or "user"),
        "canPreviewCouriers": can_preview_couriers(user),
    }


def can_preview_couriers(user: dict[str, Any]) -> bool:
    username_key = normalize_text(user.get("username"))
    role = str(user.get("role") or "").strip().lower()
    trainer_key = normalize_text(user.get("trainer"))
    return (
        role in {"admin", "coordinator", "superadmin"}
        or username_key in {normalize_text("admin"), normalize_text("Bagoly Zoltán")}
        or trainer_key == normalize_text("admin")
    )


def can_view_financial_amounts(user: dict[str, Any]) -> bool:
    return can_preview_couriers(user)


def is_unrestricted_legacy_settlement_month(month: date) -> bool:
    return month.replace(day=1) == date(2026, 6, 1)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    try:
        db_user = authenticate_pwa_db_user(username, password)
        if db_user:
            return db_user
    except Exception:
        # If the DB user table is not deployed yet, keep the legacy users.json login working.
        pass

    wanted = str(username or "").strip().casefold()
    for user in load_users():
        if not user.get("active", True):
            continue
        if str(user.get("username") or "").strip().casefold() != wanted:
            continue

        password_hash = str(user.get("passwordHash") or "")
        if password_hash and verify_password(password, password_hash):
            return user
        if user.get("password") == password:
            return user
    return None


def user_courier_id(user: dict[str, Any]) -> str:
    return str(user.get("courierId") or user.get("courier_id") or "").strip()


def find_user_by_courier_id(courier_id: str) -> dict[str, Any] | None:
    clean_id = normalize_profile_courier_id(courier_id)
    for user in load_users():
        if not user.get("active", True):
            continue
        if user_courier_id(user) == clean_id:
            return user
    return None


def save_legacy_users_data(data: dict[str, Any]) -> None:
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def change_legacy_user_password(user: dict[str, Any], current_password: str, new_password: str) -> bool:
    target_courier_id = user_courier_id(user)
    target_username = str(user.get("username") or "").strip()
    if not target_courier_id and not target_username:
        return False
    with USERS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    for row in data.get("users", []):
        same_courier = target_courier_id and user_courier_id(row) == target_courier_id
        same_username = target_username and str(row.get("username") or "").strip() == target_username
        if not (same_courier or same_username):
            continue
        password_hash = str(row.get("passwordHash") or "")
        password_ok = bool(password_hash and verify_password(current_password, password_hash))
        if not password_ok:
            password_ok = row.get("password") == current_password
        if not password_ok:
            raise HTTPException(status_code=403, detail="A jelenlegi jelszó nem megfelelő.")
        row["password"] = new_password
        row["passwordHash"] = hash_password(new_password)
        row["token"] = ""
        row["passwordUpdatedAt"] = datetime.now(timezone.utc).isoformat()
        save_legacy_users_data(data)
        return True
    return False


def reset_legacy_user_password_for_courier(courier_id: str) -> dict[str, str] | None:
    clean_id = normalize_profile_courier_id(courier_id)
    if not clean_id:
        return None
    with USERS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    password = generate_password()
    for row in data.get("users", []):
        if not row.get("active", True):
            continue
        if user_courier_id(row) != clean_id:
            continue
        row["password"] = password
        row["passwordHash"] = hash_password(password)
        row["token"] = ""
        row["passwordUpdatedAt"] = datetime.now(timezone.utc).isoformat()
        save_legacy_users_data(data)
        return {
            "username": str(row.get("username") or "").strip(),
            "password": password,
        }
    return None


def normalize_email_address(value: str) -> str:
    try:
        return validate_email(str(value or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Az e-mail cím formátuma hibás.") from exc


def create_session(user: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(user.get("username") or ""),
            str(user.get("courierId") or ""),
            str(int(time.time())),
            secrets.token_urlsafe(10),
        ]
    )
    signature = hmac.new(session_secret(), payload.encode("utf-8"), hashlib.sha256)
    return f"{payload}.{signature.hexdigest()}"


def read_session(token: str) -> dict[str, Any] | None:
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(
            session_secret(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None

        username, courier_id, issued_at, _nonce = payload.split("|", 3)
        if time.time() - int(issued_at) > SESSION_TTL_SECONDS:
            return None
    except (ValueError, TypeError):
        return None

    for user in load_users():
        if not user.get("active", True):
            continue
        if str(user.get("username") or "") != username:
            continue
        if str(user.get("courierId") or "") != courier_id:
            continue
        return user

    try:
        db_user = find_pwa_user_by_login(username)
    except Exception:
        db_user = None
    if db_user and bool(db_user.get("active", True)):
        db_courier_id = str(db_user.get("courier_id") or db_user.get("courierId") or "")
        if db_courier_id == courier_id:
            return public_pwa_user(db_user)
    return None


def require_user(token: str | None) -> dict[str, Any]:
    user = read_session(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="Bejelentkezés szükséges.")
    return user


def require_coordinator(user: dict[str, Any]) -> dict[str, Any]:
    role = str(user.get("role") or "").strip().lower()
    if role not in {"admin", "coordinator"}:
        raise HTTPException(
            status_code=403,
            detail="Ehhez a funkcióhoz koordinátori vagy admin jogosultság szükséges.",
        )
    return user


COORDINATOR_ITEM_TABLES = {
    "bonus": "cfg_coordinator_bonus_items",
    "malus": "cfg_coordinator_malus_items",
}
COORDINATOR_ENTRY_TABLES = {
    "bonus": "ops_coordinator_bonus_entries",
    "malus": "ops_coordinator_malus_entries",
}


def coordinator_table(mapping: dict[str, str], kind: str) -> str:
    kind = str(kind or "").strip().lower()
    if kind not in mapping:
        raise HTTPException(status_code=422, detail="A típus csak bonus vagy malus lehet.")
    return mapping[kind]


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def normalized_field_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def normalize_time(value: Any) -> str:
    text = str(value or "").strip().replace(".", ":")
    if not text:
        return ""
    parts = text.split(":")
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]) if len(parts) > 1 else 0:02d}"
    except ValueError:
        return text[:5]


def shift_start(value: Any) -> str:
    text = str(value or "").strip()
    for separator in ("-", "–", "—"):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return normalize_time(text)


def normalize_warehouse(value: Any) -> str:
    text = normalize_text(value).replace("_", "").replace(" ", "")
    aliases = {
        "budapest": "BUD",
        "bud1": "BUD1",
        "bud2": "BUD2",
        "bud1jit": "BUD1",
        "bud2jit": "BUD2",
    }
    return aliases.get(text, str(value or "").strip().upper())


def discord_webhook_for_shift(warehouse: str) -> str:
    coordinator_webhook = load_setting("DISCORD_COORDINATOR_WEBHOOK_URL")
    if coordinator_webhook:
        return coordinator_webhook

    normalized = normalize_warehouse(warehouse)
    if normalized:
        warehouse_webhook = load_setting(f"DISCORD_WEBHOOK_URL_{normalized}")
        if warehouse_webhook:
            return warehouse_webhook

    return load_setting("DISCORD_WEBHOOK_URL")


def send_shift_delay_discord_alert(user: dict[str, Any], payload: ShiftDelayAlertRequest) -> None:
    courier_id, courier_name = courier_identity(user)
    profile = read_billing_profile(user)
    phone_number = str(profile.get("phone_number") or user.get("phone") or "-").strip() or "-"
    warehouse = normalize_warehouse(payload.warehouse) or payload.warehouse.strip() or "-"
    webhook_url = discord_webhook_for_shift(warehouse)
    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="A koordinátori Discord webhook nincs beállítva.",
        )

    shift_time = payload.start.strip() or "?"
    if payload.end.strip():
        shift_time = f"{shift_time}-{payload.end.strip()}"
    shift_name = payload.shift_name.strip() or payload.booking_code.strip() or "Műszak"
    work_date = payload.work_date.strip() or date.today().isoformat()
    message = payload.message.strip()

    lines = [
        "🚨 **ALERT: KÉSÉS A MŰSZAKBÓL** 🚨",
        "",
        f"**Futár:** {courier_name} `#{courier_id}`",
        f"**Telefon:** `{phone_number}`",
        f"**Raktár:** `{warehouse}`",
        f"**Műszak:** {work_date} {shift_time} · {shift_name}",
    ]
    if message:
        lines.append(f"**Megjegyzés:** {message}")

    response = requests.post(
        webhook_url,
        json={"content": "\n".join(lines)},
        timeout=15,
    )
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"A Discord értesítés nem ment ki: HTTP {response.status_code}",
        )


def supabase_rows(table: str, select: str, start: date, end: date) -> list[dict]:
    url = load_setting("SUPABASE_URL").rstrip("/")
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY").strip()
    if not url or not key:
        raise RuntimeError("Hiányzik a Supabase konfiguráció.")

    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers=supabase_key_headers(key),
        params={
            "select": select,
            "work_date": f"gte.{start.isoformat()}",
            "order": "work_date.asc",
            "limit": "10000",
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return [row for row in rows if str(row.get("work_date") or "") <= end.isoformat()]



def read_giriton_future_shifts(
    user: dict[str, Any],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    courier_id, courier_name = courier_identity(user)

    print(
        "Giriton shifts query:",
        {
            "courier_id": courier_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )

    rows = supabase_rest(
        "GET",
        "giriton_future_shifts_latest",
        params={
            "select": (
                "work_date,courier_id,courier_name,warehouse_name,"
                "shift_id,shift_name,shift_start,shift_end,fetched_at"
            ),
            "courier_id": f"eq.{courier_id}",
            "work_date": f"gte.{start.isoformat()}",
            "order": "shift_start.asc",
            "limit": "500",
        },
    )

    print("Giriton shifts rows:", rows)

    result: list[dict[str, Any]] = []
    budapest_timezone = ZoneInfo("Europe/Budapest")

    for row in rows:
        work_date = str(row.get("work_date") or "").strip()
        if not work_date or work_date > end.isoformat():
            continue

        shift_start_text = str(row.get("shift_start") or "").strip()
        shift_end_text = str(row.get("shift_end") or "").strip()

        if not shift_start_text:
            continue

        # A Supabase UTC időpontjait biztosan időzónás datetime-ként értelmezzük.
        if shift_start_text.endswith("Z"):
            shift_start_text = shift_start_text[:-1] + "+00:00"
        if shift_end_text.endswith("Z"):
            shift_end_text = shift_end_text[:-1] + "+00:00"

        try:
            shift_start_value = datetime.fromisoformat(shift_start_text)
            shift_end_value = (
                datetime.fromisoformat(shift_end_text)
                if shift_end_text
                else None
            )
        except ValueError as exc:
            print(
                "Invalid shift datetime:",
                {
                    "shift_start": shift_start_text,
                    "shift_end": shift_end_text,
                    "error": str(exc),
                },
            )
            continue

        if shift_start_value.tzinfo is None:
            shift_start_value = shift_start_value.replace(tzinfo=timezone.utc)

        if shift_end_value is not None and shift_end_value.tzinfo is None:
            shift_end_value = shift_end_value.replace(tzinfo=timezone.utc)

        local_start = shift_start_value.astimezone(budapest_timezone)
        local_end = (
            shift_end_value.astimezone(budapest_timezone)
            if shift_end_value is not None
            else None
        )

        print(
            "Shift timezone debug:",
            shift_start_text,
            "=>",
            local_start.isoformat(),
        )

        result.append(
            {
                "work_date": local_start.date().isoformat(),
                "start_time": local_start.strftime("%H:%M"),
                "end_time": local_end.strftime("%H:%M") if local_end else "",
                "warehouse": str(row.get("warehouse_name") or ""),
                "courier_name": str(row.get("courier_name") or courier_name),
                "courier_id": str(row.get("courier_id") or courier_id),
                "status": "ACTIVE",
                "fetched_at": row.get("fetched_at"),
                "shift_id": row.get("shift_id"),
                "shift_name": str(row.get("shift_name") or ""),
            }
        )

    print("Giriton converted shifts:", result)
    return result


def belongs_to_user(row: dict, user: dict) -> bool:
    courier_id = str(user.get("courierId") or "").strip()
    row_id = str(row.get("courier_id") or "").strip()
    if courier_id and row_id:
        return courier_id == row_id
    return normalize_text(row.get("courier_name")) == normalize_text(user.get("username"))


def canonical_key(row: dict, source: str) -> tuple[str, str]:
    start = row.get("start_time") if source == "giriton" else shift_start(row.get("shift_text"))
    return (
        str(row.get("work_date") or ""),
        normalize_time(start),
    )


def latest_by_key(rows: list[dict], user: dict, source: str) -> dict[tuple, dict]:
    result: dict[tuple, dict] = {}
    for row in rows:
        if not belongs_to_user(row, user):
            continue
        if source == "giriton" and str(row.get("status") or "").upper() == "URES":
            continue
        if source == "muszakpro" and str(row.get("status") or "ACTIVE").upper() == "CANCELLED":
            continue
        key = canonical_key(row, source)
        previous = result.get(key)
        if not previous or str(row.get("fetched_at") or "") >= str(previous.get("fetched_at") or ""):
            result[key] = row
    return result


def comparison_shift_status(row: dict[str, Any]) -> tuple[str, str]:
    attendance_ok = str(row.get("attendance_status") or "").strip().upper() == "OK"
    muszakpro_ok = str(row.get("muszakpro_status") or "").strip().upper() == "OK"
    if attendance_ok and muszakpro_ok:
        return "confirmed", "Attendance-ben is rögzítve"
    if muszakpro_ok:
        return "waiting", "Attendance-feltöltésre vár"
    if attendance_ok:
        return "review", "MűszakProban nincs rögzítve"
    return "review", "Eltérés – ellenőrzés szükséges"


def read_attendance_muszakpro_shifts(
    user: dict[str, Any],
    start: date,
    end: date,
    days: int,
) -> list[dict[str, Any]]:
    table_name = (
        "vw_attendance_muszakpro_next_5_days"
        if days <= 5
        else "vw_attendance_muszakpro_latest_comparison"
    )
    rows = supabase_rows(
        table_name,
        (
            "work_date,courier_id,courier_name,warehouse,shift_start,shift_end,"
            "attendance_status,muszakpro_status,missing_source,"
            "attendance_shift_id,attendance_shift_name,muszakpro_shift_text,"
            "muszakpro_booking_code,collected_at"
        ),
        start,
        end,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        if not belongs_to_user(row, user):
            continue
        status, status_label = comparison_shift_status(row)
        attendance_ok = str(row.get("attendance_status") or "").strip().upper() == "OK"
        muszakpro_ok = str(row.get("muszakpro_status") or "").strip().upper() == "OK"
        items.append(
            {
                "date": str(row.get("work_date") or ""),
                "start": normalize_time(row.get("shift_start")),
                "end": normalize_time(row.get("shift_end")),
                "warehouse": str(row.get("warehouse") or ""),
                "bookingCode": str(row.get("muszakpro_booking_code") or ""),
                "status": status,
                "statusLabel": status_label,
                "giriton": attendance_ok,
                "attendance": attendance_ok,
                "muszakpro": muszakpro_ok,
                "missingSource": str(row.get("missing_source") or ""),
                "attendanceShiftName": str(row.get("attendance_shift_name") or ""),
                "muszakproShiftText": str(row.get("muszakpro_shift_text") or ""),
            }
        )
    return sorted(items, key=lambda item: (item["date"], item["start"], item["warehouse"]))


def vehicle_assignment_payload(row: dict[str, Any] | None) -> dict[str, str] | None:
    if not row:
        return None
    car = str(row.get("car") or "").strip()
    plate = str(row.get("license_plate") or "").strip()
    if not car and not plate:
        return None
    return {
        "car": car,
        "licensePlate": plate,
        "shiftStart": normalize_time(row.get("shift_start")),
        "shiftEnd": normalize_time(row.get("shift_end")),
        "shiftType": str(row.get("shift_type") or "").strip(),
        "source": str(row.get("source_name") or "").strip(),
        "fetchedAt": str(row.get("fetched_at") or "").strip(),
    }


def live_vehicle_payload(row: dict[str, Any] | None) -> dict[str, str] | None:
    if not row:
        return None
    response_json = row.get("response_json")
    driver_json = response_json if isinstance(response_json, dict) else {}
    vehicle_json = driver_json.get("vehicle") if isinstance(driver_json.get("vehicle"), dict) else {}
    plate = str(vehicle_json.get("license_plate") or row.get("license_plate") or "").strip()
    if not plate:
        return None
    status_json = driver_json.get("status") if isinstance(driver_json.get("status"), dict) else {}
    state = str(status_json.get("current_state") or row.get("current_state") or "").strip()
    source_parts = ["Élő felvétel"]
    if state:
        source_parts.append(state)
    return {
        "car": "",
        "licensePlate": plate,
        "shiftStart": normalize_time(row.get("shift_start")),
        "shiftEnd": normalize_time(row.get("shift_end")),
        "shiftType": str(row.get("shift_name") or row.get("warehouse_name") or "").strip(),
        "source": " · ".join(source_parts),
        "fetchedAt": str(row.get("last_seen_at") or row.get("fetched_at") or "").strip(),
    }


def read_live_vehicle_for_user(user: dict[str, Any]) -> dict[str, str] | None:
    courier_id = user_courier_id(user)
    courier_name = str(user.get("username") or user.get("courier_name") or user.get("name") or "").strip()
    if not courier_id and not courier_name:
        return None
    select_columns = (
        "driver_id,courier_name,warehouse_name,license_plate,current_state,"
        "route_assigned_at,shift_name,shift_start,shift_end,fetched_at,response_json"
    )
    base_params = {
        "select": select_columns,
        "order": "fetched_at.desc.nullslast,route_assigned_at.desc.nullslast",
        "limit": "10",
    }
    rows: list[dict[str, Any]] = []
    if courier_id:
        rows = optional_supabase_rows(
            "dsp_drivers_live_raw",
            params={
                **base_params,
                "driver_id": f"eq.{courier_id}",
            },
            timeout=10,
        )
    if not rows and courier_name:
        rows = optional_supabase_rows(
            "dsp_drivers_live_raw",
            params={
                **base_params,
                "courier_name": f"eq.{courier_name}",
            },
            timeout=10,
        )
    if not rows and courier_name:
        rows = optional_supabase_rows(
            "dsp_drivers_live_raw",
            params={
                **base_params,
                "courier_name": f"ilike.*{courier_name}*",
            },
            timeout=10,
        )
    if not rows:
        return None
    for row in rows:
        vehicle = live_vehicle_payload(row)
        if vehicle:
            return vehicle
    return None


def read_vehicle_assignment_rows_for_user(
    user: dict[str, Any],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    _courier_id, courier_name = courier_identity(user)
    rows = optional_supabase_rows(
        "dsp_vehicle_assignments",
        params={
            "select": "source_name,work_date,driver_name,shift_start,shift_end,car,license_plate,shift_type,fetched_at",
            "work_date": f"gte.{start.isoformat()}",
            "order": "work_date.asc,shift_start.asc.nullslast,fetched_at.desc",
            "limit": "5000",
        },
        timeout=30,
    )
    wanted_names = {
        normalize_text(courier_name),
        normalize_text(user.get("username")),
    }
    return [
        row for row in rows
        if normalize_text(row.get("driver_name")) in wanted_names
        and str(row.get("work_date") or "")[:10] <= end.isoformat()
    ]


def source_rank(source_name: Any) -> int:
    text = str(source_name or "").casefold()
    if "google" in text:
        return 0
    return 1


def best_vehicle_assignment(
    rows: list[dict[str, Any]],
    work_date: Any,
    shift_start: Any = "",
) -> dict[str, str] | None:
    date_key = str(work_date or "")[:10]
    start_key = normalize_time(shift_start)
    candidates = [row for row in rows if str(row.get("work_date") or "")[:10] == date_key]
    if not candidates:
        return None
    exact = [
        row for row in candidates
        if start_key and normalize_time(row.get("shift_start")) == start_key
    ]
    pool = exact or candidates
    pool = sorted(
        pool,
        key=lambda row: (source_rank(row.get("source_name")), str(row.get("shift_start") or ""), str(row.get("fetched_at") or "")),
        reverse=False,
    )
    return vehicle_assignment_payload(pool[0])


def attach_vehicle_assignments(
    items: list[dict[str, Any]],
    vehicle_rows: list[dict[str, Any]],
    live_vehicle: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    today_key = datetime.now(LOCAL_TIMEZONE).date().isoformat()
    for item in items:
        if live_vehicle and item.get("date") == today_key:
            item["vehicle"] = live_vehicle
        else:
            item["vehicle"] = best_vehicle_assignment(vehicle_rows, item.get("date"), item.get("start"))
    return items


def read_shifts(user: dict, days: int) -> dict[str, Any]:
    start = date.today()
    end = start + timedelta(days=days - 1)
    source_errors: list[str] = []
    vehicle_rows = read_vehicle_assignment_rows_for_user(user, start, end)
    live_vehicle = read_live_vehicle_for_user(user)

    try:
        comparison_items = read_attendance_muszakpro_shifts(user, start, end, days)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
            "items": attach_vehicle_assignments(comparison_items, vehicle_rows, live_vehicle),
            "warnings": [],
            "source": "attendance_muszakpro_comparison",
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    except Exception as exc:
        print("Attendance MuszakPro comparison shifts error:", exc)
        source_errors.append("Az új Attendance/MűszakPro műszaknézet jelenleg nem érhető el, régi forrásból próbálom.")

    try:
        giriton_raw = read_giriton_future_shifts(user, start, end)
    except Exception as exc:
        print("Giriton future shifts error:", exc)
        giriton_raw = []
        source_errors.append("A Giriton adatok jelenleg nem érhetők el.")

    try:
        muszakpro_raw = supabase_rows(
            "raw_muszakpro_bookings",
            "work_date,shift_text,warehouse,booking_code,courier_name,courier_id,status,fetched_at",
            start,
            end,
        )
    except Exception:
        try:
            muszakpro_raw = supabase_rows(
                "raw_muszakpro_bookings",
                "work_date,shift_text,warehouse,booking_code,courier_name,courier_id,fetched_at",
                start,
                end,
            )
        except Exception:
            try:
                muszakpro_raw = supabase_rows(
                    "foglalasok_raw",
                    "work_date,shift_text,warehouse,booking_code,courier_name,courier_id,fetched_at",
                    start,
                    end,
                )
            except Exception:
                muszakpro_raw = []
                source_errors.append("A MűszakPro adatok jelenleg nem érhetők el.")

    giriton = latest_by_key(giriton_raw, user, "giriton")
    muszakpro = latest_by_key(muszakpro_raw, user, "muszakpro")
    items = []
    for key in sorted(set(giriton) | set(muszakpro)):
        giriton_row = giriton.get(key)
        booking_row = muszakpro.get(key)
        source = booking_row or giriton_row or {}
        if giriton_row and booking_row:
            status = "confirmed"
            status_label = "Giritonban is rögzítve"
        elif booking_row:
            status = "waiting"
            status_label = "Giriton-feltöltésre vár"
        else:
            status = "review"
            status_label = "Eltérés – ellenőrzés szükséges"

        items.append(
            {
                "date": key[0],
                "start": key[1],
                "end": normalize_time((giriton_row or {}).get("end_time")),
                "warehouse": str(source.get("warehouse") or ""),
                "bookingCode": str((booking_row or {}).get("booking_code") or ""),
                "status": status,
                "statusLabel": status_label,
                "giriton": bool(giriton_row),
                "muszakpro": bool(booking_row),
            }
        )

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days": days,
        "items": attach_vehicle_assignments(items, vehicle_rows, live_vehicle),
        "warnings": source_errors,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }



def local_iso_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TIMEZONE).strftime("%H:%M")


def local_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TIMEZONE)


def minutes_until_route_return(route: dict[str, Any]) -> int | None:
    if route.get("realReturn"):
        return 0
    planned = local_datetime(route.get("plannedReturn"))
    if not planned:
        return None
    return max(0, int((planned - datetime.now(LOCAL_TIMEZONE)).total_seconds() // 60))


def compact_route_story_row(story: dict[str, Any] | None) -> dict[str, Any] | None:
    if not story:
        return None

    def safe_float_value(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "shiftName": str(story.get("shift_name") or ""),
        "shiftStart": str(story.get("shift_start") or ""),
        "shiftEnd": str(story.get("shift_end") or ""),
        "availableAt": str(story.get("available_at") or ""),
        "availableForShiftSince": str(story.get("available_for_shift_since") or ""),
        "queueStartedAt": str(story.get("queue_started_at") or ""),
        "routeCreatedAt": str(story.get("route_created_at") or ""),
        "courierRegisteredAt": str(story.get("courier_registered_at") or ""),
        "assignedAt": str(story.get("assigned_at") or ""),
        "loadingTime": str(story.get("loading_time") or ""),
        "plannedDeparture": str(story.get("planned_departure") or ""),
        "realDeparture": str(story.get("real_departure") or ""),
        "plannedReturn": str(story.get("planned_return") or ""),
        "realReturn": str(story.get("real_return") or ""),
        "queueEntryDeltaMinutes": safe_int(story.get("queue_entry_delta_minutes")),
        "queueWaitMinutes": safe_int(story.get("queue_wait_minutes")),
        "plannedLoadingMinutes": safe_int(story.get("planned_loading_minutes")),
        "realLoadingMinutes": safe_int(story.get("real_loading_minutes")),
        "plannedRouteMinutes": safe_int(story.get("planned_route_minutes")),
        "realRouteMinutes": safe_int(story.get("real_route_minutes")),
        "assignedToReturnMinutes": safe_int(story.get("assigned_to_return_minutes")),
        "totalRouteMinutes": safe_int(story.get("total_route_minutes")),
        "gpsDistanceKm": safe_float_value(story.get("gps_distance_km")),
        "checkpointStraightKm": safe_float_value(story.get("checkpoint_straight_km")),
        "addressCount": safe_int(story.get("address_count")),
        "timeWindowLateCount": safe_int(story.get("time_window_late_count")),
        "nextShiftDelayMinutes": safe_int(story.get("next_shift_delay_minutes")),
        "assignmentMode": str(story.get("assignment_mode") or ""),
        "storyText": str(story.get("story_text") or ""),
    }


def checkpoint_delay_minutes(checkpoint: dict[str, Any] | None) -> int:
    if not checkpoint:
        return 0
    deadline = local_datetime(checkpoint.get("deliverTill"))
    if not deadline:
        return 0
    actual = (
        local_datetime(checkpoint.get("realArrivalTime"))
        or local_datetime(checkpoint.get("estimatedArrivalTime"))
        or datetime.now(LOCAL_TIMEZONE)
    )
    return max(0, int((actual - deadline).total_seconds() // 60))


def read_current_route_story(
    courier_id: str,
    route_id: Any,
    work_date: date,
) -> dict[str, Any] | None:
    clean_route_id = str(route_id or "").strip()
    if not clean_route_id:
        return None
    rows = optional_supabase_rows(
        "mart_dsp_route_stories",
        params={
            "select": (
                "work_date,route_id,warehouse_name,shift_name,shift_start,shift_end,"
                "available_at,available_for_shift_since,queue_started_at,route_created_at,"
                "courier_registered_at,assigned_at,loading_time,planned_departure,real_departure,"
                "planned_return,real_return,queue_entry_delta_minutes,queue_wait_minutes,"
                "planned_loading_minutes,real_loading_minutes,planned_route_minutes,real_route_minutes,"
                "assigned_to_return_minutes,total_route_minutes,gps_distance_km,checkpoint_straight_km,"
                "address_count,time_window_late_count,next_shift_delay_minutes,assignment_mode,story_text"
            ),
            "courier_id": f"eq.{courier_id}",
            "route_id": f"eq.{clean_route_id}",
            "work_date": f"eq.{work_date.isoformat()}",
            "limit": "1",
        },
        timeout=30,
    )
    return compact_route_story_row(rows[0] if rows else None)


def read_latest_route_story_for_courier(courier_id: str, work_date: date) -> dict[str, Any] | None:
    rows = optional_supabase_rows(
        "mart_dsp_route_stories",
        params={
            "select": (
                "work_date,route_id,warehouse_name,shift_name,shift_start,shift_end,"
                "available_at,available_for_shift_since,queue_started_at,route_created_at,"
                "courier_registered_at,assigned_at,loading_time,planned_departure,real_departure,"
                "planned_return,real_return,queue_entry_delta_minutes,queue_wait_minutes,"
                "planned_loading_minutes,real_loading_minutes,planned_route_minutes,real_route_minutes,"
                "assigned_to_return_minutes,total_route_minutes,gps_distance_km,checkpoint_straight_km,"
                "address_count,time_window_late_count,next_shift_delay_minutes,assignment_mode,story_text"
            ),
            "courier_id": f"eq.{courier_id}",
            "work_date": f"eq.{work_date.isoformat()}",
            "order": "real_return.desc.nullsfirst,real_departure.desc.nullslast,assigned_at.desc.nullslast",
            "limit": "1",
        },
        timeout=30,
    )
    return rows[0] if rows else None


def build_route_card_from_story(story_row: dict[str, Any] | None) -> dict[str, Any] | None:
    story = compact_route_story_row(story_row)
    if not story_row or not story:
        return None
    courier_id = str(story_row.get("courier_id") or "").strip()
    courier_name = str(story_row.get("courier_name") or "").strip()
    work_date = parse_date_value(story_row.get("work_date")) or datetime.now(LOCAL_TIMEZONE).date()
    live_vehicle = read_live_vehicle_for_user({"courierId": courier_id, "username": courier_name})
    route_payload = {
        "routeId": str(story_row.get("route_id") or ""),
        "warehouse": str(story_row.get("warehouse_name") or ""),
        "status": "Mart adat",
        "totalOrders": safe_int(story_row.get("address_count")),
        "deliveredOrders": safe_int(story_row.get("address_count")) if story_row.get("real_return") else 0,
        "plannedDeparture": local_iso_time(story_row.get("planned_departure")),
        "realDeparture": local_iso_time(story_row.get("real_departure")),
        "plannedReturn": local_iso_time(story_row.get("planned_return")),
        "realReturn": local_iso_time(story_row.get("real_return")),
        "minutesUntilReturn": minutes_until_route_return(
            {
                "realReturn": story_row.get("real_return"),
                "plannedReturn": story_row.get("planned_return"),
            }
        ),
        "previous": None,
        "current": None,
        "next": None,
        "routeStory": story,
        "vehicle": live_vehicle,
    }
    return {
        "found": True,
        "totalRoutes": 1,
        "route": route_payload,
        "source": "mart_dsp_route_stories",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def fetch_driver_detail(user: dict[str, Any]) -> dict[str, Any]:
    courier_id, _courier_name = courier_identity(user)
    today = datetime.now(LOCAL_TIMEZONE).date().isoformat()
    url = (
        f"{COURIER_DETAIL_API_BASE}/fetch-drivers-detail/"
        f"{courier_id}/{today}"
        f"?organizationId={COURIER_DETAIL_ORGANIZATION_ID}"
    )
    response = requests.get(url, timeout=45)
    if not response.ok:
        print("Driver detail status:", response.status_code)
        print("Driver detail response:", response.text[:2000])
        raise HTTPException(
            status_code=502,
            detail=f"A túraadatok nem érhetők el ({response.status_code}).",
        )
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def checkpoint_is_completed(checkpoint: dict[str, Any]) -> bool:
    return bool(
        checkpoint.get("realDepartureTime")
        or (
            checkpoint.get("realArrivalTime")
            and checkpoint.get("realDepartureTime")
        )
    )


def current_checkpoint_index(checkpoints: list[dict[str, Any]]) -> int | None:
    if not checkpoints:
        return None

    ordered = sorted(
        checkpoints,
        key=lambda row: int(row.get("position") or 999999),
    )

    # Ha megérkezett egy címre, de még nem indult tovább, az az aktuális cím.
    for index, checkpoint in enumerate(ordered):
        if checkpoint.get("realArrivalTime") and not checkpoint.get("realDepartureTime"):
            return index

    # Egyébként az első még nem teljesített cím az aktuális.
    for index, checkpoint in enumerate(ordered):
        if not checkpoint.get("realDepartureTime"):
            return index

    return len(ordered) - 1


def active_route(routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not routes:
        return None

    # Elsőként a még vissza nem érkezett túrát választjuk.
    active = [
        row for row in routes
        if not row.get("realReturn")
    ]
    candidates = active or routes

    def route_sort_key(row: dict[str, Any]) -> str:
        return str(
            row.get("realDeparture")
            or row.get("plannedDeparture")
            or row.get("assignedAt")
            or row.get("createdAt")
            or ""
        )

    return sorted(candidates, key=route_sort_key, reverse=True)[0]


def build_route_card(user: dict[str, Any]) -> dict[str, Any]:
    courier_id, _courier_name = courier_identity(user)
    today = datetime.now(LOCAL_TIMEZONE).date()
    try:
        payload = fetch_driver_detail(user)
    except HTTPException:
        fallback_card = build_route_card_from_story(
            read_latest_route_story_for_courier(courier_id, today)
        )
        if fallback_card:
            return fallback_card
        raise
    routes = payload.get("routes") or []
    route = active_route(routes)

    if not route:
        fallback_story = read_latest_route_story_for_courier(
            courier_id,
            today,
        )
        fallback_card = build_route_card_from_story(fallback_story)
        if fallback_card:
            return fallback_card
        return {
            "found": False,
            "route": None,
            "totalRoutes": len(routes),
        }

    checkpoints = sorted(
        route.get("checkpoints") or [],
        key=lambda row: int(row.get("position") or 999999),
    )
    index = current_checkpoint_index(checkpoints)

    previous_checkpoint = (
        checkpoints[index - 1]
        if index is not None and index > 0
        else None
    )
    current_checkpoint = (
        checkpoints[index]
        if index is not None and index < len(checkpoints)
        else None
    )
    next_checkpoint = (
        checkpoints[index + 1]
        if index is not None and index + 1 < len(checkpoints)
        else None
    )

    route_id = route.get("id") or route.get("routeId")
    route_date = (
        local_datetime(route.get("plannedDeparture"))
        or local_datetime(route.get("realDeparture"))
        or local_datetime(route.get("assignedAt"))
        or datetime.now(LOCAL_TIMEZONE)
    ).date()
    route_story = read_current_route_story(courier_id, route_id, route_date)
    live_vehicle = read_live_vehicle_for_user(user)

    route_payload = {
        "routeId": route_id,
        "warehouse": payload.get("warehouseName") or "",
        "status": route.get("status"),
        "totalOrders": int(route.get("numTotalOrders") or 0),
        "deliveredOrders": int(route.get("numDeliveredOrders") or 0),
        "plannedDeparture": local_iso_time(route.get("plannedDeparture")),
        "realDeparture": local_iso_time(route.get("realDeparture")),
        "plannedReturn": local_iso_time(route.get("plannedReturn")),
        "realReturn": local_iso_time(route.get("realReturn")),
        "minutesUntilReturn": minutes_until_route_return(route),
        "previous": {
            "orderId": str((previous_checkpoint or {}).get("orderId") or ""),
            "position": (previous_checkpoint or {}).get("position"),
            "address": str((previous_checkpoint or {}).get("address") or ""),
        } if previous_checkpoint else None,
        "current": {
            "orderId": str((current_checkpoint or {}).get("orderId") or ""),
            "position": (current_checkpoint or {}).get("position"),
            "address": str((current_checkpoint or {}).get("address") or ""),
            "windowFrom": local_iso_time((current_checkpoint or {}).get("deliverSince")),
            "windowTo": local_iso_time((current_checkpoint or {}).get("deliverTill")),
            "plannedArrival": local_iso_time((current_checkpoint or {}).get("plannedArrivalTime")),
            "estimatedArrival": local_iso_time((current_checkpoint or {}).get("estimatedArrivalTime")),
            "realArrival": local_iso_time((current_checkpoint or {}).get("realArrivalTime")),
            "delayMinutes": checkpoint_delay_minutes(current_checkpoint),
            "isLate": checkpoint_delay_minutes(current_checkpoint) > 0,
        } if current_checkpoint else None,
        "next": {
            "orderId": str((next_checkpoint or {}).get("orderId") or ""),
            "position": (next_checkpoint or {}).get("position"),
            "address": str((next_checkpoint or {}).get("address") or ""),
            "windowFrom": local_iso_time((next_checkpoint or {}).get("deliverSince")),
            "windowTo": local_iso_time((next_checkpoint or {}).get("deliverTill")),
            "delayMinutes": checkpoint_delay_minutes(next_checkpoint),
            "isLate": checkpoint_delay_minutes(next_checkpoint) > 0,
        } if next_checkpoint else None,
        "vehicle": live_vehicle,
    }
    if route_story:
        route_payload["routeStory"] = route_story

    return {
        "found": True,
        "totalRoutes": len(routes),
        "route": route_payload,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def save_route_delay_alert(
    user: dict[str, Any],
    payload: RouteDelayAlertRequest,
) -> None:
    courier_id, courier_name = courier_identity(user)
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Írd le röviden a problémát.",
        )

    supabase_rest(
        "POST",
        "courier_route_alerts",
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "route_id": str(payload.route_id),
            "order_id": payload.order_id.strip(),
            "alert_type": "problem",
            "message": message,
            "dispatcher_notified": payload.dispatcher_notified,
            "current_address": payload.current_address.strip(),
            "current_checkpoint_position": payload.current_checkpoint_position,
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def save_route_auto_delay_alert(user: dict[str, Any], payload: RouteDelayAlertRequest) -> None:
    courier_id, courier_name = courier_identity(user)
    message = payload.message.strip() or "Időablakhoz képest késés automatikusan rögzítve a PWA-ból."
    supabase_rest(
        "POST",
        "courier_route_alerts",
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "route_id": str(payload.route_id),
            "order_id": payload.order_id.strip(),
            "alert_type": "delay",
            "message": message,
            "dispatcher_notified": False,
            "current_address": payload.current_address.strip(),
            "current_checkpoint_position": payload.current_checkpoint_position,
            "status": "auto",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def save_shift_queue_checkin(user: dict[str, Any], payload: ShiftQueueCheckinRequest) -> None:
    courier_id, courier_name = courier_identity(user)
    event_type = payload.event_type.strip() or "queued"
    if event_type not in {"queued", "returned", "shift_late"}:
        raise HTTPException(status_code=422, detail="Ismeretlen műszak esemény.")
    supabase_rest(
        "POST",
        "courier_shift_checkins",
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "work_date": payload.work_date.strip() or date.today().isoformat(),
            "start_time": payload.start.strip(),
            "end_time": payload.end.strip(),
            "warehouse": normalize_warehouse(payload.warehouse) or payload.warehouse.strip(),
            "shift_name": payload.shift_name.strip(),
            "booking_code": payload.booking_code.strip(),
            "event_type": event_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def route_alert_email_recipient() -> str:
    return (
        load_setting("ROUTE_ALERT_EMAIL_TO")
        or load_setting("CENTRAL_ALERT_EMAIL_TO")
        or load_setting("SMTP_ALERT_TO")
        or ""
    ).strip()


def send_bag_missing_email(
    *,
    courier_id: str,
    courier_name: str,
    route_id: str,
    warehouse: str,
    departure: str,
    return_time: str,
    message_text: str,
    photo: UploadFile,
    photo_content: bytes,
) -> None:
    recipient = route_alert_email_recipient()
    if not recipient:
        raise HTTPException(status_code=503, detail="A központi route alert e-mail cím nincs beállítva.")
    config = smtp_config()
    message = EmailMessage()
    message["Subject"] = f"Táska hiány jelzés - route {route_id}"
    message["From"] = formataddr(("JITT rendszer", "system@jitt.hu"))
    message["To"] = validate_email(recipient)
    message.set_content(
        "Táska hiány jelzés érkezett a futár mobil appból.\n\n"
        f"Route ID: {route_id}\n"
        f"Futár: {courier_name} #{courier_id}\n"
        f"Raktár: {warehouse or '-'}\n"
        f"Időpont: indulás {departure or '-'} / vissza {return_time or '-'}\n"
        f"Megjegyzés: {message_text or '-'}\n"
    )
    message.add_attachment(
        photo_content,
        maintype="image",
        subtype=(photo.content_type or "image/jpeg").split("/", 1)[-1],
        filename=(photo.filename or "taska_foto.jpg").replace('"', ""),
    )
    send_message(message, config)


def route_alert_payload(
    *,
    user: dict[str, Any],
    route_id: str,
    order_id: str,
    alert_type: str,
    message: str,
    dispatcher_notified: bool,
    current_address: str,
    current_checkpoint_position: int | None,
    warehouse: str,
    route_departure: str,
    route_return: str,
) -> dict[str, Any]:
    courier_id, courier_name = courier_identity(user)
    return {
        "courier_id": int(courier_id),
        "courier_name": courier_name,
        "route_id": str(route_id or "").strip(),
        "order_id": str(order_id or "").strip(),
        "alert_type": alert_type,
        "message": str(message or "").strip(),
        "dispatcher_notified": bool(dispatcher_notified),
        "current_address": str(current_address or "").strip(),
        "current_checkpoint_position": current_checkpoint_position,
        "warehouse": str(warehouse or "").strip(),
        "route_departure": str(route_departure or "").strip(),
        "route_return": str(route_return or "").strip(),
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_route_alert_photo(alert_id: str, photo: UploadFile, content: bytes) -> None:
    supabase_rest(
        "POST",
        "courier_route_alert_photos",
        payload={
            "alert_id": alert_id,
            "file_name": (photo.filename or "route_alert_photo").replace('"', ""),
            "mime_type": photo.content_type or "application/octet-stream",
            "file_size": len(content),
            "file_content_base64": base64.b64encode(content).decode("ascii"),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def save_route_alert(payload: dict[str, Any]) -> dict[str, Any]:
    rows = supabase_rest(
        "POST",
        "courier_route_alerts",
        payload=payload,
        prefer="return=representation",
    )
    return rows[0] if rows else {}



WORKFLOW_PREREQUISITES = {
    "tig": "settlement",
    "invoice_submit": "tig",
    "invoice_check": "invoice_submit",
    "invoice_payment": "invoice_check",
}
WORKFLOW_DOCUMENT_TYPES = {"settlement", "tig", "invoice"}
PROCESS_NOTE_PREFIX = "Folyamat azonosító:"


def normalize_process_id(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    if text in {"", "havi", "monthly", "alap"}:
        return ""
    return text[:80]


def process_action_key(action: str, process_id: str | None = "") -> str:
    clean_process = normalize_process_id(process_id)
    return f"process:{clean_process}:{action}" if clean_process else action


def base_action_key(action_key: str) -> str:
    match = re.fullmatch(r"process:([a-z0-9_-]+):(.+)", str(action_key or "").strip())
    return match.group(2) if match else str(action_key or "").strip()


def process_id_from_action_key(action_key: str) -> str:
    match = re.fullmatch(r"process:([a-z0-9_-]+):(.+)", str(action_key or "").strip())
    return match.group(1) if match else ""


def process_note_marker(process_id: str | None) -> str:
    clean_process = normalize_process_id(process_id)
    return f"{PROCESS_NOTE_PREFIX} {clean_process}" if clean_process else ""


def document_belongs_to_process(document: dict[str, Any], process_id: str | None) -> bool:
    clean_process = normalize_process_id(process_id)
    note = str(document.get("note") or "")
    match = re.search(r"Folyamat azonosító:\s*([a-z0-9_-]+)", note, flags=re.IGNORECASE)
    document_process = normalize_process_id(match.group(1)) if match else ""
    return document_process == clean_process


def invoice_document_exists_for_process(documents: list[dict[str, Any]], process_id: str | None) -> bool:
    return any(
        base_action_key(str(document.get("document_type") or "")) == "invoice"
        and document_belongs_to_process(document, process_id)
        for document in documents
    )


def parse_month(value: str | date | None) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    text = str(value or "").strip()
    if not text:
        return date.today().replace(day=1)
    try:
        return date.fromisoformat(text[:7] + "-01")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="A hónap formátuma YYYY-MM legyen.") from exc


def month_end(value: date) -> date:
    next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def salary_advance_installment_amounts(total_huf: int, months: int) -> list[int]:
    total = max(0, int(total_huf or 0))
    count = max(1, min(60, int(months or 1)))
    base_amount = total // count
    amounts = [base_amount for _ in range(count)]
    if amounts:
        amounts[-1] += total - sum(amounts)
    return amounts


def normalize_salary_advance_request(row: dict[str, Any]) -> dict[str, Any]:
    status_labels = {
        "requested": "Jóváhagyásra vár",
        "approved": "Jóváhagyva",
        "paid": "Kifizetve",
        "closed": "Lezárva",
        "rejected": "Elutasítva",
    }
    clean_status = str(row.get("status") or "requested").strip().lower()
    return {
        "id": str(row.get("id") or ""),
        "courierId": str(row.get("courier_id") or ""),
        "courierName": str(row.get("courier_name") or ""),
        "requestedAmountHuf": int(float(row.get("requested_amount_huf") or 0)),
        "installmentMonths": int(float(row.get("installment_months") or 0)),
        "monthlyAmountHuf": int(float(row.get("monthly_amount_huf") or 0)),
        "startDate": str(row.get("start_date") or ""),
        "status": clean_status,
        "statusLabel": status_labels.get(clean_status, clean_status or "-"),
        "processId": str(row.get("process_id") or ""),
        "note": str(row.get("note") or ""),
        "requestedAt": str(row.get("requested_at") or ""),
    }


def clean_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def supabase_headers(*, prefer: str = "") -> dict[str, str]:
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY").strip()
    if not load_setting("SUPABASE_URL") or not key:
        raise HTTPException(status_code=503, detail="Hiányzik a Supabase konfiguráció.")
    headers = supabase_key_headers(key)
    if prefer:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer
    return headers


def supabase_schema_headers(*, prefer: str = "", schema: str = "public") -> dict[str, str]:
    headers = supabase_headers(prefer=prefer)
    clean_schema = str(schema or "public").strip()
    if clean_schema and clean_schema != "public":
        headers["Accept-Profile"] = clean_schema
        headers["Content-Profile"] = clean_schema
    return headers


def supabase_rest(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    prefer: str = "",
    timeout: int = 30,
    schema: str = "public",
) -> Any:
    url = load_setting("SUPABASE_URL").rstrip("/")

    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=supabase_schema_headers(prefer=prefer, schema=schema),
        params=params,
        json=payload,
        timeout=timeout,
    )

    if not response.ok:
        print("Supabase table:", table)
        print("Supabase status:", response.status_code)
        print("Supabase response:", response.text)

        raise HTTPException(
            status_code=502,
            detail=f"Adatbázis-hiba ({response.status_code}).",
        )

    if not response.content:
        return []

    try:
        return response.json()
    except ValueError:
        return []


def courier_identity(user: dict[str, Any]) -> tuple[str, str]:
    courier_id = str(user.get("courierId") or "").strip()
    courier_name = str(user.get("username") or "").strip()
    if not courier_id:
        raise HTTPException(status_code=422, detail="A felhasználóhoz nincs futárazonosító rendelve.")
    return courier_id, courier_name


def read_courier_display_name(courier_id: str) -> str:
    rows = optional_supabase_rows(
        "courier_master",
        params={
            "select": "courier_name",
            "courier_id": f"eq.{courier_id}",
            "limit": "1",
        },
    )
    return str((rows[0] if rows else {}).get("courier_name") or "").strip()


def embedded_courier_id(value: Any) -> str:
    match = re.search(r"(?<!\d)(\d{4,6})(?!\d)", str(value or ""))
    return match.group(1) if match else ""


def resolve_preview_courier(query: str) -> tuple[str, str]:
    target = str(query or "").strip()
    if not target:
        return "", ""
    target_id = target if target.isdigit() else embedded_courier_id(target)
    if target_id:
        rows = optional_supabase_rows(
            "courier_master",
            params={
                "select": "courier_id,courier_name",
                "courier_id": f"eq.{target_id}",
                "limit": "1",
            },
        )
        if rows:
            row = rows[0]
            return str(row.get("courier_id") or target_id).strip(), str(row.get("courier_name") or target).strip()
        return target_id, target
    rows = optional_supabase_rows(
        "courier_master",
        params={
            "select": "courier_id,courier_name",
            "courier_id": f"eq.{target}",
            "limit": "1",
        },
    )
    if not rows:
        rows = optional_supabase_rows(
            "courier_master",
            params={
                "select": "courier_id,courier_name",
                "courier_name": f"ilike.*{target}*",
                "order": "courier_name.asc",
                "limit": "10",
            },
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Nem talalhato futar ezzel a nevvel vagy azonositoval.")
    if len(rows) > 1:
        exact_rows = [row for row in rows if normalize_text(row.get("courier_name")) == normalize_text(target)]
        if len(exact_rows) == 1:
            rows = exact_rows
        else:
            names = ", ".join(str(row.get("courier_name") or row.get("courier_id") or "") for row in rows[:5])
            raise HTTPException(status_code=409, detail=f"Tobb futar is talalat: {names}. Pontosits nevvel vagy ID-val.")
    row = rows[0]
    return str(row.get("courier_id") or "").strip(), str(row.get("courier_name") or "").strip()


def workflow_view_user(user: dict[str, Any], courier_id: str | None = "") -> tuple[dict[str, Any], bool]:
    target_query = str(courier_id or "").strip()
    if not target_query:
        return user, False
    if not can_preview_couriers(user):
        raise HTTPException(status_code=403, detail="Másik futár mobil nézetéhez admin jogosultság szükséges.")
    target_id, resolved_name = resolve_preview_courier(target_query)
    target_name = resolved_name or read_courier_display_name(target_id) or f"Futár {target_id}"
    preview_user = dict(user)
    preview_user["courierId"] = target_id
    preview_user["username"] = target_name
    preview_user["_previewedBy"] = str(user.get("username") or "")
    return preview_user, True


def profile_identity(user: dict[str, Any]) -> tuple[str, str]:
    return (
        str(user.get("courierId") or "").strip(),
        str(user.get("username") or "").strip(),
    )


def normalize_profile_courier_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    if not re.fullmatch(r"\d{3,10}", compact):
        raise HTTPException(status_code=422, detail="A futár ID csak szám lehet.")
    return compact


BILLING_PROFILE_FIELDS = (
    "courier_id,courier_name,phone_number,"
    "company_name,company_address,tax_number,"
    "bank_account_number,billing_email,billing_data_updated_at"
)


def read_billing_profile(user: dict[str, Any]) -> dict[str, Any]:
    courier_id, _courier_name = profile_identity(user)
    params = {
        "select": BILLING_PROFILE_FIELDS,
        "limit": "1",
    }
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"
    else:
        params["courier_name"] = f"eq.{_courier_name}"

    rows = supabase_rest("GET", "courier_master", params=params)
    if not rows:
        return {
            "courier_id": courier_id,
            "courier_name": _courier_name,
            "phone_number": str(user.get("phone") or ""),
            "company_name": "",
            "company_address": "",
            "tax_number": "",
            "bank_account_number": "",
            "billing_email": "",
            "updated_at": None,
        }
    row = rows[0]
    return {
        "courier_id": str(row.get("courier_id") or courier_id),
        "courier_name": str(row.get("courier_name") or _courier_name),
        "phone_number": str(row.get("phone_number") or ""),
        "company_name": str(row.get("company_name") or ""),
        "company_address": str(row.get("company_address") or ""),
        "tax_number": str(row.get("tax_number") or ""),
        "bank_account_number": str(row.get("bank_account_number") or ""),
        "billing_email": str(row.get("billing_email") or ""),
        "updated_at": row.get("billing_data_updated_at"),
    }


def validate_billing_profile(payload: BillingProfileUpdate) -> dict[str, str]:
    courier_id = normalize_profile_courier_id(payload.courier_id)
    courier_name = payload.courier_name.strip()
    phone_number = payload.phone_number.strip()
    company_name = payload.company_name.strip()
    company_address = payload.company_address.strip()
    tax_number = payload.tax_number.strip()
    bank_account_number = payload.bank_account_number.strip()
    billing_email = payload.billing_email.strip()

    if not company_name:
        raise HTTPException(status_code=422, detail="A vállalkozás neve kötelező.")
    if not company_address:
        raise HTTPException(status_code=422, detail="A vállalkozás székhelye kötelező.")
    if not tax_number:
        raise HTTPException(status_code=422, detail="Az adószám kötelező.")
    if billing_email and ("@" not in billing_email or "." not in billing_email.rsplit("@", 1)[-1]):
        raise HTTPException(status_code=422, detail="A számlázási e-mail formátuma hibás.")

    return {
        "courier_id": courier_id,
        "courier_name": courier_name,
        "phone_number": phone_number,
        "company_name": company_name,
        "company_address": company_address,
        "tax_number": tax_number,
        "bank_account_number": bank_account_number,
        "billing_email": billing_email,
    }


def validate_bank_account_number(value: str) -> str:
    bank_account_number = str(value or "").strip()
    compact = re.sub(r"[\s-]+", "", bank_account_number)
    if bank_account_number and not re.fullmatch(r"[0-9\s-]{8,40}", bank_account_number):
        raise HTTPException(status_code=422, detail="A bankszámlaszám csak számot, szóközt és kötőjelet tartalmazhat.")
    if compact and len(compact) not in {16, 24, 32}:
        raise HTTPException(status_code=422, detail="A bankszámlaszám hossza nem megfelelő.")
    return bank_account_number


def read_master_auth_row(courier_id: str) -> dict[str, Any] | None:
    clean_id = normalize_profile_courier_id(courier_id)
    rows = supabase_rest(
        "GET",
        "courier_master",
        params={
            "select": "courier_id,courier_name,phone_number,email,billing_email,billing_data_updated_at,updated_at",
            "courier_id": f"eq.{clean_id}",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def master_email(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("email") or row.get("billing_email") or "").strip()


def update_master_email_if_missing(row: dict[str, Any], email: str) -> bool:
    existing_email = master_email(row)
    if existing_email:
        return False

    now = datetime.now(timezone.utc).isoformat()
    supabase_rest(
        "PATCH",
        "courier_master",
        params={"courier_id": f"eq.{row.get('courier_id')}"},
        payload={
            "email": email,
            "billing_email": email,
            "billing_data_updated_at": now,
            "updated_at": now,
        },
        prefer="return=minimal",
    )
    return True


def optional_supabase_rows(
    table: str,
    *,
    params: dict[str, str],
    schema: str = "public",
    timeout: int = 30,
) -> list[dict[str, Any]]:
    try:
        return supabase_rest(
            "GET",
            table,
            params=params,
            schema=schema,
            timeout=timeout,
        ) or []
    except HTTPException:
        return []


def money_int(value: Any) -> int:
    if isinstance(value, str):
        text = value.replace("\xa0", " ").replace("Ft", "").replace("HUF", "").strip()
        text = text.replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match:
            try:
                return int(round(float(match.group(0))))
            except (TypeError, ValueError):
                return 0
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def money_from(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return money_int(row.get(key))
    return 0


def money_sum_from(row: dict[str, Any], *keys: str) -> int:
    return sum(money_int(row.get(key)) for key in keys if key in row and row.get(key) not in (None, ""))


def clean_note_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() == "nan":
        return ""
    return text


def text_from_nested(value: Any, *keys: str) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        raw = value.get(key)
        if raw not in (None, ""):
            return str(raw)
    normalized = {normalized_field_key(item_key): raw for item_key, raw in value.items()}
    for key in keys:
        raw = normalized.get(normalized_field_key(key))
        if raw not in (None, ""):
            return str(raw)
    return ""


def route_type_key(value: Any) -> str:
    text = normalize_text(value)
    if "express" in text or "exp" == text:
        return "express"
    if "regional" in text or "regios" in text or "region" in text:
        return "regional"
    if "normal" in text or "city" in text or "kiemelt" in text or "sima" in text:
        return "normal"
    return "any"


def day_type_key(value: Any) -> str:
    text = normalize_text(value)
    if "highlighted" in text or "kiemelt" in text:
        return "highlighted"
    if "normal" in text or "sima" in text:
        return "normal"
    return "any"


def date_from_row_value(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def signed_item(key: str, label: str, amount: int, *, source: str = "settlement.courier_settlement_summary", note: str = "") -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "amountHuf": int(amount),
        "source": source,
        "note": note,
    }


def count_item(key: str, label: str, count: int) -> dict[str, Any]:
    item = signed_item(key, label, count, note="darab")
    item["amountKind"] = "count"
    return item


def read_mobile_settlement_period_config(month: date) -> dict[str, Any]:
    rows = optional_supabase_rows(
        "mobile_settlement_period_config",
        schema="settlement",
        params={
            "select": "period_start,calculation_mode,warehouse_label,session_id,source_note,updated_by,updated_at",
            "period_start": f"eq.{month.isoformat()}",
            "limit": "1",
        },
        timeout=30,
    )
    return dict(rows[0]) if rows else {}


def mobile_settlement_period_is_open(month: date) -> bool:
    config = read_mobile_settlement_period_config(month)
    config_mode = str(config.get("calculation_mode") or "").strip()
    session_id = str(config.get("session_id") or "").strip()
    return config_mode in {"API", "Excel"} or bool(session_id)


def latest_settlement_session_for_month(
    courier_id: str,
    month: date,
    config: dict[str, Any],
    *,
    allow_unpublished: bool = False,
) -> dict[str, str]:
    config_mode = str(config.get("calculation_mode") or "").strip()
    if config_mode not in {"API", "Excel"}:
        if allow_unpublished:
            config_mode = ""
        else:
            return {"sessionId": "", "sourceMode": "", "sourceSheet": "", "message": "Az admin még nem publikálta a havi mobil elszámolási forrást."}
    if config_mode not in {"API", "Excel"}:
        config_mode = ""
    if not allow_unpublished and config_mode not in {"API", "Excel"}:
        return {"sessionId": "", "sourceMode": "", "sourceSheet": "", "message": "Az admin még nem publikálta a havi mobil elszámolási forrást."}
    configured_session_id = str(config.get("session_id") or "").strip()
    if configured_session_id:
        return {
            "sessionId": configured_session_id,
            "sourceMode": config_mode,
            "sourceSheet": str(config.get("source_note") or ""),
            "message": "",
        }
    period_end = month_end(month)
    params = {
        "select": "session_id,source_sheet,route_date,created_at",
        "courier_id": f"eq.{courier_id}",
        "and": f"(route_date.gte.{month.isoformat()},route_date.lte.{period_end.isoformat()})",
        "order": "created_at.desc",
        "limit": "200",
    }
    if config_mode == "API":
        params["source_sheet"] = "ilike.API financial overview%"
    rows = optional_supabase_rows(
        "jit_row",
        schema="settlement",
        params=params,
        timeout=60,
    )
    for row in rows:
        source_sheet = str(row.get("source_sheet") or "").strip()
        source_mode = "API" if source_sheet.lower().startswith("api financial overview") else "Excel"
        if config_mode and source_mode != config_mode:
            continue
        return {
            "sessionId": str(row.get("session_id") or "").strip(),
            "sourceMode": source_mode,
            "sourceSheet": source_sheet,
            "message": "",
        }
    source_label = config_mode or "API/Excel"
    return {"sessionId": "", "sourceMode": config_mode, "sourceSheet": "", "message": f"Nincs {source_label} session ehhez a hónaphoz."}


def latest_excel_balance_session_for_month(month: date) -> str:
    period_end = month_end(month)
    rows = optional_supabase_rows(
        "jit_row",
        schema="settlement",
        params={
            "select": "session_id,source_sheet,route_date,created_at",
            "and": f"(route_date.gte.{month.isoformat()},route_date.lte.{period_end.isoformat()})",
            "order": "created_at.desc",
            "limit": "500",
        },
        timeout=60,
    )
    for row in rows:
        source_sheet = str(row.get("source_sheet") or "").strip().lower()
        if source_sheet and not source_sheet.startswith("api financial overview"):
            return str(row.get("session_id") or "").strip()
    return ""


def read_courier_settlement_summary_row(courier_id: str, month: date, *, allow_unpublished: bool = False) -> dict[str, Any]:
    config = read_mobile_settlement_period_config(month)
    session = latest_settlement_session_for_month(courier_id, month, config, allow_unpublished=allow_unpublished)
    session_id = session.get("sessionId") or ""
    if not session_id:
        return {"_mobile_unavailable_message": session.get("message") or "Nincs publikált havi mobil elszámolási forrás."}
    rows = optional_supabase_rows(
        "courier_settlement_summary",
        schema="settlement",
        params={
            "select": "*",
            "session_id": f"eq.{session_id}",
            "courier_id": f"eq.{courier_id}",
            "limit": "1",
        },
        timeout=60,
    )
    if rows:
        row = dict(rows[0])
        row["_mobile_session_id"] = session_id
        row["_mobile_source_mode"] = session.get("sourceMode") or ""
        row["_mobile_source_sheet"] = session.get("sourceSheet") or ""
        return row
    return {}


def read_mobile_breakdown_overrides(courier_id: str, month: date) -> dict[str, dict[str, Any]]:
    rows = optional_supabase_rows(
        "mobile_settlement_breakdown_overrides",
        schema="settlement",
        params={
            "select": "item_key,item_label,amount_value,amount_kind,note,updated_at",
            "courier_id": f"eq.{courier_id}",
            "period_start": f"eq.{month.isoformat()}",
            "order": "updated_at.asc",
            "limit": "200",
        },
        timeout=30,
    )
    stale_keys = {"tig_cash_deduction", "cash_deduction"}
    return {
        str(row.get("item_key") or ""): row
        for row in rows
        if str(row.get("item_key") or "") and str(row.get("item_key") or "") not in stale_keys
    }


def mobile_override_item(row: dict[str, Any], fallback_key: str = "") -> dict[str, Any]:
    key = str(row.get("item_key") or fallback_key or "").strip()
    amount_kind = str(row.get("amount_kind") or "huf").strip() or "huf"
    item = signed_item(
        key,
        str(row.get("item_label") or key or "-"),
        money_int(row.get("amount_value")),
        source="settlement.mobile_settlement_breakdown_overrides",
        note=str(row.get("note") or ""),
    )
    item["amountKind"] = amount_kind
    return item


def mobile_override_amount(overrides: dict[str, dict[str, Any]], key: str) -> int:
    return money_int((overrides.get(key) or {}).get("amount_value"))


def cached_financial_lookup(cache_group: str, cache_key: str) -> Any | None:
    cached = _FINANCIAL_LOOKUP_CACHE.get((cache_group, cache_key, ""))
    if not cached:
        return None
    cached_at, value = cached
    if time.time() - cached_at > FINANCIAL_LOOKUP_CACHE_SECONDS:
        _FINANCIAL_LOOKUP_CACHE.pop((cache_group, cache_key, ""), None)
        return None
    return value


def store_financial_lookup(cache_group: str, cache_key: str, value: Any) -> Any:
    _FINANCIAL_LOOKUP_CACHE[(cache_group, cache_key, "")] = (time.time(), value)
    return value


def build_financial_breakdown_from_mobile_rows(
    user: dict[str, Any],
    month: date,
    row: dict[str, Any],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not overrides or "payable" not in overrides:
        return None
    payable_override = mobile_override_amount(overrides, "payable")
    fallback_courier_id, _fallback_courier_name = courier_identity(user)
    selected_courier_id = str(
        row.get("courier_id")
        or row.get("Courier ID")
        or row.get("courierId")
        or fallback_courier_id
        or ""
    ).strip()

    def item(key: str, *, fallback_label: str = "") -> dict[str, Any] | None:
        row_item = overrides.get(key)
        if not row_item:
            return None
        result = mobile_override_item(row_item, key)
        if fallback_label and not str(result.get("label") or "").strip():
            result["label"] = fallback_label
        return result

    def money_items(keys: list[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key in keys:
            current = item(key)
            if not current:
                continue
            if str(current.get("amountKind") or "huf") != "huf":
                continue
            if money_int(current.get("amountHuf")) or key in {"customer_rating", "loyalty_bonus"}:
                result.append(current)
        return result

    def override_amount_or(key: str, fallback: int = 0) -> int:
        if key in overrides:
            return mobile_override_amount(overrides, key)
        return fallback

    def detail_items(
        prefixes: tuple[str, ...],
        explicit_keys: list[str],
        *,
        exclude_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        excluded = exclude_keys or set()
        keys = explicit_keys + sorted(
            key
            for key in overrides
            if any(key.startswith(prefix) for prefix in prefixes)
            and key not in explicit_keys
            and key not in excluded
        )
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            current = item(key)
            if not current:
                continue
            if str(current.get("amountKind") or "huf") == "huf" and not money_int(current.get("amountHuf")):
                continue
            result.append(current)
        return result

    def normalize_base_detail_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        label_map = {
            "sima normal": "Normál city",
            "normal city": "Normál city",
            "kiemelt normal": "Kiemelt city",
            "kiemelt city": "Kiemelt city",
            "express normal": "Normál express",
            "normal express": "Normál express",
            "kiemelt express": "Kiemelt express",
        }
        normalized_items: list[dict[str, Any]] = []
        for current in items:
            updated = dict(current)
            label = str(updated.get("label") or "")
            updated["label"] = label_map.get(normalize_text(label), label)
            normalized_items.append(updated)
        return normalized_items

    base_items = normalize_base_detail_items(detail_items(("base_detail_",), []))
    if not base_items:
        base_items = money_items(["base"])
    delay_items = money_items(["delay_bonus"])
    compliance_items = money_items(["compliance_bonus"])
    customer_rating_items = detail_items(("customer_rating_",), ["customer_rating"])
    income_items = money_items([
        "base",
        "tip",
        "delay_bonus",
        "compliance_bonus",
        "loyalty_bonus",
        "customer_rating",
        "monthly_bonus",
        "manual_bonus",
    ])
    if customer_rating_items and not any(str(current.get("key") or "").startswith("customer_rating") for current in income_items):
        income_items.extend(customer_rating_items)
    deduction_items = money_items([
        "monthly_malus",
        "manual_malus",
        "atm_effect",
        "salary_advance",
        "reserve",
        "insurance_fee",
        "other_deduction",
    ])
    insurance_items = [
        current for current in (
            item("target_reserve_open"),
            item("reserve"),
            item("insurance_fee"),
            item("target_reserve_close"),
        )
        if current is not None and (money_int(current.get("amountHuf")) or current.get("key") in {"target_reserve_open", "target_reserve_close"})
    ]
    insurance_total = sum(
        money_int(current.get("amountHuf"))
        for current in insurance_items
        if current.get("key") in {"reserve", "insurance_fee"}
    )
    kiflis_detail_items = detail_items(
        ("kiflis_bonus_", "kiflis_malus_"),
        [],
        exclude_keys={"kiflis_bonus_malus", "kiflis_bonus_total", "kiflis_malus_total"},
    )
    kiflis_items = kiflis_detail_items or detail_items((), ["kiflis_bonus_total", "kiflis_malus_total", "monthly_bonus", "monthly_malus"])
    jitt_detail_items = detail_items(("jitt_bonus_", "jitt_malus_"), [])
    jitt_items = list(jitt_detail_items)
    for current in jitt_items:
        key = str(current.get("key") or "")
        note = clean_note_part(current.get("note"))
        if key.startswith("jitt_malus_"):
            current["label"] = str(current.get("label") or "JITT malus")
            if not note:
                current["note"] = "JITT/DB levonás részlete nincs megadva."
        elif key.startswith("jitt_bonus_"):
            current["label"] = str(current.get("label") or "JITT bónusz")
    has_jitt_bonus_detail = any(str(current.get("key") or "").startswith("jitt_bonus_") for current in jitt_items)
    has_jitt_malus_detail = any(str(current.get("key") or "").startswith("jitt_malus_") for current in jitt_items)
    for fallback_key, has_detail in [("manual_bonus", has_jitt_bonus_detail), ("manual_malus", has_jitt_malus_detail)]:
        fallback_item = item(fallback_key)
        if fallback_item and not has_detail and money_int(fallback_item.get("amountHuf")):
            jitt_items.append(fallback_item)
    if not jitt_items:
        jitt_items = detail_items((), ["manual_bonus", "manual_malus"])
    correction_items = detail_items(("correction_periodic_",), [])
    correction_total = sum(money_int(current.get("amountHuf")) for current in correction_items)
    tip_items = money_items(["tip"])
    tip_total = override_amount_or("tip", sum(money_int(current.get("amountHuf")) for current in tip_items))
    performance_items = [
        current for current in (
            item("orders"),
            item("routes"),
            item("highlighted_routes"),
            item("normal_routes"),
            item("loyalty_previous_normal_routes"),
            item("loyalty_current_normal_routes"),
            item("loyalty_advance_booking_days"),
            item("shift_count"),
        )
        if current is not None and str(current.get("amountKind") or "") == "count"
    ]
    kiflis_total = override_amount_or("kiflis_bonus_malus", sum(money_int(current.get("amountHuf")) for current in kiflis_items))
    jitt_total = override_amount_or("bonus_malus", sum(money_int(current.get("amountHuf")) for current in jitt_items))
    base_total = override_amount_or("base", sum(money_int(current.get("amountHuf")) for current in base_items))
    delay_total = override_amount_or("delay_bonus", sum(money_int(current.get("amountHuf")) for current in delay_items))
    compliance_total = override_amount_or("compliance_bonus", sum(money_int(current.get("amountHuf")) for current in compliance_items))
    customer_rating_total = override_amount_or("customer_rating", sum(money_int(current.get("amountHuf")) for current in customer_rating_items))
    loyalty_total = mobile_override_amount(overrides, "loyalty_bonus")
    atm_total = mobile_override_amount(overrides, "atm_effect")
    salary_advance_total = mobile_override_amount(overrides, "salary_advance")
    other_deduction_total = mobile_override_amount(overrides, "other_deduction")

    income_total = sum(
        amount
        for amount in (
            base_total,
            tip_total,
            delay_total,
            compliance_total,
            loyalty_total,
            customer_rating_total,
        )
        if amount > 0
    )
    deduction_total = 0
    for adjustment_total in (kiflis_total, jitt_total):
        if adjustment_total >= 0:
            income_total += adjustment_total
        else:
            deduction_total += adjustment_total
    for deduction_amount in (atm_total, insurance_total, salary_advance_total, other_deduction_total):
        if deduction_amount < 0:
            deduction_total += deduction_amount
    calculated_payable = income_total + deduction_total + correction_total
    payable = payable_override if payable_override is not None else calculated_payable

    cards = [
        {
            "key": "payable",
            "label": "Teljes \u00f6sszeg",
            "amountHuf": payable,
            "tone": "total",
            "items": [
                signed_item("income_total", "J\u00f3v\u00e1\u00edr\u00e1sok \u00f6sszesen", income_total),
                signed_item("deduction_total", "Levon\u00e1sok \u00f6sszesen", deduction_total),
                signed_item("correction_total", "Korrekci\u00f3k \u00f6sszesen", correction_total),
                signed_item("payable_total", "Kifizetend\u0151", payable),
            ],
        },
        {"key": "income", "label": "J\u00f3v\u00e1\u00edr\u00e1sok", "amountHuf": income_total, "tone": "income", "items": income_items},
        {"key": "base", "label": "Alapd\u00edj", "amountHuf": base_total, "tone": "income", "items": base_items},
        {"key": "tip", "label": "Borraval\u00f3", "amountHuf": tip_total, "tone": "income", "items": tip_items},
        {"key": "delay_bonus", "label": "K\u00e9sedelmi d\u00edj", "amountHuf": delay_total, "tone": "income", "items": delay_items},
        {"key": "compliance_bonus", "label": "T\u00faramegfelel\u00e9s", "amountHuf": compliance_total, "tone": "income", "items": compliance_items},
        {"key": "deductions", "label": "Levon\u00e1sok \u00f6sszesen", "amountHuf": deduction_total, "tone": "deduction", "items": deduction_items},
        {"key": "loyalty_bonus", "label": "Lojalit\u00e1si b\u00f3nusz", "amountHuf": loyalty_total, "tone": "income", "items": money_items(["loyalty_bonus"])},
        {"key": "customer_rating", "label": "\u00dcgyf\u00e9l\u00e9rt\u00e9kel\u00e9s", "amountHuf": customer_rating_total, "tone": "income", "items": customer_rating_items},
        {"key": "kiflis_bonus_malus", "label": "Kiflis levon\u00e1sok / b\u00f3nuszok", "amountHuf": kiflis_total, "tone": "info", "items": kiflis_items},
        {"key": "bonus_malus", "label": "JITT b\u00f3nusz / malus", "amountHuf": jitt_total, "tone": "info", "items": jitt_items},
        {"key": "atm_effect", "label": "ATM levon\u00e1s", "amountHuf": atm_total, "tone": "deduction", "items": money_items(["atm_effect"])},
        {"key": "insurance", "label": "Biztos\u00edt\u00e1s", "amountHuf": insurance_total, "tone": "deduction", "items": insurance_items},
        {"key": "corrections", "label": "Korrekci\u00f3k", "amountHuf": correction_total, "tone": "info", "items": correction_items},
        {"key": "performance", "label": "Teljes\u00edtm\u00e9ny", "amountHuf": mobile_override_amount(overrides, "performance"), "amountKind": "count", "tone": "info", "items": performance_items},
    ]

    complaint_excluded_keys = {"income_total", "deduction_total", "correction_total", "payable_total"}
    complaint_options = [
        {
            "key": current["key"],
            "label": current["label"],
            "amountHuf": current["amountHuf"],
            "amountKind": current.get("amountKind", "huf"),
        }
        for card in cards
        for current in card.get("items") or []
        if current.get("key") not in complaint_excluded_keys and not current.get("excludeFromTotal")
    ]
    visible_cards = [card for card in cards if card.get("key") not in {"income", "deductions"}]
    return {
        "available": True,
        "month": month.strftime("%Y-%m"),
        "sessionId": str(row.get("_mobile_session_id") or row.get("session_id") or ""),
        "sourceMode": str(row.get("_mobile_source_mode") or ""),
        "sourceSheet": str(row.get("_mobile_source_sheet") or ""),
        "totalPayableHuf": payable,
        "cards": visible_cards,
        "complaintOptions": complaint_options,
        "source": "settlement.mobile_settlement_breakdown_overrides",
        "message": "",
    }


def read_target_reserve_monthly(courier_id: str, period_start: date, period_end: date) -> dict[str, Any]:
    if not courier_id:
        return {}
    cache_key = f"{courier_id}|{period_start.isoformat()}|{period_end.isoformat()}"
    cached = cached_financial_lookup("target_reserve_monthly", cache_key)
    if cached is not None:
        return dict(cached)
    rows = optional_supabase_rows(
        "courier_target_reserve_monthly",
        schema="settlement",
        params={
            "select": "reserve_before_huf,reserve_addition_huf,insurance_fee_huf,reserve_after_huf,payable_before_insurance_huf,payable_after_insurance_huf,status,updated_at",
            "courier_id": f"eq.{courier_id}",
            "period_start": f"eq.{period_start.isoformat()}",
            "period_end": f"eq.{period_end.isoformat()}",
            "limit": "1",
        },
        timeout=30,
    )
    result = dict(rows[0]) if rows else {}
    store_financial_lookup("target_reserve_monthly", cache_key, result)
    return result


def read_courier_manual_adjustments(courier_id: str, period_start: date, period_end: date) -> list[dict[str, Any]]:
    if not courier_id:
        return []
    cache_key = f"{courier_id}|{period_start.isoformat()}|{period_end.isoformat()}"
    cached = cached_financial_lookup("manual_adjustments", cache_key)
    if cached is not None:
        return [dict(row) for row in cached]
    rows = optional_supabase_rows(
        "courier_settlement_adjustment",
        schema="settlement",
        params={
            "select": "id,adjustment_type,amount_huf,note,effective_date,valid_from,valid_to,created_at",
            "courier_id": f"eq.{courier_id}",
            "is_active": "eq.true",
            "deleted_at": "is.null",
            "order": "valid_from.asc,effective_date.asc,created_at.asc",
            "limit": "500",
        },
        timeout=30,
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        valid_from = date_from_row_value(row.get("valid_from")) or date_from_row_value(row.get("effective_date"))
        valid_to = date_from_row_value(row.get("valid_to"))
        if valid_from and valid_from > period_end:
            continue
        if valid_to and valid_to < period_start:
            continue
        adjustment_type = str(row.get("adjustment_type") or "").strip()
        if not adjustment_type:
            continue
        clean_row = dict(row)
        clean_row["adjustment_type"] = adjustment_type
        clean_row["amount_huf"] = abs(money_int(row.get("amount_huf")))
        result.append(clean_row)
    store_financial_lookup("manual_adjustments", cache_key, [dict(row) for row in result])
    return result


def imported_balance_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("normalized_data") or {}
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return payload if isinstance(payload, dict) else {}


def imported_balance_value(payload: dict[str, Any], *keys: str) -> Any:
    if not payload:
        return None
    normalized = {normalized_field_key(key): value for key, value in payload.items()}
    for key in keys:
        clean_key = normalized_field_key(key)
        if clean_key in normalized and normalized[clean_key] not in (None, ""):
            return normalized[clean_key]
    return None


def normalize_imported_courier_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"#?\s*(\d{3,10})(?:[,.]0+)?", text)
    if match:
        return match.group(1)
    match = re.search(r"#\s*(\d{3,10})", text)
    if match:
        return match.group(1)
    return text if re.fullmatch(r"\d{3,10}", text) else ""


def imported_balance_note(payload: dict[str, Any]) -> str:
    parts = [
        clean_note_part(imported_balance_value(payload, "Malus name")),
        clean_note_part(imported_balance_value(payload, "Bonus name")),
        clean_note_part(imported_balance_value(payload, "Tétel")),
        clean_note_part(imported_balance_value(payload, "Reason")),
        clean_note_part(imported_balance_value(payload, "Category")),
        clean_note_part(imported_balance_value(payload, "Comment")),
        clean_note_part(imported_balance_value(payload, "Comment 2")),
        clean_note_part(imported_balance_value(payload, "Note")),
        clean_note_part(imported_balance_value(payload, "Megjegyzés")),
        clean_note_part(imported_balance_value(payload, "Description")),
    ]
    return " | ".join(dict.fromkeys(part for part in parts if part))


def imported_balance_matches_courier(payload: dict[str, Any], courier_id: str, courier_name: str) -> bool:
    payload_id = imported_balance_value(
        payload,
        "Courier ID",
        "CourierId",
        "Courier Number",
        "Driver ID",
        "User ID",
    )
    if courier_id and normalize_imported_courier_id(payload_id) == normalize_imported_courier_id(courier_id):
        return True
    payload_name = imported_balance_value(
        payload,
        "Driver",
        "Driver Name",
        "Courier",
        "Courier Name",
        "Name",
        "Név",
    )
    payload_name_key = normalize_text(payload_name)
    courier_name_key = normalize_text(courier_name)
    if not courier_name_key or not payload_name_key:
        return False
    if payload_name_key == courier_name_key:
        return True
    payload_tokens = set(payload_name_key.split())
    courier_tokens = set(courier_name_key.split())
    return (
        len(payload_tokens) >= 2
        and len(courier_tokens) >= 2
        and (payload_tokens <= courier_tokens or courier_tokens <= payload_tokens)
    )


def imported_balance_amount(payload: dict[str, Any], *keys: str) -> int:
    normalized = {normalized_field_key(key): value for key, value in (payload or {}).items()}
    for key in keys:
        clean_key = normalized_field_key(key)
        if clean_key in normalized and normalized[clean_key] not in (None, ""):
            return money_int(normalized[clean_key])
    return 0


def read_imported_bonus_malus_items(session_id: str, courier_id: str, courier_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not session_id:
        return [], []
    table_definitions = [
        (
            "bonus_route_row",
            "monthly_bonus_import",
            "Kiflis bónusz",
            1,
            ("Bonus", "Bónusz", "Bonus amount", "Bonus total", "Amount", "Összeg", "Total"),
        ),
        (
            "penalty_row",
            "monthly_malus_import",
            "Kiflis málusz",
            -1,
            ("Value", "Amount", "Összeg", "Penalty", "Malus", "Levonás"),
        ),
    ]
    bonus_items: list[dict[str, Any]] = []
    malus_items: list[dict[str, Any]] = []
    for table_name, key_prefix, label, sign, amount_keys in table_definitions:
        rows = optional_supabase_rows(
            table_name,
            schema="settlement",
            params={
                "select": "normalized_data,source_row_no",
                "session_id": f"eq.{session_id}",
                "limit": "5000",
            },
            timeout=30,
        )
        target_items = bonus_items if sign > 0 else malus_items
        for index, source_row in enumerate(rows, start=1):
            payload = imported_balance_payload(source_row)
            if not imported_balance_matches_courier(payload, courier_id, courier_name):
                continue
            amount = abs(imported_balance_amount(payload, *amount_keys))
            if not amount:
                continue
            target_items.append(
                signed_item(
                    f"{key_prefix}_{source_row.get('source_row_no') or index}",
                    label,
                    sign * amount,
                    source=f"settlement.{table_name}",
                    note=imported_balance_note(payload),
                )
            )
    return bonus_items, malus_items


def read_periodic_fee_rules(period_start: date, period_end: date) -> list[dict[str, Any]]:
    rows = optional_supabase_rows(
        "cfg_jitt_periodic_fees",
        schema="settlement",
        params={
            "select": "*",
            "is_active": "eq.true",
            "deleted_at": "is.null",
            "valid_from": f"lte.{period_end.isoformat()}",
            "or": f"(valid_to.is.null,valid_to.gte.{period_start.isoformat()})",
            "order": "priority.asc,valid_from.desc",
            "limit": "200",
        },
        timeout=30,
    )
    return rows


def read_periodic_route_rows(courier_id: str, courier_name: str, session_id: str, period_start: date, period_end: date) -> list[dict[str, Any]]:
    if not courier_id or not session_id:
        return []
    base_params = {
        "select": "normalized_data,route_date,weekday_iso,calculated_day_type,is_route_primary",
        "session_id": f"eq.{session_id}",
        "is_route_primary": "eq.true",
        "route_date": f"gte.{period_start.isoformat()}",
        "and": f"(route_date.gte.{period_start.isoformat()},route_date.lte.{period_end.isoformat()})",
        "limit": "5000",
    }
    rows = optional_supabase_rows(
        "jit_row",
        schema="settlement",
        params={**base_params, "courier_id": f"eq.{courier_id}"},
        timeout=60,
    )
    db_prefiltered_by_courier = bool(rows)
    if not rows:
        rows = optional_supabase_rows(
            "jit_row",
            schema="settlement",
            params=base_params,
            timeout=60,
        )
    courier_key = str(courier_id or "").strip().removesuffix(".0")
    name_key = normalize_text(courier_name)
    result: list[dict[str, Any]] = []
    for row in rows:
        data = row.get("normalized_data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = {}
        row_courier_id = text_from_nested(data, "Courier ID", "courier_id", "courierId").strip().removesuffix(".0")
        row_name = normalize_text(text_from_nested(data, "Driver", "driver_name", "courier_name", "Futár"))
        row_name_tokens = set(row_name.split())
        name_tokens = set(name_key.split())
        extended_name_match = (
            bool(row_name_tokens)
            and bool(name_tokens)
            and len(row_name_tokens) >= 2
            and len(name_tokens) >= 2
            and (row_name_tokens <= name_tokens or name_tokens <= row_name_tokens)
        )
        if row_courier_id:
            if row_courier_id != courier_key:
                continue
        elif name_key and row_name != name_key and not extended_name_match and not db_prefiltered_by_courier:
            continue
        work_date = date_from_row_value(row.get("route_date") or text_from_nested(data, "Excel dátum", "work_date", "delivery_date", "date"))
        if not work_date or work_date < period_start or work_date > period_end:
            continue
        route_type_value = text_from_nested(data, "Túratípus", "Route Type", "route_type", "routeLayer", "routeType") or "NORMAL"
        result.append({
            "work_date": work_date,
            "weekday": safe_int(row.get("weekday_iso")) or work_date.isoweekday(),
            "route_type": route_type_key(route_type_value),
            "day_type": day_type_key(row.get("calculated_day_type") or text_from_nested(data, "Naptípus", "day_type")),
            "orders": money_int(text_from_nested(data, "Orders", "orders", "Rendelések", "order_count")),
            "warehouse": normalize_text(text_from_nested(data, "Warehouse", "warehouse", "Raktár", "warehouse_code")),
        })
    return result


def calculate_periodic_correction_items(courier_id: str, courier_name: str, session_id: str, period_start: date, period_end: date, warehouse: str = "") -> list[dict[str, Any]]:
    rules = read_periodic_fee_rules(period_start, period_end)
    route_rows = read_periodic_route_rows(courier_id, courier_name, session_id, period_start, period_end)
    if not rules or not route_rows:
        return []
    items: list[dict[str, Any]] = []
    day_names = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
    for index, rule in enumerate(rules, start=1):
        valid_from = date_from_row_value(rule.get("valid_from")) or period_start
        valid_to = date_from_row_value(rule.get("valid_to")) or period_end
        weekdays = parse_weekdays(rule.get("weekdays"))
        rule_route_type = str(rule.get("route_type") or "any").casefold()
        rule_day_type = str(rule.get("day_type") or "any").casefold()
        rule_warehouse = normalize_text(rule.get("warehouse_code") or "")
        selected = [
            route
            for route in route_rows
            if valid_from <= route["work_date"] <= valid_to
            and (not weekdays or route["weekday"] in weekdays)
            and (rule_route_type == "any" or route["route_type"] == rule_route_type)
            and (rule_day_type == "any" or route["day_type"] == rule_day_type)
            and (not rule_warehouse or route["warehouse"] == rule_warehouse)
        ]
        if not selected:
            continue
        condition = str(rule.get("condition_metric") or "none").casefold()
        minimum = max(money_int(rule.get("condition_min")), 0)
        maximum_raw = rule.get("condition_max")
        maximum = money_int(maximum_raw) if maximum_raw not in (None, "") else None
        unit = str(rule.get("calculation_unit") or "per_route").casefold()
        unit_amount = money_int(rule.get("courier_amount_huf"))
        route_count = len(selected)
        order_count = sum(money_int(route.get("orders")) for route in selected)
        payable_units = 0
        metric_count = route_count
        if condition == "orders_per_route":
            filtered = [
                route for route in selected
                if money_int(route.get("orders")) >= minimum and (maximum is None or money_int(route.get("orders")) <= maximum)
            ]
            route_count = len(filtered)
            order_count = sum(money_int(route.get("orders")) for route in filtered)
            payable_units = order_count if unit == "per_order" else route_count
            metric_count = route_count
        elif condition == "routes_per_day":
            day_counts: dict[date, int] = {}
            for route in selected:
                day_counts[route["work_date"]] = day_counts.get(route["work_date"], 0) + 1
            eligible_counts = [count for count in day_counts.values() if count >= minimum and (maximum is None or count <= maximum)]
            metric_count = sum(eligible_counts)
            payable_units = len(eligible_counts) if unit == "fixed" else metric_count
            if unit == "per_order":
                payable_units = order_count
        elif condition == "routes_in_period":
            ok = route_count >= minimum and (maximum is None or route_count <= maximum)
            metric_count = route_count
            payable_units = 1 if ok and unit == "fixed" else route_count if ok else 0
            if ok and unit == "per_order":
                payable_units = order_count
        elif condition == "orders_in_period":
            ok = order_count >= minimum and (maximum is None or order_count <= maximum)
            metric_count = order_count
            payable_units = order_count if ok and unit == "per_order" else 1 if ok and unit == "fixed" else route_count if ok else 0
        elif condition == "every_n_routes_per_day":
            n_value = max(minimum, 1)
            day_counts: dict[date, int] = {}
            for route in selected:
                day_counts[route["work_date"]] = day_counts.get(route["work_date"], 0) + 1
            payable_units = sum(count // n_value for count in day_counts.values())
            metric_count = payable_units
        elif condition == "every_n_routes_in_period":
            n_value = max(minimum, 1)
            payable_units = route_count // n_value
            metric_count = payable_units
        elif condition == "orders_over_threshold_every_n_per_route":
            threshold = max(minimum, 0)
            step_value = max(maximum or 1, 1)
            payable_units = sum(max(money_int(route.get("orders")) - threshold, 0) // step_value for route in selected)
            metric_count = payable_units
        else:
            payable_units = order_count if unit == "per_order" else route_count
            metric_count = route_count
        amount = 0 if unit == "per_hour" else payable_units * unit_amount
        if not amount:
            continue
        weekday_label = ", ".join(day_names.get(day, str(day)) for day in sorted(weekdays)) if weekdays else "Minden nap"
        items.append(signed_item(
            f"correction_periodic_auto_{index}",
            str(rule.get("fee_name") or "Időszakos díj"),
            amount,
            source="settlement.cfg_jitt_periodic_fees",
            note=f"{weekday_label} | {metric_count} db | {payable_units} x {unit_amount} Ft",
        ))
    return items


def manual_adjustment_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        adjustment_type = str(row.get("adjustment_type") or "").strip()
        if not adjustment_type:
            continue
        totals[adjustment_type] = totals.get(adjustment_type, 0) + abs(money_int(row.get("amount_huf")))
    return totals


def is_manual_mobile_override(row: dict[str, Any] | None) -> bool:
    note = str((row or {}).get("note") or "").strip()
    if not note:
        return False
    note_key = normalize_text(note)
    return (
        "snapshot" not in note_key
        and "publikalt" not in note_key
        and "valos elszamolasi adat" not in note_key
    )


def apply_mobile_overrides(cards: list[dict[str, Any]], overrides: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def is_manual_override(row: dict[str, Any] | None) -> bool:
        return is_manual_mobile_override(row)

    def ensure_override_item(card_key: str, item_key: str, fallback_label: str, *, allow_snapshot: bool = False) -> None:
        override = overrides.get(item_key)
        if not override or not money_int(override.get("amount_value")):
            return
        if not allow_snapshot and not is_manual_override(override):
            return
        card = next((item for item in cards if item.get("key") == card_key), None)
        if not card:
            return
        items = card.setdefault("items", [])
        if any(str(item.get("key") or "") == item_key for item in items):
            return
        items.append(
            signed_item(
                item_key,
                str(override.get("item_label") or fallback_label),
                money_int(override.get("amount_value")),
                note=str(override.get("note") or "Admin altal modositva"),
            )
        )

    for card in cards:
        card_override = overrides.get(str(card.get("key") or ""))
        if card_override and (
            is_manual_override(card_override)
            or (not money_int(card.get("amountHuf")) and money_int(card_override.get("amount_value")))
        ):
            card["amountHuf"] = money_int(card_override.get("amount_value"))
            card["amountKind"] = str(card_override.get("amount_kind") or card.get("amountKind") or "huf")
            if is_manual_override(card_override):
                card["overrideNote"] = str(card_override.get("note") or "Admin által módosítva")
        for item in card.get("items") or []:
            override = overrides.get(str(item.get("key") or ""))
            if not override:
                continue
            if not is_manual_override(override) and money_int(item.get("amountHuf")):
                continue
            item["amountHuf"] = money_int(override.get("amount_value"))
            item["amountKind"] = str(override.get("amount_kind") or item.get("amountKind") or "huf")
            item["label"] = str(override.get("item_label") or item.get("label") or "")
            item["note"] = str(override.get("note") or "Admin által módosítva")
    performance = next((card for card in cards if card.get("key") == "performance"), None)
    if performance:
        items = performance.get("items") or []
        by_key = {str(item.get("key") or ""): item for item in items}
        routes = money_int((by_key.get("routes") or {}).get("amountHuf"))
        normal = money_int((by_key.get("normal_routes") or {}).get("amountHuf"))
        highlighted = money_int((by_key.get("highlighted_routes") or {}).get("amountHuf"))
        if routes > 0 and normal + highlighted == 0 and by_key.get("normal_routes"):
            by_key["normal_routes"]["amountHuf"] = routes
    deduction_override_items = [
        ("monthly_malus", "Levonások összesen"),
        ("returned_route", "Visszavett kor"),
        ("atm_effect", "ATM hatas"),
        ("reserve", "Celtartalek"),
        ("fuel", "Uzemanyag"),
        ("damage", "Kar / levonas"),
        ("cash_missing", "KP hiany"),
        ("other_deduction", "Egyeb levonas"),
        ("instructor_fee", "Oktatoi dij"),
        ("salary_advance", "Fizetes eloleg"),
    ]
    for item_key, label in deduction_override_items:
        ensure_override_item("deductions", item_key, label)
    for item_key, label in [
        ("kiflis_bonus_total", "Kiflis bonusz"),
        ("kiflis_malus_total", "Kiflis malusz"),
        ("monthly_bonus", "Kiflis bonusz"),
        ("monthly_malus", "Kiflis malusz"),
    ]:
        ensure_override_item("kiflis_bonus_malus", item_key, label)
    for item_key, label in [
        ("manual_bonus", "JITT bonusz"),
        ("manual_malus", "JITT malusz"),
        ("accepted_route", "Elfogadott kor korrekcio"),
        ("returned_route", "Visszavett kor"),
    ]:
        ensure_override_item("bonus_malus", item_key, label)
    for item_key, label in [
        ("loyalty_bonus", "Lojalitasi bonusz"),
        ("loyalty_current_routes", "Kifutott kor"),
        ("loyalty_advance_booking_days", "Elore foglalt muszak"),
        ("loyalty_rate", "Egysegar"),
    ]:
        ensure_override_item("loyalty_bonus", item_key, label)
    for item_key, label in [
        ("customer_rating", "Ugyfelelegedettseg"),
        ("manual_customer_rating", "Kezi ugyfelelegedettseg"),
    ]:
        ensure_override_item("customer_rating", item_key, label)
    correction_detail_keys = sorted(
        item_key
        for item_key in overrides
        if item_key.startswith("correction_periodic_")
    )
    if correction_detail_keys:
        for item_key in correction_detail_keys:
            ensure_override_item("corrections", item_key, "Korrekcio", allow_snapshot=True)
    deduction_card = next((card for card in cards if card.get("key") == "deductions"), None)
    kiflis_bonus_malus_card = next((card for card in cards if card.get("key") == "kiflis_bonus_malus"), None)
    bonus_malus_card = next((card for card in cards if card.get("key") == "bonus_malus"), None)
    if deduction_card and not overrides.get("deductions"):
        deduction_card["amountHuf"] = sum(money_int(item.get("amountHuf")) for item in deduction_card.get("items") or [])
    if kiflis_bonus_malus_card and not overrides.get("kiflis_bonus_malus"):
        kiflis_bonus_malus_card["amountHuf"] = sum(money_int(item.get("amountHuf")) for item in kiflis_bonus_malus_card.get("items") or [])
    if bonus_malus_card and not overrides.get("bonus_malus"):
        bonus_malus_card["amountHuf"] = sum(money_int(item.get("amountHuf")) for item in bonus_malus_card.get("items") or [])
    for card_key in ["loyalty_bonus", "customer_rating", "corrections"]:
        card = next((item for item in cards if item.get("key") == card_key), None)
        if card and not overrides.get(card_key):
            card["amountHuf"] = sum(
                money_int(item.get("amountHuf"))
                for item in card.get("items") or []
                if str(item.get("amountKind") or "huf") == "huf" and not item.get("excludeFromTotal")
            )
    return cards


def mobile_override_row(
    key: str,
    label: str,
    amount: int,
    *,
    kind: str = "huf",
    note: str = "DB-ből pótolt mobil érték",
) -> dict[str, Any]:
    return {
        "item_key": key,
        "item_label": label,
        "amount_kind": kind,
        "amount_value": money_int(amount),
        "note": note,
    }


def should_backfill_mobile_override(overrides: dict[str, dict[str, Any]], key: str) -> bool:
    current = overrides.get(key)
    if not current:
        return True
    if is_manual_mobile_override(current):
        return False
    return money_int(current.get("amount_value")) == 0


def backfill_mobile_override(
    overrides: dict[str, dict[str, Any]],
    key: str,
    label: str,
    amount: int,
    *,
    kind: str = "huf",
    note: str = "DB-ből pótolt mobil érték",
    allow_zero: bool = False,
) -> None:
    if not allow_zero and money_int(amount) == 0:
        return
    if should_backfill_mobile_override(overrides, key):
        overrides[key] = mobile_override_row(key, label, amount, kind=kind, note=note)


def enrich_mobile_overrides_from_financial_sources(
    user: dict[str, Any],
    month: date,
    row: dict[str, Any],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not overrides:
        return overrides
    courier_id, _courier_name = courier_identity(user)
    period_end = month_end(month)
    enriched = dict(overrides)

    customer_items = read_customer_rating_bonus_items(courier_id, month)
    route_count = money_from(row, "routes", "route_count", "completed_routes")
    if customer_items and route_count > 0:
        customer_completed_routes = sum(money_int(item.get("completedRoutes")) for item in customer_items)
        unit_amount = next((money_int(item.get("unitAmountHuf")) for item in customer_items if money_int(item.get("unitAmountHuf"))), 0)
        if unit_amount and customer_completed_routes != route_count:
            first_item = customer_items[0]
            average_rating = first_item.get("averageRating")
            note_parts = []
            if average_rating not in (None, ""):
                note_parts.append(f"Átlag: {average_rating}")
            note_parts.extend([f"Kör: {route_count}", f"{route_count} x {unit_amount} Ft", "normal"])
            customer_items = [
                signed_item(
                    "customer_rating_import_1",
                    "Ügyfélértékelési bónusz",
                    route_count * unit_amount,
                    source="public.bill_jitt_invoice_customer_rating_bonus",
                    note=" | ".join(note_parts),
                )
            ]
            customer_items[0]["completedRoutes"] = route_count
            customer_items[0]["unitAmountHuf"] = unit_amount
            customer_items[0]["averageRating"] = average_rating
            customer_items[0]["routeType"] = "normal"
    customer_total = sum(money_int(item.get("amountHuf")) for item in customer_items)
    if not customer_total:
        customer_total = money_from(row, "customer_rating_bonus_huf", "customer_rating_huf")
    if customer_total and not is_manual_mobile_override(enriched.get("customer_rating")):
        for key in list(enriched.keys()):
            if key.startswith("customer_rating_") and key != "customer_rating" and not is_manual_mobile_override(enriched.get(key)):
                enriched.pop(key, None)
        enriched["customer_rating"] = mobile_override_row(
            "customer_rating",
            "Ügyfélértékelési bónusz",
            customer_total,
            note="Ügyfélértékelés DB import alapján",
        )
        for item in customer_items:
            item_key = str(item.get("key") or "")
            if item_key:
                enriched[item_key] = mobile_override_row(
                    item_key,
                    str(item.get("label") or "Ügyfélértékelési bónusz"),
                    money_int(item.get("amountHuf")),
                    note=str(item.get("note") or "Ügyfélértékelés DB import alapján"),
                )

    needs_insurance_backfill = any(
        should_backfill_mobile_override(enriched, key)
        for key in ["reserve", "insurance_fee"]
    ) or any(key not in enriched for key in ["target_reserve_open", "target_reserve_close"])
    if needs_insurance_backfill:
        target_reserve_month = read_target_reserve_monthly(courier_id, month, period_end)
        reserve_open = money_from(row, "target_reserve_open_huf", "reserve_before_huf")
        reserve_topup = -abs(money_from(row, "target_reserve_topup_huf", "reserve_deduction_huf"))
        insurance_fee = -abs(money_from(row, "insurance_fee_huf", "insurance_deduction_huf"))
        reserve_close = money_from(row, "target_reserve_close_huf", "reserve_after_huf")
        if target_reserve_month:
            reserve_open = money_from(target_reserve_month, "reserve_before_huf")
            reserve_topup = -abs(money_from(target_reserve_month, "reserve_addition_huf"))
            insurance_fee = -abs(money_from(target_reserve_month, "insurance_fee_huf"))
            reserve_close = money_from(target_reserve_month, "reserve_after_huf")
        for key, label, amount in [
            ("target_reserve_open", "Céltartalék nyitó", reserve_open),
            ("reserve", "Céltartalék levonás", reserve_topup),
            ("insurance_fee", "Biztosítási díj", insurance_fee),
            ("target_reserve_close", "Céltartalék záró", reserve_close),
        ]:
            backfill_mobile_override(
                enriched,
                key,
                label,
                amount,
                note="Céltartalék / biztosítás DB alapján",
                allow_zero=key in {"target_reserve_open", "target_reserve_close"},
            )

    has_periodic_correction = any(
        key.startswith("correction_periodic_") and money_int(value.get("amount_value"))
        for key, value in enriched.items()
    )
    if not has_periodic_correction:
        correction_total = money_from(
            row,
            "correction_huf",
            "periodic_correction_huf",
            "correction_total_huf",
            "manual_correction_huf",
            "Időszakos díjak / korrekció",
            "Korrekció",
            "Korrekciók",
        )
        backfill_mobile_override(
            enriched,
            "correction_periodic_summary",
            "Korrekció",
            correction_total,
            note="Elszámolási DB korrekció alapján",
        )

    performance_count = money_from(row, "orders", "order_count", "performance")
    route_count = money_from(row, "routes", "route_count")
    normal_routes = money_from(row, "normal_routes", "normal_route_count")
    highlighted_routes = money_from(row, "highlighted_routes", "highlighted_route_count")
    for key, label, amount in [
        ("performance", "Teljesítmény", performance_count),
        ("orders", "Cím", performance_count),
        ("routes", "Kör", route_count),
        ("normal_routes", "Normál kör", normal_routes),
        ("highlighted_routes", "Kiemelt kör", highlighted_routes),
    ]:
        backfill_mobile_override(
            enriched,
            key,
            label,
            amount,
            kind="count",
            note="Teljesítmény DB alapján",
        )

    return enriched


def refresh_payable_card_totals(
    cards: list[dict[str, Any]],
    *,
    keep_payable_override: bool = False,
    payable_override_huf: int | None = None,
) -> int:
    income_card = next((card for card in cards if card.get("key") == "income"), None)
    deduction_card = next((card for card in cards if card.get("key") == "deductions"), None)
    correction_card = next((card for card in cards if card.get("key") == "corrections"), None)
    payable_card = next((card for card in cards if card.get("key") == "payable"), None)
    income_total = money_int((income_card or {}).get("amountHuf"))
    deduction_total = money_int((deduction_card or {}).get("amountHuf"))
    correction_total = money_int((correction_card or {}).get("amountHuf"))
    if payable_override_huf is not None:
        payable_total = money_int(payable_override_huf)
    elif keep_payable_override:
        payable_total = money_int((payable_card or {}).get("amountHuf"))
    else:
        payable_total = income_total + deduction_total + correction_total
    if payable_card is not None:
        payable_card["amountHuf"] = payable_total
        payable_card["items"] = [
            signed_item("income_total", "Jóváírások összesen", income_total),
            signed_item("deduction_total", "Levonások összesen", deduction_total),
            signed_item("correction_total", "Korrekciók összesen", correction_total),
            signed_item("payable_total", "Kifizetendő", payable_total),
        ]
    return payable_total


def tig_split_amount(amount: int, tax_mode: str) -> tuple[int, int, int, str]:
    sign = -1 if amount < 0 else 1
    gross = abs(money_int(amount))
    if tax_mode == "vat":
        net_abs = int(round(gross / 1.27))
        vat_abs = gross - net_abs
        return sign * net_abs, sign * vat_abs, sign * gross, "27%" if sign > 0 else "Levonás"
    return sign * gross, 0, sign * gross, "AAM" if sign > 0 else "Levonás"


def tig_document_meta(month: date, courier_id: str) -> dict[str, str]:
    period_start = month.replace(day=1)
    period_end = month_end(period_start)
    due_date = date.today() + timedelta(days=8)
    return {
        "periodLabel": f"{period_start:%Y.%m.%d} - {period_end:%Y.%m.%d}",
        "performanceDate": due_date.isoformat(),
        "paymentDueDate": due_date.isoformat(),
        "note": f"Futár ID: {courier_id}",
    }


def apply_tig_overrides(breakdown: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not breakdown.get("available"):
        return breakdown
    rows = [
        row for row in (breakdown.get("rows") or [])
        if str(row.get("key") or "") not in {"cash_deduction", "tig_cash_deduction"}
    ]
    breakdown["rows"] = rows
    for row in rows:
        override = overrides.get(f"tig_{row.get('key') or ''}")
        if not override:
            continue
        amount = money_int(override.get("amount_value"))
        row["grossHuf"] = amount
        sign = -1 if money_int(row.get("grossHuf")) < 0 else 1
        gross_abs = abs(money_int(row.get("grossHuf")))
        if row.get("key") == "tip":
            row["netHuf"] = sign * gross_abs
            row["vatHuf"] = 0
            row["vatLabel"] = "Adómentes"
            row["grossHuf"] = sign * gross_abs
            continue
        if breakdown.get("taxMode") == "vat":
            net = int(round(gross_abs / 1.27))
            vat = gross_abs - net
            row["netHuf"] = sign * net
            row["vatHuf"] = sign * vat
            row["vatLabel"] = "27%" if sign > 0 else "Levonás"
        else:
            row["netHuf"] = money_int(row.get("grossHuf"))
            row["vatHuf"] = 0
            if row.get("key") == "tip":
                row["vatLabel"] = "Adómentes"
        row["label"] = str(override.get("item_label") or row.get("label") or "")
        if row.get("key") == "transfer_service":
            row["label"] = "Szállítási díj (494107) - átutalás"
        elif row.get("key") == "cash_service":
            row["label"] = "Szállítási díj (494107) - készpénz"
        row["note"] = str(override.get("note") or "Admin Ăˇltal mĂłdosĂ­tva")
    final_override = overrides.get("tig_final_total")
    if final_override:
        breakdown["finalTotalHuf"] = money_int(final_override.get("amount_value"))
    else:
        breakdown["finalTotalHuf"] = money_int(breakdown.get("finalTotalHuf"))
    return breakdown


def align_tig_breakdown_with_financial_cards(breakdown: dict[str, Any], financial_breakdown: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in breakdown.get("rows") or []:
        key = str(row.get("key") or "")
        if key in {"cash_deduction", "tig_cash_deduction"}:
            continue
        clean_row = dict(row)
        if key == "transfer_service":
            clean_row["label"] = "Szállítási díj (494107) - átutalás"
            clean_row["note"] = str(clean_row.get("note") or "Kifizetendő összeg borravaló nélkül.")
        elif key == "cash_service":
            clean_row["label"] = "Szállítási díj (494107) - készpénz"
            clean_row["note"] = str(clean_row.get("note") or "Külön KP sor, nem növeli az átutalásos végösszeget.")
        elif key == "tip":
            clean_row["label"] = "Borravaló"
            clean_row["note"] = str(clean_row.get("note") or "Külön tétel.")
        rows.append(clean_row)
    breakdown["rows"] = rows
    breakdown["available"] = True
    return breakdown


def build_workflow_tig_breakdown(user: dict[str, Any], month: date, financial_breakdown: dict[str, Any]) -> dict[str, Any]:
    courier_id, courier_name = courier_identity(user)
    if not financial_breakdown.get("available"):
        return {
            "available": False,
            "month": month.strftime("%Y-%m"),
            "message": "A TIG bontĂˇs az elszĂˇmolĂˇsi adatok elkĂ©szĂĽlte utĂˇn lĂˇthatĂł.",
            "rows": [],
        }
    profile_rows = optional_supabase_rows(
        "courier_master",
        params={"select": "*", "courier_id": f"eq.{courier_id}", "limit": "1"},
        timeout=30,
    )
    profile = profile_rows[0] if profile_rows else {}
    breakdown_items = {
        str(item.get("key") or ""): item
        for card in financial_breakdown.get("cards") or []
        for item in card.get("items") or []
    }
    tip_amount = money_int((breakdown_items.get("tip") or {}).get("amountHuf"))
    cash_amount = abs(money_int((breakdown_items.get("atm_effect") or breakdown_items.get("cash_missing") or {}).get("amountHuf")))
    payable = money_int(financial_breakdown.get("totalPayableHuf"))
    tig = build_tig_breakdown(
        {
            "name": courier_name,
            "company_name": profile.get("company_name") or courier_name,
            "address": profile.get("company_address") or profile.get("address") or "",
            "tax_number": profile.get("tax_number") or profile.get("tax_id") or "",
            "tig_type": profile.get("tig_type") or profile.get("tig_mode") or profile.get("invoice_type") or profile.get("invoice_vat_type") or profile.get("vat_status") or "",
            "vat_status": profile.get("vat_status") or "",
            "employment_type": profile.get("employment_type") or "",
            "employment_status": profile.get("employment_status") or "",
            "efo_status": profile.get("efo_status") or "",
            "id": courier_id,
            "document_month": month,
        },
        {"payable": payable, "cash": cash_amount, "tip": tip_amount},
    )
    tig["month"] = month.strftime("%Y-%m")
    tig["courierId"] = courier_id
    tig["courierName"] = courier_name
    fallback_meta = tig_document_meta(month, courier_id)
    document_meta = {**fallback_meta, **(tig.get("documentMeta") or {})}
    tig["buyer"] = {
        "label": "Vevő",
        "name": "Just in Time Transport Hungary Kft.",
        "postalCity": "1201 Budapest",
        "address": "Atléta utca 44.",
        "taxNumber": "32649460-2-43",
        "periodLabel": document_meta.get("periodLabel") or fallback_meta["periodLabel"],
        "performanceDate": document_meta.get("performanceDate") or fallback_meta["performanceDate"],
        "paymentDueDate": document_meta.get("paymentDueDate") or fallback_meta["paymentDueDate"],
        "note": document_meta.get("note") or fallback_meta["note"],
    }
    tig = align_tig_breakdown_with_financial_cards(tig, financial_breakdown)
    return apply_tig_overrides(tig, read_mobile_breakdown_overrides(courier_id, month))


def hidden_financial_breakdown(month: date) -> dict[str, Any]:
    return {
        "available": False,
        "amountsHidden": True,
        "month": month.strftime("%Y-%m"),
        "totalPayableHuf": 0,
        "cards": [],
        "complaintOptions": [],
        "source": "settlement.courier_settlement_summary",
        "message": "A havi elszámolási összegeket csak admin és Bagoly Zoltán láthatja.",
    }


def build_financial_breakdown(user: dict[str, Any], month: date, *, allow_unpublished: bool = False) -> dict[str, Any]:
    courier_id, _courier_name = courier_identity(user)
    allow_unpublished = allow_unpublished or is_unrestricted_legacy_settlement_month(month)
    row = read_courier_settlement_summary_row(courier_id, month, allow_unpublished=allow_unpublished)
    overrides = read_mobile_breakdown_overrides(courier_id, month)
    overrides = enrich_mobile_overrides_from_financial_sources(user, month, row or {}, overrides)
    mobile_breakdown = build_financial_breakdown_from_mobile_rows(user, month, row or {}, overrides)
    if mobile_breakdown:
        return mobile_breakdown
    if not row or row.get("_mobile_unavailable_message"):
        return {
            "available": False,
            "month": month.strftime("%Y-%m"),
            "totalPayableHuf": 0,
            "cards": [],
            "complaintOptions": [],
            "source": "settlement.courier_settlement_summary",
            "message": str(row.get("_mobile_unavailable_message") if row else "") or "Ehhez a hónaphoz még nincs mentett pénzügyi bontás.",
        }

    period_end = month_end(month)
    daily_performance_rows = load_daily_performance_for_courier(courier_id, month, period_end)
    delay_rows = load_route_delay_rows_for_courier(courier_id, month, period_end)
    compliance_rows = load_route_compliance_rows_for_courier(courier_id, month, period_end)
    delayed_orders = sum(safe_int(item.get("delayed_order_count")) for item in daily_performance_rows)
    late_count = sum(safe_int(item.get("late_count")) for item in daily_performance_rows)
    no_show_count = sum(safe_int(item.get("did_not_come_count")) for item in daily_performance_rows)
    shift_count = sum(safe_int(item.get("shift_count")) for item in daily_performance_rows)
    route_delayed_stops = sum(safe_int(item.get("delayed_stops_count")) for item in delay_rows)
    route_delay_minutes = sum(safe_int(item.get("total_delay_minutes")) for item in delay_rows)
    if not daily_performance_rows:
        delayed_orders = 0
        late_count = 0
        no_show_count = 0
        shift_count = 0
    if route_delayed_stops:
        delayed_orders = route_delayed_stops

    target_reserve_month = read_target_reserve_monthly(courier_id, month, period_end)
    base = money_from(row, "fixed_rate_huf", "courier_base_rate_huf")
    tip = money_from(row, "tip_huf")
    delay = money_from(row, "delay_bonus_huf")
    compliance = money_from(row, "compliance_bonus_huf")
    loyalty = money_from(row, "loyalty_bonus_huf")
    customer_rating = money_from(row, "customer_rating_bonus_huf", "customer_rating_huf")
    monthly_bonus = money_from(row, "monthly_bonus_huf") or money_sum_from(
        row,
        "other_route_bonus_huf",
        "imported_bonus_huf",
        "manual_bonus_huf",
    )
    monthly_malus = abs(money_from(row, "monthly_malus_huf") or money_from(row, "malus_huf"))
    monthly_adjustment_effect = money_from(row, "monthly_adjustment_effect_huf")
    if monthly_adjustment_effect:
        monthly_bonus = max(monthly_adjustment_effect, 0)
        monthly_malus = abs(min(monthly_adjustment_effect, 0))
    summary_monthly_bonus = monthly_bonus
    summary_monthly_malus = monthly_malus
    returned_route = abs(money_from(row, "monthly_returned_route_huf"))
    accepted_route = money_from(row, "monthly_accepted_route_huf")
    atm_effect = money_from(row, "atm_effect_huf") or -abs(money_from(row, "atm_deduction_huf"))
    reserve_topup = -abs(money_from(row, "target_reserve_topup_huf", "reserve_deduction_huf"))
    reserve_open = money_from(row, "target_reserve_open_huf", "reserve_before_huf")
    reserve_close = money_from(row, "target_reserve_close_huf", "reserve_after_huf")
    insurance_fee = -abs(money_from(row, "insurance_fee_huf", "insurance_deduction_huf"))
    if target_reserve_month:
        reserve_topup = -abs(money_from(target_reserve_month, "reserve_addition_huf"))
        reserve_open = money_from(target_reserve_month, "reserve_before_huf")
        reserve_close = money_from(target_reserve_month, "reserve_after_huf")
        insurance_fee = -abs(money_from(target_reserve_month, "insurance_fee_huf"))
    fuel = money_from(row, "fuel_huf")
    damage = money_from(row, "damage_huf")
    cash_missing = money_from(row, "cash_missing_huf")
    other_income = money_from(row, "other_income_huf")
    other_deduction = money_from(row, "other_deduction_huf") or -abs(money_from(row, "other_expense_huf"))
    instructor_fee = money_from(row, "instructor_fee_huf")
    payable_from_summary = money_from(row, "payable_total_huf", "payable_huf")
    payable = payable_from_summary

    manual_adjustment_rows = read_courier_manual_adjustments(courier_id, month, period_end)
    manual_adjustments = manual_adjustment_totals(manual_adjustment_rows)
    monthly_bonus += manual_adjustments.get("bonus", 0)
    customer_rating += manual_adjustments.get("customer_rating", 0)
    monthly_malus += manual_adjustments.get("malus", 0)
    atm_effect -= manual_adjustments.get("atm_deduction", 0)
    other_deduction -= manual_adjustments.get("other_expense", 0)
    main_session_id = str(row.get("_mobile_session_id") or row.get("session_id") or "")
    imported_balance_session_id = latest_excel_balance_session_for_month(month) or main_session_id
    imported_bonus_items, imported_malus_items = read_imported_bonus_malus_items(
        imported_balance_session_id,
        courier_id,
        _courier_name,
    )

    income_items = [
        signed_item("base", "Alapdíj", base),
        signed_item("tip", "Borravaló", tip),
        signed_item("delay_bonus", "Késedelmi díj", delay),
        signed_item("compliance_bonus", "Túramegfelelés", compliance),
        signed_item("loyalty_bonus", "Lojalitási bónusz", loyalty),
        signed_item("customer_rating", "Ügyfélelégedettség", customer_rating),
        signed_item("monthly_bonus", "Bónuszok összesen", monthly_bonus),
        signed_item("accepted_route", "Elfogadott kör korrekció", accepted_route),
        signed_item("other_income", "Egyéb jóváírás", other_income),
    ]
    deduction_items = [
        signed_item("monthly_malus", "Levonások összesen", -monthly_malus),
        signed_item("returned_route", "Visszavett kör", -returned_route),
        signed_item("atm_effect", "ATM hatás", atm_effect),
        signed_item("reserve", "Céltartalék", reserve_topup),
        signed_item("insurance_fee", "Biztosítási díj", insurance_fee),
        signed_item("fuel", "Üzemanyag", fuel),
        signed_item("damage", "Kár / levonás", damage),
        signed_item("cash_missing", "KP hiány", cash_missing),
        signed_item("other_deduction", "Egyéb levonás", other_deduction),
        signed_item("instructor_fee", "Oktatói díj", instructor_fee),
    ]
    income_items = [
        item for item in income_items
        if item["amountHuf"] or item["key"] == "customer_rating"
    ]
    deduction_items = [item for item in deduction_items if item["amountHuf"]]
    insurance_items = [
        signed_item("target_reserve_open", "Céltartalék nyitó", reserve_open),
        signed_item("reserve", "Céltartalék levonás", reserve_topup),
        signed_item("insurance_fee", "Biztosítási havi díj", insurance_fee),
        signed_item("target_reserve_close", "Új nyitó / záró egyenleg", reserve_close),
    ]
    insurance_items = [
        current for current in insurance_items
        if current["amountHuf"] or current["key"] in {"target_reserve_open", "target_reserve_close"}
    ]
    insurance_total = reserve_topup + insurance_fee
    income_total = sum(item["amountHuf"] for item in income_items)
    deduction_total = sum(item["amountHuf"] for item in deduction_items)
    if not payable:
        payable = income_total + deduction_total

    manual_bonus = manual_adjustments.get("bonus", 0)
    manual_malus = manual_adjustments.get("malus", 0)
    manual_customer_rating = manual_adjustments.get("customer_rating", 0)
    manual_correction_items = []
    correction_total = 0
    overrides = read_mobile_breakdown_overrides(courier_id, month)
    has_mobile_correction = any(
        (item_key == "correction" or item_key.startswith("correction_"))
        and money_int(item.get("amount_value"))
        for item_key, item in overrides.items()
    )
    if not has_mobile_correction:
        periodic_correction_items = calculate_periodic_correction_items(
            courier_id,
            _courier_name,
            imported_balance_session_id,
            month,
            period_end,
            str(row.get("warehouse_name") or row.get("warehouse") or ""),
        )
        if periodic_correction_items:
            manual_correction_items.extend(periodic_correction_items)
            correction_total = sum(item["amountHuf"] for item in manual_correction_items)
    manual_bonus_malus_types = {"bonus", "malus"}
    manual_bonus_malus_items = [
        signed_item(
            f"manual_{str(row.get('adjustment_type') or 'adjustment')}_{index}",
            {
                "bonus": "JITT bónusz",
                "malus": "JITT málusz",
            }.get(str(row.get("adjustment_type") or ""), "Kézi korrekció"),
            -money_int(row.get("amount_huf")) if str(row.get("adjustment_type") or "") == "malus" else money_int(row.get("amount_huf")),
            source="settlement.courier_settlement_adjustment",
            note=str(row.get("note") or ""),
        )
        for index, row in enumerate(manual_adjustment_rows, start=1)
        if str(row.get("adjustment_type") or "") in manual_bonus_malus_types
    ]
    imported_bonus_total = sum(money_int(item.get("amountHuf")) for item in imported_bonus_items)
    if not imported_bonus_total:
        imported_bonus_total = money_from(row, "imported_bonus_huf") or max(summary_monthly_bonus - manual_bonus, 0)
    imported_malus_total = abs(sum(money_int(item.get("amountHuf")) for item in imported_malus_items))
    if not imported_malus_total:
        imported_malus_total = money_from(row, "imported_malus_huf") or max(summary_monthly_malus - manual_malus, 0)
    summary_imported_bonus = money_from(row, "imported_bonus_huf")
    summary_imported_malus = abs(money_from(row, "imported_malus_huf"))
    imported_bonus_delta = imported_bonus_total - summary_imported_bonus
    imported_malus_delta = imported_malus_total - summary_imported_malus
    if imported_bonus_delta > 0:
        income_items.append(signed_item("kiflis_bonus_income_delta", "Kiflis bónusz", imported_bonus_delta))
    if imported_malus_delta > 0:
        deduction_items.append(signed_item("kiflis_malus_deduction_delta", "Kiflis málusz", -imported_malus_delta))
    income_items = [item for item in income_items if item["amountHuf"] or item["key"] == "customer_rating"]
    deduction_items = [item for item in deduction_items if item["amountHuf"]]
    income_total = sum(item["amountHuf"] for item in income_items)
    deduction_total = sum(item["amountHuf"] for item in deduction_items)
    kiflis_bonus_remainder = imported_bonus_total - sum(money_int(item.get("amountHuf")) for item in imported_bonus_items)
    kiflis_malus_remainder = imported_malus_total - abs(sum(money_int(item.get("amountHuf")) for item in imported_malus_items))
    kiflis_bonus_malus_items = [
        *imported_bonus_items,
        signed_item("kiflis_bonus_total", "Kiflis bónusz", kiflis_bonus_remainder),
        *imported_malus_items,
        signed_item("kiflis_malus_total", "Kiflis málusz", -kiflis_malus_remainder),
    ]
    kiflis_bonus_malus_items = [item for item in kiflis_bonus_malus_items if item["amountHuf"]]
    kiflis_bonus_malus_total = sum(item["amountHuf"] for item in kiflis_bonus_malus_items)
    jitt_bonus_malus_items = [
        signed_item("accepted_route", "Elfogadott kör korrekció", accepted_route),
        signed_item("returned_route", "Visszavett kör", -returned_route),
    ]
    jitt_bonus_malus_items = [item for item in jitt_bonus_malus_items if item["amountHuf"]] + manual_bonus_malus_items
    jitt_bonus_malus_total = sum(item["amountHuf"] for item in jitt_bonus_malus_items)
    loyalty_items = [
        signed_item("loyalty_bonus", "Lojalitási bónusz", loyalty),
        count_item("loyalty_current_routes", "Kifutott kör", money_from(row, "loyalty_current_normal_routes", "loyalty_current_route_count", "route_count", "routes")),
        count_item("loyalty_advance_booking_days", "Előre foglalt műszak", money_from(row, "loyalty_advance_booking_days", "advance_booking_days")),
        {**signed_item("loyalty_rate", "Egységösszeg", money_from(row, "loyalty_rate_huf")), "excludeFromTotal": True},
        signed_item("loyalty_status", "Státusz", 0, note=str(row.get("loyalty_status") or row.get("Lojalitás státusz") or "")),
    ]
    customer_rating_items = [
        signed_item("customer_rating", "Ügyfélelégedettség", customer_rating - manual_customer_rating),
        count_item("customer_rating_routes", "Érintett kör", money_from(row, "customer_rating_completed_routes", "completed_routes", "route_count", "routes")),
        signed_item("manual_customer_rating", "Kézi ügyfélértékelés", manual_customer_rating, source="settlement.courier_settlement_adjustment"),
    ]
    loyalty_items = [
        item for item in loyalty_items
        if item["amountHuf"] or item.get("amountKind") == "count" or str(item.get("note") or "").strip()
    ]
    customer_rating_items = [
        item for item in customer_rating_items
        if item["amountHuf"] or item.get("amountKind") == "count"
    ]
    payable = income_total + deduction_total + correction_total

    route_items = [
        count_item("orders", "Cím", money_from(row, "orders", "order_count")),
        count_item("routes", "Kör", money_from(row, "route_count", "routes")),
        count_item("highlighted_routes", "Kiemelt kör", money_from(row, "kiemelt_routes", "highlighted_routes")),
        count_item("normal_routes", "Normál kör", money_from(row, "sima_routes", "normal_routes")),
        count_item("loyalty_previous_normal_routes", "Lojalitás: előző havi normál kör", money_from(row, "loyalty_previous_normal_routes", "loyalty_previous_route_count")),
        count_item("loyalty_current_normal_routes", "Lojalitás: aktuális normál kör", money_from(row, "loyalty_current_normal_routes", "loyalty_current_route_count")),
        count_item("loyalty_advance_booking_days", "Lojalitás: előre foglalt nap", money_from(row, "loyalty_advance_booking_days", "advance_booking_days")),
        count_item("shift_count", "Műszak", shift_count),
        count_item("late_count", "Késések száma", late_count),
        count_item("delayed_orders", "Késéses cím", delayed_orders),
        count_item("delay_minutes", "Késés összesen", route_delay_minutes),
        count_item("no_show_count", "Nem jelent meg műszakban", no_show_count),
    ]
    for delay_row in delay_rows[:30]:
        minutes = safe_int(delay_row.get("total_delay_minutes"))
        delayed_stops = safe_int(delay_row.get("delayed_stops_count"))
        if minutes <= 0 and delayed_stops <= 0:
            continue
        route_items.append({
            "key": f"delay_route_{delay_row.get('route_id')}",
            "label": f"Késés: {str(delay_row.get('delivery_date') or '')[:10]} / Route {delay_row.get('route_id')}",
            "amountHuf": minutes,
            "amountKind": "count",
            "note": f"{delayed_stops} késéses cím, max {safe_int(delay_row.get('max_delay_minutes'))} perc",
            "source": "courier_financial_overview_delay",
        })
    for compliance_row in compliance_rows[:30]:
        start_delay = safe_int(compliance_row.get("planned_start_delay_minutes"))
        departure_delay = safe_int(compliance_row.get("departure_delay_minutes"))
        has_checkin = str(compliance_row.get("actual_start_at") or compliance_row.get("shift_available_at") or "").strip()
        if start_delay <= 0 and departure_delay <= 0 and has_checkin:
            continue
        route_items.append({
            "key": f"compliance_route_{compliance_row.get('route_id')}",
            "label": f"Bejelentkezés: {str(compliance_row.get('shift_date') or '')[:10]} / Route {compliance_row.get('route_id')}",
            "amountHuf": max(start_delay, 0),
            "amountKind": "count",
            "note": f"Indulás eltérés: {departure_delay} perc",
            "source": "courier_financial_overview_compliance",
        })
    hidden_performance_keys = {"late_count", "delayed_orders", "delay_minutes", "no_show_count"}
    route_items = [
        item for item in route_items
        if item.get("key") not in hidden_performance_keys
        and (item.get("amountKind") == "count" or item["amountHuf"])
    ]
    cards = [
        {
            "key": "payable",
            "label": "Teljes összeg",
            "amountHuf": payable,
            "tone": "total",
            "items": [
                signed_item("income_total", "Jóváírások összesen", income_total),
                signed_item("deduction_total", "Levonások összesen", deduction_total),
                signed_item("payable_total", "Kifizetendő", payable),
            ],
        },
        {"key": "income", "label": "Jóváírások", "amountHuf": income_total, "tone": "income", "items": income_items},
        {"key": "deductions", "label": "Levonások összesen", "amountHuf": deduction_total, "tone": "deduction", "items": deduction_items},
        {"key": "base", "label": "Alapdíj", "amountHuf": base, "tone": "income", "items": [signed_item("base", "Alapdíj", base)]},
        {"key": "delay_bonus", "label": "Késedelmi díj", "amountHuf": delay, "tone": "income", "items": [signed_item("delay_bonus", "Késedelmi díj", delay)]},
        {"key": "compliance_bonus", "label": "Túramegfelelés", "amountHuf": compliance, "tone": "income", "items": [signed_item("compliance_bonus", "Túramegfelelés", compliance)]},
        {"key": "loyalty_bonus", "label": "Lojalitási bónusz", "amountHuf": loyalty, "tone": "income", "items": loyalty_items},
        {"key": "customer_rating", "label": "Ügyfélértékelés", "amountHuf": customer_rating, "tone": "income", "items": customer_rating_items},
        {"key": "kiflis_bonus_malus", "label": "Kiflis levonások / bónuszok", "amountHuf": kiflis_bonus_malus_total, "tone": "info", "items": kiflis_bonus_malus_items},
        {"key": "bonus_malus", "label": "JITT bónusz / málusz", "amountHuf": jitt_bonus_malus_total, "tone": "info", "items": jitt_bonus_malus_items},
        {"key": "corrections", "label": "Korrekciók", "amountHuf": correction_total, "tone": "info", "items": manual_correction_items},
        {"key": "insurance", "label": "Biztosítás", "amountHuf": insurance_total, "tone": "deduction", "items": insurance_items},
        {"key": "performance", "label": "Teljesítmény", "amountHuf": money_from(row, "orders", "order_count"), "amountKind": "count", "tone": "info", "items": route_items},
    ]
    cards = apply_mobile_overrides(cards, overrides)
    for card in cards:
        if card.get("key") != "deductions":
            continue
        if not card.get("items") and money_int(card.get("amountHuf")):
            card["items"] = [
                signed_item(
                    "deduction_total_visible",
                    "LevonĂˇsok / korrekciĂłk Ă¶sszesen",
                    money_int(card.get("amountHuf")),
                    note="Ă–sszesĂ­tett mobil elszĂˇmolĂˇsi adat.",
                )
            ]
    payable = refresh_payable_card_totals(
        cards,
        keep_payable_override=bool(payable_from_summary) or is_manual_mobile_override(overrides.get("payable")),
        payable_override_huf=(
            mobile_override_amount(overrides, "payable")
            if "payable" in overrides
            else None
        ),
    )
    complaint_excluded_keys = {
        "delay_bonus",
        "compliance_bonus",
        "late_count",
        "delayed_orders",
        "delay_minutes",
        "no_show_count",
    }
    complaint_excluded_prefixes = ("delay_route_", "compliance_route_")
    complaint_options = [
        {"key": item["key"], "label": item["label"], "amountHuf": item["amountHuf"], "amountKind": item.get("amountKind", "huf")}
        for card in cards
        for item in card["items"]
        if item["key"] not in {"income_total", "deduction_total", "payable_total"}
        and item["key"] not in complaint_excluded_keys
        and not str(item["key"]).startswith(complaint_excluded_prefixes)
        and not item.get("excludeFromTotal")
    ]
    visible_cards = [card for card in cards if card.get("key") not in {"income", "deductions"}]
    return {
        "available": True,
        "month": month.strftime("%Y-%m"),
        "sessionId": str(row.get("_mobile_session_id") or row.get("session_id") or ""),
        "sourceMode": str(row.get("_mobile_source_mode") or ""),
        "sourceSheet": str(row.get("_mobile_source_sheet") or ""),
        "totalPayableHuf": payable,
        "cards": visible_cards,
        "complaintOptions": complaint_options,
        "source": "settlement.courier_settlement_summary",
        "message": "",
    }


def load_month_day_rules(period_start: date, period_end: date) -> tuple[list[dict[str, Any]], str]:
    rows = optional_supabase_rows(
        "cfg_jitt_day_definitions",
        schema="settlement",
        params={
            "select": "day_type,weekdays,valid_from,valid_to,priority",
            "is_active": "eq.true",
            "deleted_at": "is.null",
            "valid_from": f"lte.{period_end.isoformat()}",
            "or": f"(valid_to.is.null,valid_to.gte.{period_start.isoformat()})",
            "order": "priority.asc,valid_from.desc",
            "limit": "100",
        },
    )
    if rows:
        return rows, "rules"
    return [
        {
            "day_type": "highlighted",
            "weekdays": [1, 5, 6, 7],
            "valid_from": "1900-01-01",
            "valid_to": "2026-06-30",
            "priority": 999,
        },
        {
            "day_type": "highlighted",
            "weekdays": [1, 5, 6],
            "valid_from": "2026-07-01",
            "valid_to": None,
            "priority": 999,
        }
    ], "fallback"


def day_type_for_date(value: date | None, day_rules: list[dict[str, Any]]) -> str:
    if not value:
        return "unknown"
    def rule_sort_key(rule: dict[str, Any]) -> tuple[int, int]:
        try:
            valid_from = date.fromisoformat(str(rule.get("valid_from") or "1900-01-01")[:10])
            valid_from_order = -valid_from.toordinal()
        except ValueError:
            valid_from_order = 0
        return safe_int(rule.get("priority")), valid_from_order

    sorted_rules = sorted(
        day_rules,
        key=rule_sort_key,
    )
    for rule in sorted_rules:
        try:
            valid_from = date.fromisoformat(str(rule.get("valid_from") or "1900-01-01")[:10])
            valid_to_raw = str(rule.get("valid_to") or "").strip()
            valid_to = date.fromisoformat(valid_to_raw[:10]) if valid_to_raw else date.max
            weekdays = parse_weekdays(rule.get("weekdays"))
            if valid_from <= value <= valid_to and value.isoweekday() in weekdays:
                return str(rule.get("day_type") or "normal")
        except Exception:
            continue
    return "normal"


def parse_date_value(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def weekday_labels(values: Any) -> str:
    labels = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
    days = parse_weekdays(values)
    return ", ".join(labels.get(day, str(day)) for day in days)


def parse_weekdays(values: Any) -> list[int]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_days = re.findall(r"\d+", values)
    else:
        try:
            raw_days = list(values)
        except TypeError:
            raw_days = [values]
    days: list[int] = []
    for raw_day in raw_days:
        try:
            day = int(raw_day)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7 and day not in days:
            days.append(day)
    return days


def serialize_day_rules(day_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for rule in day_rules:
        result.append(
            {
                "dayType": str(rule.get("day_type") or "normal"),
                "weekdays": weekday_labels(rule.get("weekdays")),
                "validFrom": str(rule.get("valid_from") or "")[:10],
                "validTo": str(rule.get("valid_to") or "")[:10] if rule.get("valid_to") else "",
                "priority": safe_int(rule.get("priority")),
            }
        )
    return result


def safe_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").replace(",", ".")))
    except Exception:
        return 0


def safe_money_amount(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("amount")
    return safe_int(value)


def parse_api_routes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        response_json = row.get("response_json") or {}
        if isinstance(response_json, str):
            try:
                response_json = json.loads(response_json)
            except json.JSONDecodeError:
                response_json = {}
        if not isinstance(response_json, dict):
            continue
        for route in response_json.get("routes") or []:
            if not isinstance(route, dict):
                continue
            route_id = str(route.get("routeId") or route.get("id") or "").strip()
            key = f"{row.get('warehouse_id')}|{route_id or len(routes)}"
            if key in seen:
                continue
            seen.add(key)
            work_date = parse_date_value(route.get("deliveryDate") or route.get("date"))
            route_layer = str(route.get("routeLayer") or route.get("routeType") or "normal").strip().lower()
            routes.append(
                {
                    "route_id": route_id,
                    "work_date": work_date,
                    "route_type": "express" if "express" in route_layer else "regional" if "region" in route_layer else "normal",
                    "orders": safe_int(route.get("orderCount") or route.get("orders")),
                    "tips_huf": safe_money_amount(route.get("customerTipsTotal")),
                    "stops_total": safe_int(route.get("stopsTotal") or route.get("stops_total")),
                    "delivered_count": safe_int(route.get("deliveredCount") or route.get("delivered_count")),
                    "delayed_count": safe_int(route.get("delayedCount") or route.get("delayed_count")),
                    "avg_delay_minutes": safe_int(route.get("avgDelayMinutes") or route.get("avg_delay_minutes")),
                    "final_delay_minutes": safe_int(route.get("finalDelayMinutes") or route.get("final_delay_minutes")),
                    "warehouse_departure_actual": str(route.get("warehouseDepartureActual") or route.get("warehouse_departure_actual") or ""),
                    "warehouse_arrival_actual": str(route.get("warehouseArrivalActual") or route.get("warehouse_arrival_actual") or ""),
                }
            )
    return routes


def load_api_financial_routes_for_courier(
    courier_id: str,
    period_start: date,
) -> tuple[list[dict[str, Any]], str]:
    params = {
        "select": "courier_id,courier_name,warehouse_id,response_json,status_code",
        "courier_id": f"eq.{courier_id}",
        "year": f"eq.{period_start.year}",
        "month": f"eq.{period_start.month}",
        "status_code": "eq.200",
        "limit": "20",
    }
    rows: list[dict[str, Any]] = []
    source_tables: list[str] = []
    for table in ("courier_financial_overview_raw_bud1", "courier_financial_overview_raw_bud2"):
        table_rows = optional_supabase_rows(table, params=params, timeout=60)
        if table_rows:
            rows.extend(table_rows)
            source_tables.append(table)
    if not rows:
        rows = optional_supabase_rows("courier_financial_overview_raw", params=params, timeout=60)
        if rows:
            source_tables.append("courier_financial_overview_raw")
    return parse_api_routes(rows), ", ".join(source_tables) if source_tables else ""


def load_daily_performance_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    return optional_supabase_rows(
        "raw_jitt_invoice_perf_couriers_daily",
        params={
            "select": "work_date,warehouse_code,order_count,route_count,delayed_order_count,shift_count,late_count,did_not_come_count,pct_late_evaluation,pct_did_not_come_evaluation",
            "courier_id": f"eq.{courier_id}",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.asc",
            "limit": "1000",
        },
        timeout=60,
    )


def load_route_delay_rows_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    return optional_supabase_rows(
        "courier_financial_overview_delay",
        params={
            "select": (
                "delivery_date,route_id,warehouse_id,route_order_count,stops_count,"
                "delayed_stops_count,total_delay_minutes,max_delay_minutes,"
                "slot_miss_projected_count,rejected_stops_count"
            ),
            "courier_id": f"eq.{courier_id}",
            "and": f"(delivery_date.gte.{period_start.isoformat()},delivery_date.lte.{period_end.isoformat()})",
            "or": "(total_delay_minutes.gt.0,delayed_stops_count.gt.0)",
            "order": "delivery_date.asc,route_id.asc",
            "limit": "200",
        },
        timeout=60,
    )


def load_route_compliance_rows_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
    *,
    only_problem_rows: bool = True,
) -> list[dict[str, Any]]:
    params = {
        "select": (
            "shift_date,route_id,warehouse_id,planned_start_at,actual_start_at,"
            "route_assigned_at,shift_available_at,planned_departure_at,departed_at,"
            "last_order_finished_at,warehouse_arrived_at,vehicle_plate,"
            "planned_start_delay_minutes,departure_delay_minutes,return_delay_minutes"
        ),
        "courier_id": f"eq.{courier_id}",
        "and": f"(shift_date.gte.{period_start.isoformat()},shift_date.lte.{period_end.isoformat()})",
        "order": "shift_date.asc,route_id.asc",
        "limit": "700",
    }
    if only_problem_rows:
        params["or"] = "(planned_start_delay_minutes.gt.0,departure_delay_minutes.gt.0,actual_start_at.is.null,shift_available_at.is.null)"
    return optional_supabase_rows(
        "courier_financial_overview_compliance",
        params=params,
        timeout=60,
    )


def load_daily_route_history_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    return optional_supabase_rows(
        "courier_daily_route_history",
        params={
            "select": (
                "work_date,route_id,warehouse_id,order_count,stops_count,"
                "planned_start_at,actual_start_at,route_assigned_at,shift_available_at,"
                "planned_departure_at,departed_at,last_order_finished_at,warehouse_arrived_at,"
                "vehicle_model,vehicle_plate,mileage_km,vehicle_ownership"
            ),
            "courier_id": f"eq.{courier_id}",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.desc,route_id.desc",
            "limit": "500",
        },
        timeout=60,
    )


def load_route_story_rows_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    return optional_supabase_rows(
        "mart_dsp_route_stories",
        params={
            "select": (
                "work_date,route_id,warehouse_name,shift_name,shift_start,shift_end,"
                "available_at,available_for_shift_since,queue_started_at,route_created_at,"
                "courier_registered_at,assigned_at,loading_time,planned_departure,real_departure,"
                "planned_return,real_return,queue_entry_delta_minutes,queue_wait_minutes,"
                "planned_loading_minutes,real_loading_minutes,planned_route_minutes,real_route_minutes,"
                "assigned_to_return_minutes,total_route_minutes,gps_distance_km,checkpoint_straight_km,"
                "address_count,time_window_late_count,next_shift_delay_minutes,assignment_mode,story_text"
            ),
            "courier_id": f"eq.{courier_id}",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.desc,route_id.desc",
            "limit": "700",
        },
        timeout=60,
    )


def load_attendance_shift_rows_for_courier(
    courier_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    courier_key = str(courier_id or "").strip()
    if not courier_key:
        return []
    raw_rows = optional_supabase_rows(
        "raw_dsp_attendance",
        params={
            "select": "work_date,response_json",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.asc",
            "limit": "90",
        },
        timeout=60,
    ) or optional_supabase_rows(
        "dsp_attendance_raw",
        params={
            "select": "work_date,response_json",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.asc",
            "limit": "90",
        },
        timeout=60,
    )
    shifts: list[dict[str, Any]] = []
    for raw in raw_rows:
        payload = raw.get("response_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            candidates = payload.get("couriers") or payload.get("drivers") or payload.get("items") or payload
        else:
            candidates = []
        if isinstance(candidates, dict):
            candidates = candidates.get("data") or candidates.get("items") or []
        if not isinstance(candidates, list):
            continue
        for courier in candidates:
            if not isinstance(courier, dict):
                continue
            if str(courier.get("courierId") or courier.get("courier_id") or "").strip() != courier_key:
                continue
            for shift in courier.get("shifts") or []:
                if not isinstance(shift, dict):
                    continue
                shift_start = str(shift.get("shiftStart") or shift.get("shift_start") or "")
                shift_end = str(shift.get("shiftEnd") or shift.get("shift_end") or "")
                available = str(shift.get("availableForShiftSince") or shift.get("available_for_shift_since") or "")
                shifts.append({
                    "date": str(raw.get("work_date") or shift_start)[:10],
                    "shiftId": str(shift.get("shiftId") or shift.get("shift_id") or ""),
                    "shiftName": str(shift.get("shiftName") or shift.get("shift_name") or ""),
                    "warehouseName": str(courier.get("warehouseName") or courier.get("warehouse_name") or ""),
                    "shiftStart": shift_start,
                    "shiftEnd": shift_end,
                    "availableForShiftSince": available,
                })
    return shifts


def attendance_shift_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        work_date = str(row.get("date") or row.get("shiftStart") or "")[:10]
        shift_start = local_datetime(row.get("shiftStart"))
        if not work_date or not shift_start:
            continue
        lookup[(work_date, shift_start.strftime("%H:%M"))] = row
    return lookup


def match_attendance_shift_for_route(row: dict[str, Any], lookup: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    work_date = str(row.get("date") or row.get("work_date") or "")[:10]
    if not work_date or not lookup:
        return {}
    story = row.get("routeStory") or {}
    references = [
        story.get("shiftStart"),
        row.get("plannedStartAt"),
        row.get("routeAssignedAt"),
        story.get("assignedAt"),
    ]
    best: tuple[float, dict[str, Any]] | None = None
    for value in references:
        target = local_datetime(value)
        if not target:
            continue
        for (candidate_date, _candidate_time), shift in lookup.items():
            if candidate_date != work_date:
                continue
            shift_start = local_datetime(shift.get("shiftStart"))
            if not shift_start:
                continue
            distance = abs((shift_start - target).total_seconds())
            if best is None or distance < best[0]:
                best = (distance, shift)
        if best:
            break
    return best[1] if best else {}


def apply_attendance_shift_to_route_result(
    result: dict[str, Any],
    attendance_by_shift: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    attendance_shift = match_attendance_shift_for_route(result, attendance_by_shift)
    if not attendance_shift:
        return result

    result["attendanceShiftName"] = attendance_shift.get("shiftName") or ""
    result["attendanceShiftStart"] = attendance_shift.get("shiftStart") or ""
    result["attendanceShiftEnd"] = attendance_shift.get("shiftEnd") or ""
    result["attendanceAvailableForShiftSince"] = attendance_shift.get("availableForShiftSince") or ""
    result["plannedStartAt"] = str(attendance_shift.get("shiftStart") or result.get("plannedStartAt") or "")
    result["shiftAvailableAt"] = str(attendance_shift.get("availableForShiftSince") or result.get("shiftAvailableAt") or "")
    result["actualStartAt"] = str(attendance_shift.get("availableForShiftSince") or result.get("actualStartAt") or "")
    result.setdefault("routeStory", {})
    result["routeStory"]["shiftName"] = str(attendance_shift.get("shiftName") or result["routeStory"].get("shiftName") or "")
    result["routeStory"]["shiftStart"] = str(attendance_shift.get("shiftStart") or result["routeStory"].get("shiftStart") or "")
    result["routeStory"]["shiftEnd"] = str(attendance_shift.get("shiftEnd") or result["routeStory"].get("shiftEnd") or "")
    result["routeStory"]["availableForShiftSince"] = str(attendance_shift.get("availableForShiftSince") or result["routeStory"].get("availableForShiftSince") or "")
    result["routeStory"]["availableAt"] = str(attendance_shift.get("availableForShiftSince") or result["routeStory"].get("availableAt") or "")
    result["routeStory"]["queueStartedAt"] = str(attendance_shift.get("availableForShiftSince") or result["routeStory"].get("queueStartedAt") or "")
    return result


def route_story_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("work_date") or "")[:10], str(row.get("route_id") or "").strip())
        if key[0] and key[1]:
            lookup[key] = row
    return lookup


def route_row_lookup(rows: list[dict[str, Any]], date_key: str) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        route_id = str(row.get("route_id") or "").strip()
        row_date = str(row.get(date_key) or "")[:10]
        if row_date and route_id:
            lookup[(row_date, route_id)] = row
    return lookup


def daily_performance_lookup(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        work_date = str(row.get("work_date") or "")[:10]
        if work_date:
            lookup[work_date] = row
    return lookup


def load_route_notes_for_courier(courier_id: str, period_start: date, period_end: date) -> dict[tuple[str, str], dict[str, Any]]:
    rows = optional_supabase_rows(
        "pwa_courier_route_notes",
        params={
            "select": "work_date,route_id,note,updated_at",
            "courier_id": f"eq.{courier_id}",
            "and": f"(work_date.gte.{period_start.isoformat()},work_date.lte.{period_end.isoformat()})",
            "order": "work_date.desc,route_id.desc",
            "limit": "700",
        },
        timeout=30,
    )
    return route_row_lookup(rows, "work_date")


def save_route_note_for_user(user: dict[str, Any], payload: RouteNoteRequest) -> dict[str, Any]:
    courier_id, courier_name = courier_identity(user)
    work_date = parse_date_value(payload.work_date)
    if not work_date:
        raise HTTPException(status_code=422, detail="Hibás dátum.")
    route_id = clean_text(payload.route_id, limit=80)
    if not route_id:
        raise HTTPException(status_code=422, detail="Hiányzik a Route ID.")
    note = clean_text(payload.note, limit=1200)
    rows = supabase_rest(
        "POST",
        "pwa_courier_route_notes",
        params={"on_conflict": "courier_id,work_date,route_id"},
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "work_date": work_date.isoformat(),
            "route_id": route_id,
            "note": note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    row = rows[0] if rows else {}
    return {
        "ok": True,
        "note": str(row.get("note") or note),
        "updatedAt": str(row.get("updated_at") or ""),
    }


def route_quality_shift_key(row: dict[str, Any]) -> str:
    story = row.get("routeStory") or {}
    return str(
        story.get("shiftStart")
        or row.get("plannedStartAt")
        or row.get("shiftAvailableAt")
        or row.get("actualStartAt")
        or f"{row.get('date') or ''}_{row.get('routeId') or ''}"
    ).strip()


def build_route_quality_records(
    *,
    courier_id: str,
    courier_name: str,
    month: date,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def time_or_none(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(route_quality_shift_key(row), []).append(row)
    same_checkin_by_shift = {
        key: len({
            str(item.get("actualStartAt") or item.get("shiftAvailableAt") or "").strip()
            for item in items
            if str(item.get("actualStartAt") or item.get("shiftAvailableAt") or "").strip()
        }) == 1 and len(items) > 1
        for key, items in grouped.items()
    }
    records: list[dict[str, Any]] = []
    for row in rows:
        work_date = parse_date_value(row.get("date"))
        if not work_date:
            continue
        story = row.get("routeStory") or {}
        shift_key = route_quality_shift_key(row)
        late_start_minutes = safe_int(row.get("plannedStartDelayMinutes"))
        route_late_stop_count = safe_int(row.get("timeWindowLateCount"))
        route_late_stop_minutes = safe_int(row.get("timeWindowLateMinutes"))
        api_late_count = safe_int(row.get("apiLateCount"))
        api_delayed_orders = safe_int(row.get("apiDelayedOrderCount"))
        has_api_daily_quality = any(key in row and row.get(key) not in (None, "") for key in ("apiLateCount", "apiDelayedOrderCount", "apiShiftCount"))
        late_stop_count = api_delayed_orders if has_api_daily_quality else route_late_stop_count
        late_stop_minutes = route_late_stop_minutes
        queued_on_time = api_late_count <= 0 if has_api_daily_quality else late_start_minutes <= 0
        records.append({
            "courier_id": courier_id,
            "courier_name": courier_name,
            "period_start": month.isoformat(),
            "work_date": work_date.isoformat(),
            "route_id": str(row.get("routeId") or ""),
            "warehouse_id": safe_int(row.get("warehouseId")),
            "shift_key": shift_key,
            "shift_start_at": time_or_none(story.get("shiftStart") or row.get("plannedStartAt")),
            "route_type": str(row.get("routeType") or "normal"),
            "route_assigned_at": time_or_none(story.get("assignedAt") or row.get("routeAssignedAt")),
            "shift_available_at": time_or_none(story.get("availableForShiftSince") or story.get("availableAt") or row.get("shiftAvailableAt")),
            "queue_started_at": time_or_none(story.get("queueStartedAt") or row.get("actualStartAt")),
            "departed_at": time_or_none(story.get("realDeparture") or row.get("departedAt")),
            "planned_return_at": time_or_none(story.get("plannedReturn") or row.get("plannedReturnAt")),
            "real_return_at": time_or_none(story.get("realReturn") or row.get("warehouseArrivedAt")),
            "queued_on_time": queued_on_time,
            "no_late_stops": late_stop_count <= 0,
            "quality_ok": queued_on_time and late_stop_count <= 0,
            "late_start_minutes": api_late_count if has_api_daily_quality else late_start_minutes,
            "late_stop_count": late_stop_count,
            "late_stop_minutes": late_stop_minutes,
            "same_checkin_group": bool(same_checkin_by_shift.get(shift_key)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return records


def persist_route_quality_records(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    try:
        supabase_rest(
            "POST",
            "pwa_courier_route_quality_report",
            params={"on_conflict": "courier_id,work_date,route_id"},
            payload=records,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=60,
        )
    except HTTPException as exc:
        print("Route quality report save skipped:", exc.detail)


def load_customer_rating_stats(courier_id: str, period_start: date) -> dict[str, Any]:
    rows = optional_supabase_rows(
        "bill_jitt_invoice_customer_rating_bonus",
        params={
            "select": "rating_count,average_rating,completed_routes",
            "courier_id": f"eq.{courier_id}",
            "billing_month": f"eq.{period_start.isoformat()}",
            "limit": "10",
        },
    )
    if not rows:
        return {"available": False, "ratingCount": 0, "averageRating": None, "completedRoutes": 0}
    rating_count = sum(safe_int(row.get("rating_count")) for row in rows)
    completed_routes = sum(safe_int(row.get("completed_routes")) for row in rows)
    averages = [float(row.get("average_rating")) for row in rows if row.get("average_rating") not in (None, "")]
    return {
        "available": True,
        "ratingCount": rating_count,
        "averageRating": round(sum(averages) / len(averages), 2) if averages else None,
        "completedRoutes": completed_routes,
    }


def read_customer_rating_bonus_items(courier_id: str, period_start: date) -> list[dict[str, Any]]:
    cache_key = f"{courier_id}|{period_start.isoformat()}"
    cached = cached_financial_lookup("customer_rating_bonus_items", cache_key)
    if cached is not None:
        return [dict(item) for item in cached]
    rows = optional_supabase_rows(
        "bill_jitt_invoice_customer_rating_bonus",
        params={
            "select": "worksheet_name,route_type,rating_count,average_rating,bonus_per_route_huf,completed_routes,bonus_total_huf",
            "courier_id": f"eq.{courier_id}",
            "billing_month": f"eq.{period_start.isoformat()}",
            "limit": "50",
        },
    )
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        amount = money_int(row.get("bonus_total_huf"))
        completed_routes = safe_int(row.get("completed_routes"))
        unit_amount = money_int(row.get("bonus_per_route_huf"))
        average_rating = row.get("average_rating")
        route_type = str(row.get("route_type") or "").strip()
        note_parts = []
        if average_rating not in (None, ""):
            note_parts.append(f"Átlag: {average_rating}")
        if completed_routes:
            note_parts.append(f"Kör: {completed_routes}")
        if unit_amount:
            note_parts.append(f"{completed_routes} x {unit_amount} Ft")
        if route_type:
            note_parts.append(route_type)
        item = signed_item(
            f"customer_rating_import_{index}",
            "Ügyfélértékelési bónusz",
            amount,
            source="public.bill_jitt_invoice_customer_rating_bonus",
            note=" | ".join(note_parts) or str(row.get("worksheet_name") or "Ügyfélértékelés import"),
        )
        item["completedRoutes"] = completed_routes
        item["unitAmountHuf"] = unit_amount
        item["averageRating"] = average_rating
        item["routeType"] = route_type
        items.append(item)
    result = [item for item in items if item["amountHuf"]]
    store_financial_lookup("customer_rating_bonus_items", cache_key, [dict(item) for item in result])
    return result


def build_monthly_courier_statistics(user: dict[str, Any], month_value: date) -> dict[str, Any]:
    courier_id, courier_name = courier_identity(user)
    period_start = month_value.replace(day=1)
    period_end = month_end(period_start)
    with ThreadPoolExecutor(max_workers=7) as executor:
        daily_future = executor.submit(load_daily_performance_for_courier, courier_id, period_start, period_end)
        route_future = executor.submit(load_api_financial_routes_for_courier, courier_id, period_start)
        day_rules_future = executor.submit(load_month_day_rules, period_start, period_end)
        history_future = executor.submit(load_daily_route_history_for_courier, courier_id, period_start, period_end)
        story_future = executor.submit(load_route_story_rows_for_courier, courier_id, period_start, period_end)
        attendance_future = executor.submit(load_attendance_shift_rows_for_courier, courier_id, period_start, period_end)
        notes_future = executor.submit(load_route_notes_for_courier, courier_id, period_start, period_end)
        daily_rows = daily_future.result()
        route_rows, route_source = route_future.result()
        day_rules, day_rule_source = day_rules_future.result()
        history_rows = history_future.result()
        story_rows = story_future.result()
        attendance_shift_rows = attendance_future.result()
        route_notes = notes_future.result()
    stories_by_route = route_story_lookup(story_rows)
    attendance_by_shift = attendance_shift_lookup(attendance_shift_rows)
    delay_rows = load_route_delay_rows_for_courier(courier_id, period_start, period_end)
    compliance_rows = load_route_compliance_rows_for_courier(courier_id, period_start, period_end, only_problem_rows=False)
    compliance_by_route = route_row_lookup(compliance_rows, "shift_date")
    delay_by_route = route_row_lookup(delay_rows, "delivery_date")
    route_overview_by_route = route_row_lookup(route_rows, "work_date")
    daily_by_date = daily_performance_lookup(daily_rows)

    def story_route_key(row: dict[str, Any]) -> tuple[str, str]:
        return (str(row.get("work_date") or "")[:10], str(row.get("route_id") or "").strip())

    def story_route_type(row: dict[str, Any]) -> str:
        text = normalize_text(
            " ".join(
                str(row.get(key) or "")
                for key in ("shift_name", "story_text", "assignment_mode")
            )
        )
        if "express" in text:
            return "express"
        if "regional" in text or "regio" in text:
            return "regional"
        return "normal"

    story_route_rows: list[dict[str, Any]] = []
    seen_story_routes: set[tuple[str, str]] = set()
    for story_row in story_rows:
        key = story_route_key(story_row)
        if not key[0] or not key[1] or key in seen_story_routes:
            continue
        seen_story_routes.add(key)
        story_route_rows.append(story_row)

    daily_orders = sum(safe_int(row.get("order_count")) for row in daily_rows)
    daily_routes = sum(safe_int(row.get("route_count")) for row in daily_rows)
    route_orders = sum(safe_int(row.get("orders")) for row in route_rows)
    story_orders = sum(safe_int(row.get("address_count")) for row in story_route_rows)
    route_tips = sum(safe_int(route.get("tips_huf")) for route in route_rows)
    can_show_amounts = can_view_financial_amounts(user)
    route_count = len(route_rows)
    story_route_count = len(story_route_rows)
    total_routes = story_route_count or route_count or daily_routes
    total_orders = story_orders or route_orders or daily_orders
    average_orders = round(total_orders / total_routes, 1) if total_routes else 0

    highlighted_routes = 0
    normal_day_routes = 0
    express_routes = 0
    express_orders = 0
    highlighted_city_routes = 0
    normal_city_routes = 0
    highlighted_express_routes = 0
    normal_express_routes = 0
    route_types = {"normal": 0, "express": 0, "regional": 0}
    if story_route_rows:
        for route in story_route_rows:
            route_type = story_route_type(route)
            route_types[route_type] = route_types.get(route_type, 0) + 1
            is_highlighted = day_type_for_date(parse_date_value(route.get("work_date")), day_rules) == "highlighted"
            if route_type == "express":
                express_routes += 1
                express_orders += safe_int(route.get("address_count"))
                if is_highlighted:
                    highlighted_express_routes += 1
                else:
                    normal_express_routes += 1
            elif route_type == "regional":
                pass
            else:
                if is_highlighted:
                    highlighted_city_routes += 1
                else:
                    normal_city_routes += 1
            if is_highlighted:
                highlighted_routes += 1
            else:
                normal_day_routes += 1
    elif route_rows:
        for route in route_rows:
            route_type = route.get("route_type") or "normal"
            route_types[route_type] = route_types.get(route_type, 0) + 1
            is_highlighted = day_type_for_date(route.get("work_date"), day_rules) == "highlighted"
            if route_type == "express":
                express_routes += 1
                express_orders += safe_int(route.get("orders"))
                if is_highlighted:
                    highlighted_express_routes += 1
                else:
                    normal_express_routes += 1
            elif route_type == "regional":
                pass
            else:
                if is_highlighted:
                    highlighted_city_routes += 1
                else:
                    normal_city_routes += 1
            if is_highlighted:
                highlighted_routes += 1
            else:
                normal_day_routes += 1
    else:
        for row in daily_rows:
            route_count_for_day = safe_int(row.get("route_count"))
            if day_type_for_date(parse_date_value(row.get("work_date")), day_rules) == "highlighted":
                highlighted_routes += route_count_for_day
            else:
                normal_day_routes += route_count_for_day

    shift_keys = set()
    for row in story_route_rows:
        work_date = str(row.get("work_date") or "")[:10]
        shift_marker = str(row.get("shift_start") or row.get("shift_name") or "").strip()
        if work_date and shift_marker:
            shift_keys.add(f"{work_date}|{shift_marker}")
    shift_count = len(shift_keys) or sum(safe_int(row.get("shift_count")) for row in daily_rows)
    if not shift_count and route_rows:
        route_work_dates = {
            str(row.get("work_date") or "")[:10]
            for row in route_rows
            if str(row.get("work_date") or "").strip()
        }
        shift_count = len(route_work_dates)

    def compact_delay_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": str(row.get("delivery_date") or "")[:10],
            "routeId": str(row.get("route_id") or ""),
            "warehouseId": safe_int(row.get("warehouse_id")),
            "orders": safe_int(row.get("route_order_count")),
            "stops": safe_int(row.get("stops_count")),
            "delayedStops": safe_int(row.get("delayed_stops_count")),
            "delayMinutes": safe_int(row.get("total_delay_minutes")),
            "maxDelayMinutes": safe_int(row.get("max_delay_minutes")),
            "slotMissProjected": safe_int(row.get("slot_miss_projected_count")),
            "rejectedStops": safe_int(row.get("rejected_stops_count")),
        }

    def compact_compliance_row(row: dict[str, Any]) -> dict[str, Any]:
        start_delay = safe_int(row.get("planned_start_delay_minutes"))
        departure_delay = safe_int(row.get("departure_delay_minutes"))
        return {
            "date": str(row.get("shift_date") or "")[:10],
            "routeId": str(row.get("route_id") or ""),
            "warehouseId": safe_int(row.get("warehouse_id")),
            "plannedStartAt": str(row.get("planned_start_at") or ""),
            "actualStartAt": str(row.get("actual_start_at") or ""),
            "shiftAvailableAt": str(row.get("shift_available_at") or ""),
            "routeAssignedAt": str(row.get("route_assigned_at") or ""),
            "plannedDepartureAt": str(row.get("planned_departure_at") or ""),
            "departedAt": str(row.get("departed_at") or ""),
            "warehouseArrivedAt": str(row.get("warehouse_arrived_at") or ""),
            "vehiclePlate": str(row.get("vehicle_plate") or ""),
            "plannedStartDelayMinutes": start_delay,
            "departureDelayMinutes": departure_delay,
            "returnDelayMinutes": safe_int(row.get("return_delay_minutes")),
            "isLateStart": start_delay > 0,
            "isLateDeparture": departure_delay > 0,
        }

    def compact_history_row(row: dict[str, Any]) -> dict[str, Any]:
        work_date = str(row.get("work_date") or "")[:10]
        route_id = str(row.get("route_id") or "")
        route_key = (work_date, route_id)
        compliance_row = compliance_by_route.get(route_key, {})
        delay_row = delay_by_route.get(route_key, {})
        overview_row = route_overview_by_route.get(route_key, {})
        daily_row = daily_by_date.get(work_date, {})
        note_row = route_notes.get(route_key, {})
        story = compact_route_story_row(stories_by_route.get((work_date, route_id)))
        result = {
            "date": str(row.get("work_date") or "")[:10],
            "routeId": route_id,
            "warehouseId": safe_int(row.get("warehouse_id") or compliance_row.get("warehouse_id")),
            "orders": safe_int(row.get("order_count")),
            "stops": safe_int(row.get("stops_count")),
            "plannedStartAt": str(row.get("planned_start_at") or compliance_row.get("planned_start_at") or ""),
            "actualStartAt": str(row.get("actual_start_at") or compliance_row.get("actual_start_at") or ""),
            "shiftAvailableAt": str(row.get("shift_available_at") or compliance_row.get("shift_available_at") or ""),
            "routeAssignedAt": str(row.get("route_assigned_at") or compliance_row.get("route_assigned_at") or ""),
            "plannedDepartureAt": str(row.get("planned_departure_at") or compliance_row.get("planned_departure_at") or ""),
            "departedAt": str(row.get("departed_at") or compliance_row.get("departed_at") or ""),
            "lastOrderFinishedAt": str(row.get("last_order_finished_at") or compliance_row.get("last_order_finished_at") or ""),
            "warehouseArrivedAt": str(row.get("warehouse_arrived_at") or compliance_row.get("warehouse_arrived_at") or ""),
            "plannedReturnAt": str((story or {}).get("plannedReturn") or ""),
            "plannedStartDelayMinutes": safe_int(compliance_row.get("planned_start_delay_minutes")),
            "departureDelayMinutes": safe_int(compliance_row.get("departure_delay_minutes")),
            "returnDelayMinutes": safe_int(compliance_row.get("return_delay_minutes")),
            "apiShiftCount": safe_int(daily_row.get("shift_count")),
            "apiLateCount": safe_int(daily_row.get("late_count")),
            "apiDidNotComeCount": safe_int(daily_row.get("did_not_come_count")),
            "apiDelayedOrderCount": safe_int(daily_row.get("delayed_order_count")),
            "timeWindowLateCount": safe_int(delay_row.get("delayed_stops_count")),
            "timeWindowLateMinutes": safe_int(delay_row.get("total_delay_minutes")),
            "maxDelayMinutes": safe_int(delay_row.get("max_delay_minutes")),
            "routeType": str(overview_row.get("route_type") or ""),
            "routeNote": str(note_row.get("note") or ""),
            "routeNoteUpdatedAt": str(note_row.get("updated_at") or ""),
            "vehicleModel": str(row.get("vehicle_model") or ""),
            "vehiclePlate": str(row.get("vehicle_plate") or compliance_row.get("vehicle_plate") or ""),
            "mileageKm": float(row.get("mileage_km") or 0),
            "vehicleOwnership": str(row.get("vehicle_ownership") or ""),
        }
        if story:
            result["routeStory"] = story
        return apply_attendance_shift_to_route_result(result, attendance_by_shift)

    def compact_route_story_history_row(row: dict[str, Any]) -> dict[str, Any]:
        work_date, route_id = story_route_key(row)
        route_key = (work_date, route_id)
        compliance_row = compliance_by_route.get(route_key, {})
        delay_row = delay_by_route.get(route_key, {})
        daily_row = daily_by_date.get(work_date, {})
        note_row = route_notes.get(route_key, {})
        story = compact_route_story_row(row)
        result = {
            "date": work_date,
            "routeId": route_id,
            "warehouseId": safe_int(compliance_row.get("warehouse_id")),
            "orders": safe_int(row.get("address_count")),
            "stops": safe_int(row.get("address_count")),
            "plannedStartAt": str(row.get("shift_start") or compliance_row.get("planned_start_at") or ""),
            "actualStartAt": str(row.get("queue_started_at") or row.get("available_at") or compliance_row.get("actual_start_at") or ""),
            "shiftAvailableAt": str(row.get("available_for_shift_since") or row.get("available_at") or compliance_row.get("shift_available_at") or ""),
            "routeAssignedAt": str(row.get("assigned_at") or compliance_row.get("route_assigned_at") or ""),
            "plannedDepartureAt": str(row.get("planned_departure") or compliance_row.get("planned_departure_at") or ""),
            "departedAt": str(row.get("real_departure") or compliance_row.get("departed_at") or ""),
            "lastOrderFinishedAt": str(compliance_row.get("last_order_finished_at") or ""),
            "warehouseArrivedAt": str(row.get("real_return") or compliance_row.get("warehouse_arrived_at") or ""),
            "plannedReturnAt": str(row.get("planned_return") or ""),
            "plannedStartDelayMinutes": safe_int(row.get("queue_entry_delta_minutes") or compliance_row.get("planned_start_delay_minutes")),
            "departureDelayMinutes": safe_int(compliance_row.get("departure_delay_minutes")),
            "returnDelayMinutes": safe_int(compliance_row.get("return_delay_minutes")),
            "apiShiftCount": safe_int(daily_row.get("shift_count")),
            "apiLateCount": safe_int(daily_row.get("late_count")),
            "apiDidNotComeCount": safe_int(daily_row.get("did_not_come_count")),
            "apiDelayedOrderCount": safe_int(daily_row.get("delayed_order_count")),
            "timeWindowLateCount": safe_int(row.get("time_window_late_count") or delay_row.get("delayed_stops_count")),
            "timeWindowLateMinutes": safe_int(delay_row.get("total_delay_minutes")),
            "maxDelayMinutes": safe_int(delay_row.get("max_delay_minutes")),
            "routeType": story_route_type(row),
            "routeNote": str(note_row.get("note") or ""),
            "routeNoteUpdatedAt": str(note_row.get("updated_at") or ""),
            "vehicleModel": "",
            "vehiclePlate": str(compliance_row.get("vehicle_plate") or ""),
            "mileageKm": float(row.get("gps_distance_km") or 0),
            "vehicleOwnership": "",
        }
        if story:
            result["routeStory"] = story
        return apply_attendance_shift_to_route_result(result, attendance_by_shift)

    def compact_route_fallback_row(route: dict[str, Any]) -> dict[str, Any]:
        work_date = str(route.get("work_date") or "")[:10]
        route_id = str(route.get("route_id") or "")
        route_key = (work_date, route_id)
        compliance_row = compliance_by_route.get(route_key, {})
        delay_row = delay_by_route.get(route_key, {})
        overview_row = route_overview_by_route.get(route_key, route)
        daily_row = daily_by_date.get(work_date, {})
        note_row = route_notes.get(route_key, {})
        story = compact_route_story_row(stories_by_route.get((work_date, route_id)))
        result = {
            "date": work_date,
            "routeId": route_id,
            "warehouseId": safe_int(route.get("warehouse_id") or compliance_row.get("warehouse_id")),
            "orders": safe_int(route.get("orders")),
            "stops": safe_int(route.get("orders")),
            "plannedStartAt": str(compliance_row.get("planned_start_at") or ""),
            "actualStartAt": str(compliance_row.get("actual_start_at") or ""),
            "shiftAvailableAt": str(compliance_row.get("shift_available_at") or ""),
            "routeAssignedAt": str(compliance_row.get("route_assigned_at") or ""),
            "plannedDepartureAt": str(compliance_row.get("planned_departure_at") or ""),
            "departedAt": str(compliance_row.get("departed_at") or ""),
            "lastOrderFinishedAt": str(compliance_row.get("last_order_finished_at") or ""),
            "warehouseArrivedAt": str(compliance_row.get("warehouse_arrived_at") or ""),
            "plannedReturnAt": str((story or {}).get("plannedReturn") or ""),
            "plannedStartDelayMinutes": safe_int(compliance_row.get("planned_start_delay_minutes")),
            "departureDelayMinutes": safe_int(compliance_row.get("departure_delay_minutes")),
            "returnDelayMinutes": safe_int(compliance_row.get("return_delay_minutes")),
            "apiShiftCount": safe_int(daily_row.get("shift_count")),
            "apiLateCount": safe_int(daily_row.get("late_count")),
            "apiDidNotComeCount": safe_int(daily_row.get("did_not_come_count")),
            "apiDelayedOrderCount": safe_int(daily_row.get("delayed_order_count")),
            "timeWindowLateCount": safe_int(delay_row.get("delayed_stops_count")),
            "timeWindowLateMinutes": safe_int(delay_row.get("total_delay_minutes")),
            "maxDelayMinutes": safe_int(delay_row.get("max_delay_minutes")),
            "routeType": str(overview_row.get("route_type") or ""),
            "routeNote": str(note_row.get("note") or ""),
            "routeNoteUpdatedAt": str(note_row.get("updated_at") or ""),
            "vehicleModel": "",
            "vehiclePlate": str(compliance_row.get("vehicle_plate") or ""),
            "mileageKm": 0,
            "vehicleOwnership": "",
        }
        if story:
            result["routeStory"] = story
        return apply_attendance_shift_to_route_result(result, attendance_by_shift)

    delay_detail_rows: list[dict[str, Any]] = [compact_delay_row(item) for item in delay_rows]
    compliance_detail_rows: list[dict[str, Any]] = [compact_compliance_row(item) for item in compliance_rows]
    daily_history_rows = (
        [compact_route_story_history_row(row) for row in story_route_rows]
        or [compact_history_row(row) for row in history_rows]
        or [compact_route_fallback_row(route) for route in route_rows]
    )
    route_quality_records = build_route_quality_records(
        courier_id=courier_id,
        courier_name=courier_name,
        month=period_start,
        rows=daily_history_rows,
    )
    persist_route_quality_records(route_quality_records)

    return {
        "month": period_start.strftime("%Y-%m"),
        "courier": {"id": courier_id, "name": courier_name},
        "amountsHidden": not can_show_amounts,
        "amountsNote": (
            "A havi elszamolasi idoszak meg van nyitva, a publikalt osszegek megjelenhetnek."
            if can_show_amounts
            else "A forint osszegek csak havi nyitas utan jelennek meg a futaroknak."
        ),
        "summary": {
            "routes": total_routes,
            "orders": total_orders,
            "averageOrdersPerRoute": average_orders,
            "shiftCount": shift_count,
            "tipsTotalHuf": route_tips,
        },
        "performanceDetails": {
            "delayRows": delay_detail_rows,
            "complianceRows": compliance_detail_rows,
            "delaySourceRows": 0,
            "complianceSourceRows": 0,
        },
        "dailyHistory": daily_history_rows,
        "routeQuality": {
            "savedRows": len(route_quality_records),
            "okRows": sum(1 for row in route_quality_records if row.get("quality_ok")),
            "problemRows": sum(1 for row in route_quality_records if not row.get("quality_ok")),
        },
        "rawRouteOverview": {
            "source": route_source or "",
            "routes": route_rows,
        },
        "routeBreakdown": {
            "highlightedRoutes": highlighted_routes,
            "normalDayRoutes": normal_day_routes,
            "highlightedCityRoutes": highlighted_city_routes,
            "normalCityRoutes": normal_city_routes,
            "highlightedExpressRoutes": highlighted_express_routes,
            "normalExpressRoutes": normal_express_routes,
            "expressRoutes": express_routes,
            "expressOrders": express_orders,
            "normalRoutes": route_types.get("normal", 0),
            "regionalRoutes": route_types.get("regional", 0),
        },
        "customerRating": load_customer_rating_stats(courier_id, period_start),
        "dataQuality": {
            "dailyRows": len(daily_rows),
            "routeRows": len(route_rows),
            "routeStoryRows": len(story_rows),
            "routeSource": "mart_dsp_route_stories" if story_route_rows else route_source or "nincs route raw adat",
            "dayRuleSource": day_rule_source,
            "dayRules": serialize_day_rules(day_rules),
        },
    }


def save_registration_request(payload: RegistrationRequest) -> dict[str, Any]:
    courier_id = normalize_profile_courier_id(payload.courier_id)
    email = normalize_email_address(payload.email)
    courier_name = clean_text(payload.courier_name, limit=160)
    phone_number = clean_text(payload.phone_number, limit=60)
    if not courier_name:
        raise HTTPException(status_code=422, detail="A név megadása kötelező.")
    if not phone_number:
        raise HTTPException(status_code=422, detail="A telefonszám megadása kötelező.")

    rows = supabase_rest(
        "POST",
        "pwa_registration_requests",
        params={"on_conflict": "courier_id"},
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "phone_number": phone_number,
            "email": email,
            "status": "new",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else {}


def read_workflow_rows(user: dict[str, Any], month: date) -> tuple[list[dict], list[dict], list[dict]]:
    courier_id, _courier_name = courier_identity(user)
    month_value = month.isoformat()
    documents = supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "id,document_type,document_month,title,file_name,mime_type,file_size,note,uploaded_by,uploaded_at",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month_value}",
            "order": "uploaded_at.desc",
            "limit": "200",
        },
    )
    statuses = supabase_rest(
        "GET",
        "peopleforce_card_statuses",
        params={
            "select": "action_key,status,status_note,updated_by,updated_at",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month_value}",
            "order": "updated_at.desc",
            "limit": "100",
        },
    )
    complaint_params = {
        "select": "id,document_type,message,status,created_at",
        "courier_id": f"eq.{courier_id}",
        "document_month": f"eq.{month_value}",
        "status": "neq.deleted",
        "order": "created_at.desc",
        "limit": "100",
    }
    complaints = supabase_rest(
        "GET",
        "peopleforce_complaints",
        params=complaint_params,
    )
    return documents, statuses, complaints


def status_map(rows: list[dict], process_id: str | None = "") -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("action_key") or "")
        if process_id_from_action_key(key) != normalize_process_id(process_id):
            continue
        clean_key = base_action_key(key)
        if clean_key and clean_key not in result:
            result[clean_key] = row
    return result


def workflow_done(states: dict[str, dict], action: str) -> bool:
    return workflow_status(states, action) == "done"


def workflow_status(states: dict[str, dict], action: str) -> str:
    return str((states.get(action) or {}).get("status") or "").lower()


def workflow_open(states: dict[str, dict], action: str) -> bool:
    return workflow_status(states, action) == "open"


def complaints_ignored_for_billing(states: dict[str, dict]) -> bool:
    return workflow_done(states, "ignore_complaints_for_billing")


def invoice_validation_override_enabled(states: dict[str, dict]) -> bool:
    return workflow_done(states, "invoice_validation_override")


def manual_invoice_skip_enabled(states: dict[str, dict]) -> bool:
    return workflow_done(states, "manual_invoice_skip")


def courier_has_efo_assignment(user: dict[str, Any], month: date) -> bool:
    courier_id, _courier_name = courier_identity(user)
    period_start = month.replace(day=1)
    period_end = month_end(period_start)
    rows = optional_supabase_rows(
        "courier_efo_assignment",
        schema="settlement",
        params={
            "select": "valid_from,valid_to",
            "courier_id": f"eq.{courier_id}",
            "is_active": "eq.true",
            "deleted_at": "is.null",
            "valid_from": f"lte.{period_end.isoformat()}",
            "order": "valid_from.desc",
            "limit": "20",
        },
    )
    for row in rows:
        valid_to = str(row.get("valid_to") or "")[:10]
        if not valid_to or valid_to >= period_start.isoformat():
            return True
    return False


def open_payment_waiting_status(user: dict[str, Any], month: date, note: str, process_id: str | None = "") -> None:
    upsert_workflow_status(
        user,
        month,
        "invoice_payment",
        "open",
        note,
        process_id,
    )


def apply_invoice_validation_override(result: dict[str, Any], enabled: bool) -> dict[str, Any]:
    if not enabled or not result or result.get("ok"):
        return result
    checks = []
    for check in result.get("checks") or []:
        updated = dict(check)
        if updated.get("status") == "error":
            updated["status"] = "warn"
            updated["detail"] = f"Továbbengedve admin engedéllyel. {updated.get('detail') or ''}".strip()
        checks.append(updated)
    result = dict(result)
    result["checks"] = checks
    result["errors"] = 0
    result["warnings"] = sum(check.get("status") == "warn" for check in checks)
    result["ok"] = True
    result["override"] = True
    return result


def combine_invoice_validation_results(
    results: list[tuple[str, dict[str, Any]]],
    expected_gross_amount: int,
    declared_gross_amount: int,
    invoice_number: str,
    skip_invoice_number_match: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    parsed_documents = []
    gross_total = 0
    for label, result in results:
        parsed = dict(result.get("parsed") or {})
        parsed_documents.append({"type": label, **parsed})
        gross_total += int(parsed.get("grossTotal") or 0)
        for check in result.get("checks") or []:
            checks.append({**check, "title": f"{label} – {check.get('title') or 'ellenőrzés'}"})

    main_invoice_number = str((results[0][1].get("parsed") or {}).get("invoiceNumber") or "").strip()
    requested_invoice_number = str(invoice_number or "").strip()
    if skip_invoice_number_match:
        checks.append(
            {
                "status": "warn",
                "title": "Átutalásos számla számlaszáma",
                "detail": "A számlaszám-egyezés ellenőrzése ki lett hagyva.",
            }
        )
    else:
        requested_number_key = re.sub(r"[^A-Z0-9]", "", requested_invoice_number.upper())
        document_number_key = re.sub(r"[^A-Z0-9]", "", main_invoice_number.upper())
        checks.append(
            {
                "status": "ok" if requested_number_key and requested_number_key == document_number_key else "error",
                "title": "Átutalásos számla számlaszáma",
                "detail": f"Megadva: {requested_invoice_number or '-'}; dokumentum: {main_invoice_number or '-'}.",
            }
        )

    if declared_gross_amount:
        checks.append(
            {
                "status": "ok" if gross_total == declared_gross_amount else "error",
                "title": "Két számla megadott bruttó összege",
                "detail": f"Számlák összesen: {gross_total:,} Ft; megadva: {declared_gross_amount:,} Ft.".replace(",", " "),
            }
        )
    if expected_gross_amount:
        checks.append(
            {
                "status": "ok" if gross_total == expected_gross_amount else "error",
                "title": "Két számla TIG szerinti végösszege",
                "detail": f"Számlák összesen: {gross_total:,} Ft; TIG: {expected_gross_amount:,} Ft.".replace(",", " "),
            }
        )

    errors = sum(check.get("status") == "error" for check in checks)
    warnings = sum(check.get("status") == "warn" for check in checks)
    passed = sum(check.get("status") == "ok" for check in checks)
    return {
        "ok": errors == 0,
        "score": round((passed / (len(checks) or 1)) * 100),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "parsed": {
            "invoiceNumber": main_invoice_number,
            "grossTotal": gross_total,
            "documents": parsed_documents,
        },
    }


def has_open_complaint(complaints: list[dict], action: str) -> bool:
    for row in complaints:
        if base_action_key(str(row.get("document_type") or "")) != action:
            continue
        if str(row.get("status") or "").strip().lower() in {"resolved", "closed"}:
            continue
        if str(row.get("admin_response") or "").strip() or str(row.get("responded_at") or "").strip():
            continue
        return True
    return False


def upsert_workflow_status(
    user: dict[str, Any],
    month: date,
    action: str,
    status: str,
    note: str,
    process_id: str | None = "",
) -> None:
    courier_id, courier_name = courier_identity(user)
    supabase_rest(
        "POST",
        "peopleforce_card_statuses",
        params={"on_conflict": "courier_id,document_month,action_key"},
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "action_key": process_action_key(action, process_id),
            "document_month": month.isoformat(),
            "status": "done" if status == "done" else "open",
            "status_note": note,
            "updated_by": courier_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="resolution=merge-duplicates,return=representation",
    )


def build_workflow(
    user: dict[str, Any],
    month: date,
    process: str | None = "",
    *,
    preview_read_only: bool = False,
    allow_unpublished: bool = False,
    can_view_amounts: bool | None = None,
) -> dict[str, Any]:
    process_id = normalize_process_id(process)
    documents, status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(status_rows, process_id)
    legacy_unrestricted_month = is_unrestricted_legacy_settlement_month(month)
    individual_monthly_billing_open = (
        not process_id
        and str((states.get("individual_monthly_billing") or {}).get("status") or "").lower()
        in {"open", "done"}
    )
    monthly_workflow_visible = (
        not process_id
        and any(
            str((states.get(action) or {}).get("status") or "").lower() in {"open", "done"}
            for action in ("settlement", "tig", "invoice_submit", "invoice_check", "invoice_payment")
        )
    )
    amount_access = (
        legacy_unrestricted_month
        or individual_monthly_billing_open
        or monthly_workflow_visible
        or (can_view_financial_amounts(user) if can_view_amounts is None else bool(can_view_amounts))
    )
    financial_breakdown = build_financial_breakdown(
        user,
        month,
        allow_unpublished=allow_unpublished or legacy_unrestricted_month,
    ) if not process_id else {
        "available": False,
        "month": month.strftime("%Y-%m"),
        "totalPayableHuf": 0,
        "cards": [],
        "complaintOptions": [],
        "source": "settlement.courier_settlement_summary",
        "message": "Egyedi folyamatnál a havi pénzügyi bontás a havi folyamatnál látható.",
    }
    if not process_id and not amount_access:
        financial_breakdown = hidden_financial_breakdown(month)
    tig_breakdown = build_workflow_tig_breakdown(user, month, financial_breakdown) if not process_id else {
        "available": False,
        "month": month.strftime("%Y-%m"),
        "message": "Egyedi folyamatnĂˇl nincs havi TIG bontĂˇs.",
        "rows": [],
    }
    documents = [row for row in documents if document_belongs_to_process(row, process_id)]
    complaints = [
        row for row in complaints
        if process_id_from_action_key(str(row.get("document_type") or "")) == process_id
    ]
    document_groups = {
        document_type: [row for row in documents if base_action_key(str(row.get("document_type") or "")) == document_type]
        for document_type in WORKFLOW_DOCUMENT_TYPES
    }
    response_documents = [
        row for row in documents
        if row.get("document_type") == "complaint_response"
    ]
    for action in ("settlement", "tig"):
        if document_groups[action] and action not in states:
            states[action] = {"status": "open", "status_note": "Új dokumentum érkezett."}

    process_invoice_flow_ready = bool(process_id) and (
        bool(document_groups["tig"])
        or bool(document_groups["settlement"])
        or bool(states.get("settlement"))
        or bool(states.get("tig"))
        or bool(states.get("invoice_submit"))
        or bool(states.get("invoice_check"))
        or bool(states.get("invoice_payment"))
    )
    process_settlement_ready = process_invoice_flow_ready
    settlement_ready = process_settlement_ready or bool(document_groups["settlement"]) or bool(financial_breakdown.get("available"))
    settlement_done = workflow_done(states, "settlement") or process_settlement_ready
    efo_invoice_skip = not process_id and courier_has_efo_assignment(user, month)
    manual_invoice_skip = not process_id and manual_invoice_skip_enabled(states)
    invoice_skip = manual_invoice_skip or efo_invoice_skip
    tig_ready = bool(document_groups["tig"]) or bool(tig_breakdown.get("available"))
    tig_done = workflow_done(states, "tig") or process_invoice_flow_ready or (invoice_skip and settlement_done)
    invoice_submit_open = workflow_open(states, "invoice_submit") and not invoice_skip
    invoice_submit_done = False if invoice_submit_open else (workflow_done(states, "invoice_submit") or (invoice_skip and tig_done))
    invoice_check_done = False if invoice_submit_open else (workflow_done(states, "invoice_check") or (invoice_skip and tig_done))

    steps = [
        {
            "key": "settlement_document",
            "title": (
                "Elszámolás elkészült"
                if document_groups["settlement"]
                else "Várakozás az elszámolás elkészítésére"
            ),
            "done": settlement_ready,
            "locked": False,
        },
        {
            "key": "settlement",
            "title": "Elszámolás elfogadása",
            "done": settlement_done,
            "locked": not settlement_ready,
        },
        {
            "key": "tig_document",
            "title": "TIG nem szükséges ehhez a folyamathoz" if process_id else (
                "TIG elkészült"
                if tig_ready
                else "Várakozás a TIG elkészítésére"
            ),
            "done": tig_ready or process_invoice_flow_ready,
            "locked": not settlement_done,
        },
        {
            "key": "tig",
            "title": "TIG elfogadása",
            "done": tig_done,
            "locked": not settlement_done or (not process_id and not tig_ready),
        },
        {
            "key": "invoice_submit",
            "title": "Számlafeltöltés kézzel kihagyva" if manual_invoice_skip else "Számlafeltöltés",
            "done": invoice_submit_done,
            "locked": True if manual_invoice_skip else (False if invoice_submit_open else not tig_done),
        },
        {
            "key": "invoice_check",
            "title": "Számlaellenőrzés kézzel kihagyva" if manual_invoice_skip else "Számlaellenőrzés",
            "done": invoice_check_done,
            "locked": True if manual_invoice_skip else not workflow_done(states, "invoice_submit"),
        },
        {
            "key": "invoice_payment",
            "title": (
                "Havi folyamat lezĂˇrva"
                if workflow_done(states, "invoice_payment")
                else "Admin szĂˇmlaelfogadĂˇs Ă©s kifizetĂ©s"
            ),
            "done": workflow_done(states, "invoice_payment"),
            "locked": not invoice_check_done,
        },
    ]
    if financial_breakdown.get("available") and not document_groups["settlement"]:
        steps[0]["title"] = "Havi pénzügyi adatok elkészültek"
    if efo_invoice_skip:
        efo_step_updates = {
            "tig_document": {
                "title": "TIG nem szükséges EFO folyamatnál",
                "done": settlement_done,
                "locked": not settlement_done,
            },
            "tig": {
                "title": "TIG nem szükséges EFO folyamatnál",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_submit": {
                "title": "Számlafeltöltés nem szükséges EFO folyamatnál",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_check": {
                "title": "Számlaellenőrzés nem szükséges EFO folyamatnál",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_payment": {
                "locked": not settlement_done,
            },
        }
        for step in steps:
            step.update(efo_step_updates.get(str(step.get("key") or ""), {}))
    elif manual_invoice_skip:
        manual_step_updates = {
            "tig_document": {
                "title": "TIG kézzel kihagyva",
                "done": settlement_done,
                "locked": not settlement_done,
            },
            "tig": {
                "title": "TIG kézzel kihagyva",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_submit": {
                "title": "Számlafeltöltés kézzel kihagyva",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_check": {
                "title": "Számlaellenőrzés kézzel kihagyva",
                "done": settlement_done,
                "locked": True,
            },
            "invoice_payment": {
                "locked": not settlement_done,
            },
        }
        for step in steps:
            step.update(manual_step_updates.get(str(step.get("key") or ""), {}))
    safe_documents: dict[str, list[dict[str, Any]]] = {}
    for document_type, rows in document_groups.items():
        safe_documents[document_type] = [
            {
                **row,
                "downloadUrl": f"/api/documents/{quote(str(row.get('id') or ''))}",
            }
            for row in rows
        ]
    safe_response_documents = [
        {
            **row,
            "downloadUrl": f"/api/documents/{quote(str(row.get('id') or ''))}",
        }
        for row in response_documents
    ]
    complaint_actions = ("settlement", "tig", "invoice_check", "invoice_submit")
    complaints_by_action = {
        action: [row for row in complaints if base_action_key(str(row.get("document_type") or "")) == action]
        for action in complaint_actions
    }
    response_documents_by_action = {
        action: [
            row for row in safe_response_documents
            if f"({action})" in str(row.get("title") or "")
        ]
        for action in complaint_actions
    }
    for action, rows in complaints_by_action.items():
        action_responses = response_documents_by_action.get(action, [])
        if not action_responses:
            continue
        for complaint in rows:
            if complaint.get("admin_response"):
                continue
            complaint_id = str(complaint.get("id") or "")
            matching_response = next(
                (
                    row for row in action_responses
                    if complaint_id and complaint_id in str(row.get("title") or "")
                ),
                action_responses[0],
            )
            complaint["admin_response"] = (
                matching_response.get("note")
                or matching_response.get("title")
                or ""
            )
            complaint["responded_by"] = matching_response.get("uploaded_by") or "admin"
            complaint["responded_at"] = matching_response.get("uploaded_at")

    return {
        "month": month.strftime("%Y-%m"),
        "process": process_id,
        "processLabel": "Havi folyamat" if not process_id else f"Egyéb folyamat: {process_id}",
        "viewerReadOnly": preview_read_only,
        "viewingAs": public_user(user) if preview_read_only else None,
        "steps": steps,
        "states": states,
        "documents": safe_documents,
        "financialBreakdown": financial_breakdown,
        "tigBreakdown": tig_breakdown,
        "complaints": complaints_by_action,
        "complaintResponses": response_documents_by_action,
        "ignoreComplaintsForBilling": complaints_ignored_for_billing(states),
        "invoiceValidationOverride": invoice_validation_override_enabled(states),
        "efoInvoiceSkip": efo_invoice_skip,
        "manualInvoiceSkip": manual_invoice_skip,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def list_workflow_processes(user: dict[str, Any], month: date) -> list[dict[str, str]]:
    documents, status_rows, complaints = read_workflow_rows(user, month)
    process_ids: set[str] = {""}
    for row in status_rows:
        process_ids.add(process_id_from_action_key(str(row.get("action_key") or "")))
    for row in complaints:
        process_ids.add(process_id_from_action_key(str(row.get("document_type") or "")))
    for row in documents:
        note = str(row.get("note") or "")
        match = re.search(r"Folyamat azonosító:\s*([a-z0-9_-]+)", note, flags=re.IGNORECASE)
        if match:
            process_ids.add(normalize_process_id(match.group(1)))
    return [
        {
            "id": process_id,
            "label": "Havi folyamat" if not process_id else f"Egyéb folyamat: {process_id}",
        }
        for process_id in sorted(process_ids, key=lambda item: (item != "", item))
    ]


def expected_tig_amount(user: dict[str, Any], month: date) -> int:
    courier_id, _courier_name = courier_identity(user)
    rows = supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "file_content_base64",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month.isoformat()}",
            "document_type": "eq.tig",
            "order": "uploaded_at.desc",
            "limit": "5",
        },
        timeout=60,
    )
    for row in rows:
        try:
            amount = extract_expected_amount(base64.b64decode(row.get("file_content_base64") or ""))
        except Exception:
            amount = 0
        if amount:
            return amount
    financial_breakdown = build_financial_breakdown(user, month)
    tig_breakdown = build_workflow_tig_breakdown(user, month, financial_breakdown)
    if tig_breakdown.get("available"):
        return money_int(tig_breakdown.get("finalTotalHuf"))
    return 0


def slugify_filename(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return text[:80] or "futar"


def make_document_reference(courier_id: str, document_type: str, document_month: date) -> str:
    month_text = document_month.replace(day=1).strftime("%Y%m")
    digest = hashlib.sha1(f"{courier_id}:{document_type}:{month_text}".encode("utf-8")).hexdigest()[:8]
    return f"{courier_id}-{document_type.upper()}-{month_text}-{digest}"


def workflow_tig_document_exists(user: dict[str, Any], month: date, process_id: str | None = "") -> bool:
    courier_id, _courier_name = courier_identity(user)
    rows = supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "id,note",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month.isoformat()}",
            "document_type": "eq.tig",
            "order": "uploaded_at.desc",
            "limit": "20",
        },
        timeout=60,
    )
    return any(document_belongs_to_process(row, process_id) for row in rows)


def delete_workflow_tig_documents(user: dict[str, Any], month: date, process_id: str | None = "") -> int:
    courier_id, _courier_name = courier_identity(user)
    rows = supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "id,note",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month.isoformat()}",
            "document_type": "eq.tig",
            "order": "uploaded_at.desc",
            "limit": "50",
        },
        timeout=60,
    )
    deleted = 0
    for row in rows:
        document_id = str(row.get("id") or "").strip()
        if not document_id or not document_belongs_to_process(row, process_id):
            continue
        supabase_rest(
            "DELETE",
            "peopleforce_documents",
            params={"id": f"eq.{document_id}"},
            prefer="return=minimal",
            timeout=30,
        )
        deleted += 1
    return deleted


def generate_tig_after_settlement_accept(user: dict[str, Any], month: date, process_id: str | None = "") -> bool:
    clean_process_id = normalize_process_id(process_id)
    if clean_process_id:
        return False
    if workflow_tig_document_exists(user, month, clean_process_id):
        return False
    breakdown = build_financial_breakdown(user, month, allow_unpublished=True)
    if not breakdown.get("available"):
        return False
    courier_id, courier_name = courier_identity(user)
    payable = money_int(breakdown.get("totalPayableHuf"))
    if payable <= 0:
        return False
    profile_rows = optional_supabase_rows(
        "courier_master",
        params={"select": "*", "courier_id": f"eq.{courier_id}", "limit": "1"},
        timeout=30,
    )
    profile = profile_rows[0] if profile_rows else {}
    breakdown_items = {
        str(item.get("key") or ""): item
        for card in breakdown.get("cards") or []
        for item in card.get("items") or []
    }
    tip_amount = money_int((breakdown_items.get("tip") or {}).get("amountHuf"))
    cash_amount = abs(money_int((breakdown_items.get("atm_effect") or breakdown_items.get("cash_missing") or {}).get("amountHuf")))
    reference = make_document_reference(courier_id, "tig", month)
    pdf_bytes = build_tig_pdf(
        {
            "name": courier_name,
            "company_name": profile.get("company_name") or courier_name,
            "address": profile.get("company_address") or profile.get("address") or "",
            "tax_number": profile.get("tax_number") or profile.get("tax_id") or "",
            "tig_type": profile.get("tig_type") or profile.get("tig_mode") or profile.get("invoice_type") or profile.get("invoice_vat_type") or profile.get("vat_status") or "",
            "vat_status": profile.get("vat_status") or "",
            "employment_type": profile.get("employment_type") or "",
            "employment_status": profile.get("employment_status") or "",
            "efo_status": profile.get("efo_status") or "",
            "id": courier_id,
            "document_month": month,
            "document_reference": reference,
        },
        {"payable": payable, "cash": cash_amount, "tip": tip_amount},
    )
    note_parts = [
        "Automatikus TIG generálás elszámolás elfogadása után.",
        f"Elszámolási összeg: {payable} Ft.",
    ]
    process_marker = process_note_marker(clean_process_id)
    if process_marker:
        note_parts.insert(0, process_marker)
    supabase_rest(
        "POST",
        "peopleforce_documents",
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "document_type": "tig",
            "document_month": month.isoformat(),
            "title": f"TIG - {month:%Y-%m}",
            "file_name": f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_{month:%Y-%m}_{reference}.pdf",
            "mime_type": "application/pdf",
            "file_size": len(pdf_bytes),
            "file_content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "note": " ".join(note_parts),
            "uploaded_by": "PWA automata",
        },
        prefer="return=representation",
        timeout=60,
    )
    return True


def require_prerequisite(user: dict[str, Any], month: date, action: str, process_id: str | None = "") -> None:
    prerequisite = WORKFLOW_PREREQUISITES.get(action)
    if not prerequisite:
        return
    documents, status_rows, _complaints = read_workflow_rows(user, month)
    clean_process_id = normalize_process_id(process_id)
    if clean_process_id and prerequisite in {"settlement", "tig"}:
        process_documents = [row for row in documents if document_belongs_to_process(row, clean_process_id)]
        process_document_groups = {
            document_type: [
                row for row in process_documents
                if base_action_key(str(row.get("document_type") or "")) == document_type
            ]
            for document_type in WORKFLOW_DOCUMENT_TYPES
        }
        process_states = status_map(status_rows, clean_process_id)
        if (
            process_document_groups.get("tig")
            or process_document_groups.get("settlement")
            or process_states.get("settlement")
            or process_states.get("tig")
            or process_states.get("invoice_submit")
            or process_states.get("invoice_check")
            or process_states.get("invoice_payment")
        ):
            return
    if not workflow_done(status_map(status_rows, process_id), prerequisite):
        labels = {
            "settlement": "az elszámolás elfogadása",
            "tig": "a TIG elfogadása",
            "invoice_check": "a sikeres számlaellenőrzés",
        }
        raise HTTPException(status_code=409, detail=f"Előbb szükséges: {labels[prerequisite]}.")

def normalize_device_serial(value: str) -> str:
    serial = clean_text(value, limit=80).upper()
    serial = re.sub(r"[^A-Z0-9._/-]", "", serial)
    if len(serial) < 3:
        raise HTTPException(status_code=422, detail="A telefon sorszama legalabb 3 karakter legyen.")
    return serial


def normalize_device_imei(value: str) -> str:
    imei = re.sub(r"\D+", "", str(value or ""))
    if imei and len(imei) not in {14, 15, 16}:
        raise HTTPException(status_code=422, detail="Az IMEI formatuma nem megfelelo.")
    return imei[:16]


def normalize_device_status(value: str) -> str:
    allowed = {"ok", "scratched", "cracked", "broken", "missing_accessory", "other"}
    status = clean_text(value, limit=40).lower() or "ok"
    if status not in allowed:
        raise HTTPException(status_code=422, detail="Ismeretlen eszkozallapot.")
    return status


def normalize_device_event_type(value: str) -> str:
    allowed = {"handover", "return", "inspection", "damage_report"}
    event_type = clean_text(value, limit=40).lower() or "inspection"
    if event_type not in allowed:
        raise HTTPException(status_code=422, detail="Ismeretlen eszkozesemeny.")
    return event_type


def device_report_label(row: dict[str, Any]) -> str:
    labels = {
        "handover": "Atadas",
        "return": "Visszavetel",
        "inspection": "Ellenorzes",
        "damage_report": "Serules jelzes",
    }
    statuses = {
        "ok": "Rendben",
        "scratched": "Karcos",
        "cracked": "Torott",
        "broken": "Hibas",
        "missing_accessory": "Hianyzo tartozek",
        "other": "Egyeb",
    }
    return f"{labels.get(row.get('event_type'), 'Ellenorzes')} - {statuses.get(row.get('condition_status'), 'Rendben')}"


def safe_device_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "deviceId": row.get("device_id"),
        "deviceType": row.get("device_type") or "phone",
        "serialNumber": row.get("serial_number") or "",
        "imei": row.get("imei") or "",
        "courierId": row.get("courier_id"),
        "courierName": row.get("courier_name") or "",
        "eventType": row.get("event_type") or "inspection",
        "conditionStatus": row.get("condition_status") or "ok",
        "label": device_report_label(row),
        "note": row.get("note") or "",
        "photoCount": int(row.get("photo_count") or 0),
        "reportedAt": row.get("reported_at") or "",
    }


def attach_device_report_photos(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report_ids = [str(report.get("id")) for report in reports if report.get("id")]
    if not report_ids:
        return reports

    try:
        photos = supabase_rest(
            "GET",
            "pwa_device_condition_photos",
            params={
                "select": "id,report_id,file_name,mime_type,file_size,photo_label,uploaded_at",
                "report_id": f"in.({','.join(report_ids)})",
                "order": "uploaded_at.asc",
                "limit": "200",
            },
        )
    except HTTPException:
        photos = []

    photos_by_report: dict[str, list[dict[str, Any]]] = {}
    for photo in photos or []:
        report_id = str(photo.get("report_id") or "")
        photos_by_report.setdefault(report_id, []).append(
            {
                "id": photo.get("id"),
                "fileName": photo.get("file_name") or "",
                "mimeType": photo.get("mime_type") or "",
                "fileSize": int(photo.get("file_size") or 0),
                "label": photo.get("photo_label") or "",
                "uploadedAt": photo.get("uploaded_at") or "",
                "url": f"/api/devices/photos/{quote(str(photo.get('id') or ''))}",
            }
        )

    for report in reports:
        report["photos"] = photos_by_report.get(str(report.get("id") or ""), [])
    return reports


def normalize_pem_private_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    begin = "-----BEGIN PRIVATE KEY-----"
    end = "-----END PRIVATE KEY-----"
    if begin not in text or end not in text:
        return text
    body = text.split(begin, 1)[1].split(end, 1)[0]
    body = re.sub(r"\s+", "", body)
    lines = [body[index:index + 64] for index in range(0, len(body), 64)]
    return "\n".join([begin, *lines, end])


def public_vapid_key() -> str:
    key = load_setting("VAPID_PUBLIC_KEY").strip()
    private_key_b64 = load_setting("VAPID_PRIVATE_KEY_B64")
    private_key_text = ""
    if private_key_b64:
        try:
            private_key_text = normalize_pem_private_key(
                base64.b64decode(private_key_b64).decode("utf-8")
            )
        except Exception:
            private_key_text = ""
    if not private_key_text:
        private_key_text = normalize_pem_private_key(load_setting("VAPID_PRIVATE_KEY"))
    if not private_key_text and LOCAL_VAPID_PRIVATE_FILE.exists():
        try:
            private_key_text = normalize_pem_private_key(
                LOCAL_VAPID_PRIVATE_FILE.read_text(encoding="utf-8").strip()
            )
        except Exception:
            private_key_text = ""
    if not key and serialization is not None and private_key_text:
        try:
            private_key = serialization.load_pem_private_key(private_key_text.encode("utf-8"), password=None)
            public_bytes = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
            key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")
        except Exception:
            key = ""
    if not key:
        raise HTTPException(
            status_code=503,
            detail="A push értesítések még nincsenek konfigurálva.",
        )
    return key


def save_push_subscription(
    user: dict[str, Any],
    payload: PushSubscriptionRequest,
) -> None:
    courier_id, courier_name = courier_identity(user)
    endpoint = payload.endpoint.strip()
    p256dh = payload.keys.p256dh.strip()
    auth = payload.keys.auth.strip()

    if not endpoint or not p256dh or not auth:
        raise HTTPException(
            status_code=422,
            detail="Hiányos push feliratkozási adatok.",
        )

    now = datetime.now(timezone.utc).isoformat()

    try:
        supabase_rest(
            "PATCH",
            "pwa_push_subscriptions",
            params={"courier_id": f"eq.{courier_id}"},
            payload={"active": False, "updated_at": now},
            prefer="return=minimal",
        )
    except HTTPException:
        supabase_rest(
            "PATCH",
            "pwa_push_subscriptions",
            params={"courier_id": f"eq.{courier_id}"},
            payload={"active": False},
            prefer="return=minimal",
        )

    full_payload = {
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": payload.user_agent.strip(),
            "active": True,
            "last_seen_at": now,
            "updated_at": now,
    }
    try:
        supabase_rest(
            "POST",
            "pwa_push_subscriptions",
            params={"on_conflict": "endpoint"},
            payload=full_payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except HTTPException:
        minimal_payload = {
            key: value
            for key, value in full_payload.items()
            if key not in {"user_agent", "last_seen_at", "updated_at"}
        }
        supabase_rest(
            "POST",
            "pwa_push_subscriptions",
            params={"on_conflict": "endpoint"},
            payload=minimal_payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )


def active_push_subscription_count(user: dict[str, Any]) -> int:
    courier_id, _courier_name = courier_identity(user)
    try:
        rows = supabase_rest(
            "GET",
            "pwa_push_subscriptions",
            params={
                "select": "id",
                "courier_id": f"eq.{courier_id}",
                "active": "eq.true",
                "limit": "100",
            },
        )
    except HTTPException:
        return 0
    return len(rows or [])


def disable_push_subscription(
    user: dict[str, Any],
    endpoint: str,
) -> None:
    courier_id, _courier_name = courier_identity(user)
    clean_endpoint = endpoint.strip()
    if not clean_endpoint:
        return

    supabase_rest(
        "PATCH",
        "pwa_push_subscriptions",
        params={
            "courier_id": f"eq.{courier_id}",
            "endpoint": f"eq.{clean_endpoint}",
        },
        payload={
            "active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


app = FastAPI(title="Kifli Futár PWA", docs_url=None, redoc_url=None)


@app.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response):
    user = authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Hibás felhasználónév vagy jelszó.")
    token = create_session(user)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0]
    secure_cookie = request.url.scheme == "https" or forwarded_proto.strip() == "https"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    return {"user": public_user(user)}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.post("/api/register")
def register(payload: RegistrationRequest):
    courier_id = normalize_profile_courier_id(payload.courier_id)
    email = normalize_email_address(payload.email)
    master_row = read_master_auth_row(courier_id)
    if master_row:
        existing_email = master_email(master_row)
        email_updated = False
        if not existing_email:
            email_updated = update_master_email_if_missing(master_row, email)
        return {
            "ok": False,
            "redirect": "password_reset",
            "message": (
                "Ez a futár ID már szerepel a törzsben, ezért regisztráció helyett "
                "jelszó-visszaállítást kell indítani."
            ),
            "emailUpdated": email_updated,
        }

    request_row = save_registration_request(payload)
    return {
        "ok": True,
        "message": "A regisztrációs kérelmet rögzítettük. Admin jóváhagyás után lesz belépésed.",
        "request": request_row,
    }


@app.post("/api/password-reset")
def password_reset(payload: PasswordResetRequest):
    courier_id = normalize_profile_courier_id(payload.courier_id)
    email = normalize_email_address(payload.email)
    master_row = read_master_auth_row(courier_id)
    if not master_row:
        raise HTTPException(status_code=404, detail="Ez a futár ID nincs a futár törzsben.")

    existing_email = master_email(master_row)
    email_updated = False
    if existing_email and existing_email.casefold() != email.casefold():
        raise HTTPException(
            status_code=403,
            detail="A megadott e-mail cím nem egyezik a törzsben rögzített e-mail címmel.",
        )
    if not existing_email:
        email_updated = update_master_email_if_missing(master_row, email)

    reset_user = None
    try:
        reset_user = reset_pwa_user_password(courier_id)
    except Exception:
        reset_user = None
    if not reset_user:
        reset_user = reset_legacy_user_password_for_courier(courier_id)
    if not reset_user:
        raise HTTPException(
            status_code=404,
            detail="Ehhez a futár ID-hoz nincs aktív mobil felhasználó. Kérj admin segítséget.",
        )

    try:
        result = send_login_credentials(email, reset_user["username"], reset_user["password"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Az e-mail küldése sikertelen: {exc}") from exc

    return {
        "ok": True,
        "message": "Új jelszót küldtünk a megadott e-mail címre.",
        "emailUpdated": email_updated,
        "recipient": result.get("recipient"),
    }


@app.get("/api/me")
def me(giriton_pwa_session: str | None = Cookie(default=None)):
    return {"user": public_user(require_user(giriton_pwa_session))}


@app.get("/api/push/public-key")
def get_push_public_key(
    giriton_pwa_session: str | None = Cookie(default=None),
):
    require_user(giriton_pwa_session)
    return {"publicKey": public_vapid_key()}


@app.get("/api/push/status")
def get_push_status(
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    configured = True
    error = ""
    try:
        public_vapid_key()
    except HTTPException as exc:
        configured = False
        error = str(exc.detail or "")
    return {
        "configured": configured,
        "error": error,
        "activeSubscriptions": active_push_subscription_count(user),
    }


@app.post("/api/push/subscribe")
def subscribe_push(
    payload: PushSubscriptionRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    save_push_subscription(user, payload)
    return {"ok": True}


@app.post("/api/push/unsubscribe")
def unsubscribe_push(
    payload: PushSubscriptionRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    disable_push_subscription(user, payload.endpoint)
    return {"ok": True}


@app.get("/api/profile/billing")
def get_billing_profile(
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, preview = workflow_view_user(user, courier)
    return {
        "billing": read_billing_profile(view_user),
        "viewingAs": public_user(view_user) if preview else None,
        "viewerReadOnly": preview,
    }


@app.put("/api/profile/password")
def update_profile_password(
    payload: PasswordChangeRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    current_password = str(payload.current_password or "")
    new_password = str(payload.new_password or "")
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Az új jelszó legalább 8 karakter legyen.")
    if current_password == new_password:
        raise HTTPException(status_code=422, detail="Az új jelszó legyen eltérő a jelenlegitől.")

    try:
        if change_pwa_user_password(user_courier_id(user), current_password, new_password):
            return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if change_legacy_user_password(user, current_password, new_password):
        return {"ok": True}

    raise HTTPException(status_code=404, detail="A felhasználó nem található a jelszómódosításhoz.")


@app.get("/api/statistics/monthly")
def monthly_statistics(
    month: str = Query(default=""),
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, preview_read_only = workflow_view_user(user, courier)
    payload = build_monthly_courier_statistics(view_user, parse_month(month))
    if preview_read_only:
        payload["viewingAs"] = public_user(view_user)
        payload["viewerReadOnly"] = True
    return payload


@app.put("/api/statistics/route-note")
def save_statistics_route_note(
    payload: RouteNoteRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    return save_route_note_for_user(user, payload)


@app.put("/api/profile/billing")
def update_billing_profile(
    payload: BillingProfileUpdate,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    session_courier_id, session_courier_name = profile_identity(user)
    current_billing = read_billing_profile(user)
    profile = validate_billing_profile(payload)
    bank_account_number = validate_bank_account_number(profile["bank_account_number"])
    profile["bank_account_number"] = bank_account_number
    target_courier_id = session_courier_id or profile["courier_id"]

    if not target_courier_id:
        raise HTTPException(status_code=422, detail="A futár ID megadása kötelező.")
    if session_courier_id and profile["courier_id"] and profile["courier_id"] != session_courier_id:
        raise HTTPException(status_code=422, detail="A már rögzített futár ID nem módosítható.")

    now = datetime.now(timezone.utc).isoformat()
    profile["courier_id"] = target_courier_id
    if not profile["courier_name"]:
        profile["courier_name"] = current_billing.get("courier_name") or session_courier_name

    update_payload = {
        **profile,
        "source_name": "pwa_profile",
        "organization_id": COURIER_DETAIL_ORGANIZATION_ID,
        "dsp_id": "JIT",
        "active": True,
        "fetched_at": now,
        "billing_data_source": "pwa_profile",
        "billing_data_updated_at": now,
        "updated_at": now,
    }

    supabase_rest(
        "POST",
        "courier_master",
        params={"on_conflict": "courier_id"},
        payload=update_payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )

    return {
        "ok": True,
        "billing": {
            **current_billing,
            **profile,
            "updated_at": now,
        },
    }


@app.get("/api/devices/reports")
def list_device_condition_reports(
    serial_number: str = Query(default=""),
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    courier_id, _courier_name = courier_identity(view_user)
    params = {
        "select": "id,device_id,device_type,serial_number,imei,courier_id,courier_name,event_type,condition_status,note,photo_count,reported_at",
        "courier_id": f"eq.{courier_id}",
        "order": "reported_at.desc",
        "limit": "20",
    }
    if clean_text(serial_number, limit=80):
        params["serial_number"] = f"eq.{normalize_device_serial(serial_number)}"
    rows = supabase_rest("GET", "pwa_device_condition_reports", params=params)
    reports = [safe_device_report(row) for row in rows or []]
    return {"reports": attach_device_report_photos(reports)}


@app.post("/api/devices/reports")
async def create_device_condition_report(
    serial_number: str = Form(...),
    imei: str = Form(default=""),
    event_type: str = Form(default="inspection"),
    condition_status: str = Form(default="ok"),
    note: str = Form(default=""),
    photos: list[UploadFile] = File(default=[]),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, courier_name = courier_identity(user)
    serial = normalize_device_serial(serial_number)
    clean_imei = normalize_device_imei(imei)
    clean_event_type = normalize_device_event_type(event_type)
    clean_status = normalize_device_status(condition_status)
    clean_note = clean_text(note, limit=1200)
    selected_photos = [photo for photo in photos if photo and photo.filename]
    if not selected_photos:
        raise HTTPException(status_code=422, detail="Legalabb egy fotot fel kell tolteni.")
    if len(selected_photos) > MAX_DEVICE_PHOTOS:
        raise HTTPException(status_code=422, detail=f"Legfeljebb {MAX_DEVICE_PHOTOS} foto toltheto fel egyszerre.")

    now = datetime.now(timezone.utc).isoformat()
    device_rows = supabase_rest(
        "POST",
        "pwa_devices",
        params={"on_conflict": "device_type,serial_number"},
        payload={
            "device_type": "phone",
            "serial_number": serial,
            "imei": clean_imei,
            "status": "active",
            "current_courier_id": int(courier_id),
            "current_courier_name": courier_name,
            "note": clean_note,
            "updated_at": now,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    device_id = (device_rows or [{}])[0].get("id")

    report_rows = supabase_rest(
        "POST",
        "pwa_device_condition_reports",
        payload={
            "device_id": device_id,
            "device_type": "phone",
            "serial_number": serial,
            "imei": clean_imei,
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "event_type": clean_event_type,
            "condition_status": clean_status,
            "note": clean_note,
            "photo_count": len(selected_photos),
            "reported_by": courier_name,
            "reported_at": now,
        },
        prefer="return=representation",
        timeout=60,
    )
    report = (report_rows or [{}])[0]
    report_id = report.get("id")
    if not report_id:
        raise HTTPException(status_code=502, detail="Az eszkozellenorzes rogzitese nem sikerult.")

    photo_payloads = []
    for index, photo in enumerate(selected_photos, start=1):
        content = await photo.read(MAX_DEVICE_PHOTO_BYTES + 1)
        if len(content) > MAX_DEVICE_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail=f"A(z) {photo.filename} tul nagy. Maximum 8 MB lehet.")
        mime_type = str(photo.content_type or "").lower()
        if mime_type not in DEVICE_PHOTO_MIME_TYPES:
            raise HTTPException(status_code=422, detail=f"Nem tamogatott kepformatum: {photo.filename}.")
        photo_payloads.append(
            {
                "report_id": report_id,
                "file_name": clean_text(photo.filename or f"telefon_{index}.jpg", limit=160),
                "mime_type": mime_type,
                "file_size": len(content),
                "file_content_base64": base64.b64encode(content).decode("ascii"),
                "photo_label": f"Foto {index}",
            }
        )

    supabase_rest(
        "POST",
        "pwa_device_condition_photos",
        payload=photo_payloads if len(photo_payloads) > 1 else photo_payloads[0],
        prefer="return=minimal",
        timeout=90,
    )

    safe_report = safe_device_report(report)
    safe_report["photos"] = [
        {
            "fileName": payload["file_name"],
            "mimeType": payload["mime_type"],
            "fileSize": payload["file_size"],
            "label": payload["photo_label"],
        }
        for payload in photo_payloads
    ]
    return {"stored": True, "report": safe_report}


@app.get("/api/devices/photos/{photo_id}")
def get_device_condition_photo(
    photo_id: str,
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    courier_id, _courier_name = courier_identity(view_user)
    photo_rows = supabase_rest(
        "GET",
        "pwa_device_condition_photos",
        params={
            "select": "id,report_id,file_name,mime_type,file_content_base64",
            "id": f"eq.{photo_id}",
            "limit": "1",
        },
    )
    if not photo_rows:
        raise HTTPException(status_code=404, detail="A foto nem talalhato.")
    photo = photo_rows[0]
    report_rows = supabase_rest(
        "GET",
        "pwa_device_condition_reports",
        params={
            "select": "id,courier_id",
            "id": f"eq.{photo.get('report_id')}",
            "limit": "1",
        },
    )
    if not report_rows or str(report_rows[0].get("courier_id") or "") != str(courier_id):
        raise HTTPException(status_code=404, detail="A foto nem talalhato.")
    try:
        content = base64.b64decode(photo.get("file_content_base64") or "", validate=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="A foto nem olvashato.") from exc
    file_name = str(photo.get("file_name") or "telefon_foto").replace('"', "")
    return Response(
        content=content,
        media_type=photo.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(file_name)}"},
    )


@app.get("/api/shifts")
def shifts(
    days: int = Query(default=5, ge=1, le=14),
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    return read_shifts(view_user, days)


@app.post("/api/shifts/delay-alert")
def create_shift_delay_alert(
    payload: ShiftDelayAlertRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    try:
        save_shift_queue_checkin(
            user,
            ShiftQueueCheckinRequest(
                work_date=payload.work_date,
                start=payload.start,
                end=payload.end,
                warehouse=payload.warehouse,
                shift_name=payload.shift_name,
                booking_code=payload.booking_code,
                event_type="shift_late",
            ),
        )
    except Exception as exc:
        print("Shift late DB log error:", exc)
    send_shift_delay_discord_alert(user, payload)
    return {"ok": True}


@app.post("/api/shifts/queue-checkin")
def create_shift_queue_checkin(
    payload: ShiftQueueCheckinRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    save_shift_queue_checkin(require_user(giriton_pwa_session), payload)
    return {"ok": True}


@app.get("/api/routes/current")
def current_route(
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    return build_route_card(view_user)


@app.post("/api/routes/delay-alert")
def create_route_delay_alert(
    payload: RouteDelayAlertRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    save_route_delay_alert(user, payload)
    return {"ok": True}


@app.post("/api/routes/auto-delay")
def create_route_auto_delay_alert(
    payload: RouteDelayAlertRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    save_route_auto_delay_alert(user, payload)
    return {"ok": True}


@app.post("/api/routes/alert")
async def create_route_alert(
    route_id: str = Form(...),
    order_id: str = Form(default=""),
    alert_type: str = Form(default="problem"),
    message: str = Form(default=""),
    dispatcher_notified: bool = Form(default=False),
    current_address: str = Form(default=""),
    current_checkpoint_position: int | None = Form(default=None),
    warehouse: str = Form(default=""),
    route_departure: str = Form(default=""),
    route_return: str = Form(default=""),
    photo: UploadFile | None = File(default=None),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    clean_type = str(alert_type or "problem").strip().lower()
    if clean_type not in {"problem", "delay", "bag_missing"}:
        clean_type = "problem"
    clean_message = str(message or "").strip()
    if clean_type in {"problem", "delay"} and not clean_message:
        raise HTTPException(status_code=422, detail="Írj egy rövid megjegyzést.")

    photo_content = b""
    if photo:
        photo_content = await photo.read()
        if len(photo_content) > MAX_DEVICE_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="A fotó túl nagy. Maximum 8 MB lehet.")
        if photo.content_type not in DEVICE_PHOTO_MIME_TYPES:
            raise HTTPException(status_code=422, detail="Csak JPG, PNG vagy WEBP fotó tölthető fel.")
    if clean_type == "bag_missing" and not photo_content:
        raise HTTPException(status_code=422, detail="Táska hiány jelzéshez kötelező fotót feltölteni.")

    payload = route_alert_payload(
        user=user,
        route_id=route_id,
        order_id=order_id,
        alert_type=clean_type,
        message=clean_message,
        dispatcher_notified=dispatcher_notified,
        current_address=current_address,
        current_checkpoint_position=current_checkpoint_position,
        warehouse=warehouse,
        route_departure=route_departure,
        route_return=route_return,
    )
    alert = save_route_alert(payload)
    alert_id = str(alert.get("id") or "")
    if photo and photo_content and alert_id:
        save_route_alert_photo(alert_id, photo, photo_content)

    return {"ok": True, "alert": {"id": alert_id, "type": clean_type}}


@app.get("/api/workflow")
def workflow(
    month: str = Query(default=""),
    process: str = Query(default=""),
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, preview = workflow_view_user(user, courier)
    privileged_viewer = can_view_financial_amounts(user)
    return build_workflow(
        view_user,
        parse_month(month),
        process,
        preview_read_only=preview,
        allow_unpublished=preview or privileged_viewer,
        can_view_amounts=privileged_viewer,
    )


@app.get("/api/workflow/processes")
def workflow_processes(
    month: str = Query(default=""),
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    return {"processes": list_workflow_processes(view_user, parse_month(month))}


@app.post("/api/workflow/{action}/accept")
def accept_workflow_document(
    action: str,
    payload: WorkflowActionRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    if action not in {"settlement", "tig"}:
        raise HTTPException(status_code=404, detail="Ismeretlen elfogadási lépés.")
    user = require_user(giriton_pwa_session)
    month = parse_month(payload.month)
    process_id = normalize_process_id(payload.process)
    if action == "tig":
        require_prerequisite(user, month, "tig", process_id)
    documents, status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(status_rows, process_id)
    documents = [row for row in documents if document_belongs_to_process(row, process_id)]
    complaints = [
        row for row in complaints
        if process_id_from_action_key(str(row.get("document_type") or "")) == process_id
    ]
    has_action_document = any(base_action_key(str(row.get("document_type") or "")) == action for row in documents)
    financial_breakdown = build_financial_breakdown(user, month)
    has_financial_breakdown = action == "settlement" and bool(financial_breakdown.get("available"))
    has_tig_breakdown = action == "tig" and bool(build_workflow_tig_breakdown(user, month, financial_breakdown).get("available"))
    if not has_action_document and not has_financial_breakdown and not has_tig_breakdown:
        raise HTTPException(status_code=409, detail="Nincs elfogadható dokumentum ehhez a hónaphoz.")
    if has_open_complaint(complaints, action) and not complaints_ignored_for_billing(states):
        raise HTTPException(
            status_code=409,
            detail="Nyitott reklamacio mellett nem fogadhato el a dokumentum.",
        )
    upsert_workflow_status(
        user,
        month,
        action,
        "done",
        "A futár elfogadta a dokumentumot.",
        process_id,
    )
    efo_invoice_skip = not process_id and courier_has_efo_assignment(user, month)
    manual_invoice_skip = not process_id and manual_invoice_skip_enabled(states)
    invoice_skip = efo_invoice_skip or manual_invoice_skip
    skip_note_prefix = "EFO folyamat" if efo_invoice_skip else "Admin kézi továbbengedés"
    if action == "settlement" and invoice_skip:
        upsert_workflow_status(
            user,
            month,
            "tig",
            "done",
            f"{skip_note_prefix}: TIG nem szükséges.",
            process_id,
        )
        upsert_workflow_status(
            user,
            month,
            "invoice_submit",
            "done",
            f"{skip_note_prefix}: számlafeltöltés nem szükséges.",
            process_id,
        )
        upsert_workflow_status(
            user,
            month,
            "invoice_check",
            "done",
            f"{skip_note_prefix}: számlaellenőrzés nem szükséges.",
            process_id,
        )
        open_payment_waiting_status(
            user,
            month,
            f"{skip_note_prefix}: elszámolás elfogadva, admin kifizetésre vár.",
            process_id,
        )
    elif action == "settlement":
        generate_tig_after_settlement_accept(user, month, process_id)
    if action == "tig" and not process_id and manual_invoice_skip_enabled(states):
        upsert_workflow_status(
            user,
            month,
            "invoice_submit",
            "done",
            "Számlafeltöltés kézzel kihagyva.",
            process_id,
        )
        open_payment_waiting_status(
            user,
            month,
            "Számlázás kézzel kihagyva, admin kifizetésre vár.",
            process_id,
        )
        upsert_workflow_status(
            user,
            month,
            "invoice_check",
            "done",
            "Számlaellenőrzés kézzel kihagyva.",
            process_id,
        )
    return {"ok": True, "workflow": build_workflow(user, month, process_id)}


@app.post("/api/workflow/complaints")
def create_workflow_complaint(
    payload: ComplaintRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    if payload.action not in {"settlement", "tig", "invoice_check", "invoice_submit"}:
        raise HTTPException(status_code=422, detail="Reklamáció csak elszámoláshoz vagy TIG-hez küldhető.")
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Írd le röviden a reklamációt.")
    user = require_user(giriton_pwa_session)
    month = parse_month(payload.month)
    process_id = normalize_process_id(payload.process)
    courier_id, courier_name = courier_identity(user)
    _documents, _status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(_status_rows, process_id)
    if payload.action == "settlement" and workflow_done(states, "settlement"):
        raise HTTPException(
            status_code=409,
            detail="Az elszamolast mar elfogadtad, reklamaciot elotte lehet kuldeni.",
        )
    complaints = [
        row for row in complaints
        if process_id_from_action_key(str(row.get("document_type") or "")) == process_id
    ]
    if has_open_complaint(complaints, payload.action):
        raise HTTPException(
            status_code=409,
            detail="Ehhez a lepeshez mar van nyitott reklamacio. Ujat akkor tudsz kuldeni, ha az admin lezarja az elozo rekordot.",
        )
    deleted_tig_count = 0
    if payload.action == "settlement":
        deleted_tig_count = delete_workflow_tig_documents(user, month, process_id)
    supabase_rest(
        "POST",
        "peopleforce_complaints",
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "document_type": process_action_key(payload.action, process_id),
            "document_month": month.isoformat(),
            "message": message,
            "status": "new",
            "created_by": courier_name,
        },
        prefer="return=representation",
    )
    upsert_workflow_status(user, month, payload.action, "open", "Új reklamáció érkezett.", process_id)
    return {
        "ok": True,
        "deletedTigCount": deleted_tig_count,
        "workflow": build_workflow(user, month, process_id),
    }


@app.get("/api/documents/{document_id}")
def download_document(
    document_id: str,
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    courier_id, _courier_name = courier_identity(view_user)
    rows = supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "id,courier_id,file_name,mime_type,file_content_base64",
            "id": f"eq.{document_id}",
            "courier_id": f"eq.{courier_id}",
            "limit": "1",
        },
        timeout=60,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="A dokumentum nem található.")
    row = rows[0]
    try:
        content = base64.b64decode(row.get("file_content_base64") or "", validate=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="A dokumentum tartalma sérült.") from exc
    file_name = str(row.get("file_name") or "dokumentum").replace('"', "")
    return Response(
        content=content,
        media_type=str(row.get("mime_type") or "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}"},
    )


@app.post("/api/invoices/check")
async def check_invoice(
    month: str = Form(...),
    process: str = Form(default=""),
    invoice_file: UploadFile = File(...),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    month_value = parse_month(month)
    process_id = normalize_process_id(process)
    require_prerequisite(user, month_value, "invoice_check", process_id)
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    courier_id, courier_name = courier_identity(user)
    billing_profile = read_billing_profile(user)
    _documents, status_rows, _complaints = read_workflow_rows(user, month_value)
    override_enabled = invoice_validation_override_enabled(status_map(status_rows, process_id))
    result = validate_invoice(
        file_name=invoice_file.filename or "szamla",
        content=content,
        invoice_month=month_value,
        courier_name=courier_name,
        courier_id=courier_id,
        expected_gross_amount=expected_tig_amount(user, month_value),
        expected_seller_name=billing_profile["company_name"],
        expected_seller_tax_number=billing_profile["tax_number"],
        expected_seller_address=billing_profile["company_address"],
    )
    result = apply_invoice_validation_override(result, override_enabled)
    if result["ok"]:
        upsert_workflow_status(
            user,
            month_value,
            "invoice_check",
            "done",
            "A számla automatikus ellenőrzése sikeres.",
            process_id,
        )
    else:
        error_details = [
            f"{check.get('title')}: {check.get('detail')}"
            for check in result.get("checks", [])
            if check.get("status") == "error"
        ]
        failure_note = "Számlaellenőrzési hiba: " + (
            " | ".join(error_details) if error_details else "Ismeretlen ellenőrzési hiba."
        )
        upsert_workflow_status(
            user,
            month_value,
            "invoice_check",
            "open",
            failure_note[:1500],
            process_id,
        )
    return {"validation": result, "workflow": build_workflow(user, month_value, process_id)}


@app.post("/api/invoices/submit")
async def submit_invoice(
    month: str = Form(...),
    process: str = Form(default=""),
    invoice_number: str = Form(...),
    gross_amount: int = Form(...),
    tig_reference: str = Form(default=""),
    note: str = Form(default=""),
    skip_invoice_number_match: bool = Form(default=False),
    invoice_file: UploadFile = File(...),
    cash_invoice_file: UploadFile | None = File(default=None),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    month_value = parse_month(month)
    process_id = normalize_process_id(process)
    require_prerequisite(user, month_value, "invoice_submit", process_id)
    courier_id, courier_name = courier_identity(user)
    billing_profile = read_billing_profile(user)
    _documents, status_rows, _complaints = read_workflow_rows(user, month_value)
    states = status_map(status_rows, process_id)
    if (
        invoice_document_exists_for_process(_documents, process_id)
        and workflow_done(states, "invoice_submit")
        and not workflow_open(states, "invoice_submit")
    ):
        raise HTTPException(
            status_code=409,
            detail="Ehhez a folyamathoz már érkezett számla. Új feltöltéshez kérj admin segítséget.",
        )
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    cash_content = b""
    if cash_invoice_file is not None and cash_invoice_file.filename:
        cash_content = await cash_invoice_file.read(MAX_INVOICE_BYTES + 1)
    override_enabled = invoice_validation_override_enabled(states)
    expected_amount = expected_tig_amount(user, month_value)
    if cash_content:
        shared_validation = {
            "invoice_month": month_value,
            "courier_name": courier_name,
            "courier_id": courier_id,
            "expected_gross_amount": 0,
            "require_submission_fields": False,
            "expected_seller_name": billing_profile["company_name"],
            "expected_seller_tax_number": billing_profile["tax_number"],
            "expected_seller_address": billing_profile["company_address"],
        }
        main_result = validate_invoice(
            file_name=invoice_file.filename or "szamla",
            content=content,
            **shared_validation,
        )
        cash_result = validate_invoice(
            file_name=cash_invoice_file.filename or "kp_szamla",
            content=cash_content,
            **shared_validation,
        )
        result = combine_invoice_validation_results(
            [("Átutalásos számla", main_result), ("KP számla", cash_result)],
            expected_gross_amount=expected_amount,
            declared_gross_amount=gross_amount,
            invoice_number=invoice_number,
            skip_invoice_number_match=skip_invoice_number_match,
        )
    else:
        result = validate_invoice(
            file_name=invoice_file.filename or "szamla",
            content=content,
            invoice_month=month_value,
            courier_name=courier_name,
            courier_id=courier_id,
            expected_gross_amount=expected_amount,
            invoice_number=invoice_number,
            gross_amount=gross_amount,
            require_submission_fields=True,
            skip_invoice_number_match=skip_invoice_number_match,
            expected_seller_name=billing_profile["company_name"],
            expected_seller_tax_number=billing_profile["tax_number"],
            expected_seller_address=billing_profile["company_address"],
        )
    result = apply_invoice_validation_override(result, override_enabled)

    upload_documents = [
        {
            "file_name": invoice_file.filename or f"szamla_{invoice_number}.pdf",
            "content_type": invoice_file.content_type or "application/octet-stream",
            "content": content,
            "title": f"Számla {invoice_number}",
            "payment_type": "Átutalás",
        }
    ]
    if cash_content and cash_invoice_file is not None:
        upload_documents.append(
            {
                "file_name": cash_invoice_file.filename or f"kp_szamla_{invoice_number}.pdf",
                "content_type": cash_invoice_file.content_type or "application/octet-stream",
                "content": cash_content,
                "title": f"KP számla {invoice_number}",
                "payment_type": "KP",
            }
        )
    document_payloads = [
        {
            "courier_id": courier_id,
            "courier_name": courier_name,
            "document_type": "invoice",
            "document_month": month_value.isoformat(),
            "title": document["title"],
            "file_name": document["file_name"],
            "mime_type": document["content_type"],
            "file_size": len(document["content"]),
            "file_content_base64": base64.b64encode(document["content"]).decode("ascii"),
            "note": (
                (process_note_marker(process_id) + "; " if process_note_marker(process_id) else "")
                +
                f"Fizetési mód: {document['payment_type']}; bruttó összesen: {gross_amount} Ft; "
                f"TIG/elszámolás: {tig_reference}. {note}"
            ).strip(),
            "uploaded_by": courier_name,
        }
        for document in upload_documents
    ]
    supabase_rest(
        "POST",
        "peopleforce_documents",
        payload=document_payloads if len(document_payloads) > 1 else document_payloads[0],
        prefer="return=representation",
        timeout=60,
    )
    stored_count = len(document_payloads)
    stored_label = "A két számla" if stored_count == 2 else "A számla"
    upsert_workflow_status(user, month_value, "invoice_submit", "done", f"{stored_label} feltöltve és eltárolva.", process_id)
    if result["ok"]:
        upsert_workflow_status(user, month_value, "invoice_check", "done", f"{stored_label} automatikus ellenőrzése sikeres.", process_id)
    else:
        error_details = [
            f"{check.get('title')}: {check.get('detail')}"
            for check in result.get("checks", [])
            if check.get("status") == "error"
        ]
        failure_note = "Automatikus számlaellenőrzési hiba: " + (
            " | ".join(error_details) if error_details else "Ismeretlen ellenőrzési hiba."
        )
        upsert_workflow_status(user, month_value, "invoice_check", "open", failure_note[:1500], process_id)
        supabase_rest(
            "POST",
            "peopleforce_complaints",
            payload={
                "courier_id": courier_id,
                "courier_name": courier_name,
                "document_type": process_action_key("invoice_check", process_id),
                "document_month": month_value.isoformat(),
                "message": (
                    "A számla automatikus ellenőrzése hibára futott, manuális ellenőrzés szükséges. "
                    + failure_note
                )[:1800],
                "status": "new",
                "created_by": "PWA automata",
            },
            prefer="return=representation",
        )
    upsert_workflow_status(user, month_value, "my_invoices", "open", f"{stored_label} admin ellenőrzésre és kifizetésre vár.", process_id)
    upsert_workflow_status(
        user,
        month_value,
        "invoice_payment",
        "open",
        "Admin szamlaelfogadasra es kifizetesre var.",
        process_id,
    )
    return {
        "stored": True,
        "storedCount": stored_count,
        "manualReview": not result["ok"],
        "validation": result,
        "workflow": build_workflow(user, month_value, process_id),
    }


def coordinator_adjustment_setup() -> dict[str, Any]:
    couriers = supabase_rest(
        "GET",
        "courier_master",
        params={
            "select": "courier_id,courier_name,active",
            "order": "courier_name.asc,courier_id.asc",
            "limit": "5000",
        },
    )
    couriers = [
        row for row in couriers
        if str(row.get("courier_id") or "").strip()
        and str(row.get("courier_name") or "").strip()
        and row.get("active") is not False
    ]
    result: dict[str, Any] = {"couriers": couriers, "items": {}, "entries": {}}
    for kind in ("bonus", "malus"):
        result["items"][kind] = supabase_rest(
            "GET",
            COORDINATOR_ITEM_TABLES[kind],
            params={
                "select": "id,item_name,default_amount_huf,description",
                "is_active": "eq.true",
                "order": "item_name.asc",
            },
        )
        result["entries"][kind] = supabase_rest(
            "GET",
            COORDINATOR_ENTRY_TABLES[kind],
            params={
                "select": (
                    "id,courier_id,courier_name,item_name,amount_huf,note,effective_date,"
                    "recorded_by,recorded_at"
                ),
                "deleted_at": "is.null",
                "order": "recorded_at.desc",
                "limit": "150",
            },
        )
    return result


@app.get("/api/coordinator-adjustments")
def get_coordinator_adjustments(
    giriton_pwa_session: str | None = Cookie(default=None),
):
    require_coordinator(require_user(giriton_pwa_session))
    return coordinator_adjustment_setup()


@app.post("/api/coordinator-adjustments")
def add_coordinator_adjustment(
    payload: CoordinatorAdjustmentRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_coordinator(require_user(giriton_pwa_session))
    kind = str(payload.kind or "").strip().lower()
    item_table = coordinator_table(COORDINATOR_ITEM_TABLES, kind)
    entry_table = coordinator_table(COORDINATOR_ENTRY_TABLES, kind)
    amount = abs(int(payload.amount_huf or 0))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Az összegnek nagyobbnak kell lennie nullánál.")
    try:
        effective_date = date.fromisoformat(payload.effective_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Hibás dátum.") from exc

    courier_rows = supabase_rest(
        "GET",
        "courier_master",
        params={
            "select": "courier_id,courier_name",
            "courier_id": f"eq.{str(payload.courier_id).strip()}",
            "limit": "1",
        },
    )
    if not courier_rows:
        raise HTTPException(status_code=404, detail="A kiválasztott futár nem található.")
    item_rows = supabase_rest(
        "GET",
        item_table,
        params={
            "select": "id,item_name",
            "id": f"eq.{str(payload.item_id).strip()}",
            "is_active": "eq.true",
            "limit": "1",
        },
    )
    if not item_rows:
        raise HTTPException(status_code=404, detail="A kiválasztott tétel már nem aktív.")
    courier = courier_rows[0]
    item = item_rows[0]
    actor = str(user.get("username") or "unknown").strip()
    rows = supabase_rest(
        "POST",
        entry_table,
        payload={
            "courier_id": str(courier.get("courier_id") or "").strip(),
            "courier_name": str(courier.get("courier_name") or "").strip(),
            "item_id": item.get("id"),
            "item_name": str(item.get("item_name") or "").strip(),
            "amount_huf": amount,
            "note": str(payload.note or "").strip(),
            "effective_date": effective_date.isoformat(),
            "recorded_by": actor,
        },
        prefer="return=representation",
    )
    return {"entry": rows[0] if rows else {}, "setup": coordinator_adjustment_setup()}


@app.post("/api/coordinator-adjustments/{kind}/{entry_id}/delete")
def delete_coordinator_adjustment(
    kind: str,
    entry_id: str,
    payload: CoordinatorAdjustmentDeleteRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_coordinator(require_user(giriton_pwa_session))
    reason = str(payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A visszavonás indoklása kötelező.")
    entry_table = coordinator_table(COORDINATOR_ENTRY_TABLES, kind)
    supabase_rest(
        "PATCH",
        entry_table,
        params={"id": f"eq.{entry_id}", "deleted_at": "is.null"},
        payload={
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": str(user.get("username") or "unknown").strip(),
            "delete_reason": reason,
        },
        prefer="return=minimal",
    )
    return {"ok": True, "setup": coordinator_adjustment_setup()}


@app.get("/api/salary-advance/requests")
def salary_advance_requests(
    courier: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    view_user, _preview = workflow_view_user(user, courier)
    courier_id, _courier_name = courier_identity(view_user)
    rows = supabase_rest(
        "GET",
        "courier_salary_advance_request",
        params={
            "select": "*",
            "courier_id": f"eq.{courier_id}",
            "order": "requested_at.desc",
            "limit": "100",
        },
        schema="settlement",
    )
    return {"requests": [normalize_salary_advance_request(row) for row in rows]}


@app.post("/api/salary-advance/requests")
def create_salary_advance_request(
    payload: SalaryAdvanceRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, courier_name = courier_identity(user)
    try:
        start_date = date.fromisoformat(str(payload.start_date or "")[:10]).replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="A kezdő dátum hibás.") from exc
    requested_amount = int(payload.requested_amount_huf or 0)
    months = int(payload.installment_months or 0)
    if requested_amount <= 0:
        raise HTTPException(status_code=422, detail="Az igényelt összegnek pozitívnak kell lennie.")
    if months < 1 or months > 60:
        raise HTTPException(status_code=422, detail="A hónapok száma 1 és 60 között lehet.")
    amounts = salary_advance_installment_amounts(requested_amount, months)
    rows = supabase_rest(
        "POST",
        "courier_salary_advance_request",
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "requested_amount_huf": requested_amount,
            "installment_months": len(amounts),
            "monthly_amount_huf": amounts[0] if amounts else 0,
            "start_date": start_date.isoformat(),
            "status": "requested",
            "note": clean_text(payload.note, limit=1000),
            "requested_by": courier_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=representation",
        schema="settlement",
    )
    requests = salary_advance_requests(giriton_pwa_session=giriton_pwa_session)
    return {
        "request": normalize_salary_advance_request(rows[0] if rows else {}),
        "requests": requests["requests"],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/assets", StaticFiles(directory=PWA_ROOT), name="pwa-assets")


@app.get("/{path:path}")
def pwa(path: str):
    requested = (PWA_ROOT / path).resolve()
    no_store_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if path and requested.is_file() and PWA_ROOT.resolve() in requested.parents:
        media_types = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
        }
        headers = no_store_headers if requested.name in {"sw.js", "index.html"} else {"Cache-Control": "public, max-age=300"}
        return FileResponse(requested, media_type=media_types.get(requested.suffix), headers=headers)
    return FileResponse(PWA_ROOT / "index.html", headers=no_store_headers)
