from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

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
from scripts.auto_book_exact_shift_matches import is_recent_running_log


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def clean(value) -> str:
    return str(value or "").strip()


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def is_strict_exact_booking_row(row: pd.Series | dict) -> bool:
    data = row.to_dict() if hasattr(row, "to_dict") else dict(row or {})
    if clean(data.get("Állapot")) != "Egyezés":
        return False
    if clean(data.get("Giriton állapot")) != "Nincs lefoglalva":
        return False
    if clean(data.get("Eltérés")) not in {"0 perc", "0", ""}:
        return False

    muszakpro_start = foglalas._normalize_time(data.get("MűszakPro"))
    giriton_offer = foglalas._normalize_time(data.get("Giriton ajánlat"))
    return bool(muszakpro_start and giriton_offer and muszakpro_start == giriton_offer)


def load_summary(start_date: date, end_date: date, tolerance_minutes: int, source_limit: int) -> pd.DataFrame:
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
    if not muszakpro_df.empty:
        muszakpro_df = muszakpro_df.copy()
        muszakpro_df["shift_start"] = muszakpro_df.get(
            "shift_text",
            pd.Series(dtype=str),
        ).map(foglalas._shift_start)

    summary_df = foglalas._build_summary_rows(
        muszakpro_df,
        giriton_df,
        int(tolerance_minutes),
    )
    print(
        "SHIFT_AUTO_SELECT_DIAG "
        f"muszakpro_rows={len(muszakpro_df)} giriton_rows={len(giriton_df)} "
        f"summary_rows={len(summary_df)}"
    )
    return summary_df


def filter_already_running_or_done(rows: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if rows.empty:
        return rows

    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=5000,
    )
    latest_by_serial = latest_log_by_serial(log_df)
    if not latest_by_serial:
        return rows

    now_utc = datetime.now(ZoneInfo("UTC"))
    blocked_serials = {
        serial
        for serial, item in latest_by_serial.items()
        if clean(item.get("status")) in ROBOTLOG_SUCCESS_STATUSES
        or is_recent_running_log(item, now_utc)
    }
    if not blocked_serials:
        return rows

    before = len(rows)
    rows = rows[
        ~rows["Serial"].fillna("").astype(str).str.strip().isin(blocked_serials)
    ].copy()
    print(
        "SHIFT_AUTO_SELECT_DIAG "
        f"log_rows={len(log_df)} blocked_serials={len(blocked_serials)} "
        f"removed_by_log={before - len(rows)}"
    )
    return rows


def candidate_payload(row: dict) -> dict:
    serial = clean(row.get("Serial"))
    return {
        "work_date": clean(row.get("Dátum")),
        "warehouse": clean(row.get("Raktár")).upper(),
        "email": clean(row.get("E-mail")).casefold(),
        "shift_start": clean(row.get("_target_shift_start")),
        "serial": serial,
        "courier_id": clean(row.get("Courier ID")) or courier_id_from_serial(serial),
        "courier_name": clean(row.get("Dolgozó")),
        "status": clean(row.get("Állapot")),
        "muszakpro_shift_start": clean(row.get("MűszakPro")),
        "giriton_offer": clean(row.get("Giriton ajánlat")),
    }


def select_candidates(
    *,
    start_date: date,
    end_date: date,
    match_kind: str,
    tolerance_minutes: int,
    limit: int,
    source_limit: int,
) -> list[dict]:
    summary_df = load_summary(start_date, end_date, tolerance_minutes, source_limit)
    if summary_df.empty:
        return []

    print(
        "SHIFT_AUTO_SELECT_DIAG "
        f"summary_statuses={summary_df['Állapot'].value_counts(dropna=False).to_dict()}"
    )
    rows = foglalas._bookable_booking_rows(summary_df)
    if rows.empty:
        return []

    if match_kind == "exact":
        rows = rows[rows.apply(is_strict_exact_booking_row, axis=1)].copy()
    elif match_kind == "alternative":
        rows = rows[rows["Állapot"].astype(str).eq("Alternatíva")].copy()
    else:
        raise ValueError(f"Ismeretlen match_kind: {match_kind}")

    if rows.empty:
        return []

    rows["_target_shift_start"] = rows.apply(
        lambda row: foglalas._booking_target_shift_start(row.to_dict()),
        axis=1,
    )
    rows["_work_date"] = rows["Dátum"].apply(foglalas._date_from_value)
    rows = rows[
        rows["_work_date"].notna()
        & rows["Serial"].fillna("").astype(str).str.strip().ne("")
        & rows["_target_shift_start"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    rows = filter_already_running_or_done(rows, start_date, end_date)
    if rows.empty:
        return []

    rows = rows.sort_values(["Dátum", "Raktár", "_target_shift_start", "Dolgozó", "Serial"])
    return [
        candidate_payload(row)
        for row in rows.head(max(int(limit), 1)).to_dict("records")
    ]


def main() -> None:
    today = datetime.now(BUDAPEST_TZ).date()
    parser = argparse.ArgumentParser(
        description="Kiválasztja a következő 3 nap foglalható pontos vagy alternatív sorait."
    )
    parser.add_argument("--start-date", default="", help="Kezdő nap YYYY-MM-DD. Alap: holnap.")
    parser.add_argument("--days", type=int, default=3, help="Hány napot nézzen, a kezdőnappal együtt.")
    parser.add_argument("--match-kind", choices=["exact", "alternative"], required=True)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today + timedelta(days=1))
    end_date = start_date + timedelta(days=max(int(args.days), 1) - 1)
    candidates = select_candidates(
        start_date=start_date,
        end_date=end_date,
        match_kind=args.match_kind,
        tolerance_minutes=args.tolerance_minutes,
        limit=args.limit,
        source_limit=args.source_limit,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SHIFT_AUTO_SELECT "
        f"kind={args.match_kind} start={start_date} end={end_date} "
        f"days={args.days} candidates={len(candidates)} output={output_path}"
    )
    for candidate in candidates[:10]:
        print(f"SHIFT_AUTO_SELECT_ITEM {candidate}")


if __name__ == "__main__":
    main()
