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


COURIER_TARGET_TABLES = {
    1: "courier_financial_overview_raw_bud1",
    2: "courier_financial_overview_raw_bud2",
}
MONTH_TARGET_TABLES = {
    1: "courier_financial_overview_month_raw_bud1",
    2: "courier_financial_overview_month_raw_bud2",
}


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


def courier_target_table(warehouse_id: int) -> str:
    try:
        normalized_warehouse_id = int(warehouse_id)
    except (TypeError, ValueError):
        normalized_warehouse_id = 0
    if normalized_warehouse_id not in COURIER_TARGET_TABLES:
        raise RuntimeError(f"Ismeretlen warehouse_id: {warehouse_id}")
    return COURIER_TARGET_TABLES[normalized_warehouse_id]


def month_target_table(warehouse_id: int) -> str:
    try:
        normalized_warehouse_id = int(warehouse_id)
    except (TypeError, ValueError):
        normalized_warehouse_id = 0
    if normalized_warehouse_id not in MONTH_TARGET_TABLES:
        raise RuntimeError(f"Ismeretlen warehouse_id: {warehouse_id}")
    return MONTH_TARGET_TABLES[normalized_warehouse_id]


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


def build_courier_targets(
    couriers: list[dict[str, Any]],
    requested_warehouse_id: int | None,
) -> tuple[list[tuple[dict[str, Any], int]], int]:
    targets: list[tuple[dict[str, Any], int]] = []
    warehouse_ids = [requested_warehouse_id] if requested_warehouse_id is not None else [1, 2]

    for courier in couriers:
        for warehouse_id in warehouse_ids:
            targets.append((courier, int(warehouse_id)))

    return targets, 0


def payload_has_routes(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    routes = payload.get("routes")
    if isinstance(routes, list) and routes:
        return True
    try:
        return int(payload.get("totalRoutes") or 0) > 0
    except (TypeError, ValueError):
        return False


def extract_month_couriers(payload: Any) -> list[dict[str, Any]]:
    found: dict[int, dict[str, Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return

        if not isinstance(value, dict):
            return

        raw_courier_id = (
            value.get("courierId")
            or value.get("courier_id")
            or value.get("id")
        )
        try:
            courier_id = int(raw_courier_id)
        except (TypeError, ValueError):
            courier_id = 0

        if courier_id > 0 and any(key in value for key in ("courierId", "courier_id", "courierName", "courier_name")):
            found.setdefault(
                courier_id,
                {
                    "courier_id": courier_id,
                    "courier_name": clean_text(
                        value.get("courierName")
                        or value.get("courier_name")
                        or value.get("driverName")
                        or value.get("name")
                    ),
                    "warehouse_name": "",
                    "active": True,
                },
            )

        for child in value.values():
            walk(child)

    walk(payload)
    return list(found.values())


def merge_courier_targets(
    targets: list[tuple[dict[str, Any], int]],
    couriers: list[dict[str, Any]],
    warehouse_id: int,
) -> int:
    existing = {
        (int(courier.get("courier_id") or 0), int(target_warehouse_id))
        for courier, target_warehouse_id in targets
    }
    added = 0
    for courier in couriers:
        try:
            courier_id = int(courier.get("courier_id") or 0)
        except (TypeError, ValueError):
            continue
        key = (courier_id, int(warehouse_id))
        if courier_id <= 0 or key in existing:
            continue
        targets.append((courier, int(warehouse_id)))
        existing.add(key)
        added += 1
    return added


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
    table_name = courier_target_table(int(payload["warehouse_id"]))
    response = requests.post(
        f"{url}/rest/v1/{table_name}",
        headers=supabase_headers(
            "resolution=merge-duplicates,return=minimal"
        ),
        params={
            "on_conflict": "courier_id,year,month,route_layer,dsp_id,warehouse_id",
        },
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{table_name} upsert")


def upsert_month_overview(payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    table_name = month_target_table(int(payload["warehouse_id"]))
    response = requests.post(
        f"{url}/rest/v1/{table_name}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "year,month,route_layer,dsp_id,warehouse_id"},
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{table_name} upsert")


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


def read_import_diagnostics(session_id: str) -> dict[str, int]:
    if not session_id:
        return {"jit_rows": 0, "summary_rows": 0}
    url = os.environ["SUPABASE_URL"].rstrip("/")
    jit_response = requests.get(
        f"{url}/rest/v1/jit_row",
        headers=supabase_headers("count=exact", schema="settlement"),
        params={"select": "id", "session_id": f"eq.{session_id}", "limit": "1"},
        timeout=60,
    )
    raise_for_response(jit_response, "jit_row import ellenőrzés")
    summary_response = requests.get(
        f"{url}/rest/v1/courier_settlement_summary",
        headers=supabase_headers("count=exact", schema="settlement"),
        params={"select": "courier_id", "session_id": f"eq.{session_id}", "limit": "1"},
        timeout=60,
    )
    raise_for_response(summary_response, "courier_settlement_summary import ellenőrzés")
    return {
        "jit_rows": int(jit_response.headers.get("content-range", "0-0/0").split("/")[-1] or 0),
        "summary_rows": int(summary_response.headers.get("content-range", "0-0/0").split("/")[-1] or 0),
    }


def read_raw_overview_stats(*, year: int, month: int) -> dict[int, dict[str, int]]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    stats: dict[int, dict[str, int]] = {}
    for warehouse_id, table_name in COURIER_TARGET_TABLES.items():
        response = requests.get(
            f"{url}/rest/v1/{table_name}",
            headers=supabase_headers(),
            params={
                "select": "courier_id,warehouse_id,response_json",
                "year": f"eq.{year}",
                "month": f"eq.{month}",
                "status_code": "eq.200",
                "limit": "10000",
            },
            timeout=60,
        )
        raise_for_response(response, f"{table_name} statisztika")
        for row in response.json() or []:
            payload = row.get("response_json") or {}
            routes = payload.get("routes") if isinstance(payload, dict) else []
            stats.setdefault(warehouse_id, {"couriers": 0, "routes": 0})
            stats[warehouse_id]["couriers"] += 1
            stats[warehouse_id]["routes"] += len(routes or [])
    return stats


def delete_empty_raw_rows(*, year: int, month: int, warehouse_id: int) -> int:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    table_name = courier_target_table(warehouse_id)
    response = requests.get(
        f"{url}/rest/v1/{table_name}",
        headers=supabase_headers(),
        params={
            "select": "courier_id,year,month,route_layer,dsp_id,warehouse_id,response_json",
            "year": f"eq.{year}",
            "month": f"eq.{month}",
            "status_code": "eq.200",
            "limit": "10000",
        },
        timeout=60,
    )
    raise_for_response(response, f"{table_name} ures raw sorok keresese")

    deleted = 0
    for row in response.json() or []:
        if payload_has_routes(row.get("response_json")):
            continue
        delete_response = requests.delete(
            f"{url}/rest/v1/{table_name}",
            headers=supabase_headers("return=minimal"),
            params={
                "courier_id": f"eq.{int(row['courier_id'])}",
                "year": f"eq.{int(row['year'])}",
                "month": f"eq.{int(row['month'])}",
                "route_layer": f"eq.{clean_text(row.get('route_layer'))}",
                "dsp_id": f"eq.{int(row['dsp_id'])}",
                "warehouse_id": f"eq.{int(row['warehouse_id'])}",
            },
            timeout=60,
        )
        raise_for_response(delete_response, f"{table_name} ures raw sor torlese")
        deleted += 1
    return deleted


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
    courier_targets, target_skipped = build_courier_targets(couriers, args.warehouse_id)

    success = 0
    skipped = target_skipped
    failed = 0
    auth_failed = False
    discovered_targets = 0
    warehouse_ids = [args.warehouse_id] if args.warehouse_id else [1, 2]

    if args.apply:
        for warehouse_id in warehouse_ids:
            try:
                deleted_empty = delete_empty_raw_rows(
                    year=year,
                    month=month,
                    warehouse_id=warehouse_id,
                )
                if deleted_empty:
                    print(f"Torolt ures raw sorok: WH={warehouse_id} | rows={deleted_empty}")
            except Exception as exc:
                failed += 1
                print(f"Ures raw sorok torlese HIBA: WH={warehouse_id} | {exc}", file=sys.stderr)

    if not args.skip_month_overview:
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
                month_couriers = extract_month_couriers(response_json)
                if args.courier_id:
                    month_couriers = [
                        row for row in month_couriers
                        if int(row.get("courier_id") or 0) == args.courier_id
                    ]
                discovered_targets += merge_courier_targets(
                    courier_targets,
                    month_couriers,
                    warehouse_id,
                )
                total_routes = response_json.get("totalRoutes") if isinstance(response_json, dict) else None
                print(
                    f"MONTH OK: WH={warehouse_id} | routes={total_routes} | "
                    f"couriers={len(month_couriers)}"
                )
            except Exception as exc:
                failed += 1
                auth_failed = "HTTP 401" in str(exc)
                print(f"MONTH HIBA: WH={warehouse_id} | {exc}", file=sys.stderr)
                if auth_failed:
                    print("Megálltam, mert a Courier Hub hitelesítés hiányzik vagy lejárt.", file=sys.stderr)
                    return 1

    print(f"Futárok száma: {len(couriers)}")
    print(f"Célzott futár-raktár párok: {len(courier_targets)}")
    if discovered_targets:
        print(f"Havi API overview-ból hozzáadva: {discovered_targets}")
    if target_skipped:
        print(f"Kihagyva célzás közben: {target_skipped}")
    print(f"Időszak: {year}-{month:02d}")
    print("Mód:", "MENTÉS" if args.apply else "DRY-RUN")

    for courier, warehouse_id in courier_targets:
        courier_id = int(courier["courier_id"])
        courier_name = clean_text(courier.get("courier_name"))

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

            if not payload_has_routes(response_json):
                skipped += 1
                print(
                    f"NINCS ADAT: {courier_id} | {courier_name} | "
                    f"WH={warehouse_id} | routes={total_routes} | "
                    "nem írom felül a raw adatot"
                )
                continue

            db_payload = make_db_payload(
                courier=courier,
                warehouse_id=warehouse_id,
                request_url=request_url,
                status_code=status_code,
                response_json=response_json,
                year=year,
                month=month,
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
            raw_stats = read_raw_overview_stats(year=year, month=month)
            for warehouse_id in sorted(raw_stats):
                stats = raw_stats[warehouse_id]
                print(
                    "RAW DB: "
                    f"WH={warehouse_id} | "
                    f"couriers={stats['couriers']} | "
                    f"routes={stats['routes']}"
                )
        except Exception as exc:
            print(f"RAW DB statisztika HIBA: {exc}", file=sys.stderr)

    if args.apply and success > 0:
        try:
            session_id = import_api_overview_to_jit(
                year=year,
                month=month,
                warehouse_id=args.warehouse_id,
            )
            diagnostics = read_import_diagnostics(session_id)
            print(
                "API import + paraméter számítás OK: "
                f"session_id={session_id} | "
                f"jit_row={diagnostics['jit_rows']} | "
                f"summary={diagnostics['summary_rows']}"
            )
            if args.warehouse_id is not None:
                combined_session_id = import_api_overview_to_jit(
                    year=year,
                    month=month,
                    warehouse_id=None,
                )
                combined_diagnostics = read_import_diagnostics(combined_session_id)
                print(
                    "API osszesitett import + parameter szamitas OK: "
                    f"session_id={combined_session_id} | "
                    f"jit_row={combined_diagnostics['jit_rows']} | "
                    f"summary={combined_diagnostics['summary_rows']}"
                )
        except Exception as exc:
            failed += 1
            print(f"API import + paraméter számítás HIBA: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
