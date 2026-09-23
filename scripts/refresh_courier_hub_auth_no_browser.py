#!/usr/bin/env python3
"""
Courier Hub auth cache frissites bongeszo nelkul.

Egy ervenyes Courier Hub session cookie alapjan meghivja az /api/auth/session
endpointot, kiveszi az accessToken mezot, majd a meglvo sync scriptek altal
olvashato cache formatumba menti.

Pelda:
    $env:COURIER_HUB_COOKIE="next-auth.session-token=..."
    python scripts/refresh_courier_hub_auth_no_browser.py --cache-file results/courier-hub-auth.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu"
DEFAULT_PROBE_PATH = "/services/courier-hub-service/external/warehouses/1/dsps/8/shift-blocks"


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def setting(*names: str) -> str:
    for name in names:
        value = clean_text(os.getenv(name))
        if value:
            return value
    return ""


def normalize_authorization(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if text.lower().startswith(("bearer ", "basic ", "token ")):
        return text
    return f"Bearer {text}"


def token_from_authorization(value: str) -> str:
    text = clean_text(value)
    if text.lower().startswith("bearer "):
        return text.split(" ", 1)[1].strip()
    return text


def jwt_payload(value: str) -> dict[str, Any]:
    token = token_from_authorization(value)
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_part = parts[1]
    payload_part += "=" * (-len(payload_part) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_part.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def jwt_expiry_text(value: str) -> str:
    payload = jwt_payload(value)
    exp = payload.get("exp")
    if not exp:
        return "-"
    try:
        return datetime.fromtimestamp(int(exp), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return "-"


def jwt_is_expired(value: str, *, skew_seconds: int = 60) -> bool:
    payload = jwt_payload(value)
    exp = payload.get("exp")
    if not exp:
        return False
    try:
        return int(exp) <= int(datetime.now(timezone.utc).timestamp()) + int(skew_seconds)
    except (TypeError, ValueError):
        return False


def read_existing_cookie(cache_file: str) -> str:
    if not cache_file:
        return ""
    path = Path(cache_file)
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    headers = payload.get("headers")
    if isinstance(headers, dict):
        cookie = clean_text(headers.get("Cookie") or headers.get("cookie"))
        if cookie:
            return cookie
    return clean_text(payload.get("Cookie") or payload.get("cookie"))


def extract_access_token(session_payload: Any) -> str:
    if not isinstance(session_payload, dict):
        return ""

    direct = (
        session_payload.get("accessToken")
        or session_payload.get("access_token")
        or session_payload.get("token")
        or session_payload.get("authorization")
        or session_payload.get("Authorization")
    )
    if direct:
        return normalize_authorization(direct)

    for value in session_payload.values():
        if isinstance(value, dict):
            token = extract_access_token(value)
            if token:
                return token
    return ""


def merge_cookie_value(cookie_header: str, name: str, value: str) -> str:
    existing: dict[str, str] = {}
    for part in clean_text(cookie_header).split(";"):
        if "=" not in part:
            continue
        existing_name, existing_value = part.split("=", 1)
        existing_name = existing_name.strip()
        if existing_name:
            existing[existing_name] = existing_value.strip()

    clean_name = clean_text(name)
    if clean_name:
        existing[clean_name] = clean_text(value)

    return "; ".join(f"{cookie_name}={cookie_value}" for cookie_name, cookie_value in existing.items())


def merge_set_cookie(cookie_header: str, set_cookie_header: str) -> str:
    updated = cookie_header

    if not clean_text(set_cookie_header):
        return updated

    parsed = SimpleCookie()
    try:
        parsed.load(set_cookie_header)
    except Exception:
        return updated

    for name, morsel in parsed.items():
        updated = merge_cookie_value(updated, name, morsel.value)

    return updated


def fetch_session(base_url: str, cookie: str, timeout: int) -> tuple[dict[str, Any], str]:
    response = requests.get(
        f"{base_url.rstrip('/')}/api/auth/session",
        headers={
            "Accept": "application/json",
            "Cookie": cookie,
            "User-Agent": "JITT-Courier-Hub-NoBrowserAuth/1.0",
        },
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(f"session HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("session response is not a JSON object")
    updated_cookie = cookie
    for cookie_item in response.cookies:
        updated_cookie = merge_cookie_value(updated_cookie, cookie_item.name, cookie_item.value)
    updated_cookie = merge_set_cookie(updated_cookie, response.headers.get("Set-Cookie", ""))
    return payload, updated_cookie


def probe_authorization(base_url: str, probe_path: str, authorization: str, cookie: str, timeout: int) -> int:
    probe_url = f"{base_url.rstrip('/')}/{probe_path.lstrip('/')}"
    response = requests.get(
        probe_url,
        headers={
            "Accept": "application/json",
            "Authorization": authorization,
            **({"Cookie": cookie} if cookie else {}),
            "User-Agent": "JITT-Courier-Hub-NoBrowserAuth/1.0",
        },
        timeout=timeout,
    )
    return response.status_code


def write_cache(cache_file: str, authorization: str, cookie: str, session_payload: dict[str, Any]) -> None:
    path = Path(cache_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "headers": {
            "Authorization": authorization,
            **({"Cookie": cookie} if cookie else {}),
        },
        "source": "courier-hub-session-no-browser",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "session_expires": session_payload.get("expires"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=setting("COURIER_HUB_BASE_URL", "KIFLI_COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--cache-file", default=setting("COURIER_HUB_AUTH_CACHE_FILE", "KIFLI_COURIER_HUB_AUTH_CACHE_FILE") or "results/courier-hub-auth.json")
    parser.add_argument("--probe-path", default=setting("COURIER_HUB_AUTH_PROBE_PATH", "KIFLI_COURIER_HUB_AUTH_PROBE_PATH") or DEFAULT_PROBE_PATH)
    parser.add_argument("--probe-date", default=setting("COURIER_HUB_AUTH_PROBE_DATE", "KIFLI_COURIER_HUB_AUTH_PROBE_DATE") or "")
    parser.add_argument("--timeout", type=int, default=int(setting("COURIER_HUB_TIMEOUT", "KIFLI_COURIER_HUB_TIMEOUT") or "30"))
    parser.add_argument("--no-probe", action="store_true")
    args = parser.parse_args()

    cookie = (
        setting("COURIER_HUB_COOKIE", "KIFLI_COURIER_HUB_COOKIE")
        or read_existing_cookie(args.cache_file)
    )
    if not cookie:
        raise RuntimeError("Missing COURIER_HUB_COOKIE, or existing cache file with headers.Cookie")

    session_payload, updated_cookie = fetch_session(args.base_url, cookie, args.timeout)
    if updated_cookie and updated_cookie != cookie:
        cookie = updated_cookie
        session_payload, cookie = fetch_session(args.base_url, cookie, args.timeout)

    authorization = extract_access_token(session_payload)
    if not authorization:
        keys = ", ".join(sorted(str(key) for key in session_payload.keys()))
        raise RuntimeError(f"No accessToken found in session response. Top-level keys: {keys or '-'}")
    if jwt_is_expired(authorization):
        raise RuntimeError(
            "Session returned an expired accessToken; "
            f"session_expires={session_payload.get('expires') or '-'}; "
            f"access_token_expires={jwt_expiry_text(authorization)}"
        )

    probe_status = None
    if not args.no_probe:
        probe_path = args.probe_path
        if args.probe_date and "shift-blocks" in probe_path and "dateFrom=" not in probe_path:
            separator = "&" if "?" in probe_path else "?"
            probe_path = f"{probe_path}{separator}dateFrom={args.probe_date}&dateTo={args.probe_date}"
        probe_status = probe_authorization(args.base_url, probe_path, authorization, cookie, args.timeout)
        if probe_status not in {200, 204}:
            raise RuntimeError(
                f"Probe failed with HTTP {probe_status}; "
                f"session_expires={session_payload.get('expires') or '-'}; "
                f"access_token_expires={jwt_expiry_text(authorization)}"
            )

    write_cache(args.cache_file, authorization, cookie, session_payload)
    print(
        "COURIER_HUB_AUTH_NO_BROWSER_OK "
        f"cache_file={args.cache_file} "
        f"session_expires={session_payload.get('expires') or '-'} "
        f"access_token_expires={jwt_expiry_text(authorization)} "
        f"probe_status={probe_status if probe_status is not None else 'skipped'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
