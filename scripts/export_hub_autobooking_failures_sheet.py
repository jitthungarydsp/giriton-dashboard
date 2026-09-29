#!/usr/bin/env python3
"""Export HUB_JOB_AUTOBOOKING skipped full-day candidates to Google Sheets."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.google_sheets_values import replace_sheet_values_by_id  # noqa: E402
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 26523061
FAILURE_TABLE = "hub_autobooking_failures"
SHIFT_COMPARISON_TABLE = "ops_shift_comparison"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")

HEADER = [
    "Frissítve",
    "Futás ideje",
    "Dátum",
    "Raktár",
    "courierId",
    "Futár",
    "email",
    "MűszakPro kezdés",
    "HUB ajánlat",
    "Eltérés perc",
    "Egyezés típusa",
    "Shift template ID",
    "BlockKey",
    "Miért nem foglalt",
    "MűszakPro foglalási idő",
    "Serial",
    "Forrás sor",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    return date.fromisoformat(text) if text else None


def default_start_date() -> date:
    return datetime.now(LOCAL_TIMEZONE).date()


def failure_key(record: dict[str, Any]) -> str:
    return "|".join(
        [
            clean_text(record.get("work_date")),
            clean_text(record.get("warehouse")).upper(),
            clean_text(record.get("courier_id")) or clean_text(record.get("email")).casefold(),
            clean_text(record.get("muszakpro_shift_start")),
            clean_text(record.get("serial")),
            clean_text(record.get("reason")),
        ]
    )


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for record in records:
        key = failure_key(record)
        by_key[key] = record
    return list(by_key.values())


def supabase_headers() -> tuple[str, dict[str, str]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")
    return supabase_url, {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


def read_ops_shift_failed_rows(start_date: date, end_date: date, limit: int = 50000) -> list[dict[str, Any]]:
    supabase_url, headers = supabase_headers()
    response = requests.get(
        f"{supabase_url}/rest/v1/{SHIFT_COMPARISON_TABLE}",
        headers=headers,
        params=[
            (
                "select",
                (
                    "work_date,courier_id,courier_name,email,warehouse,muszakpro_shift_start,"
                    "shift_start,giriton_offer,shift_end,muszakpro_status,giriton_status,"
                    "booking_recommendation_status,difference_text,recommendation_reason,"
                    "muszakpro_booking_code,serial"
                ),
            ),
            ("booking_recommendation_status", "eq.Sikertelen"),
            ("work_date", f"gte.{start_date.isoformat()}"),
            ("work_date", f"lte.{end_date.isoformat()}"),
            ("order", "work_date.asc,warehouse.asc,muszakpro_shift_start.asc,courier_name.asc"),
            ("limit", str(int(limit))),
        ],
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def record_from_ops_shift(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "ops_shift_comparison",
        "run_at": "",
        "work_date": clean_text(row.get("work_date")),
        "warehouse": clean_text(row.get("warehouse")),
        "courier_id": row.get("courier_id") or "",
        "courier_name": clean_text(row.get("courier_name")),
        "email": clean_text(row.get("email")),
        "muszakpro_shift_start": clean_text(row.get("muszakpro_shift_start")),
        "hub_slot_from": clean_text(row.get("giriton_offer")),
        "match_diff_minutes": "",
        "match_kind": clean_text(row.get("booking_recommendation_status")),
        "shift_template_id": "",
        "block_key": "",
        "reason": clean_text(row.get("recommendation_reason")),
        "timestamp_text": "",
        "serial": clean_text(row.get("serial")),
        "source_row": "ops_shift_comparison",
        "comparison_row": row,
    }


def db_payload(record: dict[str, Any], exported_at: str) -> dict[str, Any]:
    return {
        "failure_key": failure_key(record),
        "source_name": clean_text(record.get("source")) or "hub-job-autobooking",
        "run_at": clean_text(record.get("run_at")) or None,
        "work_date": clean_text(record.get("work_date")) or None,
        "warehouse": clean_text(record.get("warehouse")) or None,
        "courier_id": int(record["courier_id"]) if clean_text(record.get("courier_id")).isdigit() else None,
        "courier_name": clean_text(record.get("courier_name")) or None,
        "email": clean_text(record.get("email")).casefold() or None,
        "muszakpro_shift_start": clean_text(record.get("muszakpro_shift_start")) or None,
        "hub_slot_from": clean_text(record.get("hub_slot_from")) or None,
        "match_diff_minutes": (
            int(record["match_diff_minutes"])
            if clean_text(record.get("match_diff_minutes")).lstrip("-").isdigit()
            else None
        ),
        "match_kind": clean_text(record.get("match_kind")) or None,
        "shift_template_id": (
            int(record["shift_template_id"])
            if clean_text(record.get("shift_template_id")).isdigit()
            else None
        ),
        "block_key": clean_text(record.get("block_key")) or None,
        "reason": clean_text(record.get("reason")) or None,
        "timestamp_text": clean_text(record.get("timestamp_text")) or None,
        "serial": clean_text(record.get("serial")) or None,
        "source_row": clean_text(record.get("source_row")) or None,
        "response_json": record,
        "last_seen_at": datetime.now(LOCAL_TIMEZONE).astimezone().isoformat(),
        "updated_at": datetime.now(LOCAL_TIMEZONE).astimezone().isoformat(),
        "exported_at_text": exported_at,
    }


def upsert_failure_records(records: list[dict[str, Any]], exported_at: str, batch_size: int = 500) -> int:
    if not records:
        return 0
    supabase_url, headers = supabase_headers()
    headers = {**headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
    written = 0
    for start in range(0, len(records), max(int(batch_size), 1)):
        batch = [db_payload(record, exported_at) for record in records[start:start + max(int(batch_size), 1)]]
        response = requests.post(
            f"{supabase_url}/rest/v1/{FAILURE_TABLE}",
            headers=headers,
            params={"on_conflict": "failure_key"},
            json=batch,
            timeout=60,
        )
        try:
            raise_for_supabase_error(response)
        except requests.HTTPError as exc:
            text = str(exc).lower()
            if "could not find" in text or "schema cache" in text or "pgrst" in text:
                print(
                    "HUB_JOB_AUTOBOOKING_FAILURES_DB_SKIPPED "
                    f"reason=missing_table table={FAILURE_TABLE} rows={len(records)}"
                )
                return written
            raise
        written += len(batch)
    return written


def row_to_sheet_row(record: dict[str, Any], exported_at: str) -> list[Any]:
    return [
        exported_at,
        clean_text(record.get("run_at")),
        clean_text(record.get("work_date")),
        clean_text(record.get("warehouse")),
        record.get("courier_id") or "",
        clean_text(record.get("courier_name")),
        clean_text(record.get("email")),
        clean_text(record.get("muszakpro_shift_start")),
        clean_text(record.get("hub_slot_from")),
        record.get("match_diff_minutes") if record.get("match_diff_minutes") not in (None, "") else "",
        clean_text(record.get("match_kind")),
        record.get("shift_template_id") or "",
        clean_text(record.get("block_key")),
        clean_text(record.get("reason")),
        clean_text(record.get("timestamp_text")),
        clean_text(record.get("serial")),
        record.get("source_row") or "",
    ]


def export_failures(input_path: Path, dry_run: bool = False) -> dict[str, Any]:
    return export_failures_for_window(input_path, None, None, dry_run=dry_run)


def export_failures_for_window(
    input_path: Path,
    start_date: date | None,
    end_date: date | None,
    *,
    dry_run: bool = False,
    save_db: bool = True,
) -> dict[str, Any]:
    raw_records = load_records(input_path)
    comparison_rows: list[dict[str, Any]] = []
    if start_date and end_date:
        comparison_rows = [
            record_from_ops_shift(row)
            for row in read_ops_shift_failed_rows(start_date, end_date)
        ]
    raw_records = [*raw_records, *comparison_rows]
    records = dedupe_records(raw_records)
    if dry_run:
        return {
            "records": len(records),
            "raw_records": len(raw_records),
            "comparison_rows": len(comparison_rows),
            "db_written": 0,
            "written_rows": 0,
            "worksheet_title": "",
            "worksheet_id": WORKSHEET_GID,
        }

    exported_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    if records:
        values = [
            HEADER,
            *[row_to_sheet_row(record, exported_at) for record in records],
        ]
    else:
        values = [
            HEADER,
            [
                exported_at,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Nincs nem foglalható HUB_JOB_AUTOBOOKING sor ebben a futásban.",
                "",
                "",
                "",
            ],
        ]

    db_written = upsert_failure_records(records, exported_at) if save_db else 0
    replace_sheet_values_by_id(SPREADSHEET_ID, WORKSHEET_GID, values)
    return {
        "records": len(records),
        "raw_records": len(raw_records),
        "comparison_rows": len(comparison_rows),
        "db_written": db_written,
        "written_rows": len(values),
        "worksheet_title": "",
        "worksheet_id": WORKSHEET_GID,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results/hub-job-autobooking/failures.json")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookahead-days", type=int, default=0)
    parser.add_argument("--skip-db-save", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    if not start_date and args.lookahead_days:
        start_date = default_start_date()
    end_date = parse_date(args.end_date)
    if start_date and not end_date:
        end_date = start_date + timedelta(days=max(int(args.lookahead_days), 0))

    result = export_failures_for_window(
        Path(args.input),
        start_date,
        end_date,
        dry_run=args.dry_run,
        save_db=not args.skip_db_save,
    )
    print(
        "HUB_JOB_AUTOBOOKING_FAILURES_SHEET "
        f"input={args.input} rows={result['records']} raw_rows={result['raw_records']} "
        f"comparison_rows={result['comparison_rows']} db_written={result['db_written']} "
        f"written_rows={result['written_rows']} "
        f"worksheet_title={result['worksheet_title']!r} "
        f"worksheet_id={result['worksheet_id']} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
