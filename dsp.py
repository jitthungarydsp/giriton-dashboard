import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.dsp_incremental_common import (
    DEFAULT_BACKFILL_START_DATE,
    get_setting,
    parse_date,
    read_latest_work_date_across,
)


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
ATTENDANCE_TABLES = [
    "raw_dsp_attendance",
    "dsp_attendance_raw",
]
DRIVER_DETAIL_TABLES = [
    "raw_dsp_driver_detail",
    "dsp_driver_detail_raw",
]


def local_today():
    return datetime.now(LOCAL_TIMEZONE).date()


def run_command(name, command, optional=False):
    print("")
    print(f"=== {name} ===")
    print(" ".join(str(part) for part in command))
    sys.stdout.flush()

    try:
        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if optional:
            print(f"{name} kihagyva / hibaval leallt: {exc}")
            return False

        raise

    return True


def resolve_date_range(args):
    end_date = parse_date(args.end_date) or local_today()

    if args.start_date:
        start_date = parse_date(args.start_date)

        if start_date is None:
            raise ValueError("Hibas --start-date. Formatum: YYYY-MM-DD.")
    elif not args.no_from_latest:
        latest_rows, latest_date = read_latest_work_date_across(
            [
                ATTENDANCE_TABLES,
                DRIVER_DETAIL_TABLES,
            ]
        )

        for table_name, work_date in latest_rows:
            print(f"Legutolso DB datum: {table_name} -> {work_date or 'nincs adat'}")

        start_date = latest_date or DEFAULT_BACKFILL_START_DATE
    else:
        start_date = end_date.replace(day=1)

    if start_date > end_date:
        start_date = end_date

    return start_date, end_date


def optional_database_url_exists():
    return bool(
        str(get_setting("DATABASE_URL") or "").strip()
        or str(get_setting("SUPABASE_DB_URL") or "").strip()
    )


def build_common_date_args(start_date, end_date):
    return [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "DSP DB pipeline. Nem ir Google Sheetbe, hanem Supabase raw/stage/mart "
            "tablakat frissit inkrementalisan."
        )
    )
    parser.add_argument("--start-date", help="Kezdo datum YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Zaro datum YYYY-MM-DD. Alap: mai nap.")
    parser.add_argument(
        "--no-from-latest",
        action="store_true",
        help=(
            "Ne a DB legutolso work_date erteketol induljon. "
            "Ha nincs --start-date, akkor az aktualis honap elso napjatol indul."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="API-t hiv, de DB-be nem ir.")
    parser.add_argument("--skip-live", action="store_true", help="fetch-drivers live km kihagyasa.")
    parser.add_argument("--skip-distance", action="store_true", help="Route kilometer szamitas kihagyasa.")
    parser.add_argument(
        "--run-sql-refresh",
        action="store_true",
        help="A regi direkt Postgres SQL stage/mart frissitest is futtatja, ha van DATABASE_URL/SUPABASE_DB_URL.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Kompatibilitasi opcio: nem futtat SQL refresh-t.",
    )
    parser.add_argument("--skip-stories", action="store_true", help="Route story epites kihagyasa.")
    parser.add_argument(
        "--stories-only",
        action="store_true",
        help="Csak a mart_dsp_route_stories epiteset futtatja a mar meglevo raw/stage adatokbol.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        start_date, end_date = resolve_date_range(args)
    except Exception as exc:
        print(f"DSP datum meghatarozas hiba: {exc}")
        sys.exit(1)

    print("")
    print(f"DSP DB frissites: {start_date.isoformat()} - {end_date.isoformat()}")
    print("Google Sheet iras: kikapcsolva.")
    sys.stdout.flush()

    date_args = build_common_date_args(start_date, end_date)
    dry_run_arg = ["--dry-run"] if args.dry_run else []

    if not args.stories_only:
        run_command(
            "Attendance raw DB frissites",
            [
                sys.executable,
                "scripts/dsp_attendance_raw.py",
                *date_args,
                *dry_run_arg,
            ],
        )
        run_command(
            "Driver detail raw DB frissites",
            [
                sys.executable,
                "scripts/load_driver_detail_raw.py",
                "--all-drivers",
                *date_args,
                *dry_run_arg,
            ],
        )

        if not args.skip_live:
            run_command(
                "Live DSP route/km snapshot",
                [
                    sys.executable,
                    "scripts/load_drivers_live_raw.py",
                    *dry_run_arg,
                ],
            )

        if not args.skip_distance:
            run_command(
                "Route kilometer szamitas",
                [
                    sys.executable,
                    "scripts/calculate_route_distances.py",
                    *date_args,
                    *dry_run_arg,
                ],
            )

        if args.run_sql_refresh and not args.skip_refresh:
            if optional_database_url_exists():
                run_command(
                    "DSP stage/mart SQL frissites",
                    [
                        sys.executable,
                        "scripts/dsp_refresh_all.py",
                    ],
                    optional=True,
                )
            else:
                print("")
                print("DSP stage/mart SQL frissites kihagyva: nincs DATABASE_URL/SUPABASE_DB_URL.")
        else:
            print("")
            print("DSP stage/mart SQL frissites alapbol kikapcsolva. Kapcsolo: --run-sql-refresh")
    else:
        print("")
        print("Csak DSP route story frissites fut (--stories-only).")

    if not args.skip_stories:
        route_story_date_args = (
            date_args
            if args.start_date or args.end_date or args.no_from_latest
            else []
        )
        run_command(
            "DSP route story frissites",
            [
                sys.executable,
                "scripts/build_dsp_route_stories.py",
                *route_story_date_args,
                "--raw",
                *dry_run_arg,
            ],
        )

    print("")
    print("DSP DB pipeline kesz.")


if __name__ == "__main__":
    main()
