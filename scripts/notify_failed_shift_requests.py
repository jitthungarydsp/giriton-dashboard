from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from page import foglalas_streamlit as foglalas
from resources.discord_notifier import send_discord_text_message_to_setting
from resources.giriton_auto_booking import (
    log_giriton_booking_result,
    read_giriton_booking_log,
)
from scripts.select_shift_auto_booking_candidates import load_summary


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
NOTIFIED_STATUS = "MANUAL_REQUEST_DISCORD_SENT"


def clean(value) -> str:
    return str(value or "").strip()


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def normalize_warehouse(value) -> str:
    text = clean(value).upper()
    if "BUD1" in text:
        return "BUD1"
    if "BUD2" in text:
        return "BUD2"
    return text


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def candidate_from_row(row: dict) -> dict:
    serial = clean(row.get("Serial"))
    warehouse = normalize_warehouse(row.get("Raktár"))
    shift_start = clean(row.get("MűszakPro"))
    return {
        "work_date": clean(row.get("Dátum")),
        "warehouse": warehouse,
        "shift_text": f"{warehouse}_{shift_start}" if warehouse and shift_start else shift_start,
        "shift_start": shift_start,
        "booking_code": "",
        "courier_id": clean(row.get("Courier ID")) or courier_id_from_serial(serial),
        "courier_name": clean(row.get("Dolgozó")),
        "email": clean(row.get("E-mail")).casefold(),
        "serial": serial,
    }


def filter_not_yet_notified(rows: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if rows.empty or "Serial" not in rows.columns:
        return rows

    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=10000,
    )
    notified_serials = set()
    if not log_df.empty and {"serial", "status"}.issubset(log_df.columns):
        notified_rows = log_df[
            log_df["status"].fillna("").astype(str).str.strip().str.upper().eq(NOTIFIED_STATUS)
        ]
        notified_serials = {
            clean(value)
            for value in notified_rows["serial"].fillna("").astype(str)
            if clean(value)
        }
    if not notified_serials:
        return rows

    before = len(rows)
    rows = rows[
        ~rows["Serial"].fillna("").astype(str).str.strip().isin(notified_serials)
    ].copy()
    print(
        "FAILED_SHIFT_REQUEST_NOTIFY_DEDUPE "
        f"already_notified={before - len(rows)} remaining={len(rows)}"
    )
    return rows


def split_discord_message(lines: list[str], limit: int = 1800) -> list[str]:
    messages: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        extra_len = len(line) + (1 if current else 0)
        if current and current_len + extra_len > limit:
            messages.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + (1 if current_len else 0)

    if current:
        messages.append("\n".join(current))
    return messages


def build_messages(rows: pd.DataFrame) -> list[dict]:
    if rows.empty:
        return []

    rows = rows.copy()
    rows["_warehouse_key"] = rows.get("Raktár", pd.Series("", index=rows.index)).map(normalize_warehouse)
    payloads: list[dict] = []

    for warehouse, warehouse_rows in rows.groupby("_warehouse_key", sort=False):
        lines = [
            "**Sikertelen foglalás - kézi megkérés kell**",
            "Az alábbi MűszakPro sorokra nincs érvényes napi terv, ezért kézzel kell megkérni:",
        ]
        for work_date, day_rows in warehouse_rows.groupby("Dátum", sort=False):
            lines.append("")
            lines.append(f"**{foglalas._format_slack_request_date(work_date)}**")
            for row in day_rows.to_dict("records"):
                courier_name = clean(row.get("Dolgozó")) or "Név nélkül"
                muszakpro_shift = clean(row.get("MűszakPro")) or "-"
                if warehouse in {"BUD1", "BUD2"}:
                    lines.append(f"- {courier_name} - {muszakpro_shift}")
                else:
                    row_warehouse = clean(row.get("Raktár")) or "-"
                    lines.append(f"- {row_warehouse} - {courier_name} - {muszakpro_shift}")

        target_warehouse = warehouse if warehouse in {"BUD1", "BUD2"} else ""
        for content in split_discord_message(lines):
            payloads.append(
                {
                    "warehouse": target_warehouse,
                    "content": content,
                    "rows": warehouse_rows,
                }
            )

    return payloads


def notify_failed_shift_requests(
    *,
    start_date: date,
    days: int,
    tolerance_minutes: int,
    source_limit: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    end_date = start_date + timedelta(days=max(int(days), 1) - 1)
    summary_df = load_summary(start_date, end_date, tolerance_minutes, source_limit)
    request_rows = foglalas._slack_daily_plan_rows(summary_df)
    request_rows = filter_not_yet_notified(request_rows, start_date, end_date)

    print(
        "FAILED_SHIFT_REQUEST_NOTIFY_TARGET "
        f"start={start_date} end={end_date} rows={len(request_rows)} dry_run={dry_run}"
    )
    if request_rows.empty:
        return 0, 0, 0

    payloads = build_messages(request_rows)
    sent_messages = 0
    logged_rows = 0
    failed_messages = 0

    for payload in payloads:
        warehouse = payload["warehouse"]
        content = payload["content"]
        if dry_run:
            print(
                "FAILED_SHIFT_REQUEST_NOTIFY_DRY_RUN "
                f"warehouse={warehouse or 'default'} chars={len(content)}"
            )
            print(content)
            sent_messages += 1
            continue

        ok, status_message = send_discord_text_message_to_setting(
            content,
            "DISCORD_FAILED_SHIFT_REQUEST_WEBHOOK_URL",
        )
        if not ok:
            failed_messages += 1
            print(
                "FAILED_SHIFT_REQUEST_NOTIFY_ERROR "
                f"warehouse={warehouse or 'default'} message={status_message}"
            )
            continue

        sent_messages += 1
        print(
            "FAILED_SHIFT_REQUEST_NOTIFY_SENT "
            f"warehouse={warehouse or 'default'} rows={len(payload['rows'])}"
        )
        for row in payload["rows"].to_dict("records"):
            log_result = log_giriton_booking_result(
                candidate_from_row(row),
                NOTIFIED_STATUS,
                "Discord manual shift request sent",
            )
            if log_result == "OK":
                logged_rows += 1

    return sent_messages, logged_rows, failed_messages


def main() -> None:
    today = datetime.now(BUDAPEST_TZ).date()
    parser = argparse.ArgumentParser(
        description="Discordra küldi a következő napok sikertelen, kézzel kérendő MűszakPro sorait."
    )
    parser.add_argument("--start-date", default="", help="Kezdő nap YYYY-MM-DD. Alap: holnap.")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--tolerance-minutes", type=int, default=30)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date, today + timedelta(days=1))
    sent_messages, logged_rows, failed_messages = notify_failed_shift_requests(
        start_date=start_date,
        days=args.days,
        tolerance_minutes=args.tolerance_minutes,
        source_limit=args.source_limit,
        dry_run=args.dry_run,
    )
    print(
        "FAILED_SHIFT_REQUEST_NOTIFY_DONE "
        f"sent_messages={sent_messages} logged_rows={logged_rows} failed_messages={failed_messages}"
    )
    if failed_messages:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
