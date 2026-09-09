#!/usr/bin/env python3
"""Sync Courier Hub performance shift data by date range."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sync_courier_financial_overview import (  # noqa: E402
    AUTH_REFRESH_STATUS_CODES,
    COURIER_TARGET_TABLES,
    clean_text,
    courier_hub_auth_configured,
    courier_hub_headers,
    raise_for_response,
    refresh_courier_hub_headers,
    safe_int,
    supabase_headers,
)


COURIER_HUB_BASE_URL = os.getenv(
    "COURIER_HUB_BASE_URL",
    "https://courier-hub.kifli.hu/services/courier-hub-service",
).rstrip("/")
COURIER_HUB_DSP_ID = int(os.getenv("COURIER_HUB_DSP_ID") or "8")


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def month_jobs(year: int, month: int, months_back: int) -> list[tuple[date, date]]:
    current = date(year, month, 1)
    jobs = []
    for offset in range(max(0, months_back), -1, -1):
        month_start = add_months(current, -offset)
        jobs.append(month_bounds(month_start.year, month_start.month))
    return jobs


def read_courier_refs(year: int, month: int, courier_id: int | None, warehouse_id: int | None) -> list[dict[str, Any]]:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    target_tables = (
        {warehouse_id: COURIER_TARGET_TABLES[int(warehouse_id)]}
        if warehouse_id
        else COURIER_TARGET_TABLES
    )
    refs: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for wh_id, table_name in target_tables.items():
        params = {
            "select": "courier_id,warehouse_id,response_json,status_code",
            "year": f"eq.{year}",
            "month": f"eq.{month}",
            "status_code": "eq.200",
            "limit": "5000",
        }
        if courier_id:
            params["courier_id"] = f"eq.{courier_id}"
        response = requests.get(
            f"{supabase_url}/rest/v1/{table_name}",
            headers=supabase_headers(),
            params=params,
            timeout=60,
        )
        raise_for_response(response, f"{table_name} courier refs")
        for row in response.json() or []:
            row_courier_id = safe_int(row.get("courier_id"))
            if row_courier_id <= 0:
                continue
            key = (int(wh_id), row_courier_id)
            if key in seen:
                continue
            seen.add(key)
            payload = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
            refs.append({
                "courier_id": row_courier_id,
                "warehouse_id": int(wh_id),
                "courier_name": clean_text(payload.get("courierName") or payload.get("name")),
            })
    return sorted(refs, key=lambda item: (item["warehouse_id"], item["courier_id"]))


def build_request_url(courier_id: int, warehouse_id: int, date_from: date, date_to: date) -> str:
    return (
        f"{COURIER_HUB_BASE_URL}/external/performance/courier/{int(courier_id)}/shifts"
        f"?dateFrom={date_from.isoformat()}&dateTo={date_to.isoformat()}"
        f"&dspId={COURIER_HUB_DSP_ID}&warehouseId={int(warehouse_id)}"
    )


def fetch_performance_shifts(courier_id: int, warehouse_id: int, date_from: date, date_to: date) -> tuple[str, int, Any]:
    request_url = build_request_url(courier_id, warehouse_id, date_from, date_to)
    timeout = int(os.getenv("COURIER_HUB_TIMEOUT", "60"))
    response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    if response.status_code in AUTH_REFRESH_STATUS_CODES and refresh_courier_hub_headers():
        response = requests.get(request_url, headers=courier_hub_headers(), timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"_non_json_response": response.text[:5000]}
    return request_url, response.status_code, payload


def shift_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("shifts"), list):
        return [item for item in payload["shifts"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def shift_time(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if "T" in text and len(text) >= 16:
        return text[11:16]
    if len(text) >= 5:
        return text[:5]
    return text


def timestamp_or_none(value: Any) -> str | None:
    text = clean_text(value)
    return text or None


def make_shift_key(courier_id: int, item: dict[str, Any], index: int) -> str:
    return ":".join([
        str(courier_id),
        clean_text(item.get("date")),
        clean_text(item.get("plannedStart")),
        clean_text(item.get("plannedEnd")),
        str(index),
    ])


def make_raw_row(
    *,
    courier_ref: dict[str, Any],
    request_url: str,
    status_code: int,
    response_json: Any,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "courier_id": int(courier_ref["courier_id"]),
        "year": date_from.year,
        "month": date_from.month,
        "dsp_id": COURIER_HUB_DSP_ID,
        "warehouse_id": int(courier_ref["warehouse_id"]),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "shift_count": len(shift_items(response_json)),
        "total_shifts": safe_int(response_json.get("totalShifts") if isinstance(response_json, dict) else 0),
        "no_show_shifts": safe_int(response_json.get("noShowShifts") if isinstance(response_json, dict) else 0),
        "late_login_shifts": safe_int(response_json.get("lateLoginShifts") if isinstance(response_json, dict) else 0),
        "fetched_at": now,
        "updated_at": now,
    }


def make_shift_rows(
    *,
    courier_ref: dict[str, Any],
    request_url: str,
    status_code: int,
    response_json: Any,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    if status_code != 200:
        return []
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    courier_id = int(courier_ref["courier_id"])
    warehouse_id = int(courier_ref["warehouse_id"])
    for index, item in enumerate(shift_items(response_json), start=1):
        work_date = parse_date(item.get("date"))
        if not work_date or work_date < date_from or work_date > date_to:
            continue
        rows.append({
            "courier_id": courier_id,
            "year": work_date.year,
            "month": work_date.month,
            "dsp_id": COURIER_HUB_DSP_ID,
            "warehouse_id": warehouse_id,
            "work_date": work_date.isoformat(),
            "shift_key": make_shift_key(courier_id, item, index),
            "shift_id": None,
            "shift_name": shift_time(item.get("plannedStart")),
            "shift_start": shift_time(item.get("plannedStart")),
            "shift_end": shift_time(item.get("plannedEnd")),
            "planned_start_at": timestamp_or_none(f"{work_date.isoformat()}T{shift_time(item.get('plannedStart'))}:00" if shift_time(item.get("plannedStart")) else ""),
            "planned_end_at": timestamp_or_none(f"{work_date.isoformat()}T{shift_time(item.get('plannedEnd'))}:00" if shift_time(item.get("plannedEnd")) else ""),
            "actual_start_at": timestamp_or_none(item.get("actualStart")),
            "evaluation": clean_text(item.get("evaluation")) or None,
            "status": clean_text(item.get("evaluation")) or None,
            "raw_shift": item,
            "request_url": request_url,
            "response_status_code": status_code,
            "source_raw_updated_at": now,
            "updated_at": now,
        })
    return rows


def upsert(table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str) -> int:
    payload = rows if isinstance(rows, list) else [rows]
    if not payload:
        return 0
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": on_conflict},
        json=payload,
        timeout=60,
    )
    raise_for_response(response, f"{table} upsert")
    return len(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--courier-id", type=int)
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--months-back", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    date_from = parse_date(args.date_from)
    date_to = parse_date(args.date_to)
    explicit_range = bool(date_from and date_to)
    if not explicit_range:
        if not args.year or not args.month:
            raise RuntimeError("--year és --month vagy --date-from és --date-to kötelező.")
        date_from, date_to = month_bounds(args.year, args.month)
    if date_from > date_to:
        raise RuntimeError("A --date-from nem lehet későbbi, mint a --date-to.")
    if not courier_hub_auth_configured():
        raise RuntimeError("Courier Hub auth nincs beállítva.")

    jobs = [(date_from, date_to)] if explicit_range else month_jobs(args.year, args.month, args.months_back)
    refs_by_period = [
        (
            job_start,
            job_end,
            read_courier_refs(job_start.year, job_start.month, args.courier_id, args.warehouse_id),
        )
        for job_start, job_end in jobs
    ]
    ref_total = sum(len(refs) for _, _, refs in refs_by_period)
    print(
        f"Performance shifts target: couriers={ref_total} periods={len(refs_by_period)} "
        f"period={date_from.isoformat()}..{date_to.isoformat()} "
        f"mode={'APPLY' if args.apply else 'DRY-RUN'}",
        flush=True,
    )

    success = 0
    failed = 0
    raw_written = 0
    shift_written = 0
    processed = 0
    for period_from, period_to, refs in refs_by_period:
        for ref in refs:
            processed += 1
            try:
                request_url, status_code, payload = fetch_performance_shifts(
                    int(ref["courier_id"]),
                    int(ref["warehouse_id"]),
                    period_from,
                    period_to,
                )
                raw_row = make_raw_row(
                    courier_ref=ref,
                    request_url=request_url,
                    status_code=status_code,
                    response_json=payload,
                    date_from=period_from,
                    date_to=period_to,
                )
                shift_rows = make_shift_rows(
                    courier_ref=ref,
                    request_url=request_url,
                    status_code=status_code,
                    response_json=payload,
                    date_from=period_from,
                    date_to=period_to,
                )
                if args.apply:
                    raw_written += upsert(
                        "courier_shift_overview_raw",
                        raw_row,
                        "courier_id,year,month,dsp_id,warehouse_id",
                    )
                    shift_written += upsert(
                        "courier_shift_overview",
                        shift_rows,
                        "courier_id,work_date,shift_key,dsp_id,warehouse_id",
                    )
                if status_code == 200:
                    success += 1
                else:
                    failed += 1
                    print(f"HTTP {status_code}: courier={ref['courier_id']} WH={ref['warehouse_id']}")
            except Exception as exc:
                failed += 1
                print(f"ERROR courier={ref['courier_id']} WH={ref['warehouse_id']}: {exc}", flush=True)
            if processed == ref_total or processed % 20 == 0:
                print(f"PROGRESS {processed}/{ref_total} raw={raw_written} shifts={shift_written}", flush=True)
            if args.sleep > 0:
                time.sleep(args.sleep)

    print(
        f"Done. success={success} failed={failed} raw_written={raw_written} shift_rows={shift_written}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
