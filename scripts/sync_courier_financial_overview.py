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
import json
import os
import subprocess
import sys
import time
from pathlib import Path
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
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTH_REFRESH_STATUS_CODES = {401, 403}
_AUTH_REFRESHED_HEADERS: dict[str, str] = {}


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
    headers.update(read_auth_cache_headers())
    headers.update(_AUTH_REFRESHED_HEADERS)
    return headers


def courier_hub_auth_configured() -> bool:
    return bool(
        clean_text(os.getenv("COURIER_HUB_AUTHORIZATION"))
        or clean_text(os.getenv("COURIER_HUB_COOKIE"))
        or clean_text(os.getenv("COURIER_HUB_API_KEY"))
        or clean_text(os.getenv("COURIER_HUB_AUTH_CACHE_FILE"))
        or clean_text(os.getenv("KIFLI_COURIER_HUB_AUTH_CACHE_FILE"))
        or clean_text(os.getenv("COURIER_HUB_AUTH_REFRESH_COMMAND"))
        or (
            clean_text(os.getenv("COURIER_HUB_USERNAME"))
            and clean_text(os.getenv("COURIER_HUB_PASSWORD"))
        )
    )


def normalize_authorization(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if text.lower().startswith(("bearer ", "basic ", "token ")):
        return text
    return f"Bearer {text}"


def parse_auth_command_output(output: str) -> dict[str, Any]:
    text = clean_text(output)
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        try:
            payload = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def read_auth_cache_headers() -> dict[str, str]:
    cache_file = clean_text(
        os.getenv("COURIER_HUB_AUTH_CACHE_FILE")
        or os.getenv("KIFLI_COURIER_HUB_AUTH_CACHE_FILE")
    )
    if not cache_file or not os.path.exists(cache_file):
        return {}
    try:
        with open(cache_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return headers_from_auth_payload(payload if isinstance(payload, dict) else {})


def headers_from_auth_payload(payload: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    nested_headers = payload.get("headers")
    if isinstance(nested_headers, dict):
        headers.update(
            {
                str(key): str(value)
                for key, value in nested_headers.items()
                if value is not None
            }
        )

    authorization = (
        payload.get("Authorization")
        or payload.get("authorization")
        or payload.get("bearer_token")
        or payload.get("token")
        or payload.get("access_token")
    )
    cookie = payload.get("Cookie") or payload.get("cookie")
    api_key = payload.get("x-api-key") or payload.get("api_key")
    if authorization:
        headers["Authorization"] = normalize_authorization(authorization)
    if cookie:
        headers["Cookie"] = str(cookie)
    if api_key:
        headers["x-api-key"] = str(api_key)
    return headers


def auth_refresh_command() -> str:
    command = clean_text(os.getenv("COURIER_HUB_AUTH_REFRESH_COMMAND"))
    if command:
        return command
    if clean_text(os.getenv("COURIER_HUB_USERNAME")) and clean_text(os.getenv("COURIER_HUB_PASSWORD")):
        return f"{sys.executable} scripts/refresh_courier_hub_auth.py"
    return ""


def refresh_courier_hub_headers() -> dict[str, str]:
    command = auth_refresh_command()
    if not command:
        return {}

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        shell=True,
        capture_output=True,
        text=True,
        timeout=int(os.getenv("COURIER_HUB_AUTH_REFRESH_TIMEOUT", "240")),
        check=False,
    )
    if completed.stderr:
        print(completed.stderr.strip())
    if completed.returncode != 0:
        print(f"COURIER_HUB_AUTH_REFRESH_FAILED exit={completed.returncode}")
        return {}

    headers = headers_from_auth_payload(parse_auth_command_output(completed.stdout))
    if headers:
        _AUTH_REFRESHED_HEADERS.update(headers)
        print(
            "COURIER_HUB_AUTH_REFRESH_APPLIED "
            f"authorization={'yes' if headers.get('Authorization') else 'no'} "
            f"cookie={'yes' if headers.get('Cookie') else 'no'}"
        )
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


def build_route_performance_detail_url(
    *,
    courier_id: int,
    route_id: int,
    warehouse_id: int,
) -> str:
    base_url = os.getenv(
        "COURIER_HUB_BASE_URL",
        "https://courier-hub.kifli.hu/services/courier-hub-service",
    ).rstrip("/")
    dsp_id = int(os.getenv("COURIER_HUB_DSP_ID", "8"))
    return (
        f"{base_url}/external/performance/courier/{courier_id}/routes/{route_id}"
        f"?dspId={dsp_id}&warehouseId={warehouse_id}"
    )


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

    response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)

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
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"_non_json_response": response.text[:5000]}
    return request_url, response.status_code, payload


def fetch_route_performance_detail(
    *,
    courier_id: int,
    route_id: int,
    warehouse_id: int,
) -> tuple[str, int, Any]:
    request_url = build_route_performance_detail_url(
        courier_id=courier_id,
        route_id=route_id,
        warehouse_id=warehouse_id,
    )
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))
    response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
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


def upsert_route_performance_detail(payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    table_name = "courier_route_performance_detail_raw"
    response = requests.post(
        f"{url}/rest/v1/{table_name}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={
            "on_conflict": "courier_id,route_id,year,month,dsp_id,warehouse_id",
        },
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{table_name} upsert")


def upsert_flat_table(table_name: str, payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/{table_name}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={
            "on_conflict": "courier_id,route_id,year,month,dsp_id,warehouse_id",
        },
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{table_name} upsert")


def upsert_daily_route_history(payload: dict[str, Any]) -> None:
    upsert_flat_table("courier_daily_route_history", payload)


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


def extract_route_ids(payload: Any) -> list[int]:
    if not isinstance(payload, dict):
        return []
    route_ids: list[int] = []
    seen: set[int] = set()
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return []
    for route in routes:
        if not isinstance(route, dict):
            continue
        raw_route_id = route.get("routeId") or route.get("route_id") or route.get("id")
        try:
            route_id = int(raw_route_id)
        except (TypeError, ValueError):
            continue
        if route_id <= 0 or route_id in seen:
            continue
        seen.add(route_id)
        route_ids.append(route_id)
    return route_ids


def extract_route_refs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    refs: list[dict[str, Any]] = []
    seen: set[int] = set()
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return []
    for route in routes:
        if not isinstance(route, dict):
            continue
        raw_route_id = route.get("routeId") or route.get("route_id") or route.get("id")
        try:
            route_id = int(raw_route_id)
        except (TypeError, ValueError):
            continue
        if route_id <= 0 or route_id in seen:
            continue
        seen.add(route_id)
        refs.append(
            {
                "route_id": route_id,
                "delivery_date": clean_text(route.get("deliveryDate")),
                "order_count": safe_int(route.get("orderCount")),
            }
        )
    return refs


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def stop_delay_minutes(stop: dict[str, Any]) -> int:
    return max(
        safe_int(stop.get("delayMinutes")),
        safe_int(stop.get("deltaMinutes")),
        0,
    )


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def iso_date(value: Any) -> str:
    text = clean_text(value)
    return text[:10] if len(text) >= 10 else ""


def minutes_between(later: Any, earlier: Any) -> int | None:
    later_text = clean_text(later)
    earlier_text = clean_text(earlier)
    if not later_text or not earlier_text:
        return None
    try:
        later_dt = datetime.fromisoformat(later_text.replace("Z", "+00:00"))
        earlier_dt = datetime.fromisoformat(earlier_text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(round((later_dt - earlier_dt).total_seconds() / 60))


def first_log_event_at(payload: Any, event_type: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    events = payload.get("log")
    if not isinstance(events, list):
        return None
    for event in events:
        if isinstance(event, dict) and clean_text(event.get("type")) == event_type:
            return clean_text(event.get("occurredAt")) or None
    return None


def build_delay_row(
    *,
    courier_id: int,
    route_ref: dict[str, Any],
    warehouse_id: int,
    response_json: Any,
    status_code: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    route_id = int(route_ref["route_id"])
    stops = response_json.get("stops") if isinstance(response_json, dict) else []
    stops = stops if isinstance(stops, list) else []
    delay_minutes: list[int] = []
    cleaned_delay_minutes: list[int] = []
    uncleaned_delay_minutes: list[int] = []
    cleaned_reasons: list[str] = []
    slot_miss_projected_count = 0
    rejected_stops_count = 0
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        delay = stop_delay_minutes(stop)
        if delay > 0:
            delay_minutes.append(delay)
            if bool(stop.get("cleaned")):
                cleaned_delay_minutes.append(delay)
                reason = clean_text(stop.get("cleanedReason") or stop.get("cleaned_reason"))
                if reason and reason not in cleaned_reasons:
                    cleaned_reasons.append(reason)
            else:
                uncleaned_delay_minutes.append(delay)
        if bool(stop.get("slotMissProjected")):
            slot_miss_projected_count += 1
        if clean_text(stop.get("rejectedByCourierReason")):
            rejected_stops_count += 1
    delivery_date = (
        clean_text(route_ref.get("delivery_date"))
        or iso_date((stops[0] if stops else {}).get("plannedArrivalAt"))
        or iso_date((response_json.get("shift") if isinstance(response_json, dict) else {}).get("plannedStartAt"))
        or f"{year}-{month:02d}-01"
    )
    return {
        "courier_id": courier_id,
        "route_id": route_id,
        "delivery_date": delivery_date,
        "year": year,
        "month": month,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "route_order_count": safe_int(route_ref.get("order_count")) or len(stops),
        "stops_count": len(stops),
        "delayed_stops_count": len(delay_minutes),
        "total_delay_minutes": sum(delay_minutes),
        "max_delay_minutes": max(delay_minutes) if delay_minutes else 0,
        "cleaned_delay_count": len(cleaned_delay_minutes),
        "uncleaned_delay_count": len(uncleaned_delay_minutes),
        "cleaned_delay_minutes": sum(cleaned_delay_minutes),
        "uncleaned_delay_minutes": sum(uncleaned_delay_minutes),
        "has_delay_cleaning": bool(cleaned_delay_minutes),
        "cleaned_reasons": cleaned_reasons,
        "slot_miss_projected_count": slot_miss_projected_count,
        "rejected_stops_count": rejected_stops_count,
        "response_status_code": status_code,
        "source_raw_updated_at": now,
        "updated_at": now,
    }


def build_compliance_row(
    *,
    courier_id: int,
    route_ref: dict[str, Any],
    warehouse_id: int,
    response_json: Any,
    status_code: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    route_id = int(route_ref["route_id"])
    shift = response_json.get("shift") if isinstance(response_json, dict) else {}
    shift = shift if isinstance(shift, dict) else {}
    planned_start_at = clean_text(shift.get("plannedStartAt")) or None
    actual_start_at = clean_text(shift.get("actualStartAt")) or None
    planned_departure_at = clean_text(shift.get("plannedDepartureAt")) or None
    departed_at = clean_text(shift.get("departedAt")) or first_log_event_at(response_json, "DEPARTED")
    route_assigned_at = first_log_event_at(response_json, "ROUTE_ASSIGNED")
    shift_available_at = first_log_event_at(response_json, "SHIFT_AVAILABLE") or actual_start_at
    last_order_finished_at = first_log_event_at(response_json, "LAST_ORDER_FINISHED")
    warehouse_arrived_at = first_log_event_at(response_json, "WAREHOUSE_ARRIVED")
    event_summary = {
        "route_assigned_at": route_assigned_at,
        "shift_available_at": shift_available_at,
        "departed_at": departed_at,
        "last_order_finished_at": last_order_finished_at,
        "warehouse_arrived_at": warehouse_arrived_at,
    }
    shift_date = (
        clean_text(route_ref.get("delivery_date"))
        or iso_date(planned_start_at)
        or iso_date(actual_start_at)
        or f"{year}-{month:02d}-01"
    )
    return {
        "courier_id": courier_id,
        "route_id": route_id,
        "shift_date": shift_date,
        "year": year,
        "month": month,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "planned_start_at": planned_start_at,
        "actual_start_at": actual_start_at,
        "route_assigned_at": route_assigned_at,
        "shift_available_at": shift_available_at,
        "planned_departure_at": planned_departure_at,
        "departed_at": departed_at,
        "last_order_finished_at": last_order_finished_at,
        "warehouse_arrived_at": warehouse_arrived_at,
        "vehicle_model": clean_text(shift.get("vehicleModel")) or None,
        "vehicle_plate": clean_text(shift.get("vehiclePlate")) or None,
        "mileage_km": safe_float(shift.get("mileageKm")),
        "vehicle_ownership": clean_text(shift.get("vehicleOwnership")) or None,
        "fridge_config": clean_text(shift.get("fridgeConfig")) or None,
        "delay_reference": clean_text(shift.get("delayReference")) or None,
        "returnables_status": clean_text(shift.get("returnablesStatus")) or None,
        "returnables_note": clean_text(shift.get("returnablesNote")) or None,
        "planned_start_delay_minutes": minutes_between(actual_start_at, planned_start_at),
        "departure_delay_minutes": minutes_between(departed_at, planned_departure_at),
        "return_delay_minutes": minutes_between(warehouse_arrived_at, last_order_finished_at),
        "event_summary": event_summary,
        "response_status_code": status_code,
        "source_raw_updated_at": now,
        "updated_at": now,
    }


def build_daily_route_history_row(
    *,
    courier_id: int,
    route_ref: dict[str, Any],
    warehouse_id: int,
    response_json: Any,
    status_code: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    route_id = int(route_ref["route_id"])
    shift = response_json.get("shift") if isinstance(response_json, dict) else {}
    shift = shift if isinstance(shift, dict) else {}
    stops = response_json.get("stops") if isinstance(response_json, dict) else []
    stops = stops if isinstance(stops, list) else []
    planned_start_at = clean_text(shift.get("plannedStartAt")) or None
    actual_start_at = clean_text(shift.get("actualStartAt")) or None
    planned_departure_at = clean_text(shift.get("plannedDepartureAt")) or None
    departed_at = clean_text(shift.get("departedAt")) or first_log_event_at(response_json, "DEPARTED")
    route_assigned_at = first_log_event_at(response_json, "ROUTE_ASSIGNED")
    shift_available_at = first_log_event_at(response_json, "SHIFT_AVAILABLE") or actual_start_at
    last_order_finished_at = first_log_event_at(response_json, "LAST_ORDER_FINISHED")
    warehouse_arrived_at = first_log_event_at(response_json, "WAREHOUSE_ARRIVED")
    work_date = (
        clean_text(route_ref.get("delivery_date"))
        or iso_date(planned_start_at)
        or iso_date(actual_start_at)
        or f"{year}-{month:02d}-01"
    )
    return {
        "courier_id": courier_id,
        "route_id": route_id,
        "work_date": work_date,
        "year": year,
        "month": month,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "order_count": safe_int(route_ref.get("order_count")) or len(stops),
        "stops_count": len(stops),
        "planned_start_at": planned_start_at,
        "actual_start_at": actual_start_at,
        "route_assigned_at": route_assigned_at,
        "shift_available_at": shift_available_at,
        "planned_departure_at": planned_departure_at,
        "departed_at": departed_at,
        "last_order_finished_at": last_order_finished_at,
        "warehouse_arrived_at": warehouse_arrived_at,
        "vehicle_model": clean_text(shift.get("vehicleModel")) or None,
        "vehicle_plate": clean_text(shift.get("vehiclePlate")) or None,
        "mileage_km": safe_float(shift.get("mileageKm")),
        "vehicle_ownership": clean_text(shift.get("vehicleOwnership")) or None,
        "response_status_code": status_code,
        "source_raw_updated_at": now,
        "updated_at": now,
    }


def make_route_performance_detail_payload(
    *,
    courier_id: int,
    route_id: int,
    warehouse_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    stops_count = 0
    if isinstance(response_json, dict) and isinstance(response_json.get("stops"), list):
        stops_count = len(response_json["stops"])
    return {
        "courier_id": courier_id,
        "route_id": route_id,
        "year": year,
        "month": month,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "stops_count": stops_count,
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
    parser.add_argument(
        "--skip-api-import",
        action="store_true",
        help="Skip settlement API import after saving Courier Hub raw data.",
    )
    parser.add_argument(
        "--with-route-details",
        action="store_true",
        help="Also fetch slow route performance details. Default: skip; use sync_courier_route_performance_details.py instead.",
    )
    parser.add_argument("--skip-route-details", action="store_true", help=argparse.SUPPRESS)
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
    route_detail_success = 0
    route_detail_failed = 0
    route_detail_skipped = 0
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

            route_refs = extract_route_refs(response_json)
            if not args.with_route_details:
                route_detail_skipped += len(route_refs)
            else:
                if route_refs:
                    print(
                        f"DETAIL START: {courier_id} | {courier_name} | "
                        f"WH={warehouse_id} | routes={len(route_refs)}",
                        flush=True,
                    )
                else:
                    print(
                        f"DETAIL NINCS ROUTE: {courier_id} | {courier_name} | WH={warehouse_id}",
                        flush=True,
                    )
                for detail_index, route_ref in enumerate(route_refs, start=1):
                    route_id = int(route_ref["route_id"])
                    try:
                        detail_url, detail_status_code, detail_json = fetch_route_performance_detail(
                            courier_id=courier_id,
                            route_id=route_id,
                            warehouse_id=warehouse_id,
                        )
                        detail_payload = make_route_performance_detail_payload(
                            courier_id=courier_id,
                            route_id=route_id,
                            warehouse_id=warehouse_id,
                            request_url=detail_url,
                            status_code=detail_status_code,
                            response_json=detail_json,
                            year=year,
                            month=month,
                        )
                        if args.apply:
                            upsert_route_performance_detail(detail_payload)
                            if detail_status_code == 200:
                                upsert_flat_table(
                                    "courier_financial_overview_delay",
                                    build_delay_row(
                                        courier_id=courier_id,
                                        route_ref=route_ref,
                                        warehouse_id=warehouse_id,
                                        response_json=detail_json,
                                        status_code=detail_status_code,
                                        year=year,
                                        month=month,
                                    ),
                                )
                                upsert_flat_table(
                                    "courier_financial_overview_compliance",
                                    build_compliance_row(
                                        courier_id=courier_id,
                                        route_ref=route_ref,
                                        warehouse_id=warehouse_id,
                                        response_json=detail_json,
                                        status_code=detail_status_code,
                                        year=year,
                                        month=month,
                                    ),
                                )
                        if detail_status_code == 200:
                            route_detail_success += 1
                        else:
                            route_detail_failed += 1
                            print(
                                f"DETAIL HTTP {detail_status_code}: "
                                f"{courier_id} | route={route_id} | WH={warehouse_id}"
                            )
                    except Exception as detail_exc:
                        route_detail_failed += 1
                        print(
                            f"DETAIL HIBA: {courier_id} | route={route_id} | "
                            f"WH={warehouse_id} | {detail_exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if detail_index == len(route_refs) or detail_index % 10 == 0:
                        print(
                            f"DETAIL PROGRESS: {courier_id} | WH={warehouse_id} | "
                            f"{detail_index}/{len(route_refs)}",
                            flush=True,
                        )
                    if args.sleep > 0:
                        time.sleep(args.sleep)

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
    if args.with_route_details:
        print(
            "Route detail: "
            f"sikeres={route_detail_success}, "
            f"hibas={route_detail_failed}, "
            f"kihagyva={route_detail_skipped}"
        )
    else:
        print(
            "Route detail: kihagyva alapbol "
            f"({route_detail_skipped} route). "
            "Reszletekhez: scripts/sync_courier_route_performance_details.py"
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

    if args.apply and success > 0 and not args.skip_api_import:
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
