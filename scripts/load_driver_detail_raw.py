import argparse
import calendar
import os
from datetime import date, datetime

import requests


DSP_ID = "JIT"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
KIFLI_API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
SOURCE_NAME = "fetch-drivers-detail"


def month_dates(month_text, include_future=False):
    year, month = map(int, month_text.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    today = date.today()

    for day in range(1, last_day + 1):
        current = date(year, month, day)

        if not include_future and current > today:
            break

        yield current


def parse_date(value):
    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d",
    ).date()


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current = date.fromordinal(
            current.toordinal() + 1
        )


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
    url = build_attendance_url(
        work_date
    )
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return response.json()


def get_driver_ids_for_date(work_date):
    data = fetch_attendance(
        work_date
    )

    driver_ids = []

    for courier in data.get("couriers", []):
        courier_id = courier.get("courierId")

        if courier_id is not None:
            driver_ids.append(
                int(courier_id)
            )

    return sorted(
        set(driver_ids)
    )


def fetch_driver_detail(driver_id, work_date):
    url = build_kifli_url(
        driver_id,
        work_date,
    )
    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return url, response.status_code, response.json()


def get_required_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Hianyzik a(z) {name} kornyezeti valtozo."
        )

    return value.rstrip("/")


def upsert_raw_rows(rows):
    if not rows:
        return

    supabase_url = get_required_env("SUPABASE_URL")
    supabase_key = get_required_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = (
        f"{supabase_url}/rest/v1/dsp_driver_detail_raw"
        f"?on_conflict=source_name,driver_id,work_date"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=rows,
        timeout=60,
    )
    response.raise_for_status()


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


def main():
    parser = argparse.ArgumentParser(
        description="fetch-drivers-detail raw havi feltoltes Supabase DB-be."
    )
    parser.add_argument(
        "--driver-id",
        required=False,
        help="Futar ID, pelda: 7688",
    )
    parser.add_argument(
        "--all-drivers",
        action="store_true",
        help="Az adott honap minden attendance-ben lathato futarjat feltolti.",
    )
    parser.add_argument(
        "--month",
        required=False,
        help="Honap YYYY-MM formatumban, pelda: 2026-07",
    )
    parser.add_argument(
        "--start-date",
        required=False,
        help="Kezdo datum YYYY-MM-DD formatumban.",
    )
    parser.add_argument(
        "--end-date",
        required=False,
        help="Zaro datum YYYY-MM-DD formatumban.",
    )
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Ha be van kapcsolva, a honap jovobeli napjait is megprobalja.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Ennyi sort kuld egyszerre Supabase-be.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak API-t hiv, DB-be nem ir.",
    )
    args = parser.parse_args()

    if not args.driver_id and not args.all_drivers:
        parser.error(
            "Adj meg --driver-id erteket vagy hasznald a --all-drivers kapcsolot."
        )

    if args.start_date or args.end_date:
        start_date = parse_date(
            args.start_date
        )
        end_date = parse_date(
            args.end_date
        ) or start_date

        if start_date is None:
            parser.error(
                "Ha --end-date van megadva, akkor --start-date is kell."
            )

        if end_date < start_date:
            parser.error(
                "--end-date nem lehet kisebb, mint --start-date."
            )

        work_dates = list(
            date_range(
                start_date,
                end_date,
            )
        )
    elif args.month:
        work_dates = list(
            month_dates(
                args.month,
                include_future=args.include_future,
            )
        )
    else:
        parser.error(
            "Adj meg --month vagy --start-date/--end-date erteket."
        )

    pending_rows = []
    fetched_count = 0
    failed_count = 0

    for work_date in work_dates:
        if args.all_drivers:
            try:
                driver_ids = get_driver_ids_for_date(
                    work_date
                )
                print(
                    f"ATTENDANCE {work_date.isoformat()}: {len(driver_ids)} futar"
                )
            except Exception as exc:
                failed_count += 1
                print(
                    f"HIBA attendance {work_date.isoformat()}: {exc}"
                )
                continue
        else:
            driver_ids = [
                int(args.driver_id)
            ]

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
                print(
                    f"OK {driver_id} {work_date.isoformat()}"
                )
            except Exception as exc:
                failed_count += 1
                print(
                    f"HIBA {driver_id} {work_date.isoformat()}: {exc}"
                )

            if len(pending_rows) >= args.batch_size:
                if not args.dry_run:
                    upsert_raw_rows(
                        pending_rows
                    )
                print(
                    f"{'DRY RUN, DB iras kihagyva' if args.dry_run else 'DB feltoltes'}: {len(pending_rows)} sor"
                )
                pending_rows = []

    if pending_rows:
        if not args.dry_run:
            upsert_raw_rows(
                pending_rows
            )
        print(
            f"{'DRY RUN, DB iras kihagyva' if args.dry_run else 'DB feltoltes'}: {len(pending_rows)} sor"
        )

    print(
        f"Kesz. Sikeres napok: {fetched_count}, hibas napok: {failed_count}"
    )


if __name__ == "__main__":
    main()
