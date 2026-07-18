import json
import os
import re
from datetime import datetime, timezone

import requests


DEFAULT_ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"


def required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def missing_column_from_response(response):
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return ""

    if payload.get("code") != "PGRST204":
        return ""

    message = str(payload.get("message") or "")
    match = re.search(r"Could not find the '([^']+)' column", message)
    if not match:
        return ""
    return match.group(1)


def raise_for_error(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        if detail:
            raise requests.HTTPError(
                f"{exc}; Supabase response: {detail[:1000]}",
                response=response,
            ) from exc
        raise


def racz_csaba_row():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "courier_id": 2875,
        "courier_name": "Rácz Csaba",
        "phone_number": "0036204246990",
        "email": "csaba.racz66@gmail.com",
        "warehouse_name": "BUD1_JIT",
        "source_name": "manual_racz_csaba",
        "organization_id": DEFAULT_ORGANIZATION_ID,
        "dsp_id": "JIT",
        "active": True,
        "company_name": "RÁCZ CSABA MIKLÓS E.V.",
        "company_address": "MAGYARORSZÁG, 2173 KARTAL SZABADSÁG ÚT 54",
        "tax_number": "59479930-1-33",
        "bank_account_number": "109180010000002770970000",
        "billing_email": "csaba.racz66@gmail.com",
        "response_json": {
            "imported_from": "manual_racz_csaba",
            "birth_date": "1966-11-29",
            "birth_place": "Baia Mare, Nagybánya (Romania)",
            "address": {
                "zip": "2173",
                "city": "Kartal",
                "street": "Szabadság utca",
                "house_number": "54",
            },
            "contract_type": "Futár Vállalkozói Szerződés /Kifli/",
            "vehicle_plates": ["SDW721", "AEJP039"],
            "source_note": "User-provided courier master row, 2026-07-18.",
        },
        "fetched_at": now,
        "updated_at": now,
        "billing_data_source": "manual_racz_csaba:2026-07-18",
        "billing_data_updated_at": now,
    }


def upsert_row(row):
    supabase_url = required_env("SUPABASE_URL").rstrip("/")
    supabase_key = required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = f"{supabase_url}/rest/v1/courier_master"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    params = {"on_conflict": "courier_id"}

    payload = dict(row)
    removed_columns = []
    while True:
        response = requests.post(
            endpoint,
            headers=headers,
            params=params,
            json=[payload],
            timeout=60,
        )
        missing_column = missing_column_from_response(response)
        if missing_column and missing_column in payload:
            removed_columns.append(missing_column)
            payload.pop(missing_column, None)
            continue
        raise_for_error(response)
        return removed_columns


def main():
    row = racz_csaba_row()
    removed_columns = upsert_row(row)
    print("OK: Rácz Csaba felvéve/frissítve a courier_master táblában.")
    print("courier_id=2875")
    print("courier_name=Rácz Csaba")
    if removed_columns:
        print("Kihagyott, DB-ben nem elérhető oszlopok: " + ", ".join(removed_columns))


if __name__ == "__main__":
    main()
