import base64
from datetime import date
from datetime import datetime
from datetime import timezone

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


DOCUMENT_COLUMNS = [
    "id",
    "courier_id",
    "courier_name",
    "document_type",
    "document_month",
    "title",
    "file_name",
    "mime_type",
    "file_size",
    "note",
    "uploaded_by",
    "uploaded_at",
    "file_content_base64",
]

COMPLAINT_COLUMNS = [
    "id",
    "courier_id",
    "courier_name",
    "document_type",
    "document_month",
    "message",
    "status",
    "created_by",
    "created_at",
]

STATUS_COLUMNS = [
    "id",
    "courier_id",
    "courier_name",
    "action_key",
    "document_month",
    "status",
    "status_note",
    "updated_by",
    "updated_at",
]


def format_month(value):
    if isinstance(value, date):
        return value.replace(day=1).isoformat()

    text = str(value or "").strip()

    if len(text) == 7:
        return f"{text}-01"

    return text[:10]


def supabase_headers(prefer_return=False):
    _supabase_url, service_role_key = get_supabase_config()
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    if prefer_return:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

    return headers


def require_supabase():
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    return supabase_url


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_documents(courier_id, document_month, document_type):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()

    if not courier_id:
        return pd.DataFrame(columns=DOCUMENT_COLUMNS)

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(),
        params={
            "select": ",".join(DOCUMENT_COLUMNS),
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{format_month(document_month)}",
            "document_type": f"eq.{document_type}",
            "order": "uploaded_at.desc",
            "limit": "200",
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=DOCUMENT_COLUMNS)

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_complaints(courier_id, document_month, document_type):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()

    if not courier_id:
        return pd.DataFrame(columns=COMPLAINT_COLUMNS)

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(),
        params={
            "select": ",".join(COMPLAINT_COLUMNS),
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{format_month(document_month)}",
            "document_type": f"eq.{document_type}",
            "order": "created_at.desc",
            "limit": "100",
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=COMPLAINT_COLUMNS)

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_document_markers(courier_id, document_month):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()

    if not courier_id:
        return pd.DataFrame(columns=["id", "document_type", "uploaded_at"])

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(),
        params={
            "select": "id,document_type,uploaded_at",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{format_month(document_month)}",
            "order": "uploaded_at.desc",
            "limit": "500",
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=["id", "document_type", "uploaded_at"])

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_complaint_markers(courier_id, document_month):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()

    if not courier_id:
        return pd.DataFrame(columns=["id", "document_type", "status", "created_at"])

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(),
        params={
            "select": "id,document_type,status,created_at",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{format_month(document_month)}",
            "order": "created_at.desc",
            "limit": "500",
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=["id", "document_type", "status", "created_at"])

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_card_statuses(courier_id, document_month):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()

    if not courier_id:
        return pd.DataFrame(columns=STATUS_COLUMNS)

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_card_statuses",
        headers=supabase_headers(),
        params={
            "select": ",".join(STATUS_COLUMNS),
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{format_month(document_month)}",
            "order": "updated_at.desc",
            "limit": "100",
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=STATUS_COLUMNS)

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_card_statuses_for_month(document_month, action_key=None):
    supabase_url = require_supabase()
    params = {
        "select": ",".join(STATUS_COLUMNS),
        "document_month": f"eq.{format_month(document_month)}",
        "order": "updated_at.desc",
        "limit": "5000",
    }

    action_key = str(action_key or "").strip()
    if action_key:
        params["action_key"] = f"eq.{action_key}"

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_card_statuses",
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )
    raise_for_supabase_error(response)
    rows = response.json()

    if not rows:
        return pd.DataFrame(columns=STATUS_COLUMNS)

    return pd.DataFrame(rows)


def upload_peopleforce_document(
    *,
    courier_id,
    courier_name,
    document_type,
    document_month,
    title,
    note,
    uploaded_file,
    uploaded_by,
):
    supabase_url = require_supabase()
    file_bytes = uploaded_file.getvalue()
    payload = {
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "document_type": str(document_type or "").strip(),
        "document_month": format_month(document_month),
        "title": str(title or "").strip(),
        "file_name": str(uploaded_file.name or "").strip(),
        "mime_type": str(uploaded_file.type or "").strip(),
        "file_size": len(file_bytes),
        "file_content_base64": base64.b64encode(file_bytes).decode("ascii"),
        "note": str(note or "").strip(),
        "uploaded_by": str(uploaded_by or "").strip(),
    }

    response = requests.post(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(prefer_return=True),
        json=payload,
        timeout=60,
    )
    raise_for_supabase_error(response)
    read_peopleforce_documents.clear()
    read_peopleforce_document_markers.clear()

    return response.json()


def upload_peopleforce_document_bytes(
    *,
    courier_id,
    courier_name,
    document_type,
    document_month,
    title,
    note,
    file_name,
    mime_type,
    file_bytes,
    uploaded_by,
):
    supabase_url = require_supabase()
    file_bytes = file_bytes or b""
    payload = {
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "document_type": str(document_type or "").strip(),
        "document_month": format_month(document_month),
        "title": str(title or "").strip(),
        "file_name": str(file_name or "").strip(),
        "mime_type": str(mime_type or "application/octet-stream").strip(),
        "file_size": len(file_bytes),
        "file_content_base64": base64.b64encode(file_bytes).decode("ascii"),
        "note": str(note or "").strip(),
        "uploaded_by": str(uploaded_by or "").strip(),
    }

    response = requests.post(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(prefer_return=True),
        json=payload,
        timeout=60,
    )
    raise_for_supabase_error(response)
    read_peopleforce_documents.clear()
    read_peopleforce_document_markers.clear()

    return response.json()


def create_peopleforce_complaint(
    *,
    courier_id,
    courier_name,
    document_type,
    document_month,
    message,
    created_by,
):
    supabase_url = require_supabase()
    payload = {
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "document_type": str(document_type or "").strip(),
        "document_month": format_month(document_month),
        "message": str(message or "").strip(),
        "status": "new",
        "created_by": str(created_by or "").strip(),
    }

    response = requests.post(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(prefer_return=True),
        json=payload,
        timeout=30,
    )
    raise_for_supabase_error(response)
    read_peopleforce_complaints.clear()
    read_peopleforce_complaint_markers.clear()

    return response.json()


def update_peopleforce_complaint_status(complaint_id, status):
    supabase_url = require_supabase()
    response = requests.patch(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(prefer_return=True),
        params={"id": f"eq.{str(complaint_id or '').strip()}"},
        json={"status": str(status or "resolved").strip()},
        timeout=30,
    )
    raise_for_supabase_error(response)
    read_peopleforce_complaints.clear()
    read_peopleforce_complaint_markers.clear()
    return response.json()


def upsert_peopleforce_card_status(
    *,
    courier_id,
    courier_name,
    action_key,
    document_month,
    status,
    status_note="",
    updated_by="",
):
    supabase_url = require_supabase()
    clean_status = str(status or "").strip().lower()

    if clean_status not in ["open", "done"]:
        clean_status = "open"

    payload = {
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "action_key": str(action_key or "").strip(),
        "document_month": format_month(document_month),
        "status": clean_status,
        "status_note": str(status_note or "").strip(),
        "updated_by": str(updated_by or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = supabase_headers(prefer_return=True)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    response = requests.post(
        f"{supabase_url}/rest/v1/peopleforce_card_statuses"
        "?on_conflict=courier_id,document_month,action_key",
        headers=headers,
        json=payload,
        timeout=30,
    )
    raise_for_supabase_error(response)
    read_peopleforce_card_statuses.clear()
    read_peopleforce_card_statuses_for_month.clear()

    return response.json()


def decode_document_content(value):
    if not value:
        return b""

    return base64.b64decode(str(value).encode("ascii"))
