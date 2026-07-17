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
from resources.pwa_push_notifications import notify_new_peopleforce_document


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
DOCUMENT_METADATA_COLUMNS = [
    column for column in DOCUMENT_COLUMNS if column != "file_content_base64"
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
    "admin_response",
    "responded_by",
    "responded_at",
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


def _notify_document_uploaded(payload):
    try:
        notify_new_peopleforce_document(
            courier_id=payload.get("courier_id"),
            document_type=payload.get("document_type"),
            document_month=payload.get("document_month"),
            title=payload.get("title"),
            file_name=payload.get("file_name"),
        )
    except Exception:
        # A dokumentumfeltöltés fontosabb, mint az értesítés. Ha a push
        # konfiguráció vagy a feliratkozás hibás, a feltöltést nem állítjuk meg.
        return


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
def read_peopleforce_documents_for_courier(courier_id, limit=500):
    supabase_url = require_supabase()
    courier_id = str(courier_id or "").strip()
    if not courier_id:
        return pd.DataFrame(columns=DOCUMENT_COLUMNS)
    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(),
        params={
            "select": ",".join(DOCUMENT_METADATA_COLUMNS),
            "courier_id": f"eq.{courier_id}",
            "order": "document_month.desc,uploaded_at.desc",
            "limit": str(int(limit)),
        },
        timeout=60,
    )
    raise_for_supabase_error(response)
    rows = response.json()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=DOCUMENT_METADATA_COLUMNS)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_documents_for_month(document_month, document_type=None, limit=5000):
    supabase_url = require_supabase()
    params = {
        "select": ",".join(DOCUMENT_METADATA_COLUMNS),
        "document_month": f"eq.{format_month(document_month)}",
        "order": "courier_name.asc,uploaded_at.desc",
        "limit": str(int(limit)),
    }
    document_type = str(document_type or "").strip()
    if document_type:
        params["document_type"] = f"eq.{document_type}"

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(),
        params=params,
        timeout=60,
    )
    raise_for_supabase_error(response)
    rows = response.json()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=DOCUMENT_METADATA_COLUMNS)


@st.cache_data(show_spinner=False, ttl=120)
def read_peopleforce_document_content(document_id):
    supabase_url = require_supabase()
    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(),
        params={
            "select": "id,file_name,mime_type,file_content_base64",
            "id": f"eq.{str(document_id or '').strip()}",
            "limit": "1",
        },
        timeout=60,
    )
    raise_for_supabase_error(response)
    rows = response.json()
    return rows[0] if rows else {}


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
    if response.status_code == 400 and "admin_response" in response.text:
        response = requests.get(
            f"{supabase_url}/rest/v1/peopleforce_complaints",
            headers=supabase_headers(),
            params={
                "select": ",".join(COMPLAINT_COLUMNS[:9]),
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
def read_peopleforce_complaints_for_month(document_month, document_type=None, limit=5000):
    supabase_url = require_supabase()
    params = {
        "select": ",".join(COMPLAINT_COLUMNS),
        "document_month": f"eq.{format_month(document_month)}",
        "order": "created_at.desc",
        "limit": str(int(limit)),
    }
    document_type = str(document_type or "").strip()
    if document_type:
        params["document_type"] = f"eq.{document_type}"

    response = requests.get(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(),
        params=params,
        timeout=60,
    )
    if response.status_code == 400 and "admin_response" in response.text:
        fallback_columns = COMPLAINT_COLUMNS[:9]
        params["select"] = ",".join(fallback_columns)
        response = requests.get(
            f"{supabase_url}/rest/v1/peopleforce_complaints",
            headers=supabase_headers(),
            params=params,
            timeout=60,
        )
    raise_for_supabase_error(response)
    rows = response.json()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=COMPLAINT_COLUMNS)


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
    read_peopleforce_documents_for_courier.clear()
    read_peopleforce_documents_for_month.clear()
    read_peopleforce_document_content.clear()
    read_peopleforce_document_markers.clear()
    _notify_document_uploaded(payload)

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
    read_peopleforce_documents_for_courier.clear()
    read_peopleforce_documents_for_month.clear()
    read_peopleforce_document_content.clear()
    read_peopleforce_document_markers.clear()
    _notify_document_uploaded(payload)

    return response.json()


def update_peopleforce_document(document_id, *, title, note):
    supabase_url = require_supabase()
    response = requests.patch(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(prefer_return=True),
        params={"id": f"eq.{str(document_id or '').strip()}"},
        json={"title": str(title or "").strip(), "note": str(note or "").strip()},
        timeout=30,
    )
    raise_for_supabase_error(response)
    read_peopleforce_documents.clear()
    read_peopleforce_documents_for_courier.clear()
    read_peopleforce_documents_for_month.clear()
    read_peopleforce_document_content.clear()
    read_peopleforce_document_markers.clear()
    return response.json()


def delete_peopleforce_document(document_id):
    supabase_url = require_supabase()
    response = requests.delete(
        f"{supabase_url}/rest/v1/peopleforce_documents",
        headers=supabase_headers(prefer_return=True),
        params={"id": f"eq.{str(document_id or '').strip()}"},
        timeout=30,
    )
    raise_for_supabase_error(response)
    read_peopleforce_documents.clear()
    read_peopleforce_documents_for_courier.clear()
    read_peopleforce_documents_for_month.clear()
    read_peopleforce_document_content.clear()
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
    read_peopleforce_complaints_for_month.clear()
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
    read_peopleforce_complaints_for_month.clear()
    read_peopleforce_complaint_markers.clear()
    return response.json()


def respond_to_peopleforce_complaint(
    complaint_id,
    response_message,
    responded_by,
    *,
    courier_id,
    courier_name,
    document_type,
    document_month,
):
    supabase_url = require_supabase()
    message = str(response_message or "").strip()
    upload_peopleforce_document_bytes(
        courier_id=courier_id,
        courier_name=courier_name,
        document_type="complaint_response",
        document_month=document_month,
        title=f"Reklamáció válasz ({document_type}) - {complaint_id}",
        note=message,
        file_name=f"reklamacio_valasz_{complaint_id}.txt",
        mime_type="text/plain; charset=utf-8",
        file_bytes=message.encode("utf-8"),
        uploaded_by=responded_by,
    )
    response = requests.patch(
        f"{supabase_url}/rest/v1/peopleforce_complaints",
        headers=supabase_headers(prefer_return=True),
        params={"id": f"eq.{str(complaint_id or '').strip()}"},
        json={
            "admin_response": str(response_message or "").strip(),
            "responded_by": str(responded_by or "").strip(),
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "status": "resolved",
        },
        timeout=30,
    )
    if response.status_code == 400 and "admin_response" in response.text:
        response = requests.patch(
            f"{supabase_url}/rest/v1/peopleforce_complaints",
            headers=supabase_headers(prefer_return=True),
            params={"id": f"eq.{str(complaint_id or '').strip()}"},
            json={"status": "resolved"},
            timeout=30,
        )
    raise_for_supabase_error(response)
    read_peopleforce_complaints.clear()
    read_peopleforce_complaints_for_month.clear()
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
