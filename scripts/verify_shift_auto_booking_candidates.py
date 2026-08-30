from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from page import foglalas_streamlit as foglalas
from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_auto_booking import (
    ROBOTLOG_SUCCESS_STATUSES,
    latest_log_by_serial,
    read_giriton_booking_log,
)
from resources.giriton_shifts_db import read_giriton_shifts_raw


def clean(value) -> str:
    return str(value or "").strip()


def load_candidates(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Nincs candidate fájl: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("A candidate fájl nem JSON lista.")
    return [dict(item or {}) for item in data]


def candidate_date_range(candidates: list[dict]) -> tuple[str, str]:
    dates = sorted(
        value
        for value in {clean(item.get("work_date")) for item in candidates}
        if value
    )
    if not dates:
        raise ValueError("A candidate listában nincs work_date.")
    return dates[0], dates[-1]


def build_summary(start_date: str, end_date: str, tolerance_minutes: int, source_limit: int) -> pd.DataFrame:
    muszakpro_df = read_foglalasok_raw(start_date=start_date, end_date=end_date, limit=source_limit)
    giriton_df = read_giriton_shifts_raw(start_date=start_date, end_date=end_date, limit=source_limit)
    if not muszakpro_df.empty:
        muszakpro_df = muszakpro_df.copy()
        muszakpro_df["shift_start"] = muszakpro_df.get(
            "shift_text",
            pd.Series(dtype=str),
        ).map(foglalas._shift_start)
    return foglalas._build_summary_rows(muszakpro_df, giriton_df, tolerance_minutes)


def summary_booked_serials(summary_df: pd.DataFrame) -> set[str]:
    if summary_df.empty or "Serial" not in summary_df.columns:
        return set()
    booked_rows = summary_df[
        summary_df.get("Állapot", pd.Series(dtype=str)).fillna("").astype(str).eq("Lefoglalva")
    ]
    return {
        clean(value)
        for value in booked_rows["Serial"].fillna("").astype(str)
        if clean(value)
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visszaellenőrzi, hogy a foglaló robot candidate sorai lefoglalt állapotba kerültek-e."
    )
    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--phase", default="booking")
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    candidates = load_candidates(Path(args.candidate_file))
    print(f"SHIFT_AUTO_VERIFY phase={args.phase} candidates={len(candidates)}")
    if not candidates:
        return

    start_date, end_date = candidate_date_range(candidates)
    summary_df = build_summary(start_date, end_date, args.tolerance_minutes, args.source_limit)
    booked_serials = summary_booked_serials(summary_df)
    log_df = read_giriton_booking_log(start_date=start_date, end_date=end_date, limit=5000)
    latest_logs = latest_log_by_serial(log_df)

    ok_count = 0
    pending = []
    for candidate in candidates:
        serial = clean(candidate.get("serial"))
        log_status = clean(latest_logs.get(serial, {}).get("status")).upper()
        log_ok = log_status in ROBOTLOG_SUCCESS_STATUSES
        db_ok = serial in booked_serials
        label = (
            f"{clean(candidate.get('work_date'))} "
            f"{clean(candidate.get('warehouse')).upper()} "
            f"{clean(candidate.get('shift_start'))} "
            f"{clean(candidate.get('courier_name'))} "
            f"serial={serial}"
        )

        if db_ok:
            print(f"SHIFT_AUTO_VERIFY_OK source=db {label}")
            ok_count += 1
            continue

        if log_ok:
            print(f"SHIFT_AUTO_VERIFY_OK source=robotlog status={log_status} {label}")
            ok_count += 1
            continue

        print(f"SHIFT_AUTO_VERIFY_PENDING status={log_status or '-'} {label}")
        pending.append(label)

    print(
        "SHIFT_AUTO_VERIFY_DONE "
        f"phase={args.phase} ok={ok_count} pending={len(pending)} "
        f"checked_at={datetime.utcnow().isoformat(timespec='seconds')}Z"
    )
    if pending and args.fail_on_missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
