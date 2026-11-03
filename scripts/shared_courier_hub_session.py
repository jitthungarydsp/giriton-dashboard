"""Share validated Hub credentials through a service-only Storage bucket."""

import json
import os
from pathlib import Path
import sys

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


def storage_request(method, *, authenticated=False, **kwargs):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    prefix = "authenticated/" if authenticated else ""
    return requests.request(
        method, f"{base}/storage/v1/object/{prefix}hub-session-cache/session.json",
        headers={"apikey": token, "Authorization": f"Bearer {token}", "x-upsert": "true"},
        timeout=5, allow_redirects=False, **kwargs,
    )


def restore(cache_file, probe_path):
    try:
        saved = storage_request("GET", authenticated=True)
        if saved.status_code != 200:
            return False
        headers = session_headers(saved.json())
        if not headers:
            return False
        probe = requests.get(
            "https://courier-hub.kifli.hu" + probe_path,
            headers={"Accept": "application/json", **headers}, timeout=5, allow_redirects=False,
        )
        if probe.status_code != 200 or not isinstance(probe.json(), (dict, list)):
            return False
        Path(cache_file).write_text(json.dumps({"headers": headers}), encoding="utf-8")
        return True
    except (KeyError, OSError, ValueError, requests.RequestException):
        return False


def publish(cache_file):
    try:
        headers = session_headers(json.loads(Path(cache_file).read_text(encoding="utf-8")))
        if headers:
            response = storage_request("POST", json={"headers": headers})
            if response.ok:
                print("Hub session shared.")
                return
    except (KeyError, OSError, ValueError, requests.RequestException):
        pass
    print("Hub session could not be shared.")


if __name__ == "__main__":
    publish(sys.argv[1])
