import argparse
import os
import sys

import requests


TABLES = {
    "bill_jitt_invoice_summary": 36,
    "bill_jitt_invoice_routes": 2318,
    "bill_jitt_invoice_final_routes": 2318,
    "bill_jitt_invoice_bonus_routes": 7,
    "bill_jitt_invoice_penalties": 1,
    "bill_jitt_contract_bonus_rules": 48,
}


def row_count(url, headers, table, filter_value=None):
    params = {"select": "imported_at", "limit": "1"}
    if filter_value:
        params["imported_at"] = filter_value
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers={**headers, "Prefer": "count=exact", "Range": "0-0"},
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    content_range = response.headers.get("Content-Range", "0/0")
    return int(content_range.rsplit("/", 1)[-1])


def main():
    parser = argparse.ArgumentParser(
        description="Keep only one verified JITT invoice import generation."
    )
    parser.add_argument("--keep-imported-at", required=True)
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    keep_filter = f"eq.{args.keep_imported_at}"

    before = {}
    for table, expected in TABLES.items():
        total = row_count(url, headers, table)
        keep = row_count(url, headers, table, keep_filter)
        before[table] = (total, keep)
        print(f"CHECK {table} total={total} keep={keep} expected={expected}")
        if keep != expected:
            raise RuntimeError(
                f"Safety check failed for {table}: expected {expected} rows at "
                f"{args.keep_imported_at}, found {keep}. No rows were deleted."
            )

    for table in TABLES:
        total, keep = before[table]
        stale = total - keep
        if stale:
            response = requests.delete(
                f"{url}/rest/v1/{table}",
                headers={**headers, "Prefer": "return=minimal"},
                params={"imported_at": f"neq.{args.keep_imported_at}"},
                timeout=120,
            )
            response.raise_for_status()
        print(f"DELETE {table} stale={stale}")

    for table, expected in TABLES.items():
        total = row_count(url, headers, table)
        stale = row_count(
            url, headers, table, f"neq.{args.keep_imported_at}"
        )
        print(f"VERIFY {table} total={total} stale={stale}")
        if total != expected or stale != 0:
            raise RuntimeError(
                f"Cleanup verification failed for {table}: total={total}, stale={stale}."
            )

    print("CLEANUP_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CLEANUP_FAILED {exc}", file=sys.stderr)
        raise
