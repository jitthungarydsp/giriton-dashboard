import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import tomllib

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-drivers"


def get_local_secret(name):
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"

    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            secrets = tomllib.load(file)
    except Exception:
        return ""

    value = secrets.get(name, "")
    if value:
        return str(value)

    supabase_section = secrets.get("supabase", {})
    if isinstance(supabase_section, dict):
        value = supabase_section.get(name, "")
        if value:
            return str(value)

    return ""


def get_required_setting(name):
    value = os.getenv(name) or get_local_secret(name)
    value = str(value or "").strip()

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} beallitas. Add meg kornyezeti valtozokent "
            "vagy a .streamlit/secrets.toml fajlban."
        )

    return value.rstrip("/")


def get_optional_setting(name):
    value = os.getenv(name) or get_local_secret(name)
    return str(value or "").strip().rstrip("/")


def supabase_headers(prefer=""):
    key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if key and not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def raise_for_supabase_error(response, table_name):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        if detail:
            raise requests.HTTPError(
                f"{exc}; tabla={table_name}; Supabase valasz: {detail[:2000]}",
                response=response,
            ) from exc
        raise


def build_fetch_drivers_url():
    return (
        f"{KIFLI_API_BASE_URL}/fetch-drivers"
        f"?id={DSP_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )


def fetch_drivers():
    url = build_fetch_drivers_url()
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return url, response.status_code, response.json()


def read_existing_courier_master():
    supabase_url = get_optional_setting("SUPABASE_URL")
    supabase_key = get_optional_setting("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        return []

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        "?select=courier_id,courier_name,email,phone_number,warehouse_name,"
        "active,response_json,fetched_at,updated_at"
        "&order=courier_name.asc,courier_id.asc"
        "&limit=5000"
    )
    headers = {
        "apikey": supabase_key,
    }
    if not supabase_key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {supabase_key}"

    response = requests.get(endpoint, headers=headers, timeout=30)
    if not response.ok:
        print(
            "FIGYELEM: courier_master olvasas kihagyva, "
            f"status={response.status_code}"
        )
        return []

    return response.json() if response.content else []


def clean_text(value):
    text = str(value or "").strip()
    if text.casefold() in {"none", "null", "nan"}:
        return ""
    return " ".join(text.split())


def to_int(value):
    if value in [None, ""]:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value):
    if value in [None, ""]:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def nested_get(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def first_value(*values):
    for value in values:
        if value not in [None, ""]:
            return value
    return None


def get_route_assigned_at(driver):
    return first_value(
        nested_get(driver, "route", "route_assigned_at"),
        nested_get(driver, "route", "routeAssignedAt"),
        nested_get(driver, "route", "assignedAt"),
        nested_get(driver, "status", "route_assigned_at"),
        nested_get(driver, "status", "routeAssignedAt"),
        nested_get(driver, "status", "assignedAt"),
        driver.get("route_assigned_at"),
        driver.get("routeAssignedAt"),
    )


def merge_base_records(records, existing_rows):
    for row in existing_rows:
        courier_id = to_int(row.get("courier_id"))
        courier_name = clean_text(row.get("courier_name"))

        if courier_id is None or not courier_name:
            continue

        records[courier_id] = {
            "courier_id": courier_id,
            "courier_name": courier_name,
            "email": clean_text(row.get("email")),
            "phone_number": clean_text(row.get("phone_number")),
            "warehouse_name": clean_text(row.get("warehouse_name")),
            "active": row.get("active"),
            "vehicle_type": "",
            "license_plate": "",
            "temperature": None,
            "last_measurement_timestamp": None,
            "current_state": "",
            "delay_minutes": None,
            "next_stop": "",
            "route_assigned_at": None,
            "source_name": "courier_master+fetch-drivers",
            "organization_id": ORGANIZATION_ID,
            "dsp_id": DSP_ID,
            "response_json": row.get("response_json") or {},
        }


def merge_live_records(records, payload):
    for driver in payload.get("drivers", []) or []:
        courier_id = to_int(driver.get("driver_id"))
        if courier_id is None:
            continue

        personal_info = driver.get("personal_info") or {}
        vehicle = driver.get("vehicle") or {}
        status = driver.get("status") or {}

        courier_name = clean_text(personal_info.get("name"))
        if not courier_name:
            continue

        current = records.setdefault(
            courier_id,
            {
                "courier_id": courier_id,
                "courier_name": courier_name,
                "email": "",
                "phone_number": "",
                "warehouse_name": "",
                "active": None,
                "vehicle_type": "",
                "license_plate": "",
                "temperature": None,
                "last_measurement_timestamp": None,
                "current_state": "",
                "delay_minutes": None,
                "next_stop": "",
                "route_assigned_at": None,
                "source_name": SOURCE_NAME,
                "organization_id": ORGANIZATION_ID,
                "dsp_id": DSP_ID,
                "response_json": {},
            },
        )

        for key, value in {
            "courier_name": courier_name,
            "email": clean_text(personal_info.get("contact_email")),
            "phone_number": clean_text(personal_info.get("contact_number")),
            "warehouse_name": clean_text(personal_info.get("warehouse_name")),
            "vehicle_type": clean_text(vehicle.get("type")),
            "license_plate": clean_text(vehicle.get("license_plate")),
            "current_state": clean_text(status.get("current_state")),
            "next_stop": clean_text(status.get("next_stop")),
        }.items():
            if value:
                current[key] = value

        current["active"] = driver.get("active")
        current["temperature"] = to_float(vehicle.get("temperature"))
        current["last_measurement_timestamp"] = parse_timestamp(
            vehicle.get("last_measurement_timestamp")
        )
        current["delay_minutes"] = to_int(status.get("delay_minutes"))
        current["route_assigned_at"] = parse_timestamp(get_route_assigned_at(driver))
        current["source_name"] = "courier_master+fetch-drivers"
        current["response_json"] = driver


def build_rows(payload, existing_rows=None):
    fetched_at = datetime.now(timezone.utc).isoformat()
    records = {}
    merge_base_records(records, existing_rows or [])
    merge_live_records(records, payload)

    rows = []
    for record in records.values():
        row = dict(record)
        row["fetched_at"] = fetched_at
        row["updated_at"] = fetched_at
        rows.append(row)

    return sorted(rows, key=lambda row: (row["courier_name"], row["courier_id"]))


def upsert_couriers(rows):
    if not rows:
        return 0

    supabase_url = get_required_setting("SUPABASE_URL")
    endpoint = (
        f"{supabase_url}/rest/v1/settlement_courier_master"
        "?on_conflict=courier_id"
    )
    response = requests.post(
        endpoint,
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        json=rows,
        timeout=60,
    )
    raise_for_supabase_error(response, "settlement_courier_master")
    return len(rows)


def insert_api_log(request_url, status_code, row_count, response_json):
    supabase_url = get_required_setting("SUPABASE_URL")
    row = {
        "source_name": SOURCE_NAME,
        "request_url": request_url,
        "status_code": status_code,
        "row_count": row_count,
        "response_json": response_json,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    response = requests.post(
        f"{supabase_url}/rest/v1/settlement_api_calls",
        headers=supabase_headers("return=minimal"),
        json=row,
        timeout=60,
    )
    raise_for_supabase_error(response, "settlement_api_calls")


def sync_settlement_courier_master(dry_run=False):
    request_url, status_code, payload = fetch_drivers()
    existing_rows = read_existing_courier_master()
    rows = build_rows(payload, existing_rows)

    result = {
        "status_code": status_code,
        "row_count": len(rows),
        "base_rows": len(existing_rows),
        "dry_run": dry_run,
    }

    if not dry_run:
        result["upserted"] = upsert_couriers(rows)
        insert_api_log(request_url, status_code, len(rows), payload)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Settlement futar torzs frissitese fetch-drivers API-bol."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = sync_settlement_courier_master(dry_run=args.dry_run)
    print(
        "Settlement courier master kesz: "
        f"status={result['status_code']} rows={result['row_count']} "
        f"base_rows={result['base_rows']} dry_run={result['dry_run']}"
    )


if __name__ == "__main__":
    main()
