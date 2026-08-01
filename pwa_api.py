import hashlib
import hmac
import base64
import json
import os
import re
import secrets
import time
import unicodedata
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

from resources.pwa_invoice_validation import MAX_INVOICE_BYTES, extract_expected_amount, validate_invoice
from resources.security import verify_password

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


class WorkflowActionRequest(BaseModel):
    month: str


class ComplaintRequest(BaseModel):
    month: str
    action: str
    message: str


class RouteDelayAlertRequest(BaseModel):
    route_id: int
    order_id: str = ""
    message: str
    dispatcher_notified: bool = False
    current_address: str = ""
    current_checkpoint_position: int | None = None


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
        value = settings.get(name) or settings.get("supabase", {}).get(name)
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
    }


def authenticate(username: str, password: str) -> dict[str, Any] | None:
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
            detail="Írd le röviden a késés okát.",
        )

    supabase_rest(
        "POST",
        "courier_route_alerts",
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "route_id": payload.route_id,
            "order_id": payload.order_id.strip(),
            "alert_type": "delay",
            "message": message,
            "dispatcher_notified": payload.dispatcher_notified,
            "current_address": payload.current_address.strip(),
            "current_checkpoint_position": payload.current_checkpoint_position,
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )



WORKFLOW_PREREQUISITES = {
    "tig": "settlement",
    "invoice_check": "tig",
    "invoice_submit": "invoice_check",
    "invoice_payment": "invoice_submit",
}
WORKFLOW_DOCUMENT_TYPES = {"settlement", "tig", "invoice"}


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


def supabase_headers(*, prefer: str = "") -> dict[str, str]:
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY").strip()
    if not load_setting("SUPABASE_URL") or not key:
        raise HTTPException(status_code=503, detail="Hiányzik a Supabase konfiguráció.")
    headers = supabase_key_headers(key)
    if prefer:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer
    return headers

def supabase_rest(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    prefer: str = "",
    timeout: int = 30,
) -> Any:
    url = load_setting("SUPABASE_URL").rstrip("/")

    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(prefer=prefer),
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


def status_map(rows: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("action_key") or "")
        if key and key not in result:
            result[key] = row
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
        if row.get("document_type") != action:
            continue
        if str(row.get("status") or "").strip().lower() == "resolved":
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
) -> None:
    courier_id, courier_name = courier_identity(user)
    supabase_rest(
        "POST",
        "peopleforce_card_statuses",
        params={"on_conflict": "courier_id,document_month,action_key"},
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "action_key": action,
            "document_month": month.isoformat(),
            "status": "done" if status == "done" else "open",
            "status_note": note,
            "updated_by": courier_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="resolution=merge-duplicates,return=representation",
    )


def build_workflow(user: dict[str, Any], month: date) -> dict[str, Any]:
    documents, status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(status_rows)
    document_groups = {
        document_type: [row for row in documents if row.get("document_type") == document_type]
        for document_type in WORKFLOW_DOCUMENT_TYPES
    }
    response_documents = [
        row for row in documents
        if row.get("document_type") == "complaint_response"
    ]
    for action in ("settlement", "tig"):
        if document_groups[action] and action not in states:
            states[action] = {"status": "open", "status_note": "Új dokumentum érkezett."}

    steps = [
        {
            "key": "settlement_document",
            "title": (
                "Elszámolás elkészült"
                if document_groups["settlement"]
                else "Várakozás az elszámolás elkészítésére"
            ),
            "done": bool(document_groups["settlement"]),
            "locked": False,
        },
        {
            "key": "settlement",
            "title": "Elszámolás elfogadása",
            "done": workflow_done(states, "settlement"),
            "locked": not bool(document_groups["settlement"]),
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
            "key": "invoice_check",
            "title": "Számlaellenőrzés",
            "done": workflow_done(states, "invoice_check"),
            "locked": not workflow_done(states, "tig"),
        },
        {
            "key": "invoice_submit",
            "title": "Számlafeltöltés",
            "done": workflow_done(states, "invoice_submit"),
            "locked": not workflow_done(states, "invoice_check"),
        },
        {
            "key": "invoice_payment",
            "title": (
                "Havi folyamat lezĂˇrva"
                if workflow_done(states, "invoice_payment")
                else "Admin szĂˇmlaelfogadĂˇs Ă©s kifizetĂ©s"
            ),
            "done": workflow_done(states, "invoice_payment"),
            "locked": not workflow_done(states, "invoice_submit"),
        },
    ]
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
        action: [row for row in complaints if row.get("document_type") == action]
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
        "steps": steps,
        "states": states,
        "documents": safe_documents,
        "complaints": complaints_by_action,
        "complaintResponses": response_documents_by_action,
        "ignoreComplaintsForBilling": complaints_ignored_for_billing(states),
        "invoiceValidationOverride": invoice_validation_override_enabled(states),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


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


def require_prerequisite(user: dict[str, Any], month: date, action: str) -> None:
    prerequisite = WORKFLOW_PREREQUISITES.get(action)
    if not prerequisite:
        return
    _documents, status_rows, _complaints = read_workflow_rows(user, month)
    if not workflow_done(status_map(status_rows), prerequisite):
        labels = {
            "settlement": "az elszámolás elfogadása",
            "tig": "a TIG elfogadása",
            "invoice_check": "a sikeres számlaellenőrzés",
        }
        raise HTTPException(status_code=409, detail=f"Előbb szükséges: {labels[prerequisite]}.")

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

    supabase_rest(
        "PATCH",
        "pwa_push_subscriptions",
        params={"courier_id": f"eq.{courier_id}"},
        payload={"active": False, "updated_at": now},
        prefer="return=minimal",
    )

    supabase_rest(
        "POST",
        "pwa_push_subscriptions",
        params={"on_conflict": "endpoint"},
        payload={
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": payload.user_agent.strip(),
            "active": True,
            "last_seen_at": now,
            "updated_at": now,
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )


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


@app.get("/api/me")
def me(giriton_pwa_session: str | None = Cookie(default=None)):
    return {"user": public_user(require_user(giriton_pwa_session))}


@app.get("/api/push/public-key")
def get_push_public_key(
    giriton_pwa_session: str | None = Cookie(default=None),
):
    require_user(giriton_pwa_session)
    return {"publicKey": public_vapid_key()}


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


@app.get("/api/shifts")
def shifts(
    days: int = Query(default=5, ge=1, le=14),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    return read_shifts(require_user(giriton_pwa_session), days)


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


@app.get("/api/workflow")
def workflow(
    month: str = Query(default=""),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    return build_workflow(require_user(giriton_pwa_session), parse_month(month))


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
    if action == "tig":
        require_prerequisite(user, month, "tig")
    documents, status_rows, complaints = read_workflow_rows(user, month)
    states = status_map(status_rows)
    if not any(row.get("document_type") == action for row in documents):
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
    )
    return {"ok": True, "workflow": build_workflow(user, month)}


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
    courier_id, courier_name = courier_identity(user)
    supabase_rest(
        "POST",
        "peopleforce_complaints",
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "document_type": payload.action,
            "document_month": month.isoformat(),
            "message": message,
            "status": "new",
            "created_by": courier_name,
        },
        prefer="return=representation",
    )
    upsert_workflow_status(user, month, payload.action, "open", "Új reklamáció érkezett.")
    return {"ok": True, "workflow": build_workflow(user, month)}


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
    invoice_file: UploadFile = File(...),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    month_value = parse_month(month)
    require_prerequisite(user, month_value, "invoice_check")
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    courier_id, courier_name = courier_identity(user)
    billing_profile = read_billing_profile(user)
    _documents, status_rows, _complaints = read_workflow_rows(user, month_value)
    override_enabled = invoice_validation_override_enabled(status_map(status_rows))
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
        )
    return {"validation": result, "workflow": build_workflow(user, month_value)}


@app.post("/api/invoices/submit")
async def submit_invoice(
    month: str = Form(...),
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
    require_prerequisite(user, month_value, "invoice_submit")
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    cash_content = b""
    if cash_invoice_file is not None and cash_invoice_file.filename:
        cash_content = await cash_invoice_file.read(MAX_INVOICE_BYTES + 1)
    courier_id, courier_name = courier_identity(user)
    billing_profile = read_billing_profile(user)
    _documents, status_rows, _complaints = read_workflow_rows(user, month_value)
    override_enabled = invoice_validation_override_enabled(status_map(status_rows))
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
    if not result["ok"]:
        error_details = [
            f"{check.get('title')}: {check.get('detail')}"
            for check in result.get("checks", [])
            if check.get("status") == "error"
        ]
        failure_note = "Számlafeltöltési hiba: " + (
            " | ".join(error_details) if error_details else "Ismeretlen feltöltési hiba."
        )
        upsert_workflow_status(
            user,
            month_value,
            "invoice_submit",
            "open",
            failure_note[:1500],
        )
        return {"stored": False, "validation": result, "workflow": build_workflow(user, month_value)}

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
    upsert_workflow_status(user, month_value, "invoice_submit", "done", f"{stored_label} ellenőrizve és eltárolva.")
    upsert_workflow_status(user, month_value, "my_invoices", "open", f"{stored_label} admin ellenőrzésre és kifizetésre vár.")
    upsert_workflow_status(
        user,
        month_value,
        "invoice_payment",
        "open",
        "Admin szamlaelfogadasra es kifizetesre var.",
    )
    return {
        "stored": True,
        "storedCount": stored_count,
        "validation": result,
        "workflow": build_workflow(user, month_value),
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
