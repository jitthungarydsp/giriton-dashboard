import hashlib
import hmac
import base64
import json
import os
import re
import secrets
import time
import unicodedata
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
from resources.pwa_users_db import authenticate_pwa_db_user, change_pwa_user_password
from resources.security import hash_password, verify_password

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
    route_id: int
    order_id: str = ""
    message: str
    dispatcher_notified: bool = False
    current_address: str = ""
    current_checkpoint_position: int | None = None


class ShiftDelayAlertRequest(BaseModel):
    work_date: str
    start: str = ""
    end: str = ""
    warehouse: str = ""
    shift_name: str = ""
    booking_code: str = ""
    message: str = ""


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
    return role == "admin" or username_key == normalize_text("Bagoly Zoltán")


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


def normalize_email_address(value: str) -> str:
    try:
        return validate_email(str(value or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Az e-mail cim formatuma hibas.") from exc


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


def read_shifts(user: dict, days: int) -> dict[str, Any]:
    start = date.today()
    end = start + timedelta(days=days - 1)
    source_errors: list[str] = []

    try:
        comparison_items = read_attendance_muszakpro_shifts(user, start, end, days)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
            "items": comparison_items,
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
        "items": items,
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
    payload = fetch_driver_detail(user)
    routes = payload.get("routes") or []
    route = active_route(routes)

    if not route:
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

    return {
        "found": True,
        "totalRoutes": len(routes),
        "route": {
            "routeId": route.get("id") or route.get("routeId"),
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
            } if current_checkpoint else None,
            "next": {
                "orderId": str((next_checkpoint or {}).get("orderId") or ""),
                "position": (next_checkpoint or {}).get("position"),
                "address": str((next_checkpoint or {}).get("address") or ""),
                "windowFrom": local_iso_time((next_checkpoint or {}).get("deliverSince")),
                "windowTo": local_iso_time((next_checkpoint or {}).get("deliverTill")),
            } if next_checkpoint else None,
        },
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
            "route_id": payload.route_id,
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


def workflow_view_user(user: dict[str, Any], courier_id: str | None = "") -> tuple[dict[str, Any], bool]:
    target_id = str(courier_id or "").strip()
    if not target_id:
        return user, False
    if not can_preview_couriers(user):
        raise HTTPException(status_code=403, detail="Másik futár mobil nézetéhez admin jogosultság szükséges.")
    target_name = read_courier_display_name(target_id) or f"Futár {target_id}"
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
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def money_from(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return money_int(row.get(key))
    return 0


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
            "limit": "200",
        },
        timeout=30,
    )
    return {str(row.get("item_key") or ""): row for row in rows if str(row.get("item_key") or "")}


def apply_mobile_overrides(cards: list[dict[str, Any]], overrides: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def is_manual_override(row: dict[str, Any] | None) -> bool:
        note = str((row or {}).get("note") or "").strip()
        if not note:
            return False
        note_key = normalize_text(note)
        return "snapshot" not in note_key and "publikalt" not in note_key

    for card in cards:
        card_override = overrides.get(str(card.get("key") or ""))
        if is_manual_override(card_override):
            card["amountHuf"] = money_int(card_override.get("amount_value"))
            card["amountKind"] = str(card_override.get("amount_kind") or card.get("amountKind") or "huf")
            card["overrideNote"] = str(card_override.get("note") or "Admin által módosítva")
        for item in card.get("items") or []:
            override = overrides.get(str(item.get("key") or ""))
            if not is_manual_override(override):
                continue
            item["amountHuf"] = money_int(override.get("amount_value"))
            item["amountKind"] = str(override.get("amount_kind") or item.get("amountKind") or "huf")
            item["label"] = str(override.get("item_label") or item.get("label") or "")
            item["note"] = str(override.get("note") or "Admin által módosítva")
    return cards


def build_financial_breakdown(user: dict[str, Any], month: date, *, allow_unpublished: bool = False) -> dict[str, Any]:
    courier_id, _courier_name = courier_identity(user)
    row = read_courier_settlement_summary_row(courier_id, month, allow_unpublished=allow_unpublished)
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
    delayed_orders = sum(safe_int(item.get("delayed_order_count")) for item in daily_performance_rows)
    late_count = sum(safe_int(item.get("late_count")) for item in daily_performance_rows)
    no_show_count = sum(safe_int(item.get("did_not_come_count")) for item in daily_performance_rows)
    shift_count = sum(safe_int(item.get("shift_count")) for item in daily_performance_rows)
    performance_note = "DB napi teljesítmény"
    if not daily_performance_rows:
        delayed_orders = 0
        late_count = 0
        no_show_count = 0
        shift_count = 0
        performance_note = "Dummy adat"

    base = money_from(row, "fixed_rate_huf", "courier_base_rate_huf")
    tip = money_from(row, "tip_huf")
    delay = money_from(row, "delay_bonus_huf")
    compliance = money_from(row, "compliance_bonus_huf")
    loyalty = money_from(row, "loyalty_bonus_huf")
    customer_rating = money_from(row, "customer_rating_bonus_huf")
    monthly_bonus = money_from(row, "monthly_bonus_huf")
    monthly_malus = abs(money_from(row, "monthly_malus_huf"))
    returned_route = abs(money_from(row, "monthly_returned_route_huf"))
    accepted_route = money_from(row, "monthly_accepted_route_huf")
    atm_effect = money_from(row, "atm_effect_huf")
    reserve_topup = money_from(row, "target_reserve_topup_huf")
    fuel = money_from(row, "fuel_huf")
    damage = money_from(row, "damage_huf")
    cash_missing = money_from(row, "cash_missing_huf")
    other_income = money_from(row, "other_income_huf")
    other_deduction = money_from(row, "other_deduction_huf")
    instructor_fee = money_from(row, "instructor_fee_huf")
    payable = money_from(row, "payable_total_huf")

    income_items = [
        signed_item("base", "Alapdíj", base),
        signed_item("tip", "Borravaló", tip),
        signed_item("delay_bonus", "Késedelmi díj", delay),
        signed_item("compliance_bonus", "Túramegfelelés", compliance),
        signed_item("loyalty_bonus", "Lojalitás", loyalty),
        signed_item("customer_rating", "Ügyfélértékelési bónusz", customer_rating),
        signed_item("monthly_bonus", "Havi bónusz", monthly_bonus),
        signed_item("accepted_route", "Elfogadott kör korrekció", accepted_route),
        signed_item("other_income", "Egyéb jóváírás", other_income),
    ]
    deduction_items = [
        signed_item("monthly_malus", "Havi málusz", -monthly_malus),
        signed_item("returned_route", "Visszavett kör", -returned_route),
        signed_item("atm_effect", "ATM hatás", atm_effect),
        signed_item("reserve", "Céltartalék", reserve_topup),
        signed_item("fuel", "Üzemanyag", fuel),
        signed_item("damage", "Kár / levonás", damage),
        signed_item("cash_missing", "KP hiány", cash_missing),
        signed_item("other_deduction", "Egyéb levonás", other_deduction),
        signed_item("instructor_fee", "Oktatói díj", instructor_fee),
    ]
    income_items = [item for item in income_items if item["amountHuf"]]
    deduction_items = [item for item in deduction_items if item["amountHuf"]]
    income_total = sum(item["amountHuf"] for item in income_items)
    deduction_total = sum(item["amountHuf"] for item in deduction_items)
    if not payable:
        payable = income_total + deduction_total

    route_items = [
        count_item("orders", "Cím", money_from(row, "orders", "order_count")),
        count_item("routes", "Kör", money_from(row, "route_count", "routes")),
        count_item("highlighted_routes", "Kiemelt kör", money_from(row, "kiemelt_routes", "highlighted_routes")),
        count_item("normal_routes", "Normál kör", money_from(row, "sima_routes", "normal_routes")),
        count_item("shift_count", "Műszak", shift_count),
        count_item("late_count", "Késések száma", late_count),
        count_item("delayed_orders", "Késéses cím", delayed_orders),
        count_item("no_show_count", "Nem jelent meg műszakban", no_show_count),
    ]
    for item in route_items:
        item["note"] = performance_note
    route_items = [item for item in route_items if item.get("amountKind") == "count" or item["amountHuf"]]
    cards = [
        {
            "key": "payable",
            "label": "Teljes összeg",
            "amountHuf": payable,
            "tone": "total",
            "items": [
                signed_item("income_total", "Jóváírások összesen", income_total),
                signed_item("deduction_total", "Levonások / korrekciók összesen", deduction_total),
                signed_item("payable_total", "Kifizetendő", payable),
            ],
        },
        {"key": "income", "label": "Jóváírások", "amountHuf": income_total, "tone": "income", "items": income_items},
        {"key": "deductions", "label": "Levonások / korrekciók", "amountHuf": deduction_total, "tone": "deduction", "items": deduction_items},
        {"key": "performance", "label": "Teljesítmény", "amountHuf": money_from(row, "orders", "order_count"), "amountKind": "count", "tone": "info", "items": route_items},
    ]
    overrides = read_mobile_breakdown_overrides(courier_id, month)
    cards = apply_mobile_overrides(cards, overrides)
    payable_card = next((card for card in cards if card.get("key") == "payable"), {})
    payable = money_int(payable_card.get("amountHuf")) if payable_card else payable
    complaint_options = [
        {"key": item["key"], "label": item["label"], "amountHuf": item["amountHuf"], "amountKind": item.get("amountKind", "huf")}
        for card in cards
        for item in card["items"]
        if item["key"] not in {"income_total", "deduction_total", "payable_total"}
    ]
    return {
        "available": True,
        "month": month.strftime("%Y-%m"),
        "sessionId": str(row.get("_mobile_session_id") or row.get("session_id") or ""),
        "sourceMode": str(row.get("_mobile_source_mode") or ""),
        "sourceSheet": str(row.get("_mobile_source_sheet") or ""),
        "totalPayableHuf": payable,
        "cards": cards,
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


def build_monthly_courier_statistics(user: dict[str, Any], month_value: date) -> dict[str, Any]:
    courier_id, courier_name = courier_identity(user)
    period_start = month_value.replace(day=1)
    period_end = month_end(period_start)
    daily_rows = load_daily_performance_for_courier(courier_id, period_start, period_end)
    route_rows, route_source = load_api_financial_routes_for_courier(courier_id, period_start)
    day_rules, day_rule_source = load_month_day_rules(period_start, period_end)

    daily_orders = sum(safe_int(row.get("order_count")) for row in daily_rows)
    daily_routes = sum(safe_int(row.get("route_count")) for row in daily_rows)
    route_orders = sum(safe_int(row.get("orders")) for row in route_rows)
    route_tips = sum(safe_int(route.get("tips_huf")) for route in route_rows)
    route_count = len(route_rows)
    total_routes = route_count or daily_routes
    total_orders = route_orders or daily_orders
    average_orders = round(total_orders / total_routes, 1) if total_routes else 0

    highlighted_routes = 0
    normal_day_routes = 0
    express_routes = 0
    express_orders = 0
    route_types = {"normal": 0, "express": 0, "regional": 0}
    if route_rows:
        for route in route_rows:
            route_type = route.get("route_type") or "normal"
            route_types[route_type] = route_types.get(route_type, 0) + 1
            if route_type == "express":
                express_routes += 1
                express_orders += safe_int(route.get("orders"))
            if day_type_for_date(route.get("work_date"), day_rules) == "highlighted":
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

    delayed_orders = sum(safe_int(row.get("delayed_order_count")) for row in daily_rows)
    late_count = sum(safe_int(row.get("late_count")) for row in daily_rows)
    no_show_count = sum(safe_int(row.get("did_not_come_count")) for row in daily_rows)
    shift_count = sum(safe_int(row.get("shift_count")) for row in daily_rows)

    return {
        "month": period_start.strftime("%Y-%m"),
        "courier": {"id": courier_id, "name": courier_name},
        "amountsHidden": True,
        "amountsNote": "A teljes bevetel mobilon rejtve van, a borravalo megjelenik.",
        "summary": {
            "routes": total_routes,
            "orders": total_orders,
            "averageOrdersPerRoute": average_orders,
            "delayedOrders": delayed_orders,
            "lateCount": late_count,
            "noShowCount": no_show_count,
            "shiftCount": shift_count,
            "tipsTotalHuf": route_tips,
        },
        "routeBreakdown": {
            "highlightedRoutes": highlighted_routes,
            "normalDayRoutes": normal_day_routes,
            "expressRoutes": express_routes,
            "expressOrders": express_orders,
            "normalRoutes": route_types.get("normal", 0),
            "regionalRoutes": route_types.get("regional", 0),
        },
        "customerRating": load_customer_rating_stats(courier_id, period_start),
        "dataQuality": {
            "dailyRows": len(daily_rows),
            "routeRows": len(route_rows),
            "routeSource": route_source or "nincs route raw adat",
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
        raise HTTPException(status_code=422, detail="A nev megadasa kotelezo.")
    if not phone_number:
        raise HTTPException(status_code=422, detail="A telefonszam megadasa kotelezo.")

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
        "select": "id,document_type,message,status,created_at,admin_response,responded_by,responded_at",
        "courier_id": f"eq.{courier_id}",
        "document_month": f"eq.{month_value}",
        "order": "created_at.desc",
        "limit": "100",
    }
    try:
        complaints = supabase_rest(
            "GET",
            "peopleforce_complaints",
            params=complaint_params,
        )
    except HTTPException as exc:
        if exc.status_code != 502:
            raise
        complaint_params["select"] = "id,document_type,message,status,created_at"
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
    return str((states.get(action) or {}).get("status") or "").lower() == "done"


def complaints_ignored_for_billing(states: dict[str, dict]) -> bool:
    return workflow_done(states, "ignore_complaints_for_billing")


def invoice_validation_override_enabled(states: dict[str, dict]) -> bool:
    return workflow_done(states, "invoice_validation_override")


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
) -> dict[str, Any]:
    process_id = normalize_process_id(process)
    documents, status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(status_rows, process_id)
    financial_breakdown = build_financial_breakdown(user, month, allow_unpublished=allow_unpublished) if not process_id else {
        "available": False,
        "month": month.strftime("%Y-%m"),
        "totalPayableHuf": 0,
        "cards": [],
        "complaintOptions": [],
        "source": "settlement.courier_settlement_summary",
        "message": "Egyedi folyamatnál a havi pénzügyi bontás a havi folyamatnál látható.",
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

    settlement_ready = bool(document_groups["settlement"]) or bool(financial_breakdown.get("available"))

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
            "done": workflow_done(states, "settlement"),
            "locked": not settlement_ready,
        },
        {
            "key": "tig_document",
            "title": (
                "TIG elkészült"
                if document_groups["tig"]
                else "Várakozás a TIG elkészítésére"
            ),
            "done": bool(document_groups["tig"]),
            "locked": not workflow_done(states, "settlement"),
        },
        {
            "key": "tig",
            "title": "TIG elfogadása",
            "done": workflow_done(states, "tig"),
            "locked": not workflow_done(states, "settlement") or not bool(document_groups["tig"]),
        },
        {
            "key": "invoice_submit",
            "title": "Számlafeltöltés",
            "done": workflow_done(states, "invoice_submit"),
            "locked": not workflow_done(states, "tig"),
        },
        {
            "key": "invoice_check",
            "title": "Számlaellenőrzés",
            "done": workflow_done(states, "invoice_check"),
            "locked": not workflow_done(states, "invoice_submit"),
        },
        {
            "key": "invoice_payment",
            "title": (
                "Havi folyamat lezĂˇrva"
                if workflow_done(states, "invoice_payment")
                else "Admin szĂˇmlaelfogadĂˇs Ă©s kifizetĂ©s"
            ),
            "done": workflow_done(states, "invoice_payment"),
            "locked": not workflow_done(states, "invoice_check"),
        },
    ]
    if financial_breakdown.get("available") and not document_groups["settlement"]:
        steps[0]["title"] = "Havi pénzügyi adatok elkészültek"
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
        "complaints": complaints_by_action,
        "complaintResponses": response_documents_by_action,
        "ignoreComplaintsForBilling": complaints_ignored_for_billing(states),
        "invoiceValidationOverride": invoice_validation_override_enabled(states),
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
    return 0


def require_prerequisite(user: dict[str, Any], month: date, action: str, process_id: str | None = "") -> None:
    prerequisite = WORKFLOW_PREREQUISITES.get(action)
    if not prerequisite:
        return
    _documents, status_rows, _complaints = read_workflow_rows(user, month)
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
                "Ez a futar ID mar szerepel a torzsben, ezert regisztracio helyett "
                "jelszo-visszaallitast kell inditani."
            ),
            "emailUpdated": email_updated,
        }

    request_row = save_registration_request(payload)
    return {
        "ok": True,
        "message": "A regisztracios kerelmet rogzitettuk. Admin jovahagyas utan lesz belepesed.",
        "request": request_row,
    }


@app.post("/api/password-reset")
def password_reset(payload: PasswordResetRequest):
    courier_id = normalize_profile_courier_id(payload.courier_id)
    email = normalize_email_address(payload.email)
    user = find_user_by_courier_id(courier_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Ehhez a futar ID-hoz nincs aktiv mobil felhasznalo. Kerj admin segitseget.",
        )

    master_row = read_master_auth_row(courier_id)
    if not master_row:
        raise HTTPException(status_code=404, detail="Ez a futar ID nincs a futar torzsben.")

    existing_email = master_email(master_row)
    email_updated = False
    if existing_email and existing_email.casefold() != email.casefold():
        raise HTTPException(
            status_code=403,
            detail="A megadott e-mail cim nem egyezik a torzsben rogzitett e-mail cimmel.",
        )
    if not existing_email:
        email_updated = update_master_email_if_missing(master_row, email)

    password = str(user.get("password") or "").strip()
    if not password:
        raise HTTPException(
            status_code=409,
            detail="Ehhez a felhasznalohoz nincs olvashato jelszo, admin jelszoreset szukseges.",
        )

    try:
        result = send_login_credentials(email, str(user.get("username") or "").strip(), password)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Az e-mail kuldese sikertelen: {exc}") from exc

    return {
        "ok": True,
        "message": "Elkuldtem a belepesi adatokat a megadott e-mail cimre.",
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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    return {"billing": read_billing_profile(user)}


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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    return build_monthly_courier_statistics(user, parse_month(month))


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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, _courier_name = courier_identity(user)
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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, _courier_name = courier_identity(user)
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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    return read_shifts(require_user(giriton_pwa_session), days)


@app.post("/api/shifts/delay-alert")
def create_shift_delay_alert(
    payload: ShiftDelayAlertRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    send_shift_delay_discord_alert(require_user(giriton_pwa_session), payload)
    return {"ok": True}


@app.get("/api/routes/current")
def current_route(
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    return build_route_card(user)


@app.post("/api/routes/delay-alert")
def create_route_delay_alert(
    payload: RouteDelayAlertRequest,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    save_route_delay_alert(user, payload)
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
    return build_workflow(
        view_user,
        parse_month(month),
        process,
        preview_read_only=preview,
        allow_unpublished=preview,
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
    has_financial_breakdown = action == "settlement" and bool(build_financial_breakdown(user, month).get("available"))
    if not has_action_document and not has_financial_breakdown:
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
    complaints = [
        row for row in complaints
        if process_id_from_action_key(str(row.get("document_type") or "")) == process_id
    ]
    if has_open_complaint(complaints, payload.action):
        raise HTTPException(
            status_code=409,
            detail="Ehhez a lepeshez mar van nyitott reklamacio. Ujat akkor tudsz kuldeni, ha az admin lezarja az elozo rekordot.",
        )
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
    return {"ok": True, "workflow": build_workflow(user, month, process_id)}


@app.get("/api/documents/{document_id}")
def download_document(
    document_id: str,
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, _courier_name = courier_identity(user)
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
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    cash_content = b""
    if cash_invoice_file is not None and cash_invoice_file.filename:
        cash_content = await cash_invoice_file.read(MAX_INVOICE_BYTES + 1)
    courier_id, courier_name = courier_identity(user)
    billing_profile = read_billing_profile(user)
    _documents, status_rows, _complaints = read_workflow_rows(user, month_value)
    override_enabled = invoice_validation_override_enabled(status_map(status_rows, process_id))
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
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    courier_id, _courier_name = courier_identity(user)
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
    requests = salary_advance_requests(giriton_pwa_session)
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
    if path and requested.is_file() and PWA_ROOT.resolve() in requested.parents:
        media_types = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
        }
        return FileResponse(requested, media_type=media_types.get(requested.suffix))
    return FileResponse(PWA_ROOT / "index.html")
