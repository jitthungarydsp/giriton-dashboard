from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.pwa_users_db import PWA_USERS_TABLE, _request
from resources.security import hash_password
from resources.users import normalize_courier_id


USERS_FILE = PROJECT_ROOT / "data" / "users.json"


def load_json_users() -> list[dict[str, Any]]:
    with USERS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file).get("users", [])


def find_user(courier_id: str) -> dict[str, Any]:
    clean_id = normalize_courier_id(courier_id)
    matches = [
        user
        for user in load_json_users()
        if normalize_courier_id(user.get("courierId") or user.get("courier_id")) == clean_id
    ]
    if not matches:
        raise RuntimeError(f"Nincs users.json rekord erre a Courier ID-ra: {clean_id}")

    active_matches = [user for user in matches if user.get("active", True)]
    preferred = [
        user
        for user in active_matches
        if str(user.get("username") or "").strip()
        and normalize_courier_id(user.get("courierId") or user.get("courier_id")) == clean_id
    ]
    if preferred:
        return preferred[0]
    return active_matches[0] if active_matches else matches[0]


def sync_user(courier_id: str) -> dict[str, Any]:
    user = find_user(courier_id)
    clean_id = normalize_courier_id(user.get("courierId") or user.get("courier_id") or courier_id)
    username = str(user.get("username") or "").strip()
    if not username:
        raise RuntimeError(f"A {clean_id} users.json rekordban nincs felhasználónév.")

    password_hash = str(user.get("passwordHash") or "").strip()
    plain_password = str(user.get("password") or "").strip()
    if not password_hash and plain_password:
        password_hash = hash_password(plain_password)
    if not password_hash:
        raise RuntimeError(f"A {clean_id} users.json rekordban nincs jelszó vagy passwordHash.")

    now = datetime.now(timezone.utc).isoformat()
    rows = _request(
        "POST",
        PWA_USERS_TABLE,
        params={"on_conflict": "courier_id"},
        payload={
            "courier_id": int(clean_id),
            "username": username,
            "email": str(user.get("credentialEmail") or "").strip() or None,
            "role": str(user.get("role") or "user").strip() or "user",
            "active": bool(user.get("active", True)),
            "password_hash": password_hash,
            "updated_at": now,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    if rows is None:
        raise RuntimeError("A pwa_users tábla nem érhető el. Futtasd a docs/pwa_users.sql migrációt.")
    return rows[0] if rows else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Egy PWA user átemelése users.json-ból pwa_users DB-be.")
    parser.add_argument("--courier-id", required=True)
    args = parser.parse_args()

    row = sync_user(args.courier_id)
    print("OK: PWA user DB-be szinkronizálva.")
    print(f"courier_id={row.get('courier_id')}")
    print(f"username={row.get('username')}")
    print(f"active={row.get('active')}")


if __name__ == "__main__":
    main()
