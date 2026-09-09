from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import Any

import requests


SETTLEMENT_SCHEMA = "settlement"

NORMALIZED_TABLES = (
    "courier_settlement_summary",
    "jit_row",
    "penalty_row",
    "atm_balance_row",
    "bonus_route_row",
    "performance_indicator_row",
)
PROCESSING_CHILD_TABLES = (
    "validation_error",
    "sheet_processing_result",
)
PROCESSING_RUN_TABLE = "processing_run"
IMPORT_TABLE = "excel_import"

COPY_TABLES = (
    *NORMALIZED_TABLES,
    *PROCESSING_CHILD_TABLES,
    PROCESSING_RUN_TABLE,
    IMPORT_TABLE,
)

RestParams = dict[str, str] | list[tuple[str, str]]


class SupabaseRest:
    def __init__(self, url: str, key: str) -> None:
        if not url or not key:
            raise ValueError("Supabase URL és service role kulcs is szükséges.")
        self.url = url.rstrip("/")
        self.key = key.strip()

    def headers(self, prefer: str = "") -> dict[str, str]:
        result = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Profile": SETTLEMENT_SCHEMA,
            "Content-Profile": SETTLEMENT_SCHEMA,
        }
        if prefer:
            result["Prefer"] = prefer
        return result

    def raise_for_error(self, response: requests.Response, table: str) -> None:
        if response.status_code < 400:
            return
        raise RuntimeError(
            f"Supabase {table}: HTTP {response.status_code}: {response.text[:2000]}"
        )

    def select(
        self,
        table: str,
        columns: str = "*",
        params: RestParams | None = None,
        offset: int = 0,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        query: list[tuple[str, str]] = [("select", columns)]
        if isinstance(params, dict):
            query.extend(params.items())
        elif params:
            query.extend(params)
        response = requests.get(
            f"{self.url}/rest/v1/{table}",
            headers={**self.headers(), "Range-Unit": "items", "Range": f"{offset}-{offset + limit - 1}"},
            params=query,
            timeout=120,
        )
        self.raise_for_error(response, table)
        return response.json() or []

    def delete_session_rows(self, table: str, session_id: str) -> int:
        response = requests.delete(
            f"{self.url}/rest/v1/{table}",
            headers=self.headers("return=representation"),
            params={"session_id": f"eq.{session_id}", "select": "session_id"},
            timeout=120,
        )
        self.raise_for_error(response, table)
        return len(response.json() or [])

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        response = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers=self.headers("return=minimal"),
            json=rows,
            timeout=120,
        )
        self.raise_for_error(response, table)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def fetch_all(
    client: SupabaseRest,
    table: str,
    select: str = "*",
    page_size: int = 1000,
    params: RestParams | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.select(table, select, params=params, offset=offset, limit=page_size)
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def discover_month_session_ids(source: SupabaseRest, start: date, end_exclusive: date) -> set[str]:
    session_ids: set[str] = set()

    summary_rows = fetch_all(
        source,
        "courier_settlement_summary",
        "session_id,period_start,period_end",
    )
    for row in summary_rows:
        session_id = str(row.get("session_id") or "").strip()
        period_start = str(row.get("period_start") or "")[:10]
        period_end = str(row.get("period_end") or "")[:10]
        if not session_id:
            continue
        if period_start and period_end:
            if period_start < end_exclusive.isoformat() and period_end >= start.isoformat():
                session_ids.add(session_id)

    jit_rows = fetch_all(
        source,
        "jit_row",
        "session_id,route_date",
        params=[
            ("route_date", f"gte.{start.isoformat()}"),
            ("route_date", f"lt.{end_exclusive.isoformat()}"),
        ],
    )
    for row in jit_rows:
        session_id = str(row.get("session_id") or "").strip()
        if session_id:
            session_ids.add(session_id)

    return session_ids


def fetch_source_session_rows(source: SupabaseRest, table: str, session_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        source,
        table,
        "*",
        params={"session_id": f"eq.{session_id}"},
    )


def insert_rows(target: SupabaseRest, table: str, rows: list[dict[str, Any]], batch_size: int = 500) -> int:
    inserted = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        if not batch:
            continue
        target.insert_rows(table, batch)
        inserted += len(batch)
    return inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Júliusi vagy más havi settlement Excel import visszatöltése Supabase restore projektből."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="Tényleges visszatöltés. Enélkül csak ellenőrzés.")
    parser.add_argument("--source-url", default=os.getenv("RESTORE_SUPABASE_URL"))
    parser.add_argument("--source-key", default=os.getenv("RESTORE_SUPABASE_SERVICE_ROLE_KEY"))
    parser.add_argument("--target-url", default=os.getenv("SUPABASE_URL"))
    parser.add_argument("--target-key", default=os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="Konkrét session_id visszatöltése. Többször is megadható.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start, end_exclusive = month_bounds(args.year, args.month)

    source = SupabaseRest(args.source_url, args.source_key)
    target = SupabaseRest(args.target_url, args.target_key)

    session_ids = {str(item).strip() for item in (args.session_ids or []) if str(item).strip()}
    if not session_ids:
        session_ids = discover_month_session_ids(source, start, end_exclusive)

    if not session_ids:
        print(f"Nincs visszaállítható session a restore projektben erre: {args.year}-{args.month:02d}")
        return 1

    print(f"Visszaállítandó hónap: {args.year}-{args.month:02d}")
    print(f"Talált session: {len(session_ids)}")
    for session_id in sorted(session_ids):
        print(f"  - {session_id}")

    copied_total = 0
    deleted_total = 0

    for session_id in sorted(session_ids):
        for table in COPY_TABLES:
            rows = fetch_source_session_rows(source, table, session_id)
            if not rows:
                continue
            print(f"{table}: {len(rows)} sor")
            if args.apply:
                deleted_total += target.delete_session_rows(table, session_id)
                copied_total += insert_rows(target, table, rows)

    if args.apply:
        print(f"Kész. Törölt célsor: {deleted_total}, visszatöltött sor: {copied_total}")
    else:
        print("Dry-run kész. Tényleges visszatöltéshez add hozzá: --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
