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
from datetime import date, datetime, timedelta
from typing import Any

import requests

from sync_courier_financial_overview import (
    COURIER_TARGET_TABLES,
    build_compliance_row,
    build_daily_route_history_row,
    build_delay_row,
    clean_text,
    courier_hub_auth_configured,
    fetch_route_performance_detail,
    make_route_performance_detail_payload,
    raise_for_response,
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
    args = parser.parse_args()

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
    for year, month, job_start, job_end in month_jobs:
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        month_end = next_month - timedelta(days=1)
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
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    if not refs:
        print("No routes found in raw financial overview tables for this filter.")
        return 0
    if not courier_hub_auth_configured():
        print(
            "Courier Hub auth nincs beallitva. Allitsd be a COURIER_HUB_AUTHORIZATION, "
            "COURIER_HUB_COOKIE vagy COURIER_HUB_API_KEY kornyezeti valtozot, majd futtasd ujra."
        )
        return 1

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
    print(f"Done. Route detail success={success}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
