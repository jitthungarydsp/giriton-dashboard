import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import tomllib
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT = PROJECT_ROOT / "elszamolas-pwa"

COURIER_SELECT_FIELDS = (
    "courier_id,courier_name,email,phone_number,warehouse_name,active,"
    "vehicle_type,license_plate,temperature,last_measurement_timestamp,"
    "current_state,delay_minutes,next_stop,route_assigned_at,fetched_at,updated_at"
)
COURIER_HUB_BASE_URL = "https://courier-hub.kifli.hu"
FINANCIAL_OVERVIEW_SOURCE = "courier-hub-financial-overview-courier-overview"


app = FastAPI(title="JITT Settlement PWA")


def clean_setting(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text.replace("\\n", "\n")


def load_setting(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return clean_setting(value)

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            settings = tomllib.load(file)
    except Exception:
        return ""

    value = settings.get(name) or settings.get("supabase", {}).get(name)
    return clean_setting(value)


def supabase_headers(prefer: str = "") -> dict[str, str]:
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not load_setting("SUPABASE_URL") or not key:
        raise HTTPException(
            status_code=503,
            detail="Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas.",
        )

    headers = {"apikey": key}
    if key and not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer
    return headers


def supabase_get(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url = load_setting("SUPABASE_URL").rstrip("/")
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase olvasasi hiba ({response.status_code}): {response.text[:1000]}",
        )
    return response.json() if response.content else []


def supabase_post(table: str, payload: dict[str, Any] | list[dict[str, Any]], params=None, prefer=""):
    url = load_setting("SUPABASE_URL").rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(prefer=prefer),
        params=params or {},
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase irasi hiba ({response.status_code}): {response.text[:1000]}",
        )
    if not response.content:
        return []
    try:
        return response.json()
    except ValueError:
        return []


def normalize_authorization(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    lower = text.lower()
    if lower.startswith(("bearer ", "basic ", "token ")):
        return text

    return f"Bearer {text}"


def load_json_setting(name: str) -> dict[str, Any]:
    value = load_setting(name)
    if not value:
        return {}

    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"A(z) {name} nem ervenyes JSON.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=503,
            detail=f"A(z) {name} JSON objektum legyen.",
        )

    return parsed


def fetch_courier_hub_session_token(cookie: str) -> str:
    if not cookie:
        return ""

    response = requests.get(
        f"{COURIER_HUB_BASE_URL}/api/auth/session",
        headers={
            "Accept": "application/json",
            "Cookie": cookie,
            "User-Agent": "jitt-settlement-pwa/1.0",
        },
        timeout=30,
    )

    if response.status_code in (401, 403):
        return ""

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Courier Hub session hiba ({response.status_code}): {response.text[:1000]}",
        )

    try:
        payload = response.json()
    except ValueError:
        return ""

    return normalize_authorization(payload.get("accessToken"))


def courier_hub_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "jitt-settlement-pwa/1.0",
    }

    authorization = normalize_authorization(
        load_setting("COURIER_HUB_ACCESS_TOKEN")
        or load_setting("KIFLI_COURIER_HUB_AUTHORIZATION")
        or load_setting("KIFLI_COURIER_HUB_BEARER_TOKEN")
    )

    if not authorization:
        session_payload = load_json_setting("COURIER_HUB_SESSION_JSON")
        authorization = normalize_authorization(session_payload.get("accessToken"))

    cookie = load_setting("KIFLI_COURIER_HUB_COOKIE") or load_setting("COURIER_HUB_SESSION_COOKIE")
    api_key = load_setting("KIFLI_COURIER_HUB_API_KEY")
    extra_headers = load_json_setting("KIFLI_COURIER_HUB_EXTRA_HEADERS_JSON")

    if not authorization and cookie:
        authorization = fetch_courier_hub_session_token(cookie)

    if authorization:
        headers["Authorization"] = authorization

    if cookie:
        headers["Cookie"] = cookie

    if api_key:
        headers["x-api-key"] = api_key

    for key, value in extra_headers.items():
        if value is not None:
            headers[str(key)] = str(value)

    if "Authorization" not in headers and "Cookie" not in headers and "x-api-key" not in headers:
        raise HTTPException(
            status_code=503,
            detail=(
                "Hianyzik a Courier Hub auth. Hasznalhato: COURIER_HUB_ACCESS_TOKEN, "
                "COURIER_HUB_SESSION_JSON, KIFLI_COURIER_HUB_AUTHORIZATION, "
                "KIFLI_COURIER_HUB_BEARER_TOKEN vagy KIFLI_COURIER_HUB_COOKIE. "
                "A token kb. 24 ora utan lejar, ezert ezt secrets/env oldalon kell frissiteni."
            ),
        )

    return headers


def build_financial_overview_url(year: int, month: int, warehouse_id: int, dsp_id: int = 8):
    return (
        f"{COURIER_HUB_BASE_URL}"
        f"/services/courier-hub-service/external/warehouses/{warehouse_id}"
        f"/dsps/{dsp_id}/financial-overview/courier-overview"
        f"?year={year}&month={month}"
    )


def build_financial_courier_detail_url(courier_id: Any, year: int, month: int) -> str:
    period = f"{year}-{month:02d}"
    return f"{COURIER_HUB_BASE_URL}/hu/financial-overview/courier/{courier_id}?period={period}&layer=COMBINED"


def summarize_financial_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("courierRows", "couriers", "items", "data", "rows", "eligibilities", "content", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        else:
            rows = []
    else:
        rows = []

    return {
        "rowCount": len(rows),
        "payloadType": type(payload).__name__,
        "sampleKeys": sorted(list(rows[0].keys()))[:20] if rows and isinstance(rows[0], dict) else [],
    }


def extract_financial_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("courierRows", "couriers", "items", "data", "rows", "eligibilities", "content", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    return []


def enrich_financial_rows(rows: list[dict[str, Any]], year: int, month: int) -> list[dict[str, Any]]:
    enriched = []
    for row in rows:
        item = dict(row)
        courier_id = (
            item.get("courierId")
            or item.get("courier_id")
            or item.get("userId")
            or item.get("user_id")
            or item.get("id")
        )
        if courier_id:
            item["courierDetailUrl"] = build_financial_courier_detail_url(courier_id, year, month)
        enriched.append(item)
    return enriched


def save_financial_overview_raw(
    *,
    year: int,
    month: int,
    warehouse_id: int,
    dsp_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "source_name": FINANCIAL_OVERVIEW_SOURCE,
        "year": year,
        "month": month,
        "warehouse_id": warehouse_id,
        "dsp_id": dsp_id,
        "dsp_code": "JIT",
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "fetched_at": now,
        "updated_at": now,
    }
    supabase_post(
        "settlement_financial_overview_raw",
        row,
        params={"on_conflict": "source_name,year,month,warehouse_id,dsp_id"},
        prefer="resolution=merge-duplicates,return=minimal",
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/settlement/couriers")
def settlement_couriers(
    search: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=5000),
):
    params = {
        "select": COURIER_SELECT_FIELDS,
        "order": "courier_name.asc,courier_id.asc",
        "limit": str(limit),
    }
    rows = supabase_get("settlement_courier_master", params)

    query = search.strip().casefold()
    if query:
        rows = [
            row
            for row in rows
            if query
            in " ".join(
                str(row.get(field) or "")
                for field in (
                    "courier_id",
                    "courier_name",
                    "email",
                    "phone_number",
                    "warehouse_name",
                    "license_plate",
                    "current_state",
                )
            ).casefold()
        ]

    alert_counts = {
        "home": 0,
        "settlement": 0,
        "tig": 0,
        "billing": 0,
        "complaints": 0,
    }

    return {
        "couriers": rows,
        "count": len(rows),
        "alertCounts": alert_counts,
    }


@app.get("/api/settlement/financial-overview")
def settlement_financial_overview(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    warehouse_id: int = Query(default=1, ge=1, le=99),
    dsp_id: int = Query(default=8, ge=1, le=9999),
    save_raw: bool = Query(default=True),
):
    request_url = build_financial_overview_url(year, month, warehouse_id, dsp_id)
    response = requests.get(
        request_url,
        headers=courier_hub_headers(),
        timeout=60,
    )

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="A Courier Hub token lejart vagy nincs jogosultsag. Frissitsd a COURIER_HUB_ACCESS_TOKEN erteket.",
        )

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Courier Hub hiba ({response.status_code}): {response.text[:1000]}",
        )

    payload = response.json() if response.content else {}
    saved = False
    save_warning = ""

    if save_raw:
        try:
            save_financial_overview_raw(
                year=year,
                month=month,
                warehouse_id=warehouse_id,
                dsp_id=dsp_id,
                request_url=request_url,
                status_code=response.status_code,
                response_json=payload,
            )
            saved = True
        except HTTPException as exc:
            detail = str(exc.detail)
            if "PGRST205" in detail or "Could not find the table" in detail:
                save_warning = (
                    "A Courier Hub adat lejott, de a raw tabla meg nincs letrehozva: "
                    "public.settlement_financial_overview_raw. Futtasd a docs/settlement_schema.sql SQL-t."
                )
            else:
                raise

    return {
        "year": year,
        "month": month,
        "warehouseId": warehouse_id,
        "dspId": dsp_id,
        "requestUrl": request_url,
        "statusCode": response.status_code,
        "saved": saved,
        "saveWarning": save_warning,
        "summary": summarize_financial_payload(payload),
        "rows": enrich_financial_rows(extract_financial_rows(payload), year, month),
        "payload": payload,
    }


app.mount("/assets", StaticFiles(directory=APP_ROOT), name="settlement-assets")


@app.get("/{path:path}")
def settlement_pwa(path: str):
    requested = (APP_ROOT / path).resolve()
    app_root = APP_ROOT.resolve()
    if path and requested.is_file() and (requested == app_root or app_root in requested.parents):
        media_types = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
        }
        return FileResponse(requested, media_type=media_types.get(requested.suffix))
    return FileResponse(APP_ROOT / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "elszamolas_api:app",
        host="127.0.0.1",
        port=8530,
        reload=True,
    )
