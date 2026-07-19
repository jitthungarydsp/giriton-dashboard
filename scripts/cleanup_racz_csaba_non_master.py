import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TARGET_COURIER_ID = "2875"
TARGET_EMAILS = {
    "csaba.racz66@gmail.com",
}
TARGET_NAME_PARTS = (
    "racz",
    "rácz",
    "răˇcz",
    "răcz",
    "csaba",
)

MASTER_TABLES = {
    "courier_master",
    "core_couriers",
}

SKIP_TABLE_PREFIXES = (
    "pg_",
)

DIRECT_ID_COLUMNS = (
    "courier_id",
    "driver_id",
    "courierId",
    "driverId",
    "user_number",
    "user_id",
)

DIRECT_EMAIL_COLUMNS = (
    "email",
    "billing_email",
    "contact_email",
    "courier_email",
    "driver_email",
)

DIRECT_NAME_COLUMNS = (
    "courier_name",
    "driver_name",
    "name",
    "full_name",
    "employee_name",
    "user_name",
)

JSON_COLUMNS = (
    "response_json",
    "raw_payload",
    "payload",
    "data",
)


def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")


def get_setting(name):
    value = os.getenv(name)
    if value:
        return str(value)

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            secrets = tomllib.load(file)
    except Exception:
        return ""

    if name in secrets:
        return str(secrets.get(name) or "")

    supabase_section = secrets.get("supabase", {})
    if isinstance(supabase_section, dict) and name in supabase_section:
        return str(supabase_section.get(name) or "")

    return ""


def get_config():
    load_dotenv_if_available()
    url = get_setting("SUPABASE_URL").rstrip("/")
    key = get_setting("SUPABASE_SERVICE_ROLE_KEY").strip()

    if not url or not key:
        raise RuntimeError(
            "Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY. "
            "Add meg környezeti változóként vagy .streamlit/secrets.toml-ban."
        )

    return url, key


def headers(key, prefer=None):
    result = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if prefer:
        result["Prefer"] = prefer
    return result


def raise_for_error(response, context=""):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        suffix = f"; {context}" if context else ""
        if detail:
            raise requests.HTTPError(
                f"{exc}{suffix}; Supabase válasz: {detail[:1000]}",
                response=response,
            ) from exc
        raise


def fetch_openapi(supabase_url, key):
    response = requests.get(
        f"{supabase_url}/rest/v1/",
        headers={
            **headers(key),
            "Accept": "application/openapi+json",
        },
        timeout=60,
    )
    raise_for_error(response, "OpenAPI schema")
    return response.json()


def table_definitions(openapi):
    definitions = openapi.get("definitions") or {}
    tables = {}

    for table_name, definition in definitions.items():
        if table_name in MASTER_TABLES:
            continue
        if table_name.startswith(SKIP_TABLE_PREFIXES):
            continue

        properties = definition.get("properties") or {}
        if not isinstance(properties, dict):
            continue

        tables[table_name] = set(properties.keys())

    return tables


def encoded_filter(column, operator_value):
    return f"{quote(column, safe='')}={quote(operator_value, safe='.*')}"


def candidate_filters(columns):
    filters = []

    for column in DIRECT_ID_COLUMNS:
        if column in columns:
            filters.append((column, encoded_filter(column, f"eq.{TARGET_COURIER_ID}")))

    for column in DIRECT_EMAIL_COLUMNS:
        if column in columns:
            for email in TARGET_EMAILS:
                filters.append((column, encoded_filter(column, f"eq.{email}")))

    for column in DIRECT_NAME_COLUMNS:
        if column in columns:
            filters.append((column, encoded_filter(column, "ilike.*Rácz*")))
            filters.append((column, encoded_filter(column, "ilike.*Racz*")))
            filters.append((column, encoded_filter(column, "ilike.*Csaba*")))

    # The common raw json columns cannot be filtered reliably through every
    # PostgREST setup. We fetch a small candidate set only when there is no
    # direct identifying column; the final match is still verified locally.
    return filters


def row_matches(row):
    text = json.dumps(row, ensure_ascii=False).lower()

    if TARGET_COURIER_ID in text:
        return True

    for email in TARGET_EMAILS:
        if email.lower() in text:
            return True

    has_racz = any(
        part in text
        for part in (
            "racz",
            "rácz",
            "răˇcz",
            "răcz",
        )
    )
    has_csaba = "csaba" in text

    return has_racz and has_csaba


def primary_key_columns(columns):
    for candidates in (
        ("id",),
        ("work_date", "courier_id", "route_id"),
        ("work_date", "driver_id"),
        ("source_name", "work_date", "courier_name"),
        ("source_name", "work_date", "driver_id"),
        ("source_name", "courier_id", "work_date"),
        ("source_name", "driver_id", "work_date"),
    ):
        if all(column in columns for column in candidates):
            return candidates

    return ()


def select_columns(columns):
    wanted = [
        "id",
        "work_date",
        "courier_id",
        "driver_id",
        "courier_name",
        "driver_name",
        "name",
        "email",
        "route_id",
        "shift_id",
        "created_at",
        "fetched_at",
        "updated_at",
    ]
    selected = [column for column in wanted if column in columns]

    if selected:
        return ",".join(selected)

    return "*"


def read_rows_for_filter(supabase_url, key, table_name, columns, filter_query):
    endpoint = (
        f"{supabase_url}/rest/v1/{quote(table_name, safe='')}"
        f"?select={quote(select_columns(columns), safe=',*')}"
        f"&{filter_query}"
        "&limit=1000"
    )
    response = requests.get(
        endpoint,
        headers=headers(key),
        timeout=60,
    )

    if response.status_code in (400, 404):
        return []

    raise_for_error(response, table_name)
    return response.json()


def read_json_scan_candidates(supabase_url, key, table_name, columns):
    if not any(column in columns for column in JSON_COLUMNS):
        return []

    endpoint = (
        f"{supabase_url}/rest/v1/{quote(table_name, safe='')}"
        f"?select={quote(select_columns(columns), safe=',*')}"
        "&limit=1000"
    )
    response = requests.get(endpoint, headers=headers(key), timeout=60)

    if response.status_code in (400, 404):
        return []

    raise_for_error(response, table_name)
    return response.json()


def unique_rows(rows):
    seen = set()
    result = []

    for row in rows:
        marker = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(row)

    return result


def filter_for_row(row, key_columns):
    parts = []
    for column in key_columns:
        value = row.get(column)
        if value is None:
            return ""
        parts.append(encoded_filter(column, f"eq.{value}"))

    return "&".join(parts)


def delete_rows(supabase_url, key, table_name, key_columns, rows):
    deleted = 0

    for row in rows:
        filter_query = filter_for_row(row, key_columns)
        if not filter_query:
            continue

        endpoint = (
            f"{supabase_url}/rest/v1/{quote(table_name, safe='')}"
            f"?{filter_query}"
        )
        response = requests.delete(
            endpoint,
            headers=headers(key, prefer="return=representation"),
            timeout=60,
        )
        raise_for_error(response, f"DELETE {table_name}")
        deleted += len(response.json())

    return deleted


def inspect_table(supabase_url, key, table_name, columns):
    rows = []

    for _label, filter_query in candidate_filters(columns):
        rows.extend(
            read_rows_for_filter(
                supabase_url,
                key,
                table_name,
                columns,
                filter_query,
            )
        )

    if not rows:
        rows.extend(
            read_json_scan_candidates(
                supabase_url,
                key,
                table_name,
                columns,
            )
        )

    matched = [row for row in unique_rows(rows) if row_matches(row)]
    return matched


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Rácz Csaba sorainak törlése minden nem-master Supabase táblából."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Tényleges törlés. Enélkül csak dry-run listázás történik.",
    )
    parser.add_argument(
        "--table",
        action="append",
        default=[],
        help="Csak adott táblát vizsgál. Többször is megadható.",
    )
    args = parser.parse_args()

    supabase_url, key = get_config()
    openapi = fetch_openapi(supabase_url, key)
    tables = table_definitions(openapi)

    if args.table:
        selected = set(args.table)
        tables = {
            name: columns
            for name, columns in tables.items()
            if name in selected
        }

    total_found = 0
    total_deleted = 0

    print("Rácz Csaba DB takarítás")
    print(f"Master táblák kihagyva: {', '.join(sorted(MASTER_TABLES))}")
    print(f"Mód: {'ÉLES TÖRLÉS' if args.apply else 'DRY-RUN'}")
    print()

    for table_name in sorted(tables):
        columns = tables[table_name]
        matched = inspect_table(supabase_url, key, table_name, columns)

        if not matched:
            continue

        total_found += len(matched)
        keys = primary_key_columns(columns)

        print(f"{table_name}: {len(matched)} találat")
        if keys:
            print(f"  törlési kulcs: {', '.join(keys)}")
        else:
            print("  nincs biztonságos törlési kulcs, kihagyom")

        for row in matched[:5]:
            preview = {
                key: row.get(key)
                for key in (
                    "id",
                    "work_date",
                    "courier_id",
                    "driver_id",
                    "courier_name",
                    "driver_name",
                    "name",
                    "email",
                    "route_id",
                    "shift_id",
                )
                if key in row
            }
            print(f"  minta: {json.dumps(preview, ensure_ascii=False)}")

        if len(matched) > 5:
            print(f"  ... további {len(matched) - 5} sor")

        if args.apply and keys:
            deleted = delete_rows(supabase_url, key, table_name, keys, matched)
            total_deleted += deleted
            print(f"  törölve: {deleted}")

        print()

    print(f"Összes találat: {total_found}")
    if args.apply:
        print(f"Összes törölt sor: {total_deleted}")
    else:
        print("Tényleges törléshez futtasd újra --apply kapcsolóval.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        sys.exit(1)
