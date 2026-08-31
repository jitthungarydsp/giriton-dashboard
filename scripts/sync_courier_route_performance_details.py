#!/usr/bin/env python3
"""Courier Hub route performance detail sync.

This script intentionally runs separately from sync_courier_financial_overview.py.
Use the financial overview sync for the two main monthly API calls, then use this
script when route-level delay/compliance details are needed.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from sync_courier_financial_overview import (
    AUTH_REFRESH_STATUS_CODES,
    COURIER_TARGET_TABLES,
    base_request_url,
    build_compliance_row,
    build_daily_route_history_row,
    build_delay_row,
    clean_text,
    courier_hub_auth_configured,
    courier_hub_headers,
    fetch_route_performance_detail,
    make_route_performance_detail_payload,
    raise_for_response,
    refresh_courier_hub_headers,
    safe_int,
    supabase_headers,
    upsert_flat_table,
    upsert_daily_route_history,
    upsert_route_performance_detail,
)


def month_day(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if len(text) == 2 and text.isdigit():
        return text
    try:
        return f"{int(text):02d}"
    except ValueError:
        return text[-2:] if len(text) >= 10 else text


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def month_starts_between(start_date: date, end_date: date) -> list[date]:
    months: list[date] = []
    current = start_date.replace(day=1)
    final = end_date.replace(day=1)
    while current <= final:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def read_latest_synced_work_date(
    *,
    courier_id: int | None,
    warehouse_id: int | None,
) -> date | None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    params = {
        "select": "work_date",
        "order": "work_date.desc",
        "limit": "1",
    }
    if courier_id:
        params["courier_id"] = f"eq.{courier_id}"
    if warehouse_id:
        params["warehouse_id"] = f"eq.{warehouse_id}"

    response = requests.get(
        f"{url}/rest/v1/courier_daily_route_history",
        headers=supabase_headers(),
        params=params,
        timeout=60,
    )
    raise_for_response(response, "courier_daily_route_history latest work_date")
    rows = response.json() or []
    if not rows:
        return None
    return parse_date(rows[0].get("work_date"))


def read_route_refs(
    *,
    courier_id: int | None,
    year: int,
    month: int,
    warehouse_id: int | None,
    day: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    target_tables = (
        {warehouse_id: COURIER_TARGET_TABLES[int(warehouse_id)]}
        if warehouse_id
        else COURIER_TARGET_TABLES
    )
    refs: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    wanted_day = month_day(day)

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
            f"{url}/rest/v1/{table_name}",
            headers=supabase_headers(),
            params=params,
            timeout=60,
        )
        raise_for_response(response, f"{table_name} route refs")

        for row in response.json() or []:
            row_courier_id = safe_int(row.get("courier_id"))
            if row_courier_id <= 0:
                continue

            payload = row.get("response_json") or {}
            routes = payload.get("routes") if isinstance(payload, dict) else []
            if not isinstance(routes, list):
                continue

            for route in routes:
                if not isinstance(route, dict):
                    continue
                route_id = safe_int(route.get("routeId") or route.get("route_id") or route.get("id"))
                if route_id <= 0:
                    continue

                delivery_date = clean_text(route.get("deliveryDate"))
                if wanted_day and delivery_date[8:10] != wanted_day:
                    continue
                route_date = parse_date(delivery_date)
                if start_date and (not route_date or route_date < start_date):
                    continue
                if end_date and (not route_date or route_date > end_date):
                    continue

                key = (int(wh_id), row_courier_id, route_id)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(
                    {
                        "courier_id": row_courier_id,
                        "route_id": route_id,
                        "delivery_date": delivery_date,
                        "order_count": safe_int(route.get("orderCount")),
                        "warehouse_id": int(wh_id),
                        "year": year,
                        "month": month,
                    }
                )

    return sorted(
        refs,
        key=lambda item: (
            item.get("delivery_date") or "",
            item["warehouse_id"],
            item["courier_id"],
            item["route_id"],
        ),
    )


def read_courier_refs(
    *,
    courier_id: int | None,
    year: int,
    month: int,
    warehouse_id: int | None,
) -> list[dict[str, Any]]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
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
            f"{url}/rest/v1/{table_name}",
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
            payload = row.get("response_json") or {}
            refs.append(
                {
                    "courier_id": row_courier_id,
                    "warehouse_id": int(wh_id),
                    "courier_name": clean_text((payload or {}).get("courierName") if isinstance(payload, dict) else ""),
                    "year": year,
                    "month": month,
                }
            )

    return sorted(refs, key=lambda item: (item["warehouse_id"], item["courier_id"]))


def build_shift_overview_url(
    *,
    courier_id: int,
    warehouse_id: int,
    year: int,
    month: int,
) -> str:
    return (
        f"{base_request_url(warehouse_id)}"
        f"/couriers/{courier_id}/shifts"
        f"?year={year}&month={month}"
    )


def fetch_shift_overview(
    *,
    courier_id: int,
    warehouse_id: int,
    year: int,
    month: int,
) -> tuple[str, int, Any]:
    request_url = build_shift_overview_url(
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
        payload = {"_non_json_response": response.text[:5000]}
    return request_url, response.status_code, payload


def shift_items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("shifts", "items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def first_clean(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean_text(mapping.get(key))
        if value:
            return value
    return ""


def shift_date_from_item(item: dict[str, Any]) -> str:
    value = first_clean(item, "date", "shiftDate", "workDate", "day", "startAt", "start", "from")
    return value[:10] if len(value) >= 10 else value


def shift_time_from_item(item: dict[str, Any], *keys: str) -> str:
    value = first_clean(item, *keys)
    if ("T" in value or " " in value) and len(value) >= 16:
        return value[11:16]
    if len(value) >= 5:
        return value[:5]
    return value


def timestamp_from_item(item: dict[str, Any], *keys: str) -> str | None:
    value = first_clean(item, *keys)
    if not value:
        return None
    if len(value) >= 10 and ("T" in value or "-" in value):
        return value
    return None


def make_shift_key(courier_id: int, item: dict[str, Any], index: int) -> str:
    shift_id = first_clean(item, "shiftId", "shift_id", "id")
    if shift_id:
        return f"id:{shift_id}"
    shift_date = shift_date_from_item(item)
    shift_start = shift_time_from_item(item, "startTime", "shiftStart", "start", "from", "startAt")
    shift_end = shift_time_from_item(item, "endTime", "shiftEnd", "end", "to", "endAt")
    shift_name = first_clean(item, "name", "shiftName", "title", "label")
    return f"{courier_id}:{shift_date}:{shift_start}:{shift_end}:{shift_name}:{index}"


def make_shift_raw_payload(
    *,
    courier_id: int,
    warehouse_id: int,
    request_url: str,
    status_code: int,
    response_json: Any,
    year: int,
    month: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    shifts = shift_items_from_payload(response_json)
    return {
        "courier_id": courier_id,
        "year": year,
        "month": month,
        "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
        "warehouse_id": warehouse_id,
        "request_url": request_url,
        "status_code": status_code,
        "response_json": response_json,
        "shift_count": len(shifts),
        "fetched_at": now,
        "updated_at": now,
    }


def make_shift_rows(
    *,
    courier_ref: dict[str, Any],
    request_url: str,
    status_code: int,
    response_json: Any,
    year: int,
    month: int,
    start_date: date | None,
    end_date: date | None,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    courier_id = int(courier_ref["courier_id"])
    warehouse_id = int(courier_ref["warehouse_id"])
    if status_code != 200:
        return rows
    for index, item in enumerate(shift_items_from_payload(response_json), start=1):
        work_date_text = shift_date_from_item(item)
        work_date = parse_date(work_date_text)
        if not work_date:
            continue
        if start_date and (not work_date or work_date < start_date):
            continue
        if end_date and (not work_date or work_date > end_date):
            continue
        rows.append(
            {
                "courier_id": courier_id,
                "year": year,
                "month": month,
                "dsp_id": int(os.getenv("COURIER_HUB_DSP_ID", "8")),
                "warehouse_id": warehouse_id,
                "work_date": work_date.isoformat() if work_date else None,
                "shift_key": make_shift_key(courier_id, item, index),
                "shift_id": first_clean(item, "shiftId", "shift_id", "id") or None,
                "shift_name": first_clean(item, "name", "shiftName", "title", "label") or None,
                "shift_start": shift_time_from_item(item, "startTime", "shiftStart", "start", "from", "startAt") or None,
                "shift_end": shift_time_from_item(item, "endTime", "shiftEnd", "end", "to", "endAt") or None,
                "planned_start_at": timestamp_from_item(item, "plannedStartAt", "startAt"),
                "planned_end_at": timestamp_from_item(item, "plannedEndAt", "endAt"),
                "status": first_clean(item, "status", "state") or None,
                "raw_shift": item,
                "request_url": request_url,
                "response_status_code": status_code,
                "source_raw_updated_at": now,
                "updated_at": now,
            }
        )
    return rows


def upsert_shift_raw(payload: dict[str, Any]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    response = requests.post(
        f"{url}/rest/v1/courier_shift_overview_raw",
        headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "courier_id,year,month,dsp_id,warehouse_id"},
        json=payload,
        timeout=60,
    )
    raise_for_response(response, "courier_shift_overview_raw upsert")


def upsert_shift_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    url = os.environ["SUPABASE_URL"].rstrip("/")
    for start in range(0, len(rows), 500):
        response = requests.post(
            f"{url}/rest/v1/courier_shift_overview",
            headers=supabase_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "courier_id,work_date,shift_key,dsp_id,warehouse_id"},
            json=rows[start:start + 500],
            timeout=60,
        )
        raise_for_response(response, "courier_shift_overview upsert")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--courier-id", type=int)
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--day", help="Optional day filter, e.g. 05 or 2026-07-05.")
    parser.add_argument("--start-date", help="Optional inclusive date filter, e.g. 2026-08-05.")
    parser.add_argument("--end-date", help="Optional inclusive date filter, e.g. 2026-08-31.")
    parser.add_argument(
        "--since-last-work-date",
        action="store_true",
        help="Only sync routes after the latest courier_daily_route_history.work_date until today.",
    )
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--skip-shifts", action="store_true", help="Skip Courier Hub monthly shifts endpoint sync.")
    parser.add_argument("--skip-route-details", action="store_true", help="Skip route performance detail endpoint sync.")
    parser.add_argument(
        "--only-shifts",
        action="store_true",
        help="Only sync Courier Hub monthly shifts; skip route performance details.",
    )
    args = parser.parse_args()
    if args.only_shifts:
        args.skip_route_details = True

    start_date = parse_date(args.start_date)
    parsed_end_date = parse_date(args.end_date)
    end_date = parsed_end_date or date.today()
    if args.start_date and not start_date:
        raise RuntimeError("Invalid --start-date. Use YYYY-MM-DD.")
    if args.end_date and not parsed_end_date:
        raise RuntimeError("Invalid --end-date. Use YYYY-MM-DD.")

    if args.since_last_work_date:
        latest_work_date = read_latest_synced_work_date(
            courier_id=args.courier_id,
            warehouse_id=args.warehouse_id,
        )
        if latest_work_date:
            start_date = latest_work_date
        elif not start_date and args.year and args.month:
            start_date = date(args.year, args.month, 1)
        elif not start_date:
            start_date = date.today().replace(day=1)
        print(
            "Latest synced work_date:",
            latest_work_date.isoformat() if latest_work_date else "-",
        )

    if args.day and (args.start_date or args.end_date or args.since_last_work_date):
        raise RuntimeError("--day nem keverhető --start-date/--end-date/--since-last-work-date szűréssel.")

    if not args.since_last_work_date and not start_date and (not args.year or not args.month):
        raise RuntimeError("--year és --month kötelező, kivéve --since-last-work-date vagy --start-date használatakor.")

    if args.month and (args.month < 1 or args.month > 12):
        raise RuntimeError("Month must be between 1 and 12.")

    month_jobs: list[tuple[int, int, date | None, date | None]]
    if start_date:
        if start_date > end_date:
            print(f"No missing days. start_date={start_date.isoformat()} end_date={end_date.isoformat()}")
            return 0
        month_jobs = []
        for month_start in month_starts_between(start_date, end_date):
            next_month = (
                date(month_start.year + 1, 1, 1)
                if month_start.month == 12
                else date(month_start.year, month_start.month + 1, 1)
            )
            month_end = next_month - timedelta(days=1)
            month_jobs.append(
                (
                    month_start.year,
                    month_start.month,
                    max(start_date, month_start),
                    min(end_date, month_end),
                )
            )
    else:
        month_jobs = [(int(args.year), int(args.month), None, None)]

    refs: list[dict[str, Any]] = []
    courier_refs: list[dict[str, Any]] = []
    for year, month, job_start, job_end in month_jobs:
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        month_end = next_month - timedelta(days=1)
        if not args.skip_shifts:
            courier_refs.extend(
                read_courier_refs(
                    courier_id=args.courier_id,
                    year=year,
                    month=month,
                    warehouse_id=args.warehouse_id,
                )
            )
        if not args.skip_route_details:
            refs.extend(
                read_route_refs(
                    courier_id=args.courier_id,
                    year=year,
                    month=month,
                    warehouse_id=args.warehouse_id,
                    day=args.day or "",
                    start_date=job_start,
                    end_date=min(job_end or month_end, month_end),
                )
            )

    period_label = (
        f"{start_date.isoformat()}..{end_date.isoformat()}"
        if start_date
        else f"{args.year}-{args.month:02d}" + (f"-{month_day(args.day)}" if args.day else "")
    )
    courier_label = str(args.courier_id) if args.courier_id else "all"
    print(f"Route detail target: courier={courier_label} | period={period_label} | routes={len(refs)}")
    if not args.skip_shifts:
        print(f"Shift overview target: courier-months={len(courier_refs)}")
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    if not refs and (args.skip_shifts or not courier_refs):
        print("No routes or couriers found in raw financial overview tables for this filter.")
        return 0
    if not courier_hub_auth_configured():
        print(
            "Courier Hub auth nincs beallitva. Allitsd be a COURIER_HUB_AUTHORIZATION, "
            "COURIER_HUB_COOKIE vagy COURIER_HUB_API_KEY kornyezeti valtozot, majd futtasd ujra."
        )
        return 1

    shift_success = 0
    shift_failed = 0
    shift_rows_total = 0
    if not args.skip_shifts:
        seen_shift_ref: set[tuple[int, int, int, int]] = set()
        unique_courier_refs: list[dict[str, Any]] = []
        for courier_ref in courier_refs:
            key = (
                int(courier_ref["warehouse_id"]),
                int(courier_ref["courier_id"]),
                int(courier_ref["year"]),
                int(courier_ref["month"]),
            )
            if key in seen_shift_ref:
                continue
            seen_shift_ref.add(key)
            unique_courier_refs.append(courier_ref)

        for index, courier_ref in enumerate(unique_courier_refs, start=1):
            try:
                request_url, status_code, response_json = fetch_shift_overview(
                    courier_id=int(courier_ref["courier_id"]),
                    warehouse_id=int(courier_ref["warehouse_id"]),
                    year=int(courier_ref["year"]),
                    month=int(courier_ref["month"]),
                )
                raw_payload = make_shift_raw_payload(
                    courier_id=int(courier_ref["courier_id"]),
                    warehouse_id=int(courier_ref["warehouse_id"]),
                    request_url=request_url,
                    status_code=status_code,
                    response_json=response_json,
                    year=int(courier_ref["year"]),
                    month=int(courier_ref["month"]),
                )
                rows = make_shift_rows(
                    courier_ref=courier_ref,
                    request_url=request_url,
                    status_code=status_code,
                    response_json=response_json,
                    year=int(courier_ref["year"]),
                    month=int(courier_ref["month"]),
                    start_date=start_date,
                    end_date=end_date if start_date else None,
                )
                if args.apply:
                    upsert_shift_raw(raw_payload)
                    upsert_shift_rows(rows)
                if status_code == 200:
                    shift_success += 1
                    shift_rows_total += len(rows)
                else:
                    shift_failed += 1
                    print(
                        f"SHIFTS HTTP {status_code}: courier={courier_ref['courier_id']} "
                        f"| WH={courier_ref['warehouse_id']} | "
                        f"{int(courier_ref['year'])}-{int(courier_ref['month']):02d}"
                    )
                    if status_code == 401:
                        print("Courier Hub 401: friss auth kell a shifts API-hoz.")
                        break
            except Exception as exc:
                shift_failed += 1
                print(
                    f"SHIFTS ERROR: courier={courier_ref['courier_id']} "
                    f"| WH={courier_ref['warehouse_id']} | {exc}"
                )
            if index == len(unique_courier_refs) or index % 20 == 0:
                print(f"SHIFTS PROGRESS: {index}/{len(unique_courier_refs)} rows={shift_rows_total}")
            if args.sleep > 0:
                time.sleep(args.sleep)

    success = 0
    failed = 0
    unauthorized = 0
    for index, route_ref in enumerate(refs, start=1):
        courier_id = int(route_ref["courier_id"])
        route_id = int(route_ref["route_id"])
        warehouse_id = int(route_ref["warehouse_id"])
        route_date = parse_date(route_ref.get("delivery_date"))
        route_year = route_date.year if route_date else int(route_ref["year"])
        route_month = route_date.month if route_date else int(route_ref["month"])
        try:
            detail_url, status_code, detail_json = fetch_route_performance_detail(
                courier_id=courier_id,
                route_id=route_id,
                warehouse_id=warehouse_id,
            )
            detail_payload = make_route_performance_detail_payload(
                courier_id=courier_id,
                route_id=route_id,
                warehouse_id=warehouse_id,
                request_url=detail_url,
                status_code=status_code,
                response_json=detail_json,
                year=route_year,
                month=route_month,
            )
            if args.apply:
                upsert_route_performance_detail(detail_payload)
                if status_code == 200:
                    upsert_flat_table(
                        "courier_financial_overview_delay",
                        build_delay_row(
                            courier_id=courier_id,
                            route_ref=route_ref,
                            warehouse_id=warehouse_id,
                            response_json=detail_json,
                            status_code=status_code,
                            year=route_year,
                            month=route_month,
                        ),
                    )
                    upsert_flat_table(
                        "courier_financial_overview_compliance",
                        build_compliance_row(
                            courier_id=courier_id,
                            route_ref=route_ref,
                            warehouse_id=warehouse_id,
                            response_json=detail_json,
                            status_code=status_code,
                            year=route_year,
                            month=route_month,
                        ),
                    )
                    upsert_daily_route_history(
                        build_daily_route_history_row(
                            courier_id=courier_id,
                            route_ref=route_ref,
                            warehouse_id=warehouse_id,
                            response_json=detail_json,
                            status_code=status_code,
                            year=route_year,
                            month=route_month,
                        )
                    )

            if status_code == 200:
                success += 1
            else:
                failed += 1
                print(f"DETAIL HTTP {status_code}: courier={courier_id} | route={route_id} | WH={warehouse_id}")
                if status_code == 401:
                    unauthorized += 1
                    print(
                        "Courier Hub 401: az auth hianyzik vagy lejart. Friss COURIER_HUB_AUTHORIZATION/"
                        "COURIER_HUB_COOKIE kell a route detail API-hoz."
                    )
                    break
        except Exception as exc:
            failed += 1
            print(f"DETAIL ERROR: courier={courier_id} | route={route_id} | WH={warehouse_id} | {exc}")

        if index == len(refs) or index % 10 == 0:
            print(f"DETAIL PROGRESS: {index}/{len(refs)}")
        if args.sleep > 0:
            time.sleep(args.sleep)

    if unauthorized:
        print("Megjegyzes: a havi overview raw adatok ettol meg hasznalhatok, de auto/rendszam/km csak sikeres detail sync utan lesz.")
    if not args.skip_shifts:
        print(f"Done. Shift overview success={shift_success}, failed={shift_failed}, rows={shift_rows_total}")
    print(f"Done. Route detail success={success}, failed={failed}")
    return 1 if failed or shift_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
