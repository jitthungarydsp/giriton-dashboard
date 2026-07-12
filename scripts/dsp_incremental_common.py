import os
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKFILL_START_DATE = date(2026, 6, 1)


def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")


load_dotenv_if_available()


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


def get_required_setting(name):
    value = str(get_setting(name) or "").strip()

    if not value:
        raise RuntimeError(f"Hianyzik a(z) {name} beallitas.")

    return value


def get_supabase_config():
    return (
        get_required_setting("SUPABASE_URL").rstrip("/"),
        get_required_setting("SUPABASE_SERVICE_ROLE_KEY"),
    )


def supabase_headers(extra=None):
    _supabase_url, service_role_key = get_supabase_config()
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    if extra:
        headers.update(extra)

    return headers


def raise_for_supabase_error(response, table_name=""):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        suffix = f"; tabla={table_name}" if table_name else ""

        if detail:
            raise requests.HTTPError(
                f"{exc}{suffix}; Supabase valasz: {detail[:1000]}",
                response=response,
            ) from exc

        raise


def is_missing_table_response(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()

    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def table_exists(table_name, select_column="work_date"):
    supabase_url, _service_role_key = get_supabase_config()
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        f"?select={select_column}&limit=1"
    )
    response = requests.get(
        endpoint,
        headers=supabase_headers(),
        timeout=30,
    )

    if is_missing_table_response(response):
        return False

    raise_for_supabase_error(response, table_name)
    return True


def resolve_table(candidates, select_column="work_date"):
    for table_name in candidates:
        if table_exists(table_name, select_column=select_column):
            return table_name

    raise RuntimeError(
        "Egyik Supabase tabla sem talalhato: "
        + ", ".join(candidates)
    )


def parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def read_latest_work_date(table_candidates):
    supabase_url, _service_role_key = get_supabase_config()
    table_name = resolve_table(table_candidates)
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        "?select=work_date"
        "&order=work_date.desc"
        "&limit=1"
    )
    response = requests.get(
        endpoint,
        headers=supabase_headers(),
        timeout=30,
    )
    raise_for_supabase_error(response, table_name)
    rows = response.json()

    if not rows:
        return table_name, None

    return table_name, parse_date(rows[0].get("work_date"))


def read_latest_work_date_across(candidate_groups):
    latest = []

    for candidates in candidate_groups:
        try:
            table_name, work_date = read_latest_work_date(candidates)
        except RuntimeError as exc:
            if "Hianyzik" in str(exc):
                raise

            print(f"Legutolso datum kihagyva: {exc}", file=sys.stderr)
            continue

        latest.append((table_name, work_date))

    dates = [work_date for _table_name, work_date in latest if work_date]

    if not dates:
        return latest, None

    return latest, min(dates)
