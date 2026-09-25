#!/usr/bin/env python3
"""Export HUB_JOB_AUTOBOOKING skipped full-day candidates to Google Sheets."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google_client import open_spreadsheet  # noqa: E402


SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 26523061
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


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in records:
        key = (
            clean_text(record.get("work_date")),
            clean_text(record.get("warehouse")).upper(),
            clean_text(record.get("courier_id")) or clean_text(record.get("email")).casefold(),
            clean_text(record.get("muszakpro_shift_start")),
            clean_text(record.get("hub_slot_from")),
            clean_text(record.get("reason")),
        )
        by_key[key] = record
    return list(by_key.values())


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
    raw_records = load_records(input_path)
    records = dedupe_records(raw_records)
    if dry_run:
        return {
            "records": len(records),
            "raw_records": len(raw_records),
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

    spreadsheet = open_spreadsheet(SPREADSHEET_ID)
    worksheet = spreadsheet.get_worksheet_by_id(WORKSHEET_GID)
    if worksheet is None:
        raise RuntimeError(f"Nem található worksheet gid={WORKSHEET_GID}.")

    worksheet.clear()
    worksheet.update(
        range_name="A1",
        values=values,
    )
    return {
        "records": len(records),
        "raw_records": len(raw_records),
        "written_rows": len(values),
        "worksheet_title": worksheet.title,
        "worksheet_id": worksheet.id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results/hub-job-autobooking/failures.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = export_failures(Path(args.input), dry_run=args.dry_run)
    print(
        "HUB_JOB_AUTOBOOKING_FAILURES_SHEET "
        f"input={args.input} rows={result['records']} raw_rows={result['raw_records']} "
        f"written_rows={result['written_rows']} "
        f"worksheet_title={result['worksheet_title']!r} "
        f"worksheet_id={result['worksheet_id']} dry_run={args.dry_run}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
