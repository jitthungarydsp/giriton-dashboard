from __future__ import annotations

from datetime import date
from datetime import datetime
from typing import Any

import requests

from resources.courier_master_db import read_courier_master_by_id
from resources.email_sender import (
    DEFAULT_EMAIL_TEMPLATES,
    app_login_url,
    render_template_text,
    send_custom_email,
    validate_email,
)
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


EMAIL_TEMPLATE_TABLE = "email_templates"
EMAIL_LOG_TABLE = "courier_email_log"


def _schema_headers(prefer: str = "") -> dict[str, str]:
    _url, service_role_key = get_supabase_config()
    if not service_role_key:
        raise RuntimeError("Hiányzik a Supabase service role kulcs.")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept-Profile": "settlement",
        "Content-Profile": "settlement",
    }
    if prefer:
        headers["Prefer"] = prefer
        headers["Content-Type"] = "application/json"
    return headers


def _table_url(table_name: str) -> str:
    supabase_url, _service_role_key = get_supabase_config()
    if not supabase_url:
        raise RuntimeError("Hiányzik a Supabase URL.")
    return f"{supabase_url.rstrip('/')}/rest/v1/{table_name}"


def _format_month(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().replace(day=1).isoformat()[:7]
    if isinstance(value, date):
        return value.replace(day=1).isoformat()[:7]
    text = str(value or "").strip()
    return text[:7] if text else ""


def default_template_rows() -> list[dict[str, Any]]:
    return [
        {
            "template_key": key,
            "template_name": str(template.get("name") or key),
            "subject": str(template.get("subject") or ""),
            "body": str(template.get("body") or ""),
            "is_active": True,
            "updated_by": "system",
        }
        for key, template in DEFAULT_EMAIL_TEMPLATES.items()
    ]


def ensure_default_email_templates(updated_by: str = "system") -> int:
    rows = default_template_rows()
    for row in rows:
        row["updated_by"] = updated_by
    response = requests.post(
        _table_url(EMAIL_TEMPLATE_TABLE),
        params={"on_conflict": "template_key"},
        headers=_schema_headers(prefer="resolution=ignore-duplicates,return=representation"),
        json=rows,
        timeout=30,
    )
    raise_for_supabase_error(response)
    try:
        return len(response.json() or [])
    except ValueError:
        return len(rows)


def read_email_templates(active_only: bool = False) -> list[dict[str, Any]]:
    params = {
        "select": "template_key,template_name,subject,body,is_active,updated_by,updated_at,created_at",
        "order": "template_name.asc",
    }
    try:
        response = requests.get(
            _table_url(EMAIL_TEMPLATE_TABLE),
            params=params,
            headers=_schema_headers(),
            timeout=30,
        )
        raise_for_supabase_error(response)
        rows = response.json() or []
    except Exception:
        rows = []
    by_key = {str(row.get("template_key") or ""): row for row in rows}
    for default_row in default_template_rows():
        by_key.setdefault(default_row["template_key"], default_row)
    merged_rows = list(by_key.values())
    if active_only:
        merged_rows = [row for row in merged_rows if bool(row.get("is_active", True))]
    return sorted(merged_rows, key=lambda row: str(row.get("template_name") or row.get("template_key") or ""))


def read_email_template(template_key: str) -> dict[str, Any]:
    clean_key = str(template_key or "").strip()
    for row in read_email_templates(active_only=False):
        if str(row.get("template_key") or "").strip() == clean_key:
            return row
    template = DEFAULT_EMAIL_TEMPLATES.get(clean_key) or DEFAULT_EMAIL_TEMPLATES["free_text"]
    return {
        "template_key": clean_key or "free_text",
        "template_name": str(template.get("name") or clean_key or "Szabad szöveg"),
        "subject": str(template.get("subject") or "JITT üzenet"),
        "body": str(template.get("body") or ""),
        "is_active": True,
    }


def save_email_template(
    template_key: str,
    template_name: str,
    subject: str,
    body: str,
    is_active: bool,
    updated_by: str = "system",
) -> dict[str, Any]:
    clean_key = str(template_key or "").strip()
    if not clean_key:
        raise ValueError("A sablon kulcsa kötelező.")
    if not str(template_name or "").strip():
        raise ValueError("A sablon neve kötelező.")
    if not str(subject or "").strip():
        raise ValueError("A tárgy kötelező.")
    if not str(body or "").strip():
        raise ValueError("A sablon szövege kötelező.")
    payload = {
        "template_key": clean_key,
        "template_name": str(template_name).strip(),
        "subject": str(subject).strip(),
        "body": str(body).strip(),
        "is_active": bool(is_active),
        "updated_by": str(updated_by or "system").strip(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    response = requests.post(
        _table_url(EMAIL_TEMPLATE_TABLE),
        params={"on_conflict": "template_key"},
        headers=_schema_headers(prefer="resolution=merge-duplicates,return=representation"),
        json=payload,
        timeout=30,
    )
    raise_for_supabase_error(response)
    result = response.json() or []
    return result[0] if result else payload


def courier_email_from_profile(courier_id: str) -> str:
    try:
        profile = read_courier_master_by_id(courier_id)
    except Exception:
        return ""
    if profile.empty:
        return ""
    row = profile.iloc[0]
    return str(row.get("email") or row.get("billing_email") or "").strip()


def log_email_event(
    *,
    courier_id: str,
    courier_name: str,
    recipient_email: str,
    template_key: str,
    subject: str,
    body: str,
    status: str,
    error_message: str = "",
    sent_by: str = "system",
    context: dict[str, Any] | None = None,
) -> None:
    payload = {
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "recipient_email": str(recipient_email or "").strip(),
        "template_key": str(template_key or "").strip(),
        "subject": str(subject or "").strip(),
        "body": str(body or "").strip(),
        "status": str(status or "").strip() or "sent",
        "error_message": str(error_message or "").strip(),
        "sent_by": str(sent_by or "system").strip(),
        "context": context or {},
    }
    try:
        response = requests.post(
            _table_url(EMAIL_LOG_TABLE),
            headers=_schema_headers(prefer="return=minimal"),
            json=payload,
            timeout=30,
        )
        raise_for_supabase_error(response)
    except Exception:
        return


def build_template_variables(
    *,
    courier_id: str = "",
    courier_name: str = "",
    month: Any = "",
    amount_huf: str = "",
    document_type: str = "",
    document_title: str = "",
    admin_message: str = "",
    status_note: str = "",
    free_text: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variables = {
        "courier_id": courier_id,
        "courier_name": courier_name or "Futár",
        "month": _format_month(month),
        "amount_huf": amount_huf,
        "document_type": document_type,
        "document_title": document_title,
        "admin_message": admin_message,
        "status_note": status_note,
        "free_text": free_text,
        "login_url": app_login_url(),
    }
    variables.update(extra or {})
    return variables


def send_courier_template_email(
    *,
    courier_id: str,
    courier_name: str,
    template_key: str,
    variables: dict[str, Any] | None = None,
    recipient_email: str = "",
    sent_by: str = "system",
    raise_errors: bool = False,
) -> dict[str, Any]:
    recipient = str(recipient_email or courier_email_from_profile(courier_id)).strip()
    subject = ""
    body = ""
    try:
        recipient = validate_email(recipient)
        template = read_email_template(template_key)
        render_variables = build_template_variables(
            courier_id=str(courier_id or ""),
            courier_name=str(courier_name or ""),
            extra=variables or {},
        )
        subject, body = render_template_text(template.get("subject"), template.get("body"), render_variables)
        result = send_custom_email(recipient, subject, body)
        log_email_event(
            courier_id=courier_id,
            courier_name=courier_name,
            recipient_email=recipient,
            template_key=template_key,
            subject=subject,
            body=body,
            status="sent",
            sent_by=sent_by,
            context=render_variables,
        )
        return result
    except Exception as exc:
        log_email_event(
            courier_id=courier_id,
            courier_name=courier_name,
            recipient_email=recipient,
            template_key=template_key,
            subject=subject,
            body=body,
            status="failed",
            error_message=str(exc),
            sent_by=sent_by,
            context=variables or {},
        )
        if raise_errors:
            raise
        return {"recipient": recipient, "subject": subject, "error": str(exc)}
