from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from page import foglalas_streamlit as foglalas
from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_auto_booking import (
    LOG_TABLE,
    ROBOTLOG_SUCCESS_STATUSES,
    latest_log_by_serial,
    read_giriton_booking_log,
)
from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)
from resources.giriton_shifts_db import read_giriton_shifts_raw
from scripts.auto_book_exact_shift_matches import is_recent_running_log


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
SHIFT_COMPARISON_TABLE = "ops_shift_comparison"
SHIFT_COMPARISON_SOURCE = "shift-auto-booking-selector"


def clean(value) -> str:
    return str(value or "").strip()


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def db_time(value):
    text = foglalas._normalize_time(value)
    if not text:
        return None
    if len(text) == 4:
        text = f"0{text}"
    if len(text) == 5:
        return f"{text}:00"
    return text


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
    try:
        summary_logged = log_summary_to_shift_comparison(summary_df, start_date, end_date)
        print(f"SHIFT_AUTO_SELECT_COMPARISON_DB_LOGGED rows={summary_logged}")
    except Exception as exc:
        print(f"SHIFT_AUTO_SELECT_COMPARISON_DB_LOG_FAILED {type(exc).__name__}: {exc}")
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


def optional_int(value):
    text = clean(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def comparison_key_from_summary_row(row: dict) -> str:
    serial = clean(row.get("Serial"))
    person = (
        clean(row.get("Courier ID"))
        or courier_id_from_serial(serial)
        or clean(row.get("E-mail")).casefold()
        or clean(row.get("Dolgozó")).casefold()
    )
    return "|".join([
        SHIFT_COMPARISON_SOURCE,
        clean(row.get("Dátum")),
        person,
        clean(row.get("Raktár")).upper(),
        foglalas._normalize_time(row.get("MűszakPro")) or clean(row.get("MűszakPro")),
        serial,
    ])


def shift_comparison_row_from_summary(row: dict, updated_at: str) -> dict:
    status = clean(row.get("Állapot"))
    giriton_state = clean(row.get("Giriton állapot"))
    muszakpro_shift_start = clean(row.get("MűszakPro"))
    giriton_offer = clean(row.get("Giriton ajánlat"))
    serial = clean(row.get("Serial"))
    courier_id = clean(row.get("Courier ID")) or courier_id_from_serial(serial)
    return {
        "source_name": SHIFT_COMPARISON_SOURCE,
        "comparison_key": comparison_key_from_summary_row(row),
        "work_date": clean(row.get("Dátum")) or None,
        "courier_id": optional_int(courier_id),
        "courier_name": clean(row.get("Dolgozó")),
        "email": clean(row.get("E-mail")).casefold(),
        "warehouse": clean(row.get("Raktár")).upper(),
        "shift_start": db_time(muszakpro_shift_start),
        "shift_end": None,
        "giriton_status": giriton_state or "-",
        "muszakpro_status": "OK" if muszakpro_shift_start and muszakpro_shift_start != "-" else "-",
        "missing_source": "" if status in {"Egyezés", "Alternatíva", "Lefoglalva"} else status,
        "giriton_check": status,
        "muszakpro_booking_code": "",
        "booking_recommendation_status": status,
        "giriton_offer": db_time(giriton_offer),
        "muszakpro_shift_start": db_time(muszakpro_shift_start),
        "difference_text": clean(row.get("Eltérés")),
        "recommendation_reason": clean(row.get("Ok")),
        "serial": serial,
        "source_summary": {
            "muszakpro_shift_start": muszakpro_shift_start,
            "giriton_booking": clean(row.get("Giriton foglalás")),
            "giriton_offer": giriton_offer,
            "giriton_state": giriton_state,
            "difference": clean(row.get("Eltérés")),
            "status": status,
            "reason": clean(row.get("Ok")),
            "serial": serial,
        },
        "updated_at": updated_at,
    }


def post_shift_comparison_rows(supabase_url: str, service_role_key: str, rows: list[dict]) -> requests.Response:
    return requests.post(
        f"{supabase_url}/rest/v1/{SHIFT_COMPARISON_TABLE}?on_conflict=comparison_key",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=rows,
        timeout=60,
    )


def strip_optional_shift_comparison_columns(rows: list[dict]) -> list[dict]:
    optional_columns = {
        "source_name",
        "booking_recommendation_status",
        "giriton_offer",
        "muszakpro_shift_start",
        "difference_text",
        "recommendation_reason",
        "serial",
    }
    return [
        {
            key: value
            for key, value in row.items()
            if key not in optional_columns
        }
        for row in rows
    ]


def delete_existing_shift_comparison_rows(supabase_url: str, service_role_key: str, start_date: date, end_date: date) -> None:
    response = requests.delete(
        (
            f"{supabase_url}/rest/v1/{SHIFT_COMPARISON_TABLE}"
            f"?source_name=eq.{SHIFT_COMPARISON_SOURCE}"
            f"&work_date=gte.{start_date.isoformat()}"
            f"&work_date=lte.{end_date.isoformat()}"
        ),
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Prefer": "return=minimal",
        },
        timeout=60,
    )
    if response.status_code == 400 and "source_name" in response.text:
        return
    raise_for_supabase_error(response)


def log_summary_to_shift_comparison(summary_df: pd.DataFrame, start_date: date, end_date: date) -> int:
    if summary_df.empty:
        return 0

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        print("SHIFT_AUTO_SELECT_COMPARISON_DB_LOG_SKIPPED missing_supabase_config")
        return 0

    updated_at = datetime.now(BUDAPEST_TZ).isoformat(timespec="seconds")
    rows = [
        shift_comparison_row_from_summary(row, updated_at)
        for row in summary_df.to_dict("records")
        if comparison_key_from_summary_row(row)
    ]
    if not rows:
        return 0

    delete_existing_shift_comparison_rows(
        supabase_url,
        service_role_key,
        start_date,
        end_date,
    )

    total = 0
    for index in range(0, len(rows), 500):
        batch = rows[index:index + 500]
        response = post_shift_comparison_rows(supabase_url, service_role_key, batch)
        if response.status_code == 400 and "column" in response.text.lower():
            response = post_shift_comparison_rows(
                supabase_url,
                service_role_key,
                strip_optional_shift_comparison_columns(batch),
            )
        raise_for_supabase_error(response)
        total += len(batch)

    return total


def strip_optional_log_columns(rows: list[dict]) -> list[dict]:
    optional_columns = {
        "match_kind",
        "recommendation_status",
        "muszakpro_shift_start",
        "giriton_offer",
    }
    return [
        {
            key: value
            for key, value in row.items()
            if key not in optional_columns
        }
        for row in rows
    ]


def post_log_rows(supabase_url: str, service_role_key: str, rows: list[dict]) -> requests.Response:
    return requests.post(
        f"{supabase_url}/rest/v1/{LOG_TABLE}",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=rows,
        timeout=60,
    )


def log_candidates_to_db(candidates: list[dict], *, match_kind: str, start_date: date, end_date: date) -> int:
    if not candidates:
        return 0

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        print("SHIFT_AUTO_SELECT_DB_LOG_SKIPPED missing_supabase_config")
        return 0

    selected_at = datetime.now(BUDAPEST_TZ).isoformat(timespec="seconds")
    github_run_id = clean(os.getenv("GITHUB_RUN_ID"))
    github_run_attempt = clean(os.getenv("GITHUB_RUN_ATTEMPT"))
    rows = []
    for candidate in candidates:
        warehouse = clean(candidate.get("warehouse")).upper()
        shift_start = clean(candidate.get("shift_start"))
        recommendation_status = clean(candidate.get("status")) or (
            "Egyezés" if match_kind == "exact" else "Alternatíva"
        )
        muszakpro_shift_start = clean(candidate.get("muszakpro_shift_start"))
        giriton_offer = clean(candidate.get("giriton_offer"))
        rows.append({
            "source_name": "shift-auto-booking-selector",
            "work_date": clean(candidate.get("work_date")) or None,
            "courier_id": optional_int(candidate.get("courier_id")),
            "courier_name": clean(candidate.get("courier_name")),
            "email": clean(candidate.get("email")).casefold(),
            "warehouse": warehouse,
            "shift_text": f"{warehouse}_{shift_start}" if warehouse and shift_start else shift_start,
            "shift_start": shift_start,
            "match_kind": clean(match_kind),
            "recommendation_status": recommendation_status,
            "muszakpro_shift_start": muszakpro_shift_start,
            "giriton_offer": giriton_offer,
            "booking_code": "",
            "serial": clean(candidate.get("serial")),
            "status": f"CANDIDATE_SELECTED_{clean(match_kind).upper()}",
            "message": (
                f"{recommendation_status}: MűszakPro {muszakpro_shift_start or '-'} "
                f"-> Giriton ajánlat {giriton_offer or shift_start or '-'}. "
                "A robot ezt a sort foglalásra kiválasztotta."
            ),
            "response_json": {
                "candidate": candidate,
                "match_kind": match_kind,
                "recommendation_status": recommendation_status,
                "muszakpro_shift_start": muszakpro_shift_start,
                "giriton_offer": giriton_offer,
                "selection_window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "selected_at": selected_at,
                "github_run_id": github_run_id,
                "github_run_attempt": github_run_attempt,
            },
        })

    response = post_log_rows(supabase_url, service_role_key, rows)
    if response.status_code == 400 and "column" in response.text.lower():
        response = post_log_rows(
            supabase_url,
            service_role_key,
            strip_optional_log_columns(rows),
        )
    raise_for_supabase_error(response)
    return len(rows)


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
    parser.add_argument("--start-date", default="", help="Kezdő nap YYYY-MM-DD. Alap: ma.")
    parser.add_argument("--days", type=int, default=3, help="Hány napot nézzen, a kezdőnappal együtt.")
    parser.add_argument("--match-kind", choices=["exact", "alternative"], required=True)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today)
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
    try:
        db_logged = log_candidates_to_db(
            candidates,
            match_kind=args.match_kind,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        db_logged = 0
        print(f"SHIFT_AUTO_SELECT_DB_LOG_FAILED {type(exc).__name__}: {exc}")
    print(
        "SHIFT_AUTO_SELECT "
        f"kind={args.match_kind} start={start_date} end={end_date} "
        f"days={args.days} candidates={len(candidates)} db_logged={db_logged} output={output_path}"
    )
    for candidate in candidates[:10]:
        print(f"SHIFT_AUTO_SELECT_ITEM {candidate}")


if __name__ == "__main__":
    main()
