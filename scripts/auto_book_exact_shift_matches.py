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
RUNNING_LOG_BLOCK_MINUTES = 120


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


def lead_start_date(today: date, min_lead_hours: int) -> date:
    days = max((max(int(min_lead_hours), 1) + 23) // 24, 1)
    return today + timedelta(days=days)


def parse_log_datetime(value) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed


def is_recent_running_log(item: dict, now: datetime) -> bool:
    status = clean(item.get("status"))
    if not status.startswith("STEP_"):
        return False
    created_at = parse_log_datetime(item.get("created_at"))
    if created_at is None:
        return False
    age_minutes = (now.astimezone(created_at.tzinfo) - created_at).total_seconds() / 60
    return 0 <= age_minutes <= RUNNING_LOG_BLOCK_MINUTES


def load_exact_matches(
    start_date: date,
    end_date: date,
    min_lead_hours: int,
    tolerance_minutes: int,
    limit: int,
    source_limit: int,
) -> pd.DataFrame:
    muszakpro_df = read_foglalasok_raw(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=max(int(source_limit), 1),
    )
    giriton_df = read_giriton_shifts_raw(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=max(int(source_limit), 1),
    )
    summary_df = foglalas._build_summary_rows(
        muszakpro_df,
        giriton_df,
        int(tolerance_minutes),
    )
    print(
        "AUTO_EXACT_DIAG "
        f"muszakpro_rows={len(muszakpro_df)} giriton_rows={len(giriton_df)} "
        f"summary_rows={len(summary_df)}"
    )
    if summary_df.empty:
        return summary_df

    first_bookable_date = lead_start_date(datetime.now(BUDAPEST_TZ).date(), min_lead_hours)
    summary_df = summary_df.copy()
    summary_df["_work_date"] = summary_df["Dátum"].apply(foglalas._date_from_value)
    print(
        "AUTO_EXACT_DIAG "
        f"summary_statuses={summary_df['Állapot'].value_counts(dropna=False).to_dict() if 'Állapot' in summary_df.columns else {}}"
    )
    exact_all = summary_df[summary_df["Állapot"].astype(str).eq("Egyezés")].copy()
    exact_from_lead = exact_all[
        exact_all["_work_date"].notna()
        & (exact_all["_work_date"] >= first_bookable_date)
    ].copy()
    if not summary_df.empty:
        sample_columns = [
            column
            for column in ["Dátum", "Dolgozó", "Raktár", "MűszakPro", "Giriton ajánlat", "Giriton foglalás", "Giriton állapot", "Eltérés", "Állapot", "Ok", "Serial"]
            if column in summary_df.columns
        ]
        sample = summary_df.head(5)[sample_columns].to_dict("records")
        print(f"AUTO_EXACT_DIAG sample_rows={sample}")
    print(
        "AUTO_EXACT_DIAG "
        f"exact_all={len(exact_all)} exact_from_{first_bookable_date}={len(exact_from_lead)} "
        f"exact_giriton_states={exact_from_lead['Giriton állapot'].value_counts(dropna=False).to_dict() if 'Giriton állapot' in exact_from_lead.columns else {}}"
    )
    rows = foglalas._bookable_booking_rows(summary_df)
    print(
        "AUTO_EXACT_DIAG "
        f"bookable_all={len(rows)} "
        f"bookable_statuses={rows['Állapot'].value_counts(dropna=False).to_dict() if not rows.empty and 'Állapot' in rows.columns else {}}"
    )
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
    rows["_work_date"] = rows["Dátum"].apply(foglalas._date_from_value)
    rows = rows[
        rows["_shift_datetime"].notna()
        & rows["_work_date"].notna()
        & (rows["_work_date"] >= first_bookable_date)
    ].copy()
    print(
        "AUTO_EXACT_DIAG "
        f"bookable_exact_from_{first_bookable_date}={len(rows)}"
    )
    if rows.empty:
        return rows

    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=5000,
    )
    latest_by_serial = latest_log_by_serial(log_df)
    if latest_by_serial:
        now_utc = datetime.now(ZoneInfo("UTC"))
        blocked_serials = {
            serial
            for serial, item in latest_by_serial.items()
            if clean(item.get("status")) in ROBOTLOG_SUCCESS_STATUSES
            or is_recent_running_log(item, now_utc)
        }
        before_log_filter = len(rows)
        rows = rows[
            ~rows["Serial"].fillna("").astype(str).str.strip().isin(blocked_serials)
        ].copy()
        print(
            "AUTO_EXACT_DIAG "
            f"log_rows={len(log_df)} blocked_serials={len(blocked_serials)} "
            f"after_log_filter={len(rows)} removed_by_log={before_log_filter - len(rows)}"
        )

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
        description="Legalább 72 órával későbbi, pontos műszakfoglalási egyezések automatikus indítása."
    )
    parser.add_argument("--start-date", default="", help="Kezdő dátum YYYY-MM-DD. Alap: ma.")
    parser.add_argument("--end-date", default="", help="Záró dátum YYYY-MM-DD. Alap: ma + lookahead-days.")
    parser.add_argument("--lookahead-days", type=int, default=5)
    parser.add_argument("--min-lead-hours", type=int, default=72)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--ref", default=clean(os.getenv("GITHUB_REF")) or DEFAULT_REF)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today)
    default_end = today + timedelta(days=max(int(args.lookahead_days), 1))
    end_date = parse_date(args.end_date, default_end)

    rows = load_exact_matches(
        start_date=start_date,
        end_date=end_date,
        min_lead_hours=args.min_lead_hours,
        tolerance_minutes=args.tolerance_minutes,
        limit=args.limit,
        source_limit=args.source_limit,
    )
    print(
        "AUTO_EXACT_MATCHES "
        f"start={start_date} end={end_date} min_lead_hours={args.min_lead_hours} "
        f"first_bookable_date={lead_start_date(today, args.min_lead_hours)} "
        f"lookahead_days={args.lookahead_days} source_limit={args.source_limit} "
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
