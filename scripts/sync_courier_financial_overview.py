#!/usr/bin/env python3
"""
Courier Hub havi financial overview JSON -> Supabase.

Működés:
- beolvassa az aktív futárokat a public.courier_master táblából;
- a warehouse_name alapján meghatározza a warehouseId értéket;
- futáronként meghívja:
  /external/warehouses/{warehouse_id}/dsps/8/financial-overview/courier-overview
  /external/warehouses/{warehouse_id}/dsps/8/financial-overview/couriers/{courier_id}/routes
- a teljes JSON választ eltárolja/upserteli Supabase-be.

Alapból dry-run. Tényleges mentéshez:
    python sync_courier_financial_overview.py --apply

Szükséges környezeti változók:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Opcionális:
    COURIER_HUB_BASE_URL
    COURIER_HUB_DSP_ID          (alapértelmezett: 8)
    COURIER_HUB_DSP_CODE        (alapértelmezett: JIT)
    COURIER_HUB_TIMEOUT         (alapértelmezett: 60)
    COURIER_HUB_COOKIE
    COURIER_HUB_AUTHORIZATION
    COURIER_HUB_API_KEY
    WAREHOUSE_ID_BUD1           (alapértelmezett: 1)
    WAREHOUSE_ID_BUD2           (alapértelmezett: 2)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timezone
from typing import Any

import requests


COURIER_TARGET_TABLE = "courier_financial_overview_raw"
MONTH_TARGET_TABLE = "courier_financial_overview_month_raw"


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_warehouse(value: Any) -> str:
    text = clean_text(value).upper().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "BUD": "BUD1",
        "BUDAPEST": "BUD1",
        "BUD1JIT": "BUD1",
        "BUD2JIT": "BUD2",
    }
    return aliases.get(text, text)


def warehouse_id_from_name(value: Any) -> int | None:
    name = normalize_warehouse(value)
    mapping = {
        "BUD1": int(os.getenv("WAREHOUSE_ID_BUD1", "1")),
        "BUD2": int(os.getenv("WAREHOUSE_ID_BUD2", "2")),
    }
    return mapping.get(name)


def supabase_headers(prefer: str = "", schema: str = "public") -> dict[str, str]:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def raise_for_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    body = response.text[:3000]
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {body}")


def read_couriers() -> list[dict[str, Any]]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.get(
        f"{url}/rest/v1/courier_master",
        headers=supabase_headers(),
        params={
            "select": "courier_id,courier_name,warehouse_name,active",
            "order": "courier_id.asc",
            "limit": "10000",
        },
        timeout=60,
    )
    raise_for_response(response, "courier_master lekérés")
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("A courier_master válasza nem lista.")
    return rows


def courier_hub_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "JITT-Courier-Financial-Sync/1.0",
    }
    authorization = clean_text(os.getenv("COURIER_HUB_AUTHORIZATION"))
    cookie = clean_text(os.getenv("COURIER_HUB_COOKIE"))
    api_key = clean_text(os.getenv("COURIER_HUB_API_KEY"))
    if authorization:
        headers["Authorization"] = authorization if authorization.lower().startswith("bearer ") else f"Bearer {authorization}"
    if cookie:
        headers["Cookie"] = cookie
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def base_request_url(warehouse_id: int) -> str:
    base_url = os.getenv(
        "COURIER_HUB_BASE_URL",
        "https://courier-hub.kifli.hu/services/courier-hub-service",
    ).rstrip("/")
    dsp_id = int(os.getenv("COURIER_HUB_DSP_ID", "8"))
    return f"{base_url}/external/warehouses/{warehouse_id}/dsps/{dsp_id}/financial-overview"


def build_courier_request_url(
    *,
    courier_id: int,
    warehouse_id: int,
    year: int,
    month: int,
) -> str:
    return (
        f"{base_request_url(warehouse_id)}"
        f"/couriers/{courier_id}/routes"
        f"?year={year}&month={month}"
    )


def build_month_request_url(*, warehouse_id: int, year: int, month: int) -> str:
    return f"{base_request_url(warehouse_id)}/courier-overview?year={year}&month={month}"


def fetch_financial_overview(
    *,
    courier_id: int,
    warehouse_id: int,
    year: int,
    month: int,
) -> tuple[str, int, Any]:
    request_url = build_courier_request_url(
        courier_id=courier_id,
        warehouse_id=warehouse_id,
        year=year,
        month=month,
    )
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))

    response = requests.get(
        request_url,
        headers=courier_hub_headers(),
        timeout=timeout,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {
            "_non_json_response": response.text[:5000],
        }

    return request_url, response.status_code, payload


def fetch_month_overview(*, warehouse_id: int, year: int, month: int) -> tuple[str, int, Any]:
    request_url = build_month_request_url(warehouse_id=warehouse_id, year=year, month=month)
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))
    response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"_non_json_response": response.text[:5000]}
    return request_url, response.status_code, payload


def validate_payload(payload: Any, expected_courier_id: int) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("A Courier Hub válasza nem JSON objektum.")

    actual_id = payload.get("courierId")
    if actual_id is None:
        raise RuntimeError("A Courier Hub válaszából hiányzik a courierId.")

    if str(actual_id) != str(expected_courier_id):
        raise RuntimeError(
            f"Eltérő courierId a válaszban: várt={expected_courier_id}, kapott={actual_id}"
        )


def upsert_financial_overview(payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/{COURIER_TARGET_TABLE}",
        headers=supabase_headers(
            "resolution=merge-duplicates,return=minimal"
        ),
        params={
            "on_conflict": "courier_id,year,month,route_layer,dsp_id,warehouse_id",
        },
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{COURIER_TARGET_TABLE} upsert")


def upsert_month_overview(payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/{MONTH_TARGET_TABLE}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "year,month,route_layer,dsp_id,warehouse_id"},
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{MONTH_TARGET_TABLE} upsert")


def import_api_overview_to_jit(*, year: int, month: int, warehouse_id: int | None = None) -> str:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/rpc/import_api_financial_overview_to_jit",
        headers=supabase_headers("return=representation", schema="settlement"),
        json={
            "p_year": year,
            "p_month": month,
            "p_warehouse_id": warehouse_id,
        },
        timeout=120,
    )
    raise_for_response(response, "import_api_financial_overview_to_jit")
    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and payload:
        return str(payload[0])
    return str(payload or "")


def make_db_payload(
    *,
    courier: dict[str, Any],
    warehouse_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    route_layer = "COMBINED"
    if isinstance(response_json, dict):
        route_layer = clean_text(response_json.get("routeLayer")) or route_layer

    return {
        "courier_id": int(courier["courier_id"]),
        "courier_name": clean_text(courier.get("courier_name")),
        "year": year,
        "month": month,
        "route_layer": route_layer,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "fetched_at": now,
        "updated_at": now,
    }


def make_month_db_payload(
    *,
    warehouse_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    route_layer = "COMBINED"
    if isinstance(response_json, dict):
        route_layer = clean_text(response_json.get("routeLayer")) or route_layer
    return {
        "year": year,
        "month": month,
        "route_layer": route_layer,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "fetched_at": now,
        "updated_at": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--courier-id", type=int)
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--skip-month-overview", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    today = date.today()
    year = args.year or today.year
    month = args.month or today.month

    if month < 1 or month > 12:
        raise RuntimeError("A hónap 1 és 12 közötti szám legyen.")

    couriers = read_couriers()
    if args.courier_id:
        couriers = [
            row for row in couriers
            if int(row.get("courier_id") or 0) == args.courier_id
        ]

    print(f"Futárok száma: {len(couriers)}")
    print(f"Időszak: {year}-{month:02d}")
    print("Mód:", "MENTÉS" if args.apply else "DRY-RUN")

    success = 0
    skipped = 0
    failed = 0
    auth_failed = False

    if not args.skip_month_overview:
        warehouse_ids = [args.warehouse_id] if args.warehouse_id else [1, 2]
        for warehouse_id in warehouse_ids:
            try:
                request_url, status_code, response_json = fetch_month_overview(
                    warehouse_id=warehouse_id,
                    year=year,
                    month=month,
                )
                if status_code != 200:
                    if status_code == 401:
                        raise RuntimeError(
                            "Courier Hub HTTP 401: hiányzó vagy lejárt bejelentkezés. "
                            "Állítsd be a COURIER_HUB_COOKIE vagy COURIER_HUB_AUTHORIZATION környezeti változót."
                        )
                    raise RuntimeError(f"Courier Hub HTTP {status_code}: {str(response_json)[:1000]}")
                db_payload = make_month_db_payload(
                    warehouse_id=warehouse_id,
                    request_url=request_url,
                    status_code=status_code,
                    response_json=response_json,
                    year=year,
                    month=month,
                )
                if args.apply:
                    upsert_month_overview(db_payload)
                total_routes = response_json.get("totalRoutes") if isinstance(response_json, dict) else None
                print(f"MONTH OK: WH={warehouse_id} | routes={total_routes}")
            except Exception as exc:
                failed += 1
                auth_failed = "HTTP 401" in str(exc)
                print(f"MONTH HIBA: WH={warehouse_id} | {exc}", file=sys.stderr)
                if auth_failed:
                    print("Megálltam, mert a Courier Hub hitelesítés hiányzik vagy lejárt.", file=sys.stderr)
                    return 1

    for courier in couriers:
        courier_id = int(courier["courier_id"])
        courier_name = clean_text(courier.get("courier_name"))
        warehouse_name = clean_text(courier.get("warehouse_name"))
        if args.warehouse_id:
            courier_warehouse_ids = [args.warehouse_id]
        else:
            inferred_warehouse_id = warehouse_id_from_name(warehouse_name)
            courier_warehouse_ids = [inferred_warehouse_id] if inferred_warehouse_id else [1, 2]

        for warehouse_id in courier_warehouse_ids:
            if warehouse_id is None:
                skipped += 1
                print(
                    f"KIHAGYVA: {courier_id} | {courier_name} | "
                    f"ismeretlen warehouse_name={warehouse_name!r}"
                )
                continue

            try:
                request_url, status_code, response_json = fetch_financial_overview(
                    courier_id=courier_id,
                    warehouse_id=warehouse_id,
                    year=year,
                    month=month,
                )

                if status_code != 200:
                    raise RuntimeError(
                        f"Courier Hub HTTP {status_code}: {str(response_json)[:1000]}"
                    )

                validate_payload(response_json, courier_id)

                db_payload = make_db_payload(
                    courier=courier,
                    warehouse_id=warehouse_id,
                    request_url=request_url,
                    status_code=status_code,
                    response_json=response_json,
                    year=year,
                    month=month,
                )

                total_cost = (
                    response_json.get("totalCost", {}).get("amount")
                    if isinstance(response_json, dict)
                    else None
                )
                total_routes = (
                    response_json.get("totalRoutes")
                    if isinstance(response_json, dict)
                    else None
                )
                total_orders = (
                    response_json.get("totalOrders")
                    if isinstance(response_json, dict)
                    else None
                )

                if args.apply:
                    upsert_financial_overview(db_payload)

                success += 1
                print(
                    f"OK: {courier_id} | {courier_name} | "
                    f"WH={warehouse_id} | routes={total_routes} | "
                    f"orders={total_orders} | totalCost={total_cost}"
                )

            except Exception as exc:
                failed += 1
                print(
                    f"HIBA: {courier_id} | {courier_name} | WH={warehouse_id} | {exc}",
                    file=sys.stderr,
                )

            if args.sleep > 0:
                time.sleep(args.sleep)

    print(
        f"\nKész. Sikeres: {success}, kihagyva: {skipped}, hibás: {failed}"
    )
    if args.apply and success > 0:
        try:
            session_id = import_api_overview_to_jit(
                year=year,
                month=month,
                warehouse_id=args.warehouse_id,
            )
            print(f"API import + paraméter számítás OK: session_id={session_id}")
        except Exception as exc:
            failed += 1
            print(f"API import + paraméter számítás HIBA: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
