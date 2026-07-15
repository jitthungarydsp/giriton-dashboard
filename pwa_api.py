import hashlib
import hmac
import json
import os
import secrets
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests
import tomllib
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from resources.security import verify_password


PROJECT_ROOT = Path(__file__).resolve().parent
PWA_ROOT = PROJECT_ROOT / "pwa"
USERS_FILE = PROJECT_ROOT / "data" / "users.json"
LOCAL_SESSION_SECRET_FILE = PROJECT_ROOT / ".pwa_session_secret"
SESSION_COOKIE = "giriton_pwa_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


class LoginRequest(BaseModel):
    username: str
    password: str


def load_setting(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            settings = tomllib.load(file)
        value = settings.get(name) or settings.get("supabase", {}).get(name)
        return str(value or "")
    except Exception:
        return ""


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
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Hiányzik a Supabase konfiguráció.")

    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
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


def read_shifts(user: dict, days: int) -> dict[str, Any]:
    start = date.today()
    end = start + timedelta(days=days - 1)
    source_errors: list[str] = []

    try:
        giriton_raw = supabase_rows(
            "giriton_shifts_raw",
            "work_date,start_time,end_time,warehouse,courier_name,courier_id,status,fetched_at",
            start,
            end,
        )
    except Exception:
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


app = FastAPI(title="Giriton Futár PWA", docs_url=None, redoc_url=None)


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


@app.get("/api/shifts")
def shifts(
    days: int = Query(default=5, ge=1, le=14),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    return read_shifts(require_user(giriton_pwa_session), days)


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
