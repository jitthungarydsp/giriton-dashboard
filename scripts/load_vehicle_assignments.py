import argparse
import os
from datetime import datetime

import requests


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-vehicle-assignments"


def get_required_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value.rstrip("/")


def build_vehicle_assignments_url():
    return (
        f"{KIFLI_API_BASE_URL}/"
        f"fetch-vehicle-assignments"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
    )


def fetch_vehicle_assignments():
    url = build_vehicle_assignments_url()
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return url, response.status_code, response.json()


def normalize_time(value):
    text = str(value or "").strip()

    if not text:
        return None

    if len(text) == 5:
        return f"{text}:00"

    return text


def build_rows(response_json):
    rows = []
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    for day in response_json.get("assignmentsForDate", []) or []:
        work_date = day.get("Date")

        for assignment in day.get("Assignments", []) or []:
            driver_name = str(
                assignment.get("Driver") or ""
            ).strip()

            if not work_date or not driver_name:
                continue

            rows.append({
                "source_name": SOURCE_NAME,
                "organization_id": ORGANIZATION_ID,
                "dsp_id": DSP_ID,
                "work_date": work_date,
                "driver_name": driver_name,
                "shift_start": normalize_time(
                    assignment.get("Start")
                ),
                "shift_end": normalize_time(
                    assignment.get("End")
                ),
                "car": assignment.get("Car") or "",
                "license_plate": assignment.get("License Plate") or "",
                "shift_type": assignment.get("Shift Type") or "",
                "vehicle_type_id": (
                    str(assignment.get("Vehicle Type ID"))
                    if assignment.get("Vehicle Type ID") is not None
                    else ""
                ),
                "response_json": assignment,
                "fetched_at": fetched_at,
            })

    return rows


def upsert_rows(rows):
    if not rows:
        return

    supabase_url = get_required_env("SUPABASE_URL")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/dsp_vehicle_assignments"
        "?on_conflict=source_name,work_date,driver_name,shift_start,shift_end"
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
        description="fetch-vehicle-assignments feltoltes Supabase DB-be."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak API-t hiv, DB-be nem ir.",
    )
    args = parser.parse_args()

    _url, status_code, response_json = fetch_vehicle_assignments()
    rows = build_rows(
        response_json
    )

    print(
        f"API status: {status_code}"
    )
    print(
        f"Vehicle assignment sorok: {len(rows)}"
    )

    if rows[:3]:
        for row in rows[:3]:
            print(
                f"MINTA {row['work_date']} {row['driver_name']} {row['license_plate']} {row['shift_start']}-{row['shift_end']}"
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
