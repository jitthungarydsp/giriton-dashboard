import argparse
import json
import os
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SOURCE_NAME = "courier_hub_performance_couriers"
BASE_URL = "https://courier-hub.kifli.hu/services/courier-hub-service/external/performance/dsp"
DEFAULT_DSP_CODE = "JIT"
DEFAULT_DSP_ID = 8
DEFAULT_START_DATE = "2026-06-01"
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
WAREHOUSE_TABLES = {
    1: ("BUD1", "jitt_invoice_performance_bud1_raw"),
    2: ("BUD2", "jitt_invoice_performance_bud2_raw"),
}


def get_setting(name):
    env_value = os.getenv(name)

    if env_value:
        return env_value

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"

    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            secrets = tomllib.load(file)
    except Exception:
        return ""

    if name in secrets:
        return str(secrets.get(name) or "")

    supabase_section = secrets.get("supabase", {})

    if isinstance(supabase_section, dict) and name in supabase_section:
        return str(supabase_section.get(name) or "")

    return ""


def get_required_setting(name):
    value = str(get_setting(name) or "").strip()

    if not value:
        raise RuntimeError(f"Missing required setting: {name}")

    return value


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_budapest():
    return datetime.now(BUDAPEST_TZ).date()


def parse_warehouse_ids(value):
    ids = []

    for item in str(value or "").split(","):
        item = item.strip()

        if not item:
            continue

        warehouse_id = int(item)

        if warehouse_id not in WAREHOUSE_TABLES:
            raise ValueError(
                f"Unsupported warehouse_id={warehouse_id}. Supported: 1,2"
            )

        ids.append(warehouse_id)

    return ids or [1, 2]


def iter_chunks(start_date, end_date, chunk_days):
    current = start_date
    chunk_size = max(int(chunk_days), 1)

    while current <= end_date:
        current_end = min(
            current + timedelta(days=chunk_size - 1),
            end_date,
        )
        yield current, current_end
        current = current_end + timedelta(days=1)


def build_request_url(dsp_code, dsp_id, warehouse_id, date_from, date_to):
    return (
        f"{BASE_URL}/{dsp_code}/couriers"
        f"?dateFrom={date_from.isoformat()}"
        f"&dateTo={date_to.isoformat()}"
        f"&dspId={int(dsp_id)}"
        f"&warehouseId={int(warehouse_id)}"
    )


def normalize_authorization(value):
    text = str(value or "").strip()

    if not text:
        return ""

    lower = text.lower()

    if lower.startswith(("bearer ", "basic ", "token ")):
        return text

    return f"Bearer {text}"


def build_courier_hub_headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": "giriton-dashboard-jitt-invoice-import/1.0",
    }
    authorization = normalize_authorization(
        get_setting("KIFLI_COURIER_HUB_AUTHORIZATION")
        or get_setting("KIFLI_COURIER_HUB_BEARER_TOKEN")
    )
    cookie = str(get_setting("KIFLI_COURIER_HUB_COOKIE") or "").strip()
    api_key = str(get_setting("KIFLI_COURIER_HUB_API_KEY") or "").strip()
    extra_headers_json = str(
        get_setting("KIFLI_COURIER_HUB_EXTRA_HEADERS_JSON") or ""
    ).strip()

    if authorization:
        headers["Authorization"] = authorization

    if cookie:
        headers["Cookie"] = cookie

    if api_key:
        headers["x-api-key"] = api_key

    if extra_headers_json:
        extra_headers = json.loads(extra_headers_json)

        if not isinstance(extra_headers, dict):
            raise ValueError("KIFLI_COURIER_HUB_EXTRA_HEADERS_JSON must be an object.")

        headers.update(
            {
                str(key): str(value)
                for key, value in extra_headers.items()
            }
        )

    return headers


def fetch_performance(url, headers):
    response = requests.get(
        url,
        headers=headers,
        timeout=90,
    )
    content_type = response.headers.get("Content-Type", "")

    try:
        payload = response.json()
    except ValueError:
        payload = {
            "_raw_text": response.text,
            "_content_type": content_type,
        }

    return response.status_code, payload


def build_raw_row(
    dsp_code,
    dsp_id,
    warehouse_id,
    date_from,
    date_to,
    request_url,
    status_code,
    response_json,
    fetch_batch_id,
):
    warehouse_code, _table_name = WAREHOUSE_TABLES[warehouse_id]
    now_utc = datetime.now(timezone.utc).isoformat()

    return {
        "source_name": SOURCE_NAME,
        "dsp_code": dsp_code,
        "dsp_id": int(dsp_id),
        "warehouse_id": int(warehouse_id),
        "warehouse_code": warehouse_code,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "request_url": request_url,
        "status_code": int(status_code),
        "response_json": response_json,
        "fetched_at": now_utc,
        "fetch_batch_id": fetch_batch_id,
        "updated_at": now_utc,
    }


def raise_for_supabase_error(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()

        if detail:
            raise requests.HTTPError(
                f"{exc}; Supabase response: {detail[:1000]}",
                response=response,
            ) from exc

        raise


def post_supabase_rows(table_name, rows):
    if not rows:
        return 0

    supabase_url = get_required_setting("SUPABASE_URL").rstrip("/")
    supabase_key = get_required_setting("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?on_conflict=source_name,dsp_code,dsp_id,warehouse_id,date_from,date_to"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=90,
    )
    raise_for_supabase_error(response)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Courier Hub performance raw import JITT invoice rendszerhez."
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help="Kezdo datum YYYY-MM-DD. Alap: 2026-06-01.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Zaro datum YYYY-MM-DD. Alap: mai nap.",
    )
    parser.add_argument(
        "--warehouse-ids",
        default="1,2",
        help="Raktar ID lista vesszovel: 1,2.",
    )
    parser.add_argument(
        "--dsp-code",
        default=DEFAULT_DSP_CODE,
        help="DSP kod. Alap: JIT.",
    )
    parser.add_argument(
        "--dsp-id",
        type=int,
        default=DEFAULT_DSP_ID,
        help="Courier Hub DSP ID. Alap: 8.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Hany nap legyen egy API hivasban. Alap: 7.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API-t hiv, de DB-be nem ir.",
    )
    parser.add_argument(
        "--save-http-errors",
        action="store_true",
        help="HTTP 4xx/5xx valaszokat is elmenti raw sorba.",
    )
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date) if args.end_date else today_budapest()

    if end_date < start_date:
        parser.error("--end-date nem lehet kisebb, mint --start-date.")

    warehouse_ids = parse_warehouse_ids(args.warehouse_ids)
    headers = build_courier_hub_headers()
    fetch_batch_id = str(uuid4())
    rows_by_table = {
        table_name: []
        for _warehouse_code, table_name in WAREHOUSE_TABLES.values()
    }
    ok_count = 0
    failed_count = 0

    for warehouse_id in warehouse_ids:
        warehouse_code, table_name = WAREHOUSE_TABLES[warehouse_id]

        for date_from, date_to in iter_chunks(
            start_date,
            end_date,
            args.chunk_days,
        ):
            request_url = build_request_url(
                args.dsp_code,
                args.dsp_id,
                warehouse_id,
                date_from,
                date_to,
            )

            try:
                status_code, response_json = fetch_performance(
                    request_url,
                    headers,
                )

                if status_code >= 400 and not args.save_http_errors:
                    raise RuntimeError(
                        f"Courier Hub HTTP {status_code}: {str(response_json)[:500]}"
                    )

                rows_by_table[table_name].append(
                    build_raw_row(
                        args.dsp_code,
                        args.dsp_id,
                        warehouse_id,
                        date_from,
                        date_to,
                        request_url,
                        status_code,
                        response_json,
                        fetch_batch_id,
                    )
                )
                ok_count += 1
                print(
                    f"OK {warehouse_code} {date_from.isoformat()}..{date_to.isoformat()} status={status_code}"
                )
            except Exception as exc:
                failed_count += 1
                print(
                    f"HIBA {warehouse_code} {date_from.isoformat()}..{date_to.isoformat()}: {exc}"
                )

    if args.dry_run:
        for table_name, rows in rows_by_table.items():
            print(f"DRY_RUN {table_name}: rows={len(rows)}")
        print(f"SUMMARY ok={ok_count} failed={failed_count}")
        return

    written = 0

    for table_name, rows in rows_by_table.items():
        count = post_supabase_rows(table_name, rows)
        written += count
        print(f"DB_UPSERT {table_name}: {count}")

    print(
        f"SUMMARY written={written} ok={ok_count} failed={failed_count} batch={fetch_batch_id}"
    )

    if failed_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
