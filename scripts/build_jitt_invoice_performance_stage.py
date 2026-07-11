import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.load_jitt_invoice_performance_raw import (  # noqa: E402
    get_required_setting,
    parse_date,
    today_budapest,
)


SOURCE_NAME = "courier_hub_performance_couriers"
TARGET_TABLE = "stg_jitt_invoice_performance_couriers"
RAW_TABLES = [
    (1, "BUD1", ["raw_jitt_invoice_perf_bud1", "jitt_invoice_performance_bud1_raw"]),
    (2, "BUD2", ["raw_jitt_invoice_perf_bud2", "jitt_invoice_performance_bud2_raw"]),
]


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_number(value, is_percent=False):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)

        if is_percent and 0 < abs(number) <= 1:
            return number * 100

        return number

    text = normalize_text(value)

    if not text:
        return None

    text = (
        text.replace("%", "")
        .replace("\xa0", " ")
        .replace(" ", "")
        .replace(",", ".")
    )

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    return float(match.group(0))


def as_int(value):
    number = parse_number(value)

    if number is None:
        return None

    return int(round(number))


def as_percent(value):
    number = parse_number(value, is_percent=True)

    if number is None:
        return None

    return round(number, 2)


def safe_percent(numerator, denominator):
    if denominator in (None, 0):
        return None

    if numerator is None:
        return None

    return round((float(numerator) / float(denominator)) * 100, 2)


def build_key_map(data):
    key_map = {}

    for key, value in data.items():
        key_map.setdefault(normalize_key(key), []).append((key, value))

    return key_map


def first_value(key_map, names, prefer_percent_key=False):
    normalized_names = {normalize_key(name) for name in names}
    matches = []

    for key, values in key_map.items():
        if key in normalized_names:
            matches.extend(values)

    if not matches:
        return None

    if prefer_percent_key:
        for original_key, value in matches:
            original_text = str(original_key).lower()

            if "%" in original_text or "percent" in original_text or "percentage" in original_text:
                return value

    return matches[0][1]


def find_percent_value(key_map, exact_names, loose_names):
    value = first_value(key_map, exact_names, prefer_percent_key=True)

    if value is not None:
        return value

    loose_normalized = {normalize_key(name) for name in loose_names}

    for normalized, values in key_map.items():
        if normalized not in loose_normalized:
            continue

        for original_key, item_value in values:
            original_text = str(original_key).lower()

            if "%" in original_text or "percent" in original_text or "percentage" in original_text:
                return item_value

    return None


def extract_courier_id(data, key_map):
    direct_value = first_value(
        key_map,
        [
            "courier_id",
            "courierId",
            "courier",
            "driver_id",
            "driverId",
            "driver",
            "id",
        ],
    )

    if direct_value is None:
        return ""

    text = normalize_text(direct_value)
    match = re.search(r"\d+", text)

    if not match:
        return ""

    return match.group(0)


def has_metric_shape(data):
    key_map = build_key_map(data)
    courier_id = extract_courier_id(data, key_map)

    if not courier_id:
        return False

    metric_keys = {
        "shifts",
        "shiftcount",
        "orders",
        "ordercount",
        "delayed",
        "delayedorders",
        "delaypercent",
        "delaypercentage",
        "latepercent",
        "latepercentage",
        "noshowpercent",
        "noshowpercentage",
        "compliance",
        "compliancepercent",
        "compliancepercentage",
    }

    return bool(metric_keys.intersection(set(key_map)))


def traverse_json(value):
    if isinstance(value, dict):
        if has_metric_shape(value):
            yield value

        for child in value.values():
            yield from traverse_json(child)

    elif isinstance(value, list):
        for child in value:
            yield from traverse_json(child)


def choose_best_candidate(existing, candidate):
    if existing is None:
        return candidate

    existing_score = sum(
        existing.get(key) is not None
        for key in [
            "shifts",
            "orders",
            "delayed",
            "delay_percent",
            "late_percent",
            "no_show_percent",
            "compliance_score_percent",
        ]
    )
    candidate_score = sum(
        candidate.get(key) is not None
        for key in [
            "shifts",
            "orders",
            "delayed",
            "delay_percent",
            "late_percent",
            "no_show_percent",
            "compliance_score_percent",
        ]
    )

    if candidate_score > existing_score:
        return candidate

    return existing


def delay_level(delay_percent):
    if delay_percent is None:
        return ""

    if delay_percent <= 1.50:
        return "Szint 1"

    if delay_percent <= 3.00:
        return "Szint 2"

    if delay_percent <= 5.00:
        return "Szint 3"

    return "Nincs bonusz"


def compliance_level(compliance_bad_percent):
    if compliance_bad_percent is None:
        return ""

    if compliance_bad_percent <= 2.00:
        return "Szint 1"

    if compliance_bad_percent <= 4.00:
        return "Szint 2"

    if compliance_bad_percent <= 10.00:
        return "Szint 3"

    return "Nincs bonusz"


def extract_metric_row(
    item,
    raw_row,
    raw_table,
):
    key_map = build_key_map(item)
    courier_id = extract_courier_id(item, key_map)

    if not courier_id:
        return None

    shifts = as_int(
        first_value(
            key_map,
            [
                "shifts",
                "shift_count",
                "shiftCount",
            ],
        )
    )
    orders = as_int(
        first_value(
            key_map,
            [
                "orders",
                "order_count",
                "orderCount",
                "total_orders",
                "totalOrders",
            ],
        )
    )
    delayed = as_int(
        first_value(
            key_map,
            [
                "delayed",
                "delayed_orders",
                "delayedOrders",
                "delayed_count",
                "delayedCount",
            ],
        )
    )
    courier_name = normalize_text(
        first_value(
            key_map,
            [
                "courier_name",
                "courierName",
                "driver_name",
                "driverName",
                "name",
            ],
        )
        or ""
    )
    delay_percent = as_percent(
        find_percent_value(
            key_map,
            ["delay_percent", "delayPercent", "delay_percentage", "delayPercentage"],
            ["delay"],
        )
    )
    late_percent = as_percent(
        find_percent_value(
            key_map,
            ["late_percent", "latePercent", "late_percentage", "latePercentage"],
            ["late"],
        )
    )
    no_show_percent = as_percent(
        find_percent_value(
            key_map,
            [
                "no_show_percent",
                "noShowPercent",
                "no_show_percentage",
                "noShowPercentage",
                "no-show %",
            ],
            ["no_show", "noShow", "no-show"],
        )
    )
    source_compliance_percent = as_percent(
        find_percent_value(
            key_map,
            [
                "compliance",
                "compliance_percent",
                "compliancePercent",
                "compliance_percentage",
                "compliancePercentage",
            ],
            ["compliance"],
        )
    )

    if delay_percent is None:
        delay_percent = safe_percent(delayed, orders)

    if late_percent is None:
        late_percent = 0.0

    if no_show_percent is None:
        no_show_percent = 0.0

    compliance_bad_percent = round(
        (0.7 * float(no_show_percent)) + (0.3 * float(late_percent)),
        2,
    )
    compliance_score_percent = round(100 - compliance_bad_percent, 2)

    if source_compliance_percent is not None:
        compliance_score_percent = source_compliance_percent

    now_utc = datetime.now(timezone.utc).isoformat()

    return {
        "source_name": raw_row.get("source_name") or SOURCE_NAME,
        "dsp_code": raw_row.get("dsp_code") or "JIT",
        "dsp_id": raw_row.get("dsp_id") or 8,
        "warehouse_id": raw_row.get("warehouse_id"),
        "warehouse_code": raw_row.get("warehouse_code") or "",
        "date_from": raw_row.get("date_from"),
        "date_to": raw_row.get("date_to"),
        "courier_id": courier_id,
        "courier_name": courier_name,
        "shifts": shifts,
        "orders": orders,
        "delayed": delayed,
        "delay_percent": delay_percent,
        "late_percent": late_percent,
        "no_show_percent": no_show_percent,
        "compliance_bad_percent": compliance_bad_percent,
        "compliance_score_percent": compliance_score_percent,
        "source_compliance_percent": source_compliance_percent,
        "delay_level": delay_level(delay_percent),
        "compliance_level": compliance_level(compliance_bad_percent),
        "raw_table": raw_table,
        "raw_fetched_at": raw_row.get("fetched_at"),
        "raw_row": item,
        "calculated_at": now_utc,
        "updated_at": now_utc,
    }


def build_stage_rows(raw_row, raw_table):
    payload = raw_row.get("response_json")
    best_by_courier = {}

    for item in traverse_json(payload):
        row = extract_metric_row(item, raw_row, raw_table)

        if not row:
            continue

        courier_id = row["courier_id"]
        best_by_courier[courier_id] = choose_best_candidate(
            best_by_courier.get(courier_id),
            row,
        )

    return list(best_by_courier.values())


def supabase_headers():
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")

    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def table_exists_or_readable(table_name):
    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    endpoint = f"{supabase_url}/rest/v1/{table_name}"
    response = requests.get(
        endpoint,
        headers=supabase_headers(),
        params={"select": "date_from", "limit": "1"},
        timeout=30,
    )

    return response.status_code < 400


def read_raw_rows(table_name, start_date, end_date, limit):
    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    endpoint = f"{supabase_url}/rest/v1/{table_name}"
    response = requests.get(
        endpoint,
        headers=supabase_headers(),
        params={
            "select": (
                "source_name,dsp_code,dsp_id,warehouse_id,warehouse_code,"
                "date_from,date_to,status_code,response_json,fetched_at"
            ),
            "status_code": "eq.200",
            "date_to": f"gte.{start_date.isoformat()}",
            "date_from": f"lte.{end_date.isoformat()}",
            "order": "date_from.asc,date_to.asc,fetched_at.desc",
            "limit": str(limit),
        },
        timeout=90,
    )

    if response.status_code >= 400:
        return []

    return response.json()


def post_stage_rows(rows):
    if not rows:
        return 0

    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    service_role_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/{TARGET_TABLE}"
        "?on_conflict=source_name,dsp_code,dsp_id,warehouse_id,date_from,date_to,courier_id"
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


def pick_raw_table(table_names):
    for table_name in table_names:
        if table_exists_or_readable(table_name):
            return table_name

    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Courier Hub performance raw JSON feldolgozasa stage tablaba."
    )
    parser.add_argument(
        "--start-date",
        default="2026-06-01",
        help="Kezdo datum YYYY-MM-DD. Alap: 2026-06-01.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Zaro datum YYYY-MM-DD. Alap: mai Budapest szerinti nap.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum raw sor forrastablankent.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nem ir DB-be, csak kiirja a talalt sorokat.",
    )
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else today_budapest()

    rows_to_write = []

    for _warehouse_id, warehouse_code, table_names in RAW_TABLES:
        raw_table = pick_raw_table(table_names)

        if not raw_table:
            print(f"SKIP {warehouse_code}: nincs elerheto raw tabla {table_names}")
            continue

        raw_rows = read_raw_rows(
            raw_table,
            start_date,
            end_date,
            args.limit,
        )
        print(f"RAW {warehouse_code} {raw_table}: {len(raw_rows)} sor")

        for raw_row in raw_rows:
            stage_rows = build_stage_rows(raw_row, raw_table)
            rows_to_write.extend(stage_rows)
            print(
                f"  {raw_row.get('date_from')}..{raw_row.get('date_to')} "
                f"couriers={len(stage_rows)}"
            )

    if args.dry_run:
        print(f"DRY_RUN stage rows={len(rows_to_write)}")

        for row in rows_to_write[:20]:
            print(
                json.dumps(
                    {
                        "courier_id": row["courier_id"],
                        "warehouse_code": row["warehouse_code"],
                        "date_from": row["date_from"],
                        "date_to": row["date_to"],
                        "shifts": row["shifts"],
                        "orders": row["orders"],
                        "delayed": row["delayed"],
                        "delay_percent": row["delay_percent"],
                        "late_percent": row["late_percent"],
                        "no_show_percent": row["no_show_percent"],
                        "compliance_bad_percent": row["compliance_bad_percent"],
                        "compliance_score_percent": row["compliance_score_percent"],
                    },
                    ensure_ascii=False,
                )
            )

        return

    written = post_stage_rows(rows_to_write)
    print(f"STAGE_UPSERT {TARGET_TABLE}: {written}")


if __name__ == "__main__":
    main()
