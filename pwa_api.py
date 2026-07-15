import hashlib
import hmac
import base64
import json
import os
import secrets
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import tomllib
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from resources.pwa_invoice_validation import MAX_INVOICE_BYTES, extract_expected_amount, validate_invoice
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


class WorkflowActionRequest(BaseModel):
    month: str


class ComplaintRequest(BaseModel):
    month: str
    action: str
    message: str


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


WORKFLOW_PREREQUISITES = {
    "tig": "settlement",
    "invoice_check": "tig",
    "invoice_submit": "invoice_check",
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
    complaints = supabase_rest(
        "GET",
        "peopleforce_complaints",
        params={
            "select": "id,document_type,message,status,created_at,admin_response,responded_by,responded_at",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month_value}",
            "order": "created_at.desc",
            "limit": "100",
        },
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
    return {
        "month": month.strftime("%Y-%m"),
        "steps": steps,
        "states": states,
        "documents": safe_documents,
        "complaints": {
            action: [row for row in complaints if row.get("document_type") == action]
            for action in ("settlement", "tig")
        },
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
    documents, _statuses, _complaints = read_workflow_rows(user, month)
    if not any(row.get("document_type") == action for row in documents):
        raise HTTPException(status_code=409, detail="Nincs elfogadható dokumentum ehhez a hónaphoz.")
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
    if payload.action not in {"settlement", "tig"}:
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
    result = validate_invoice(
        file_name=invoice_file.filename or "szamla",
        content=content,
        invoice_month=month_value,
        courier_name=courier_name,
        courier_id=courier_id,
        expected_gross_amount=expected_tig_amount(user, month_value),
        expected_seller_tax_number=str(user.get("taxNumber") or user.get("tax_number") or ""),
        expected_seller_address=str(user.get("billingAddress") or user.get("billing_address") or ""),
    )
    if result["ok"]:
        upsert_workflow_status(
            user,
            month_value,
            "invoice_check",
            "done",
            "A számla automatikus ellenőrzése sikeres.",
        )
    return {"validation": result, "workflow": build_workflow(user, month_value)}


@app.post("/api/invoices/submit")
async def submit_invoice(
    month: str = Form(...),
    invoice_number: str = Form(...),
    gross_amount: int = Form(...),
    tig_reference: str = Form(default=""),
    note: str = Form(default=""),
    invoice_file: UploadFile = File(...),
    giriton_pwa_session: str | None = Cookie(default=None),
):
    user = require_user(giriton_pwa_session)
    month_value = parse_month(month)
    require_prerequisite(user, month_value, "invoice_submit")
    content = await invoice_file.read(MAX_INVOICE_BYTES + 1)
    courier_id, courier_name = courier_identity(user)
    result = validate_invoice(
        file_name=invoice_file.filename or "szamla",
        content=content,
        invoice_month=month_value,
        courier_name=courier_name,
        courier_id=courier_id,
        expected_gross_amount=expected_tig_amount(user, month_value),
        invoice_number=invoice_number,
        gross_amount=gross_amount,
        require_submission_fields=True,
        expected_seller_tax_number=str(user.get("taxNumber") or user.get("tax_number") or ""),
        expected_seller_address=str(user.get("billingAddress") or user.get("billing_address") or ""),
    )
    if not result["ok"]:
        return {"stored": False, "validation": result, "workflow": build_workflow(user, month_value)}

    file_name = invoice_file.filename or f"szamla_{invoice_number}.pdf"
    supabase_rest(
        "POST",
        "peopleforce_documents",
        payload={
            "courier_id": courier_id,
            "courier_name": courier_name,
            "document_type": "invoice",
            "document_month": month_value.isoformat(),
            "title": f"Számla {invoice_number}",
            "file_name": file_name,
            "mime_type": invoice_file.content_type or "application/octet-stream",
            "file_size": len(content),
            "file_content_base64": base64.b64encode(content).decode("ascii"),
            "note": f"Bruttó: {gross_amount} Ft; TIG/elszámolás: {tig_reference}. {note}".strip(),
            "uploaded_by": courier_name,
        },
        prefer="return=representation",
        timeout=60,
    )
    for action in ("invoice_submit", "my_invoices"):
        upsert_workflow_status(user, month_value, action, "done", "A számla ellenőrizve és eltárolva.")
    return {"stored": True, "validation": result, "workflow": build_workflow(user, month_value)}


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
