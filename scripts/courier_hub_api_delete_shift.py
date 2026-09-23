#!/usr/bin/env python3
"""Delete a Courier Hub shift assignment through the official shift-blocks API."""

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
from scripts.courier_hub_api_book_shift import (  # noqa: E402
    dry_run_check,
    hub_request,
    normalize_time,
    normalize_warehouse_id,
)
from scripts.sync_courier_financial_overview import (  # noqa: E402
    courier_hub_auth_configured,
    raise_for_response,
)
from scripts.sync_courier_hub_master import DEFAULT_BASE_URL, clean_text  # noqa: E402


def build_delete_url(base_url: str, warehouse_id: int, dsp_id: int, shift_block_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/external/warehouses/{int(warehouse_id)}"
        f"/dsps/{int(dsp_id)}/shift-blocks/{int(shift_block_id)}/assignments"
    )


def response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:5000]}


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
        "booking_engine": "hub_api_delete",
        "shift_template_id": args.shift_template_id,
        "hub_response": response,
    }
    try:
        log_giriton_booking_result(candidate, status, message)
    except Exception as exc:
        print(f"HUB_API_DELETE_LOG_FAILED {type(exc).__name__}: {exc}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Courier Hub API alapu muszaktorles.")
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
    parser.add_argument(
        "--shift-block-id",
        type=int,
        default=int(os.getenv("COURIER_HUB_DELETE_SHIFT_BLOCK_ID") or "0"),
        help="A Courier Hub delete endpoint path shift-block id-ja. A UI hivasban jelenleg 0.",
    )
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
        "HUB_API_DELETE_SHIFT "
        f"mode={'LIVE' if args.live else 'DRY_RUN'} "
        f"date={args.date} warehouse={clean_text(args.warehouse).upper()} "
        f"shiftTemplateId={args.shift_template_id} slotFrom={slot_from} "
        f"courierId={args.courier_id} shiftBlockId={args.shift_block_id}",
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
        status = "DELETE_DRY_RUN_OK" if check.get("found") else "DELETE_DRY_RUN_NOT_FOUND"
        print(f"HUB_API_DELETE_DRY_RUN {json.dumps(check, ensure_ascii=False)}", flush=True)
        log_result(args, status, json.dumps(check, ensure_ascii=False), check)
        return 0 if check.get("found") else 3

    url = build_delete_url(args.base_url, warehouse_id, args.dsp_id, args.shift_block_id)
    response = hub_request("DELETE", url, json=request_body)
    payload = response_payload(response)
    if response.ok:
        log_result(args, "COURIER_DELETED", "HUB API delete accepted.", payload)
        print(
            "HUB_API_DELETE_OK "
            f"status={response.status_code} at={datetime.now(timezone.utc).isoformat()} "
            f"response={json.dumps(payload, ensure_ascii=False)[:2000]}",
            flush=True,
        )
        return 0

    log_result(args, "HUB_API_DELETE_ERROR", f"HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:1000]}", payload)
    raise_for_response(response, "Courier Hub shift-blocks assignment delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
