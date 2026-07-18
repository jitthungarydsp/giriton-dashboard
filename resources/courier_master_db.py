from datetime import datetime, timezone
import re

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


SELECT_FIELDS = (
    "courier_id,courier_name,phone_number,email,warehouse_name,"
    "company_name,company_address,tax_number,"
    "bank_account_number,billing_email,"
    "active,fetched_at,updated_at"
)

DEFAULT_ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"

STAGING_SELECT_FIELDS = (
    "id,source_file,source_row_number,courier_id,courier_name,email,phone_number,"
    "company_name,company_address,tax_number,bank_account_number,billing_email"
)


def _clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "#ref!", "n/a"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _normalize_courier_id(value):
    text = _clean_text(value)
    if not text:
        return ""
    try:
        numeric = float(text.replace(",", "."))
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass
    return text


def _normalize_phone(value):
    digits = re.sub(r"\D+", "", _clean_text(value))
    if digits.startswith("0036"):
        digits = "36" + digits[4:]
    elif digits.startswith("06"):
        digits = "36" + digits[2:]
    elif len(digits) == 9 and digits.startswith(("20", "30", "31", "50", "70")):
        digits = "36" + digits
    return digits


def _normalize_tax_number(value):
    return re.sub(r"\s+", "", _clean_text(value)).upper()


def _supabase_headers(service_role_key, *, prefer=None):
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        f"?select={SELECT_FIELDS}"
        "&order=courier_name.asc,courier_id.asc"
        "&limit=5000"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=30,
    )

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master_by_id(courier_id):
    supabase_url, service_role_key = get_supabase_config()
    courier_id = str(courier_id or "").strip()

    if not supabase_url or not service_role_key or not courier_id:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master"
        f"?select={SELECT_FIELDS}"
        f"&courier_id=eq.{courier_id}"
        "&limit=1"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    response = requests.get(
        endpoint,
        headers=headers,
        timeout=30,
    )

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=300)
def read_courier_master_sheet_import():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        return pd.DataFrame()

    endpoint = (
        f"{supabase_url}/rest/v1/courier_master_sheet_import"
        f"?select={STAGING_SELECT_FIELDS}"
        "&order=source_file.asc,source_row_number.asc"
        "&limit=5000"
    )

    response = requests.get(
        endpoint,
        headers=_supabase_headers(service_role_key),
        timeout=30,
    )

    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _unique_phone_index(master_rows):
    grouped = {}
    duplicates = set()
    for row in master_rows:
        phone = _normalize_phone(row.get("phone_number"))
        if not phone:
            continue
        if phone in grouped:
            duplicates.add(phone)
        else:
            grouped[phone] = row
    return {phone: row for phone, row in grouped.items() if phone not in duplicates}


def _build_billing_patch(staging_row, master_row):
    patch = {}
    changed_fields = []
    for field in (
        "company_name",
        "company_address",
        "tax_number",
        "bank_account_number",
        "billing_email",
    ):
        value = _clean_text(staging_row.get(field))
        if field == "tax_number":
            value = _normalize_tax_number(value)
        current = _clean_text(master_row.get(field))
        if value and value != current:
            patch[field] = value
            changed_fields.append(field)

    for field in ("email", "phone_number"):
        current = _clean_text(master_row.get(field))
        value = _clean_text(staging_row.get(field))
        if not current and value:
            patch[field] = value
            changed_fields.append(field)

    if patch:
        patch["billing_data_source"] = (
            f"courier_master_sheet_import:{staging_row.get('source_file')}:"
            f"{staging_row.get('source_row_number')} ({', '.join(changed_fields)})"
        )
        now = datetime.now(timezone.utc).isoformat()
        patch["billing_data_updated_at"] = now
        patch["updated_at"] = now

    return patch


def _build_master_insert(staging_row):
    courier_id = _normalize_courier_id(staging_row.get("courier_id"))
    courier_name = _clean_text(staging_row.get("courier_name"))
    if not courier_id or not courier_name:
        return {}

    try:
        courier_id_value = int(courier_id)
    except (TypeError, ValueError):
        return {}

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "courier_id": courier_id_value,
        "courier_name": courier_name,
        "phone_number": _clean_text(staging_row.get("phone_number")),
        "email": _clean_text(staging_row.get("email")),
        "warehouse_name": _clean_text(staging_row.get("warehouse_name")),
        "source_name": "courier_master_sheet_import",
        "organization_id": DEFAULT_ORGANIZATION_ID,
        "dsp_id": "JIT",
        "active": True,
        "response_json": {
            "imported_from": "courier_master_sheet_import",
            "source_file": staging_row.get("source_file"),
            "source_row_number": staging_row.get("source_row_number"),
        },
        "fetched_at": now,
        "updated_at": now,
        "billing_data_source": (
            f"courier_master_sheet_import:{staging_row.get('source_file')}:"
            f"{staging_row.get('source_row_number')}"
        ),
        "billing_data_updated_at": now,
    }

    for field in (
        "company_name",
        "company_address",
        "tax_number",
        "bank_account_number",
        "billing_email",
    ):
        value = _clean_text(staging_row.get(field))
        if field == "tax_number":
            value = _normalize_tax_number(value)
        if value:
            row[field] = value

    return row


def build_billing_staging_update_preview(courier_ids=None):
    courier_filter = {
        _normalize_courier_id(courier_id)
        for courier_id in (courier_ids or [])
        if _normalize_courier_id(courier_id)
    }
    master_df = read_courier_master()
    staging_df = read_courier_master_sheet_import()

    if master_df.empty or staging_df.empty:
        return {
            "updates": [],
            "no_match": [],
            "master_count": len(master_df),
            "staging_count": len(staging_df),
        }

    master_rows = master_df.to_dict("records")
    master_by_id = {
        _normalize_courier_id(row.get("courier_id")): row
        for row in master_rows
        if _normalize_courier_id(row.get("courier_id"))
    }
    master_by_phone = _unique_phone_index(master_rows)

    updates = []
    no_match = []
    inserts = []
    seen_master_ids = set()
    seen_insert_ids = set()
    for staging_row in staging_df.to_dict("records"):
        staging_id = _normalize_courier_id(staging_row.get("courier_id"))
        master_row = master_by_id.get(staging_id) if staging_id else None
        if not master_row:
            master_row = master_by_phone.get(_normalize_phone(staging_row.get("phone_number")))
        if not master_row:
            if (
                staging_id
                and staging_id not in master_by_id
                and staging_id not in seen_insert_ids
                and (not courier_filter or staging_id in courier_filter)
            ):
                insert_row = _build_master_insert(staging_row)
                if insert_row:
                    seen_insert_ids.add(staging_id)
                    inserts.append(
                        {
                            "courier_id": staging_id,
                            "courier_name": staging_row.get("courier_name"),
                            "row": insert_row,
                        }
                    )
                    continue
            no_match.append(staging_row)
            continue

        master_id = _normalize_courier_id(master_row.get("courier_id"))
        if courier_filter and master_id not in courier_filter:
            continue
        if master_id in seen_master_ids:
            continue

        patch = _build_billing_patch(staging_row, master_row)
        if patch:
            seen_master_ids.add(master_id)
            updates.append(
                {
                    "courier_id": master_id,
                    "courier_name": master_row.get("courier_name") or staging_row.get("courier_name"),
                    "source_name": staging_row.get("courier_name"),
                    "patch": patch,
                }
            )

    return {
        "updates": updates,
        "inserts": inserts,
        "no_match": no_match,
        "master_count": len(master_df),
        "staging_count": len(staging_df),
    }


def apply_billing_staging_updates(updates, inserts=None):
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a Supabase kapcsolat.")

    success = 0
    inserted = 0
    failures = []
    for update in updates:
        courier_id = _normalize_courier_id(update.get("courier_id"))
        patch = dict(update.get("patch") or {})
        if not courier_id or not patch:
            continue
        response = requests.patch(
            f"{supabase_url}/rest/v1/courier_master",
            headers=_supabase_headers(service_role_key, prefer="return=minimal"),
            params={"courier_id": f"eq.{courier_id}"},
            json=patch,
            timeout=30,
        )
        if response.ok:
            success += 1
        else:
            failures.append(
                {
                    "courier_id": courier_id,
                    "courier_name": update.get("courier_name"),
                    "error": response.text[:1000],
                }
            )

    insert_rows = [dict(row.get("row") or {}) for row in (inserts or []) if row.get("row")]
    if insert_rows:
        response = requests.post(
            f"{supabase_url}/rest/v1/courier_master",
            headers=_supabase_headers(
                service_role_key,
                prefer="resolution=merge-duplicates,return=minimal",
            ),
            params={"on_conflict": "courier_id"},
            json=insert_rows,
            timeout=60,
        )
        if response.ok:
            inserted = len(insert_rows)
        else:
            for row in insert_rows:
                failures.append(
                    {
                        "courier_id": row.get("courier_id"),
                        "courier_name": row.get("courier_name"),
                        "error": response.text[:1000],
                    }
                )

    read_courier_master.clear()
    read_courier_master_by_id.clear()
    read_courier_master_sheet_import.clear()
    return {"success": success, "inserted": inserted, "failures": failures}


def update_courier_master_profile(courier_id, profile_fields):
    supabase_url, service_role_key = get_supabase_config()
    courier_id = _normalize_courier_id(courier_id)

    if not supabase_url or not service_role_key:
        raise RuntimeError("Hianyzik a Supabase kapcsolat.")

    if not courier_id:
        raise RuntimeError("Hianyzik a futar ID.")

    allowed_fields = {
        "courier_name",
        "email",
        "phone_number",
        "warehouse_name",
        "company_name",
        "company_address",
        "tax_number",
        "bank_account_number",
        "billing_email",
    }

    patch = {}
    for field, value in (profile_fields or {}).items():
        if field not in allowed_fields:
            continue

        cleaned = _clean_text(value)
        if field == "tax_number":
            cleaned = _normalize_tax_number(cleaned)

        patch[field] = cleaned

    if not patch:
        return {"updated": False, "message": "Nincs mentheto valtozas."}

    now = datetime.now(timezone.utc).isoformat()
    patch["updated_at"] = now

    upsert_row = dict(patch)
    try:
        upsert_row["courier_id"] = int(courier_id)
    except (TypeError, ValueError):
        upsert_row["courier_id"] = courier_id

    upsert_row.setdefault("source_name", "profile_form")
    upsert_row.setdefault("organization_id", DEFAULT_ORGANIZATION_ID)
    upsert_row.setdefault("dsp_id", "JIT")
    upsert_row.setdefault("active", True)
    upsert_row.setdefault("fetched_at", now)

    response = requests.post(
        f"{supabase_url}/rest/v1/courier_master",
        headers=_supabase_headers(
            service_role_key,
            prefer="resolution=merge-duplicates,return=minimal",
        ),
        params={"on_conflict": "courier_id"},
        json=upsert_row,
        timeout=30,
    )
    raise_for_supabase_error(response)

    read_courier_master.clear()
    read_courier_master_by_id.clear()

    return {"updated": True, "message": "Profil adatok mentve."}
