from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from resources.security import hash_password, verify_password
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error
from resources.users import generate_password, normalize_courier_id, normalize_name


PWA_USERS_TABLE = "pwa_users"


def _headers(prefer: str = "") -> dict[str, str]:
    _supabase_url, service_role_key = get_supabase_config()
    headers = {
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    if service_role_key and not service_role_key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {service_role_key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(method: str, table: str, *, params: dict[str, str] | None = None, payload: Any = None, prefer: str = "") -> Any:
    supabase_url, _service_role_key = get_supabase_config()
    if not supabase_url:
        return None
    response = requests.request(
        method,
        f"{supabase_url.rstrip('/')}/rest/v1/{table}",
        headers=_headers(prefer),
        params=params,
        json=payload,
        timeout=30,
    )
    if response.status_code == 404:
        return None
    raise_for_supabase_error(response)
    if not response.content:
        return None
    return response.json()


def public_pwa_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(row.get("username") or ""),
        "courierId": str(row.get("courier_id") or row.get("courierId") or ""),
        "role": str(row.get("role") or "user"),
        "active": bool(row.get("active", True)),
    }


def find_pwa_user_by_login(username: str) -> dict[str, Any] | None:
    wanted = str(username or "").strip()
    if not wanted:
        return None
    rows = _request(
        "GET",
        PWA_USERS_TABLE,
        params={
            "select": "username,courier_id,role,active,password_hash,email",
            "username": f"eq.{wanted}",
            "limit": "1",
        },
    )
    if rows:
        return rows[0]

    # Backward-compatible fallback for case/spacing/accent drift.
    rows = _request(
        "GET",
        PWA_USERS_TABLE,
        params={
            "select": "username,courier_id,role,active,password_hash,email",
            "active": "eq.true",
            "limit": "10000",
        },
    ) or []
    wanted_key = normalize_name(wanted)
    for row in rows:
        if normalize_name(row.get("username")) == wanted_key:
            return row
    return None


def find_pwa_user_by_courier_id(courier_id: str) -> dict[str, Any] | None:
    clean_courier_id = normalize_courier_id(courier_id)
    if not clean_courier_id:
        return None
    rows = _request(
        "GET",
        PWA_USERS_TABLE,
        params={
            "select": "courier_id,username,email,role,active,password_hash",
            "courier_id": f"eq.{clean_courier_id}",
            "active": "eq.true",
            "limit": "1",
        },
    )
    if rows is None or not rows:
        return None
    return rows[0]


def update_pwa_user_email_if_missing(courier_id: str, email: str) -> bool:
    clean_courier_id = normalize_courier_id(courier_id)
    clean_email = str(email or "").strip()
    if not clean_courier_id or not clean_email:
        return False
    row = find_pwa_user_by_courier_id(clean_courier_id)
    if not row or str(row.get("email") or "").strip():
        return False

    _request(
        "PATCH",
        PWA_USERS_TABLE,
        params={"courier_id": f"eq.{clean_courier_id}"},
        payload={
            "email": clean_email,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )
    return True


def authenticate_pwa_db_user(username: str, password: str) -> dict[str, Any] | None:
    row = find_pwa_user_by_login(username)
    if not row or not bool(row.get("active", True)):
        return None
    password_hash = str(row.get("password_hash") or "")
    if password_hash and verify_password(password, password_hash):
        return public_pwa_user(row)
    return None


def upsert_pwa_user_with_password(
    *,
    courier_id: str,
    username: str,
    recipient_email: str,
    role: str = "user",
) -> dict[str, Any]:
    clean_courier_id = normalize_courier_id(courier_id)
    clean_username = str(username or "").strip()
    clean_email = str(recipient_email or "").strip()
    if not clean_courier_id:
        raise ValueError("A Courier ID megadása kötelező.")
    if not clean_username:
        raise ValueError("A felhasználónév kötelező.")
    if not clean_email:
        raise ValueError("Az e-mail cím kötelező.")

    password = generate_password()
    now = datetime.now(timezone.utc).isoformat()
    rows = _request(
        "POST",
        PWA_USERS_TABLE,
        params={"on_conflict": "courier_id"},
        payload={
            "courier_id": int(clean_courier_id),
            "username": clean_username,
            "email": clean_email,
            "role": role or "user",
            "active": True,
            "password_hash": hash_password(password),
            "password_updated_at": now,
            "credential_email_sent_at": now,
            "updated_at": now,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    if rows is None:
        raise RuntimeError("A pwa_users tábla nem érhető el. Futtasd a docs/pwa_users.sql migrációt.")
    return {
        "action": "upserted",
        "username": clean_username,
        "password": password,
        "recipient": clean_email,
        "row": rows[0] if rows else {},
    }


def change_pwa_user_password(courier_id: str, current_password: str, new_password: str) -> bool:
    clean_courier_id = normalize_courier_id(courier_id)
    if not clean_courier_id:
        return False
    rows = _request(
        "GET",
        PWA_USERS_TABLE,
        params={
            "select": "courier_id,password_hash",
            "courier_id": f"eq.{clean_courier_id}",
            "limit": "1",
        },
    )
    if rows is None:
        return False
    if not rows:
        return False

    password_hash = str(rows[0].get("password_hash") or "")
    if not password_hash or not verify_password(current_password, password_hash):
        raise ValueError("A jelenlegi jelszó nem megfelelő.")

    now = datetime.now(timezone.utc).isoformat()
    _request(
        "PATCH",
        PWA_USERS_TABLE,
        params={"courier_id": f"eq.{clean_courier_id}"},
        payload={
            "password_hash": hash_password(new_password),
            "password_updated_at": now,
            "updated_at": now,
        },
        prefer="return=minimal",
    )
    return True


def reset_pwa_user_password(courier_id: str) -> dict[str, Any] | None:
    clean_courier_id = normalize_courier_id(courier_id)
    if not clean_courier_id:
        return None
    rows = _request(
        "GET",
        PWA_USERS_TABLE,
        params={
            "select": "courier_id,username,email,active",
            "courier_id": f"eq.{clean_courier_id}",
            "active": "eq.true",
            "limit": "1",
        },
    )
    if rows is None:
        return None
    if not rows:
        return None

    password = generate_password()
    now = datetime.now(timezone.utc).isoformat()
    _request(
        "PATCH",
        PWA_USERS_TABLE,
        params={"courier_id": f"eq.{clean_courier_id}"},
        payload={
            "password_hash": hash_password(password),
            "password_updated_at": now,
            "updated_at": now,
        },
        prefer="return=minimal",
    )
    return {
        "username": str(rows[0].get("username") or "").strip(),
        "password": password,
        "email": str(rows[0].get("email") or "").strip(),
    }


def sync_pwa_users_from_json_users(users: list[dict[str, Any]]) -> dict[str, int]:
    result = {"synced": 0, "skipped": 0}
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for user in users:
        courier_id = normalize_courier_id(user.get("courierId") or user.get("courier_id"))
        username = str(user.get("username") or "").strip()
        if not courier_id or not username:
            result["skipped"] += 1
            continue
        password_hash = str(user.get("passwordHash") or "").strip()
        if not password_hash and str(user.get("password") or "").strip():
            password_hash = hash_password(str(user.get("password") or "").strip())
        if not password_hash:
            result["skipped"] += 1
            continue
        rows.append(
            {
                "courier_id": int(courier_id),
                "username": username,
                "email": str(user.get("credentialEmail") or "").strip() or None,
                "role": str(user.get("role") or "user").strip() or "user",
                "active": bool(user.get("active", True)),
                "password_hash": password_hash,
                "updated_at": now,
            }
        )

    if not rows:
        return result

    response_rows = _request(
        "POST",
        PWA_USERS_TABLE,
        params={"on_conflict": "courier_id"},
        payload=rows,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    if response_rows is None:
        raise RuntimeError("A pwa_users tábla nem érhető el. Futtasd a docs/pwa_users.sql migrációt.")
    result["synced"] = len(rows)
    return result
