import argparse
import calendar
import time
from datetime import date, datetime

import requests

try:
    from scripts.dsp_incremental_common import (
        DEFAULT_BACKFILL_START_DATE,
        get_supabase_config,
        parse_date,
        read_latest_work_date,
        resolve_table,
        raise_for_supabase_error,
        supabase_headers,
    )
except ModuleNotFoundError:
    from dsp_incremental_common import (
        DEFAULT_BACKFILL_START_DATE,
        get_supabase_config,
        parse_date,
        read_latest_work_date,
        resolve_table,
        raise_for_supabase_error,
        supabase_headers,
    )


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-drivers-detail"
TARGET_TABLE_CANDIDATES = [
    "dsp_driver_detail_raw",
]


def month_dates(month_text, include_future=False):
    year, month = map(int, month_text.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    today = date.today()

    for day in range(1, last_day + 1):
        current = date(year, month, day)

        if not include_future and current > today:
            break

        yield current


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


def build_kifli_url(driver_id, work_date):
    return (
        f"{KIFLI_API_BASE_URL}/"
        f"fetch-drivers-detail/{driver_id}/{work_date.isoformat()}"
        f"?organizationId={ORGANIZATION_ID}"
    )


def build_attendance_url(work_date):
    return (
        f"{KIFLI_API_BASE_URL}/"
        f"fetch-attendance/{DSP_ID}/{work_date.isoformat()}"
        f"?organizationId={ORGANIZATION_ID}"
    )


def fetch_attendance(work_date):
    url = build_attendance_url(work_date)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def get_driver_ids_for_date(work_date):
    data = fetch_attendance(work_date)
    driver_ids = []

    for courier in data.get("couriers", []) or []:
        courier_id = courier.get("courierId")

        if courier_id is not None:
            driver_ids.append(int(courier_id))

    return sorted(set(driver_ids))


def fetch_driver_detail(driver_id, work_date):
    url = build_kifli_url(driver_id, work_date)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return url, response.status_code, response.json()


def is_statement_timeout(exc):
    text = str(exc).lower()
    return "57014" in text or "statement timeout" in text or "canceling statement" in text


def post_raw_rows(endpoint, headers, rows, table_name, retries=3):
    last_error = None

    for attempt in range(1, retries + 1):
        response = requests.post(
            endpoint,
            headers=headers,
            json=rows,
            timeout=120,
        )

        try:
            raise_for_supabase_error(response, table_name)
            return
        except requests.HTTPError as exc:
            last_error = exc

            if not is_statement_timeout(exc) or attempt >= retries:
                break

            wait_seconds = attempt * 3
            print(
                f"Supabase timeout, ujraprobalas {wait_seconds} mp mulva "
                f"({attempt}/{retries})..."
            )
            time.sleep(wait_seconds)

    raise last_error


def upsert_raw_rows(rows):
    if not rows:
        return 0

    supabase_url, _supabase_key = get_supabase_config()
    table_name = resolve_table(TARGET_TABLE_CANDIDATES)
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?on_conflict=source_name,driver_id,work_date"
    )
    headers = supabase_headers(
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
    )
    try:
        post_raw_rows(endpoint, headers, rows, table_name)
    except requests.HTTPError as exc:
        if len(rows) <= 1 or not is_statement_timeout(exc):
            raise

        middle = len(rows) // 2
        print(
            f"Supabase timeout {len(rows)} soros csomagnal, "
            f"felezes: {middle} + {len(rows) - middle} sor."
        )
        upsert_raw_rows(rows[:middle])
        upsert_raw_rows(rows[middle:])

    return len(rows)


def build_raw_row(driver_id, work_date, request_url, status_code, response_json):
    return {
        "source_name": SOURCE_NAME,
        "organization_id": ORGANIZATION_ID,
        "dsp_id": DSP_ID,
        "driver_id": int(driver_id),
        "work_date": work_date.isoformat(),
        "request_url": request_url,
        "status_code": int(status_code),
        "response_json": response_json,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def resolve_work_dates(args):
    if args.start_date or args.end_date:
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date) or start_date

        if start_date is None:
            raise ValueError("Ha --end-date van megadva, akkor --start-date is kell.")

        if end_date < start_date:
            raise ValueError("--end-date nem lehet kisebb, mint --start-date.")

        return list(date_range(start_date, end_date))

    if args.from_latest:
        table_name, latest_date = read_latest_work_date(TARGET_TABLE_CANDIDATES)
        start_date = latest_date or DEFAULT_BACKFILL_START_DATE
        end_date = date.today()
        print(
            f"Driver-detail inkrementalis indulas: tabla={table_name}, start={start_date}, end={end_date}"
        )
        return list(date_range(start_date, end_date))

    if args.month:
        return list(month_dates(args.month, include_future=args.include_future))

    raise ValueError("Adj meg --month, --from-latest vagy --start-date/--end-date erteket.")


def main():
    parser = argparse.ArgumentParser(
        description="fetch-drivers-detail raw feltoltes Supabase DB-be."
    )
    parser.add_argument("--driver-id", required=False, help="Futar ID, pelda: 7688")
    parser.add_argument(
        "--all-drivers",
        action="store_true",
        help="Az adott nap attendance-ben lathato osszes futarjat feltolti.",
    )
    parser.add_argument("--month", required=False, help="Honap YYYY-MM formatumban.")
    parser.add_argument("--start-date", required=False, help="Kezdo datum YYYY-MM-DD.")
    parser.add_argument("--end-date", required=False, help="Zaro datum YYYY-MM-DD.")
    parser.add_argument(
        "--from-latest",
        action="store_true",
        help="A DB-ben talalhato legutolso work_date naptol indul.",
    )
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Honap modban jovobeli napokat is megprobal.",
    )
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.driver_id and not args.all_drivers:
        parser.error("Adj meg --driver-id erteket vagy hasznald a --all-drivers kapcsolot.")

    try:
        work_dates = resolve_work_dates(args)
    except ValueError as exc:
        parser.error(str(exc))

    pending_rows = []
    fetched_count = 0
    failed_count = 0

    for work_date in work_dates:
        if args.all_drivers:
            try:
                driver_ids = get_driver_ids_for_date(work_date)
                print(f"ATTENDANCE {work_date.isoformat()}: {len(driver_ids)} futar")
            except Exception as exc:
                failed_count += 1
                print(f"HIBA attendance {work_date.isoformat()}: {exc}")
                continue
        else:
            driver_ids = [int(args.driver_id)]

        for driver_id in driver_ids:
            try:
                request_url, status_code, response_json = fetch_driver_detail(
                    driver_id,
                    work_date,
                )
                pending_rows.append(
                    build_raw_row(
                        driver_id,
                        work_date,
                        request_url,
                        status_code,
                        response_json,
                    )
                )
                fetched_count += 1
                print(f"OK driver-detail {driver_id} {work_date.isoformat()}")
            except Exception as exc:
                failed_count += 1
                print(f"HIBA driver-detail {driver_id} {work_date.isoformat()}: {exc}")

            if len(pending_rows) >= args.batch_size:
                if not args.dry_run:
                    upsert_raw_rows(pending_rows)

                print(
                    f"{'DRY RUN, DB iras kihagyva' if args.dry_run else 'DB feltoltes'}: {len(pending_rows)} sor"
                )
                pending_rows = []

    if pending_rows:
        if not args.dry_run:
            upsert_raw_rows(pending_rows)

        print(
            f"{'DRY RUN, DB iras kihagyva' if args.dry_run else 'DB feltoltes'}: {len(pending_rows)} sor"
        )

    print(f"Kesz. Sikeres driver-detail sorok: {fetched_count}, hibak: {failed_count}")


if __name__ == "__main__":
    main()
