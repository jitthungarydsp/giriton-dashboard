#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resources.google_auth import get_client, get_service_account_email
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


DEFAULT_SHEET_ID = "1zcLlf4VzkKAVrODbbpS4-bYjvu9vaZuR2tIWUUqwLzU"
DEFAULT_GID = 321601566
SOURCE_BY = "vehicle-sheet-import"
HUNGARIAN_COUNTIES = {
    "bacs_kiskun": "Bács-Kiskun",
    "baranya": "Baranya",
    "bekes": "Békés",
    "borsod_abauj_zemplen": "Borsod-Abaúj-Zemplén",
    "csongrad_csanad": "Csongrád-Csanád",
    "fejer": "Fejér",
    "gyor_moson_sopron": "Győr-Moson-Sopron",
    "hajdu_bihar": "Hajdú-Bihar",
    "heves": "Heves",
    "jasz_nagykun_szolnok": "Jász-Nagykun-Szolnok",
    "komarom_esztergom": "Komárom-Esztergom",
    "nograd": "Nógrád",
    "pest": "Pest",
    "somogy": "Somogy",
    "szabolcs_szatmar_bereg": "Szabolcs-Szatmár-Bereg",
    "tolna": "Tolna",
    "vas": "Vas",
    "veszprem": "Veszprém",
    "zala": "Zala",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def clean_text(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def normalize_plate(value: Any) -> str:
    text = str(value or "").upper()
    match = re.search(r"\b[A-Z]{3,4}[-\s]?\d{3}\b", text)
    if not match:
        return ""
    compact = re.sub(r"[^A-Z0-9]", "", match.group(0))
    return f"{compact[:-3]}-{compact[-3:]}"


def normalize_warehouse(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "BUD1" in text:
        return "BUD1"
    if "BUD2" in text:
        return "BUD2"
    if text in {"1", "WH1"}:
        return "BUD1"
    if text in {"2", "WH2"}:
        return "BUD2"
    return ""


def parse_date(value: Any) -> str | None:
    text = str(value or "").strip().rstrip(".")
    if not text:
        return None
    for pattern in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def normalize_company(value: Any) -> str:
    text = clean_text(value, 160)
    text = re.sub(r"^\d+[_\-\s]*", "", text).strip()
    return text


def ownership_from_company(company: str) -> tuple[str, str]:
    clean_company = normalize_company(company)
    if normalize_text(clean_company) in {"jitt", "0_jitt"}:
        return "own", ""
    if not clean_company:
        return "own", ""
    return "rented", clean_company


def toll_payload(value: Any) -> tuple[str, list[str]]:
    key = normalize_text(value)
    if not key or key in {"nincs", "meg_nincs", "meg_nincsen", "nem"}:
        return "none", []
    if key in {"orszagos", "orszagos_matrica"}:
        return "national", []
    if key in HUNGARIAN_COUNTIES:
        return "county", [HUNGARIAN_COUNTIES[key]]
    if key in {"van", "igen"}:
        return "has", []
    return "has", []


def worksheet_by_gid(sheet_id: str, gid: int):
    try:
        spreadsheet = get_client().open_by_key(sheet_id)
    except PermissionError as exc:
        email = get_service_account_email() or "a beallitott Google service account"
        raise RuntimeError(f"A Google Sheet nincs megosztva ezzel a fiokkal: {email}") from exc
    worksheet = spreadsheet.get_worksheet_by_id(int(gid))
    if not worksheet:
        raise RuntimeError(f"Nincs worksheet ezzel a gid-del: {gid}")
    return worksheet


def read_sheet_cars(sheet_id: str, gid: int) -> list[dict[str, Any]]:
    values = worksheet_by_gid(sheet_id, gid).get_all_values()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_number, row in enumerate(values[2:], start=3):
        padded = row + [""] * max(0, 10 - len(row))
        plate = normalize_plate(padded[2])
        if not plate or plate in seen:
            continue
        seen.add(plate)
        sheet_warehouse = normalize_warehouse(padded[1])
        rows.append(
            {
                "source_row": row_number,
                "company": clean_text(padded[0], 160),
                "warehouse_code": sheet_warehouse,
                "license_plate": plate,
                "car_status": "assignable" if sheet_warehouse in {"BUD1", "BUD2"} else "other",
                "created_by": SOURCE_BY,
                "updated_by": SOURCE_BY,
            }
        )
    return rows


def supabase_config() -> tuple[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    return url.rstrip("/"), key


def supabase_headers(prefer: str = "") -> dict[str, str]:
    _url, key = supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_get(table: str, params: dict[str, str], *, page_size: int = 1000, max_rows: int = 50000) -> list[dict[str, Any]]:
    url, _key = supabase_config()
    rows: list[dict[str, Any]] = []
    while len(rows) < max_rows:
        start = len(rows)
        end = min(start + page_size - 1, max_rows - 1)
        response = requests.get(
            f"{url}/rest/v1/{table}",
            headers={**supabase_headers(), "Range-Unit": "items", "Range": f"{start}-{end}"},
            params=params,
            timeout=60,
        )
        raise_for_supabase_error(response)
        chunk = response.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
    return rows


def existing_config_plates() -> set[str]:
    rows = supabase_get(
        "vw_pwa_vehicle_configurations_latest",
        {"select": "license_plate", "limit": "10000"},
        max_rows=10000,
    )
    return {normalize_plate(row.get("license_plate")) for row in rows if normalize_plate(row.get("license_plate"))}


def db_vehicle_plate_warehouses() -> dict[str, str]:
    result: dict[str, str] = {}
    sources = [
        ("courier_hub_route_statistics", {"select": "vehicle_plate,warehouse_code", "vehicle_plate": "not.is.null", "limit": "50000"}),
        ("courier_hub_live_map_courier_latest", {"select": "vehicle_plate,warehouse_id", "vehicle_plate": "not.is.null", "limit": "10000"}),
        ("dsp_drivers_live_raw", {"select": "license_plate,warehouse_name", "license_plate": "not.is.null", "limit": "10000"}),
        ("dsp_vehicle_assignments", {"select": "license_plate", "license_plate": "not.is.null", "limit": "50000"}),
    ]
    for table, params in sources:
        try:
            rows = supabase_get(table, params)
        except requests.HTTPError as exc:
            print(f"WARN source skipped {table}: {exc}")
            continue
        for row in rows:
            plate = normalize_plate(row.get("vehicle_plate") or row.get("license_plate"))
            if not plate:
                continue
            warehouse = normalize_warehouse(row.get("warehouse_code") or row.get("warehouse_name") or row.get("warehouse_id"))
            if plate not in result or warehouse:
                result[plate] = warehouse or result.get(plate, "")
    return result


def build_payloads(sheet_rows: list[dict[str, Any]], plate_warehouses: dict[str, str], existing_configs: set[str], *, replace_existing: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "sheet_rows": len(sheet_rows),
        "not_in_db": 0,
        "missing_warehouse": 0,
        "already_configured": 0,
        "ready": 0,
    }
    payloads: list[dict[str, Any]] = []
    for row in sheet_rows:
        plate = row["license_plate"]
        if plate not in plate_warehouses:
            stats["not_in_db"] += 1
            continue
        if plate in existing_configs and not replace_existing:
            stats["already_configured"] += 1
            continue
        warehouse = row.get("warehouse_code") or plate_warehouses.get(plate) or ""
        if warehouse not in {"BUD1", "BUD2"}:
            stats["missing_warehouse"] += 1
            continue
        payload = dict(row)
        payload["warehouse_code"] = warehouse
        payload.pop("source_row", None)
        payload.pop("company", None)
        payloads.append(payload)
    stats["ready"] = len(payloads)
    return payloads, stats


def insert_payloads(payloads: list[dict[str, Any]]) -> int:
    if not payloads:
        return 0
    url, _key = supabase_config()
    written = 0
    for start in range(0, len(payloads), 500):
        chunk = payloads[start : start + 500]
        response = requests.post(
            f"{url}/rest/v1/pwa_vehicle_configurations",
            headers=supabase_headers("return=minimal"),
            json=chunk,
            timeout=60,
        )
        raise_for_supabase_error(response)
        written += len(chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Autó konfigurációk egyszeri importja Google Sheetből.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--gid", type=int, default=DEFAULT_GID)
    parser.add_argument("--apply", action="store_true", help="DB-be ír. Enélkül csak dry-run.")
    parser.add_argument("--replace-existing", action="store_true", help="Már konfigurált rendszámokra is új verziósort ír.")
    args = parser.parse_args()

    sheet_rows = read_sheet_cars(args.sheet_id, args.gid)
    plate_warehouses = db_vehicle_plate_warehouses()
    existing_configs = existing_config_plates()
    payloads, stats = build_payloads(
        sheet_rows,
        plate_warehouses,
        existing_configs,
        replace_existing=args.replace_existing,
    )
    print(
        "PWA_VEHICLE_CONFIG_IMPORT "
        f"sheet_rows={stats['sheet_rows']} db_plates={len(plate_warehouses)} "
        f"already_configured={stats['already_configured']} not_in_db={stats['not_in_db']} "
        f"missing_warehouse={stats['missing_warehouse']} ready={stats['ready']} dry_run={not args.apply}"
    )
    for row in payloads[:20]:
        print(
            "PWA_VEHICLE_CONFIG_ROW "
            f"plate={row['license_plate']} warehouse={row['warehouse_code']} "
            f"status={row['car_status']}"
        )
    if not args.apply:
        print("DRY-RUN: éles importhoz add meg: --apply")
        return 0
    written = insert_payloads(payloads)
    print(f"PWA_VEHICLE_CONFIG_DONE inserted={written}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"PWA_VEHICLE_CONFIG_ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
