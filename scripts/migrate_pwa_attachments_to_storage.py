"""Move legacy Base64 attachments to the private Supabase Storage bucket.

Run without --apply first. The default mode only reports what would be moved.
The SQL migration in sql/pwa_attachment_storage.sql must be applied first.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import secrets
import sys
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value.strip("'\"")
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""
    try:
        with secrets_path.open("rb") as file:
            settings = tomllib.load(file)
        value = (
            settings.get(name)
            or settings.get("supabase", {}).get(name)
        )
        return str(value or "").strip().strip("'\"")
    except Exception:
        return ""


def supabase_headers() -> dict[str, str]:
    key = load_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")
    headers = {"apikey": key}
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def supabase_rest(method: str, table: str, *, params: dict[str, str], payload: dict[str, Any] | None = None) -> Any:
    url = load_setting("SUPABASE_URL").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is missing")
    headers = supabase_headers()
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    return response.json() if response.content else []


def upload_pwa_attachment(*, prefix: str, record_id: Any, file_name: Any, mime_type: str, content: bytes) -> dict[str, str]:
    bucket = load_setting("SUPABASE_STORAGE_BUCKET") or "pwa-attachments"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(file_name or "attachment"))[:120]
    safe_record = re.sub(r"[^A-Za-z0-9_-]+", "_", str(record_id or "record"))
    path = f"{prefix}/{safe_record}/{secrets.token_hex(12)}-{safe_name}"
    url = load_setting("SUPABASE_URL").rstrip("/")
    headers = supabase_headers()
    headers.update({"Content-Type": mime_type or "application/octet-stream", "x-upsert": "false"})
    response = requests.post(
        f"{url}/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
        headers=headers,
        data=content,
        timeout=90,
    )
    response.raise_for_status()
    return {
        "storage_bucket": bucket,
        "storage_path": path,
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


TABLES = [
    {
        "table": "pwa_device_condition_photos",
        "select": "id,report_id,file_name,mime_type,file_size,file_content_base64,storage_bucket,storage_path",
        "prefix": "device-condition",
        "record_key": "report_id",
    },
    {
        "table": "pwa_atm_payment",
        "select": "id,courier_id,file_name,mime_type,file_size,file_content_base64,storage_bucket,storage_path",
        "prefix": "atm-payments",
        "record_key": "courier_id",
    },
    {
        "table": "courier_route_alert_photos",
        "select": "id,alert_id,file_name,mime_type,file_size,file_content_base64,storage_bucket,storage_path",
        "prefix": "route-alerts",
        "record_key": "alert_id",
    },
]


def legacy_rows(table: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    return supabase_rest(
        "GET",
        table["table"],
        params={
            "select": table["select"],
            "storage_path": "is.null",
            "file_size": "gt.0",
            "order": "id.asc",
            "limit": str(limit),
        },
        timeout=90,
    ) or []


def migrate_table(table: dict[str, Any], *, apply: bool, limit: int) -> tuple[int, int, int]:
    rows = legacy_rows(table, limit)
    moved = skipped = failed = 0
    for row in rows:
        encoded = str(row.get("file_content_base64") or "")
        if not encoded:
            skipped += 1
            continue
        try:
            content = base64.b64decode(encoded, validate=True)
            if not apply:
                print(f"DRY RUN  {table['table']} id={row.get('id')} bytes={len(content)}")
                moved += 1
                continue
            storage = upload_pwa_attachment(
                prefix=table["prefix"],
                record_id=row.get(table["record_key"]),
                file_name=row.get("file_name") or "attachment",
                mime_type=row.get("mime_type") or "application/octet-stream",
                content=content,
            )
            supabase_rest(
                "PATCH",
                table["table"],
                params={"id": f"eq.{row.get('id')}"},
                payload={"file_content_base64": "", **storage},
                prefer="return=minimal",
                timeout=60,
            )
            print(f"MOVED    {table['table']} id={row.get('id')} bytes={len(content)}")
            moved += 1
        except Exception as exc:  # keep processing the other files
            failed += 1
            print(f"FAILED   {table['table']} id={row.get('id')}: {exc}")
    return len(rows), moved, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually upload and update rows")
    parser.add_argument("--limit", type=int, default=500, help="maximum rows per table")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}; limit/table: {args.limit}")
    totals = [0, 0, 0]
    for table in TABLES:
        result = migrate_table(table, apply=args.apply, limit=args.limit)
        totals = [left + right for left, right in zip(totals, result)]
        print(f"{table['table']}: rows={result[0]} moved={result[1]} failed={result[2]}")
    print(f"TOTAL: rows={totals[0]} moved={totals[1]} failed={totals[2]}")
    return 1 if totals[2] else 0


if __name__ == "__main__":
    raise SystemExit(main())
