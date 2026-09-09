#!/usr/bin/env python3
"""Quick Google Routes API probe for Courier Hub distance calculation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_courier_hub_statistics import WAREHOUSE_ADDRESSES, google_routes_api_key  # noqa: E402


def main() -> int:
    api_key = google_routes_api_key()
    if not api_key:
        print("GOOGLE_ROUTES_PROBE=missing_key")
        print("Allitsd be: GOOGLE_ROUTES_API_KEY vagy GOOGLE_MAPS_API_KEY")
        return 1

    body: dict[str, Any] = {
        "origin": {"address": WAREHOUSE_ADDRESSES[1]},
        "destination": {"address": WAREHOUSE_ADDRESSES[2]},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "languageCode": "hu-HU",
        "units": "METRIC",
    }
    response = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
        },
        json=body,
        timeout=20,
    )
    print(f"GOOGLE_ROUTES_STATUS={response.status_code}")
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        error = payload.get("error") if isinstance(payload, dict) else {}
        print(f"GOOGLE_ROUTES_ERROR_STATUS={error.get('status') or '-'}")
        print(f"GOOGLE_ROUTES_ERROR_MESSAGE={error.get('message') or payload}")
        return 1

    route = (payload.get("routes") or [{}])[0] if isinstance(payload, dict) else {}
    print(f"GOOGLE_ROUTES_DISTANCE_METERS={route.get('distanceMeters')}")
    print(f"GOOGLE_ROUTES_DURATION={route.get('duration')}")
    print(f"GOOGLE_ROUTES_STATIC_DURATION={route.get('staticDuration')}")
    print("GOOGLE_ROUTES_PROBE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
