#!/usr/bin/env python3
"""Book a Courier Hub shift block through the official shift-blocks API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.giriton_auto_booking import log_giriton_booking_result  # noqa: E402
from scripts.sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    courier_hub_auth_configured,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
)
from scripts.sync_courier_hub_master import DEFAULT_BASE_URL, clean_text, int_or_none  # noqa: E402


WAREHOUSE_IDS = {
    "BUD1": 1,
    "BUD2": 2,
    "1": 1,
    "2": 2,
}


def normalize_time(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) < 2:
        return text
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return text
    return f"{hour:02d}:{minute:02d}:00"


def normalize_warehouse_id(value: Any) -> int:
    text = clean_text(value).upper()
    warehouse_id = WAREHOUSE_IDS.get(text)
    if warehouse_id is None:
        raise RuntimeError("Ismeretlen raktar. Hasznalhato ertek: BUD1 vagy BUD2.")
    return warehouse_id


def build_assign_url(base_url: str, warehouse_id: int, dsp_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{int(dsp_id)}/shift-blocks/assign"
    )


def build_shift_blocks_url(base_url: str, warehouse_id: int, dsp_id: int, work_date: str) -> str:
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{int(dsp_id)}/shift-blocks?dateFrom={work_date}&dateTo={work_date}"
    )


def hub_headers() -> dict[str, str]:
    headers = {
        **courier_hub_headers(),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "JITT-Courier-Hub-Api-Booking/1.0",
    }
    return headers


def hub_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))
    response = requests.request(method, url, headers=hub_headers(), timeout=timeout, **kwargs)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.request(method, url, headers=hub_headers(), timeout=timeout, **kwargs)
    return response


def response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:5000]}


def shift_block_matches(item: dict[str, Any], shift_template_id: int, slot_from: str) -> bool:
    item_template_id = int_or_none(item.get("shiftTemplateId") or item.get("shift_template_id"))
    item_slot = normalize_time(item.get("slotFrom") or item.get("slot_from"))
    return item_template_id == shift_template_id and item_slot == slot_from


def dry_run_check(base_url: str, warehouse_id: int, dsp_id: int, work_date: str, shift_template_id: int, slot_from: str) -> dict[str, Any]:
    url = build_shift_blocks_url(base_url, warehouse_id, dsp_id, work_date)
    response = hub_request("GET", url)
    payload = response_payload(response)
    raise_for_response(response, "Courier Hub shift-blocks dry-run")

    items = payload if isinstance(payload, list) else payload.get("content") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    for item in items:
        if isinstance(item, dict) and shift_block_matches(item, shift_template_id, slot_from):
            opened = int_or_none(item.get("opened")) or 0
            assigned = int_or_none(item.get("assigned")) or 0
            return {
                "found": True,
                "blockKey": item.get("blockKey") or item.get("block_key"),
                "status": item.get("status"),
                "assigned": item.get("assigned"),
                "opened": item.get("opened"),
                "free_slots": max(opened - assigned, 0),
            }

    return {
        "found": False,
        "message": "A megadott shiftTemplateId + slotFrom nem talalhato a HUB shift-blocks valaszban.",
    }


def log_result(args: argparse.Namespace, status: str, message: str, response: Any) -> None:
    candidate = {
        "work_date": args.date,
        "courier_id": args.courier_id,
        "courier_name": args.courier_name,
        "email": clean_text(args.email).casefold(),
        "warehouse": clean_text(args.warehouse).upper(),
        "shift_text": clean_text(args.shift_start or args.slot_from),
        "shift_start": normalize_time(args.shift_start or args.slot_from),
        "booking_code": "",
        "serial": clean_text(args.serial),
        "booking_engine": "hub_api",
        "shift_template_id": args.shift_template_id,
        "hub_response": response,
    }
    try:
        log_giriton_booking_result(candidate, status, message)
    except Exception as exc:
        print(f"HUB_API_BOOK_LOG_FAILED {type(exc).__name__}: {exc}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Courier Hub API alapu muszakfoglalas.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--warehouse", required=True)
    parser.add_argument("--dsp-id", type=int, default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"))
    parser.add_argument("--shift-template-id", type=int, required=True)
    parser.add_argument("--slot-from", default="")
    parser.add_argument("--shift-start", default="")
    parser.add_argument("--courier-id", type=int, required=True)
    parser.add_argument("--courier-name", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--serial", default="")
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if not courier_hub_auth_configured():
        raise RuntimeError("Hianyzik a Courier Hub auth. COURIER_HUB_COOKIE vagy auth cache szukseges.")

    warehouse_id = normalize_warehouse_id(args.warehouse)
    slot_from = normalize_time(args.slot_from or args.shift_start)
    if not slot_from:
        raise RuntimeError("Hianyzik a slotFrom / shift-start.")

    request_body = {
        "date": args.date,
        "shiftTemplateId": int(args.shift_template_id),
        "slotFrom": slot_from,
        "courierIds": [int(args.courier_id)],
    }

    print(
        "HUB_API_BOOK_SHIFT "
        f"mode={'LIVE' if args.live else 'DRY_RUN'} "
        f"date={args.date} warehouse={clean_text(args.warehouse).upper()} "
        f"shiftTemplateId={args.shift_template_id} slotFrom={slot_from} "
        f"courierId={args.courier_id}",
        flush=True,
    )

    if args.dry_run or not args.live:
        check = dry_run_check(
            args.base_url,
            warehouse_id,
            args.dsp_id,
            args.date,
            int(args.shift_template_id),
            slot_from,
        )
        status = "DRY_RUN_OK" if check.get("found") else "DRY_RUN_NOT_FOUND"
        print(f"HUB_API_BOOK_DRY_RUN {json.dumps(check, ensure_ascii=False)}", flush=True)
        log_result(args, status, json.dumps(check, ensure_ascii=False), check)
        return 0 if check.get("found") else 3

    url = build_assign_url(args.base_url, warehouse_id, args.dsp_id)
    response = hub_request("POST", url, json=request_body)
    payload = response_payload(response)
    if response.ok:
        log_result(args, "COURIER_ADDED", "HUB API booking accepted.", payload)
        print(
            "HUB_API_BOOK_OK "
            f"status={response.status_code} at={datetime.now(timezone.utc).isoformat()} "
            f"response={json.dumps(payload, ensure_ascii=False)[:2000]}",
            flush=True,
        )
        return 0

    log_result(args, "HUB_API_ERROR", f"HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:1000]}", payload)
    raise_for_response(response, "Courier Hub shift-blocks assign")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
