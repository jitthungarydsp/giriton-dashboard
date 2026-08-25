from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from page import foglalas_streamlit as foglalas
from resources.giriton_auto_booking import (
    ROBOTLOG_SUCCESS_STATUSES,
    latest_log_by_serial,
    read_giriton_booking_log,
)
from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_shifts_db import read_giriton_shifts_raw


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
DEFAULT_OWNER = "jitthungarydsp"
DEFAULT_REPO = "giriton-dashboard"
DEFAULT_REF = "main"
DEFAULT_WORKFLOW = "giriton-auto-booking.yml"


def clean(value) -> str:
    return str(value or "").strip()


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def parse_shift_datetime(work_date, shift_start) -> datetime | None:
    work_day = foglalas._date_from_value(work_date)
    start_text = foglalas._normalize_time(shift_start)
    if work_day is None or not start_text:
        return None
    try:
        hour, minute = [int(part) for part in start_text.split(":", 1)]
    except ValueError:
        return None
    return datetime.combine(work_day, time(hour, minute), tzinfo=BUDAPEST_TZ)


def load_exact_matches(
    start_date: date,
    end_date: date,
    horizon_hours: int,
    tolerance_minutes: int,
    limit: int,
) -> pd.DataFrame:
    muszakpro_df = read_foglalasok_raw(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=max(int(limit), 1),
    )
    giriton_df = read_giriton_shifts_raw(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=max(int(limit), 1),
    )
    summary_df = foglalas._build_summary_rows(
        muszakpro_df,
        giriton_df,
        int(tolerance_minutes),
    )
    if summary_df.empty:
        return summary_df

    now = datetime.now(BUDAPEST_TZ)
    horizon_end = now + timedelta(hours=max(int(horizon_hours), 1))
    rows = foglalas._bookable_booking_rows(summary_df)
    if rows.empty:
        return rows

    rows = rows[rows["Állapot"].astype(str).eq("Egyezés")].copy()
    if rows.empty:
        return rows

    rows["_target_shift_start"] = rows.apply(
        lambda row: foglalas._booking_target_shift_start(row.to_dict()),
        axis=1,
    )
    rows["_shift_datetime"] = rows.apply(
        lambda row: parse_shift_datetime(row.get("Dátum"), row.get("_target_shift_start")),
        axis=1,
    )
    rows = rows[
        rows["_shift_datetime"].notna()
        & (rows["_shift_datetime"] >= now)
        & (rows["_shift_datetime"] <= horizon_end)
    ].copy()
    if rows.empty:
        return rows

    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=5000,
    )
    latest_by_serial = latest_log_by_serial(log_df)
    if latest_by_serial:
        blocked_serials = {
            serial
            for serial, item in latest_by_serial.items()
            if clean(item.get("status")) in ROBOTLOG_SUCCESS_STATUSES
            or clean(item.get("status")).startswith("STEP_")
        }
        rows = rows[
            ~rows["Serial"].fillna("").astype(str).str.strip().isin(blocked_serials)
        ].copy()

    rows = rows.sort_values(["_shift_datetime", "Raktár", "Dolgozó", "Serial"])
    return rows.head(max(int(limit), 1))


def github_token() -> str:
    for name in ["GITHUB_TOKEN", "GITHUB_ACTIONS_TOKEN", "GH_TOKEN", "GITHUB_PAT"]:
        value = clean(os.getenv(name))
        if value:
            return value
    raise RuntimeError(
        "Hiányzik a GitHub token. Add meg valamelyiket: GITHUB_TOKEN, "
        "GITHUB_ACTIONS_TOKEN, GH_TOKEN vagy GITHUB_PAT."
    )


def dispatch_auto_booking(row: dict, workflow: str, ref: str) -> str:
    owner = clean(os.getenv("GITHUB_OWNER")) or DEFAULT_OWNER
    repo = clean(os.getenv("GITHUB_REPO")) or DEFAULT_REPO
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
    inputs = {
        "start_date": clean(row.get("Dátum")),
        "end_date": clean(row.get("Dátum")),
        "serial": clean(row.get("Serial")),
        "warehouse": clean(row.get("Raktár")).upper(),
        "email": clean(row.get("E-mail")).casefold(),
        "shift_start": clean(row.get("_target_shift_start")),
        "dry_run": "false",
    }
    response = requests.post(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token()}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": ref, "inputs": inputs},
        timeout=30,
    )
    if response.status_code != 204:
        raise RuntimeError(
            f"GitHub workflow indítás sikertelen: HTTP {response.status_code} - {response.text[:500]}"
        )
    return (
        f"{inputs['work_date'] if 'work_date' in inputs else inputs['start_date']} "
        f"{inputs['warehouse']} {inputs['shift_start']} "
        f"{clean(row.get('Dolgozó'))} serial={inputs['serial']}"
    )


def main() -> None:
    today = datetime.now(BUDAPEST_TZ).date()
    parser = argparse.ArgumentParser(
        description="Következő 72 órás, pontos műszakfoglalási egyezések automatikus indítása."
    )
    parser.add_argument("--start-date", default="", help="Kezdő dátum YYYY-MM-DD. Alap: ma.")
    parser.add_argument("--end-date", default="", help="Záró dátum YYYY-MM-DD. Alap: ma + horizon.")
    parser.add_argument("--horizon-hours", type=int, default=72)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--ref", default=clean(os.getenv("GITHUB_REF")) or DEFAULT_REF)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today)
    default_end = today + timedelta(days=max((int(args.horizon_hours) + 23) // 24, 1))
    end_date = parse_date(args.end_date, default_end)

    rows = load_exact_matches(
        start_date=start_date,
        end_date=end_date,
        horizon_hours=args.horizon_hours,
        tolerance_minutes=args.tolerance_minutes,
        limit=args.limit,
    )
    print(
        "AUTO_EXACT_MATCHES "
        f"start={start_date} end={end_date} horizon_hours={args.horizon_hours} "
        f"matches={len(rows)} dry_run={args.dry_run}"
    )
    if rows.empty:
        return

    for row in rows.to_dict("records"):
        label = (
            f"{clean(row.get('Dátum'))} {clean(row.get('Raktár')).upper()} "
            f"{clean(row.get('_target_shift_start'))} {clean(row.get('Dolgozó'))} "
            f"serial={clean(row.get('Serial'))}"
        )
        if args.dry_run:
            print(f"DRY_RUN would_dispatch {label}")
            continue
        result = dispatch_auto_booking(row, workflow=args.workflow, ref=args.ref)
        print(f"DISPATCHED {result}")


if __name__ == "__main__":
    main()
