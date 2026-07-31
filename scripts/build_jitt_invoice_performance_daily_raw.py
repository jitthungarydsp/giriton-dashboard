import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_jitt_invoice_performance_stage import (  # noqa: E402
    RAW_TABLES,
    SOURCE_NAME,
    as_int,
    build_key_map,
    extract_courier_id,
    first_value,
    normalize_text,
    parse_number,
    traverse_json,
)
from scripts.load_jitt_invoice_performance_raw import (  # noqa: E402
    get_required_setting,
    parse_date,
    today_budapest,
)


TARGET_TABLE = "raw_jitt_invoice_perf_couriers_daily"


def as_decimal(value):
    number = parse_number(value)

    if number is None:
        return None

    return round(number, 6)


def pick_value(key_map, *names):
    return first_value(key_map, list(names))


def extract_daily_courier_row(item, raw_row, raw_table):
    key_map = build_key_map(item)
    courier_id = extract_courier_id(item, key_map)

    if not courier_id:
        return None

    work_date = raw_row.get("date_from")
    now_utc = datetime.now(timezone.utc).isoformat()

    return {
        "source_name": raw_row.get("source_name") or SOURCE_NAME,
        "dsp_code": raw_row.get("dsp_code") or "JIT",
        "dsp_id": raw_row.get("dsp_id") or 8,
        "warehouse_id": raw_row.get("warehouse_id"),
        "warehouse_code": raw_row.get("warehouse_code") or "",
        "work_date": work_date,
        "courier_id": courier_id,
        "courier_name": normalize_text(
            pick_value(key_map, "courierName", "courier_name") or ""
        ),
        "external_carrier_id": as_int(
            pick_value(key_map, "externalCarrierId", "external_carrier_id")
        ),
        "external_carrier_name": normalize_text(
            pick_value(key_map, "externalCarrierName", "external_carrier_name") or ""
        ),
        "external_carrier_short_name": normalize_text(
            pick_value(
                key_map,
                "externalCarrierShortName",
                "external_carrier_short_name",
            )
            or ""
        ),
        "order_count": as_int(pick_value(key_map, "orderCount", "order_count")),
        "route_count": as_int(pick_value(key_map, "routeCount", "route_count")),
        "delayed_order_count": as_int(
            pick_value(key_map, "delayedOrderCount", "delayed_order_count")
        ),
        "pct_of_delayed_orders": as_decimal(
            pick_value(key_map, "pctOfDelayedOrders", "pct_of_delayed_orders")
        ),
        "shift_count": as_int(pick_value(key_map, "shiftCount", "shift_count")),
        "late_count": as_int(pick_value(key_map, "lateCount", "late_count")),
        "did_not_come_count": as_int(
            pick_value(key_map, "didNotComeCount", "did_not_come_count")
        ),
        "pct_late_evaluation": as_decimal(
            pick_value(key_map, "pctLateEvaluation", "pct_late_evaluation")
        ),
        "pct_did_not_come_evaluation": as_decimal(
            pick_value(
                key_map,
                "pctDidNotComeEvaluation",
                "pct_did_not_come_evaluation",
            )
        ),
        "raw_table": raw_table,
        "raw_fetched_at": raw_row.get("fetched_at"),
        "raw_row": item,
        "created_at": now_utc,
        "updated_at": now_utc,
    }


def build_daily_rows(raw_row, raw_table):
    if raw_row.get("date_from") != raw_row.get("date_to"):
        return []

    rows_by_courier = {}

    for item in traverse_json(raw_row.get("response_json")):
        row = extract_daily_courier_row(item, raw_row, raw_table)

        if not row:
            continue

        rows_by_courier[row["courier_id"]] = row

    return list(rows_by_courier.values())


def supabase_headers():
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")

    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def table_exists_or_readable(table_name):
    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    response = requests.get(
        f"{supabase_url}/rest/v1/{table_name}",
        headers=supabase_headers(),
        params={"select": "date_from", "limit": "1"},
        timeout=30,
    )

    return response.status_code < 400


def pick_raw_table(table_names):
    for table_name in table_names:
        if table_exists_or_readable(table_name):
            return table_name

    return ""


def read_raw_rows(table_name, start_date, end_date, limit):
    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    response = requests.get(
        f"{supabase_url}/rest/v1/{table_name}",
        headers=supabase_headers(),
        params={
            "select": (
                "source_name,dsp_code,dsp_id,warehouse_id,warehouse_code,"
                "date_from,date_to,status_code,response_json,fetched_at"
            ),
            "status_code": "eq.200",
            "date_from": f"gte.{start_date.isoformat()}",
            "date_to": f"lte.{end_date.isoformat()}",
            "order": "date_from.asc,warehouse_id.asc,fetched_at.desc",
            "limit": str(limit),
        },
        timeout=90,
    )

    if response.status_code >= 400:
        return []

    return response.json()


def post_daily_rows(rows):
    if not rows:
        return 0

    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/{TARGET_TABLE}"
        "?on_conflict=source_name,dsp_code,dsp_id,warehouse_id,work_date,courier_id"
    )
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=90,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"{exc}; Supabase response: {response.text[:1000]}",
            response=response,
        ) from exc

    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="JITT Courier Hub performance napi futar raw sorok epitesa."
    )
    parser.add_argument("--start-date", default="2026-06-01")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else today_budapest()
    rows_to_write = []

    for _warehouse_id, warehouse_code, table_names in RAW_TABLES:
        raw_table = pick_raw_table(table_names)

        if not raw_table:
            print(f"SKIP {warehouse_code}: raw tabla nem olvashato")
            continue

        raw_rows = read_raw_rows(raw_table, start_date, end_date, args.limit)
        print(f"RAW {warehouse_code} table={raw_table} rows={len(raw_rows)}")

        for raw_row in raw_rows:
            daily_rows = build_daily_rows(raw_row, raw_table)
            rows_to_write.extend(daily_rows)
            print(
                f"  {raw_row.get('date_from')} {warehouse_code} "
                f"couriers={len(daily_rows)}"
            )

    if args.dry_run:
        print(f"DRY_RUN daily rows={len(rows_to_write)}")

        for row in rows_to_write[:20]:
            print(
                json.dumps(
                    {
                        "work_date": row["work_date"],
                        "warehouse_code": row["warehouse_code"],
                        "courier_id": row["courier_id"],
                        "order_count": row["order_count"],
                        "route_count": row["route_count"],
                        "shift_count": row["shift_count"],
                        "late_count": row["late_count"],
                        "did_not_come_count": row["did_not_come_count"],
                    },
                    ensure_ascii=False,
                )
            )

        return

    written = post_daily_rows(rows_to_write)
    print(f"DAILY_RAW_UPSERT {TARGET_TABLE}: {written}")


if __name__ == "__main__":
    main()
