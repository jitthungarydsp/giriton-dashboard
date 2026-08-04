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
from typing import Any

import requests

from sync_courier_financial_overview import (
    COURIER_TARGET_TABLES,
    build_compliance_row,
    build_daily_route_history_row,
    build_delay_row,
    clean_text,
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


def read_route_refs(
    *,
    courier_id: int | None,
    year: int,
    month: int,
    warehouse_id: int | None,
    day: str = "",
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
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--day", help="Optional day filter, e.g. 05 or 2026-07-05.")
    parser.add_argument("--warehouse-id", type=int, choices=[1, 2])
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    if args.month < 1 or args.month > 12:
        raise RuntimeError("Month must be between 1 and 12.")

    refs = read_route_refs(
        courier_id=args.courier_id,
        year=args.year,
        month=args.month,
        warehouse_id=args.warehouse_id,
        day=args.day or "",
    )
    period_label = f"{args.year}-{args.month:02d}" + (f"-{month_day(args.day)}" if args.day else "")
    courier_label = str(args.courier_id) if args.courier_id else "all"
    print(f"Route detail target: courier={courier_label} | period={period_label} | routes={len(refs)}")
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    if not refs:
        print("No routes found in raw financial overview tables for this filter.")
        return 0

    success = 0
    failed = 0
    for index, route_ref in enumerate(refs, start=1):
        courier_id = int(route_ref["courier_id"])
        route_id = int(route_ref["route_id"])
        warehouse_id = int(route_ref["warehouse_id"])
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
                year=args.year,
                month=args.month,
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
                            year=args.year,
                            month=args.month,
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
                            year=args.year,
                            month=args.month,
                        ),
                    )
                    upsert_daily_route_history(
                        build_daily_route_history_row(
                            courier_id=courier_id,
                            route_ref=route_ref,
                            warehouse_id=warehouse_id,
                            response_json=detail_json,
                            status_code=status_code,
                            year=args.year,
                            month=args.month,
                        )
                    )

            if status_code == 200:
                success += 1
            else:
                failed += 1
                print(f"DETAIL HTTP {status_code}: courier={courier_id} | route={route_id} | WH={warehouse_id}")
        except Exception as exc:
            failed += 1
            print(f"DETAIL ERROR: courier={courier_id} | route={route_id} | WH={warehouse_id} | {exc}")

        if index == len(refs) or index % 10 == 0:
            print(f"DETAIL PROGRESS: {index}/{len(refs)}")
        if args.sleep > 0:
            time.sleep(args.sleep)

    print(f"Done. Route detail success={success}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
