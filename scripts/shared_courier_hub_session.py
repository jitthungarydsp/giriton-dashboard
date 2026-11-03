"""Share validated Hub credentials through a service-only Storage bucket."""

import json
import os
from pathlib import Path
import sys
from time import sleep
from contextlib import contextmanager
from tempfile import TemporaryDirectory

import requests


def session_headers(payload):
    headers = payload.get("headers") if isinstance(payload, dict) else None
    if not isinstance(headers, dict):
        return {}
    return {
        name: headers[name]
        for name in ("Authorization", "Cookie")
        if isinstance(headers.get(name), str) and headers[name]
    }


@contextmanager
def stored_session_environment(headers):
    with TemporaryDirectory() as directory:
        cache = Path(directory) / "session.json"
        cache.write_text(json.dumps({"headers": headers}), encoding="utf-8")
        env = os.environ.copy()
        for prefix in ("COURIER_HUB", "KIFLI_COURIER_HUB"):
            for suffix in ("AUTH_REFRESH_COMMAND", "USERNAME", "PASSWORD", "AUTHORIZATION", "COOKIE", "API_KEY"):
                env.pop(f"{prefix}_{suffix}", None)
            env[f"{prefix}_AUTH_CACHE_FILE"] = str(cache)
        yield env


def storage_request(method, *, authenticated=False, **kwargs):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    prefix = "authenticated/" if authenticated else ""
    return requests.request(
        method, f"{base}/storage/v1/object/{prefix}hub-session-cache/session.json",
        headers={"apikey": token, "Authorization": f"Bearer {token}", "x-upsert": "true"},
        timeout=5, allow_redirects=False, **kwargs,
    )


def probe_session(headers, probe_path):
    if not headers:
        return "unavailable"
    try:
        probe = requests.get(
            "https://courier-hub.kifli.hu" + probe_path,
            headers={"Accept": "application/json", **headers}, timeout=5, allow_redirects=False,
        )
        if probe.status_code in (401, 403):
            return "unavailable"
        if probe.status_code == 200 and isinstance(probe.json(), (dict, list)):
            return "accepted"
    except (ValueError, requests.RequestException):
        pass
    return "error"


def select_session(load_payload, probe_path):
    payload = load_payload()
    current = session_headers(payload)
    status = probe_session(current, probe_path)
    if status == "accepted":
        return current
    if status == "error":
        return {}

    sleep(60)
    refreshed = load_payload() or payload
    latest = session_headers(refreshed)
    if probe_session(latest, probe_path) == "accepted":
        return latest
    backup = session_headers({"headers": refreshed.get("backupHeaders")}) if isinstance(refreshed, dict) else {}
    return backup if backup and backup != latest and probe_session(backup, probe_path) == "accepted" else {}


def read_pwa_session(client, warehouse_ids, start, end):
    def load_payload():
        try:
            return json.loads(client.storage.from_("hub-session-cache").download("session.json"))
        except Exception:
            return {}
    return select_session(
        load_payload,
        f"/services/courier-hub-service/external/warehouses/{warehouse_ids[0]}/dsps/8"
        f"/shift-blocks?dateFrom={start}&dateTo={end}",
    )


def restore(cache_file, probe_path):
    def load_payload():
        try:
            saved = storage_request("GET", authenticated=True)
            return saved.json() if saved.status_code == 200 else {}
        except (KeyError, OSError, ValueError, requests.RequestException):
            return {}

    try:
        headers = select_session(load_payload, probe_path)
        if not headers:
            return False
        Path(cache_file).write_text(json.dumps({"headers": headers}), encoding="utf-8")
        return True
    except (KeyError, OSError, ValueError, requests.RequestException):
        return False


def publish(cache_file):
    try:
        headers = session_headers(json.loads(Path(cache_file).read_text(encoding="utf-8")))
        if headers:
            saved = storage_request("GET", authenticated=True)
            if saved.status_code not in (200, 404):
                print("Hub session could not be shared.")
                return
            previous = saved.json() if saved.status_code == 200 else {}
            if not isinstance(previous, dict):
                previous = {}
            current = session_headers(previous)
            backup = session_headers({"headers": previous.get("backupHeaders")})
            current_token = current.get("Authorization") or current.get("Cookie")
            new_token = headers.get("Authorization") or headers.get("Cookie")
            if current_token and current_token != new_token:
                backup = current
            payload = {"headers": headers}
            if backup and (backup.get("Authorization") or backup.get("Cookie")) != new_token:
                payload["backupHeaders"] = backup
            response = storage_request("POST", json=payload)
            if response.ok:
                print("Hub session shared.")
                return
    except (KeyError, OSError, ValueError, requests.RequestException):
        pass
    print("Hub session could not be shared.")


if __name__ == "__main__":
    publish(sys.argv[1])
