from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.foglalasok_db import (
    name_without_courier_id,
    normalize_email,
    normalize_name,
    read_courier_lookup_from_hub_identity,
)
from resources.shift_comparison_db import courier_id_from_comparison_key
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


TABLE_NAME = "ops_shift_comparison"


def clean(value) -> str:
    return str(value or "").strip()


def headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def parse_start_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def read_null_courier_rows(
    supabase_url: str,
    service_role_key: str,
    start_date=None,
    end_date=None,
    limit: int = 10000,
) -> list[dict]:
    filters = [
        "select=id,comparison_key,work_date,courier_id,courier_name,email,warehouse",
        "courier_id=is.null",
        "order=work_date.asc,courier_name.asc",
        f"limit={int(limit)}",
    ]
    if start_date:
        filters.append(f"work_date=gte.{start_date.isoformat()}")
    if end_date:
        filters.append(f"work_date=lte.{end_date.isoformat()}")

    response = requests.get(
        f"{supabase_url}/rest/v1/{TABLE_NAME}?{'&'.join(filters)}",
        headers=headers(service_role_key),
        timeout=60,
    )
    raise_for_supabase_error(response)
    return response.json()


def resolve_from_hub_identity(row: dict, lookup: dict) -> int | None:
    key_id = courier_id_from_comparison_key(row.get("comparison_key"))
    if key_id:
        return key_id

    email = normalize_email(row.get("email"))
    if email and email in lookup.get("by_email", {}):
        return int(lookup["by_email"][email]["courier_id"])

    warehouse = clean(row.get("warehouse")).upper()
    name_keys = {
        normalize_name(row.get("courier_name")),
        name_without_courier_id(row.get("courier_name")),
    }
    for name_key in name_keys:
        courier = lookup.get("by_name", {}).get(name_key)
        if not courier:
            continue
        courier_warehouse = clean(courier.get("warehouse")).upper()
        if warehouse and courier_warehouse and warehouse != courier_warehouse:
            continue
        return int(courier["courier_id"])

    return None


def upsert_courier_ids(
    supabase_url: str,
    service_role_key: str,
    rows: list[dict],
) -> None:
    if not rows:
        return

    response = requests.post(
        f"{supabase_url}/rest/v1/{TABLE_NAME}?on_conflict=id",
        headers={
            **headers(service_role_key),
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=rows,
        timeout=60,
    )
    raise_for_supabase_error(response)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ops_shift_comparison courier_id visszatoltese courier_hub_courier_identity_raw alapjan."
    )
    parser.add_argument("--start-date", default="")
    parser.add_argument("--days", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = parse_start_date(args.start_date)
    end_date = start_date + timedelta(days=max(args.days, 1) - 1) if start_date and args.days else None

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")

    lookup = read_courier_lookup_from_hub_identity()
    rows = read_null_courier_rows(
        supabase_url,
        service_role_key,
        start_date=start_date,
        end_date=end_date,
        limit=args.limit,
    )

    matched = []
    missing = []
    for row in rows:
        courier_id = resolve_from_hub_identity(row, lookup)
        if courier_id:
            matched.append((row, courier_id))
        else:
            missing.append(row)

    if not args.dry_run:
        update_rows = [
            {
                "id": row["id"],
                "courier_id": courier_id,
            }
            for row, courier_id in matched
        ]
        for index in range(0, len(update_rows), 500):
            upsert_courier_ids(
                supabase_url,
                service_role_key,
                update_rows[index:index + 500],
            )

    print(
        "OPS_SHIFT_COMPARISON_COURIER_ID_BACKFILL "
        f"checked={len(rows)} matched={len(matched)} updated={0 if args.dry_run else len(matched)} "
        f"missing={len(missing)} dry_run={args.dry_run}"
    )
    for row in missing[:20]:
        print(
            "OPS_SHIFT_COMPARISON_COURIER_ID_MISSING "
            f"{row.get('work_date')} | {row.get('courier_name')} | {row.get('email')} | {row.get('warehouse')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
