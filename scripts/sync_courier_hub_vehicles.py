#!/usr/bin/env python3
"""Courier Hub vehicles + vehicle history/documents -> Supabase raw tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
    supabase_headers,
)

DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service"
WAREHOUSE_CODES = {1: "BUD1", 2: "BUD2"}
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def text_or_none(value: Any) -> str | None:
    value = clean(value)
    return value or None


def int_or_none(value: Any) -> int | None:
    value = clean(value)
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    value = clean(value).lower()
    if value in {"true", "1", "yes", "active"}:
        return True
    if value in {"false", "0", "no", "inactive", "removed"}:
        return False
    return None


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def vehicle_id(row: dict[str, Any]) -> int | None:
    return int_or_none(first(row, "id", "vehicleId", "vehicle_id", "externalId", "external_id"))


def items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("content", "items", "data", "vehicles", "results", "history", "documents", "vehicleHistory", "vehicleDocuments"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        # Detail/history/document endpoints may return one object directly.
        # Keeping it as one raw record is safer than silently dropping it.
        return [payload]
    return []


def get_json(url: str, *, attempts: int = 4) -> tuple[int, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=courier_hub_headers(), timeout=60)
            if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
                response = requests.get(url, headers=courier_hub_headers(), timeout=60)
            if response.status_code in RETRY_STATUS_CODES and attempt < attempts:
                time.sleep(min(2**attempt, 10))
                continue
            try:
                payload = response.json()
            except ValueError:
                payload = {"text": response.text[:2000]}
            return response.status_code, payload
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2**attempt, 10))
    raise last_error or RuntimeError("Courier Hub vehicle request failed")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:40]


def record_key(row: dict[str, Any], fallback: str) -> tuple[str, str | None]:
    record_id = first(row, "id", "documentId", "document_id", "historyId", "history_id", "uuid")
    record_id_text = text_or_none(record_id)
    return record_id_text or canonical_hash(row), record_id_text


def request_urls(base_url: str, warehouse_id: int, dsp_id: int, vehicle: int) -> dict[str, str]:
    root = f"{base_url.rstrip('/')}/external/warehouses/{warehouse_id}/dsps/{dsp_id}/vehicles/{vehicle}"
    return {"detail": root, "history": f"{root}/history", "documents": f"{root}/documents"}


def supabase_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str, *, chunk_size: int = 200) -> int:
    if not rows:
        return 0
    url = os.environ["SUPABASE_URL"].rstrip("/")
    written = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        response = requests.post(
            f"{url}/rest/v1/{table}",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": on_conflict},
            json=chunk,
            timeout=60,
        )
        raise_for_response(response, f"{table} upsert")
        written += len(chunk)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--warehouse-ids", default="1,2")
    parser.add_argument("--dsp-id", type=int, default=8)
    parser.add_argument("--page-size", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    warehouses = [int(value.strip()) for value in args.warehouse_ids.split(",") if value.strip()]
    fetched_at = datetime.now(timezone.utc).isoformat()
    vehicle_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []
    counters = {"vehicles": 0, "details": 0, "history": 0, "documents": 0}

    for warehouse_id in warehouses:
        list_url = (
            f"{args.base_url.rstrip('/')}/external/warehouses/{warehouse_id}/dsps/{args.dsp_id}/vehicles"
            f"?page=0&size={args.page_size}&includeRemoved=true"
        )
        list_status, list_payload = get_json(list_url)
        if list_status >= 400:
            raise RuntimeError(f"Courier Hub vehicle list failed: HTTP {list_status} ({list_url})")
        vehicles = items(list_payload)
        for listed in vehicles:
            current_id = vehicle_id(listed)
            if current_id is None:
                continue
            counters["vehicles"] += 1
            urls = request_urls(args.base_url, warehouse_id, args.dsp_id, current_id)
            detail_status, detail_payload = get_json(urls["detail"])
            detail = detail_payload if isinstance(detail_payload, dict) else {"data": detail_payload}
            counters["details"] += 1
            detail_row = detail if isinstance(detail, dict) else {}
            vehicle_rows.append({
                "warehouse_id": warehouse_id,
                "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
                "dsp_id": args.dsp_id,
                "vehicle_id": current_id,
                "registration_number": text_or_none(first(detail_row, "registrationNumber", "licensePlate", "licencePlate", "plate") or first(listed, "registrationNumber", "licensePlate", "licencePlate", "plate")),
                "vehicle_type": text_or_none(first(detail_row, "type", "vehicleType", "vehicle_type") or first(listed, "type", "vehicleType", "vehicle_type")),
                "status": text_or_none(first(detail_row, "status", "state") or first(listed, "status", "state")),
                "removed": bool_or_none(first(detail_row, "removed", "isRemoved") or first(listed, "removed", "isRemoved")),
                "list_request_url": list_url,
                "detail_request_url": urls["detail"],
                "list_status_code": list_status,
                "detail_status_code": detail_status,
                "list_response_json": listed,
                "detail_response_json": detail_payload,
                "fetched_at": fetched_at,
                "updated_at": fetched_at,
            })

            history_status, history_payload = get_json(urls["history"])
            for history in items(history_payload):
                key, record_id = record_key(history, "history")
                history_rows.append({
                    "warehouse_id": warehouse_id,
                    "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
                    "dsp_id": args.dsp_id,
                    "vehicle_id": current_id,
                    "history_key": key,
                    "history_record_id": record_id,
                    "request_url": urls["history"],
                    "status_code": history_status,
                    "response_json": history,
                    "fetched_at": fetched_at,
                    "updated_at": fetched_at,
                })
            counters["history"] += len(items(history_payload))

            documents_status, documents_payload = get_json(urls["documents"])
            for document in items(documents_payload):
                key, document_id = record_key(document, "document")
                document_rows.append({
                    "warehouse_id": warehouse_id,
                    "warehouse_code": WAREHOUSE_CODES.get(warehouse_id, f"WH{warehouse_id}"),
                    "dsp_id": args.dsp_id,
                    "vehicle_id": current_id,
                    "document_key": key,
                    "document_id": document_id,
                    "document_type": text_or_none(first(document, "type", "documentType", "document_type", "name")),
                    "request_url": urls["documents"],
                    "status_code": documents_status,
                    "response_json": document,
                    "fetched_at": fetched_at,
                    "updated_at": fetched_at,
                })
            counters["documents"] += len(items(documents_payload))

    if not args.dry_run:
        supabase_upsert("courier_hub_vehicle_raw", vehicle_rows, "warehouse_id,dsp_id,vehicle_id")
        supabase_upsert("courier_hub_vehicle_history_raw", history_rows, "warehouse_id,dsp_id,vehicle_id,history_key")
        supabase_upsert("courier_hub_vehicle_documents_raw", document_rows, "warehouse_id,dsp_id,vehicle_id,document_key")
    print(json.dumps({"dry_run": args.dry_run, **counters}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
