#!/usr/bin/env python3
"""Export all rows from muszakpro.bookings."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


DEFAULT_OUTPUT = "results/muszakpro-bookings.csv"
MUSZAKPRO_SCHEMA = "muszakpro"
TABLE_NAME = "bookings"

COLUMNS = [
    "id",
    "source_name",
    "source_row",
    "timestamp_text",
    "work_date",
    "email",
    "shift_text",
    "warehouse",
    "booking_code",
    "admin_recorder",
    "giriton_uploaded",
    "system_check",
    "legacy_key",
    "courier_id",
    "courier_name",
    "serial",
    "status",
    "event_type",
    "cancelled_at",
    "cancelled_by",
    "response_json",
    "fetched_at",
    "created_at",
    "updated_at",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def supabase_headers() -> dict[str, str]:
    _supabase_url, service_role_key = get_supabase_config()
    if not service_role_key:
        raise RuntimeError("Hianyzik a SUPABASE_SERVICE_ROLE_KEY.")
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept-Profile": MUSZAKPRO_SCHEMA,
        "Content-Profile": MUSZAKPRO_SCHEMA,
    }


def build_params(args: argparse.Namespace) -> list[tuple[str, str]]:
    params = [
        ("select", ",".join(COLUMNS)),
        ("order", "work_date.asc,timestamp_text.asc,source_row.asc,email.asc"),
    ]
    if args.start_date:
        params.append(("work_date", f"gte.{args.start_date}"))
    if args.end_date:
        params.append(("work_date", f"lte.{args.end_date}"))
    if args.email:
        params.append(("email", f"eq.{args.email.strip().casefold()}"))
    if args.courier_id:
        params.append(("courier_id", f"eq.{int(args.courier_id)}"))
    if args.status:
        params.append(("status", f"eq.{args.status.strip().upper()}"))
    return params


def read_bookings(args: argparse.Namespace) -> list[dict[str, Any]]:
    supabase_url, _service_role_key = get_supabase_config()
    if not supabase_url:
        raise RuntimeError("Hianyzik a SUPABASE_URL.")

    endpoint = f"{supabase_url}/rest/v1/{TABLE_NAME}"
    params = build_params(args)
    headers_base = supabase_headers()
    page_size = max(min(int(args.page_size), 1000), 1)
    total_limit = max(int(args.limit), 0)
    rows: list[dict[str, Any]] = []

    while True:
        range_start = len(rows)
        if total_limit and range_start >= total_limit:
            break
        range_end = range_start + page_size - 1
        if total_limit:
            range_end = min(range_end, total_limit - 1)

        response = requests.get(
            endpoint,
            headers={
                **headers_base,
                "Range-Unit": "items",
                "Range": f"{range_start}-{range_end}",
            },
            params=params,
            timeout=60,
        )
        raise_for_supabase_error(response)
        chunk = response.json()
        if not isinstance(chunk, list) or not chunk:
            break

        rows.extend(chunk)
        expected = range_end - range_start + 1
        if len(chunk) < expected:
            break

    return rows


def serializable_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    response_json = result.get("response_json")
    if isinstance(response_json, (dict, list)):
        result["response_json"] = json.dumps(response_json, ensure_ascii=False, sort_keys=True)
    return result


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(serializable_row(row))


def write_json(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_jsonl(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_rows(rows: list[dict[str, Any]], output_path: Path, output_format: str) -> None:
    if output_format == "csv":
        write_csv(rows, output_path)
    elif output_format == "json":
        write_json(rows, output_path)
    elif output_format == "jsonl":
        write_jsonl(rows, output_path)
    else:
        raise ValueError(f"Ismeretlen formatum: {output_format}")


def print_summary(rows: list[dict[str, Any]], output_path: Path, output_format: str) -> None:
    dates = sorted({clean_text(row.get("work_date")) for row in rows if clean_text(row.get("work_date"))})
    statuses: dict[str, int] = {}
    for row in rows:
        status = clean_text(row.get("status")) or "-"
        statuses[status] = statuses.get(status, 0) + 1
    status_text = ",".join(f"{key}:{value}" for key, value in sorted(statuses.items())) or "-"
    print(
        "MUSZAKPRO_BOOKINGS_EXPORT "
        f"rows={len(rows)} format={output_format} output={output_path} "
        f"first_date={(dates[0] if dates else '-')} last_date={(dates[-1] if dates else '-')} "
        f"statuses={status_text}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="muszakpro.bookings teljes export.")
    parser.add_argument("--start-date", default="", help="Opcionalis kezdo datum YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Opcionalis zaro datum YYYY-MM-DD.")
    parser.add_argument("--email", default="", help="Opcionalis email szuro.")
    parser.add_argument("--courier-id", type=int, default=0, help="Opcionalis courier_id szuro.")
    parser.add_argument("--status", default="", help="Opcionalis statusz szuro, pl. ACTIVE.")
    parser.add_argument("--limit", type=int, default=0, help="0 = osszes sor.")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--format", choices=["csv", "json", "jsonl"], default="csv")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = read_bookings(args)
    output_path = Path(args.output)
    write_rows(rows, output_path, args.format)
    print_summary(rows, output_path, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
