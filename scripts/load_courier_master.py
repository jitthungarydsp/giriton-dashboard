import argparse
import os
from datetime import datetime

import requests


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-drivers"


def get_required_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value.rstrip("/")


def build_fetch_drivers_url():
    return (
        f"{KIFLI_API_BASE_URL}/"
        f"fetch-drivers"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )


def fetch_drivers():
    url = build_fetch_drivers_url()
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return url, response.status_code, response.json()


def clean_text(value):
    return str(value or "").strip()


def build_rows(response_json):
    rows = []
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    for driver in response_json.get("drivers", []) or []:
        courier_id = driver.get("driver_id")
        personal_info = driver.get("personal_info") or {}

        if courier_id in [None, ""]:
            continue

        courier_name = clean_text(
            personal_info.get("name")
        )

        if not courier_name:
            continue

        rows.append({
            "courier_id": int(courier_id),
            "courier_name": courier_name,
            "phone_number": clean_text(
                personal_info.get("contact_number")
            ),
            "email": clean_text(
                personal_info.get("contact_email")
            ),
            "warehouse_name": clean_text(
                personal_info.get("warehouse_name")
            ),
            "source_name": SOURCE_NAME,
            "organization_id": ORGANIZATION_ID,
            "dsp_id": DSP_ID,
            "active": bool(driver.get("active")),
            "response_json": driver,
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
        })

    return rows


def upsert_rows(rows):
    if not rows:
        return

    supabase_url = get_required_env("SUPABASE_URL")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?on_conflict=courier_id"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=60,
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Courier master feltoltes Supabase DB-be."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak API-t hiv, DB-be nem ir.",
    )
    args = parser.parse_args()
    _url, status_code, response_json = fetch_drivers()
    rows = build_rows(
        response_json
    )

    print(
        f"API status: {status_code}"
    )
    print(
        f"Courier master sorok: {len(rows)}"
    )

    for row in rows[:5]:
        print(
            f"MINTA #{row['courier_id']} {row['courier_name']} "
            f"{row['warehouse_name']} {row['phone_number']}"
        )

    if args.dry_run:
        print(
            "DRY RUN, DB iras kihagyva."
        )
        return

    upsert_rows(
        rows
    )
    print(
        f"DB feltoltes: {len(rows)} sor"
    )


if __name__ == "__main__":
    main()
