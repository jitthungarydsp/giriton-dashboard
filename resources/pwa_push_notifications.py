from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from pywebpush import WebPushException, webpush

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUSH_SUBSCRIPTION_TABLE = "pwa_push_subscriptions"
PUSH_DELIVERY_TABLE = "pwa_push_delivery_log"
LOCAL_VAPID_PRIVATE_FILE = PROJECT_ROOT / "vapid_private.pem"


def load_setting(name: str) -> str:
    def clean(value: Any) -> str:
        text = str(value or "").strip()
        if (
            len(text) >= 2
            and text[0] == text[-1]
            and text[0] in {"'", '"'}
        ):
            text = text[1:-1].strip()
        return text.replace("\\n", "\n")

    value = os.getenv(name, "").strip()
    if value:
        return clean(value)

    try:
        value = st.secrets.get(name, "")
        if value:
            return clean(value)
        supabase_section = st.secrets.get("supabase", {})
        if isinstance(supabase_section, Mapping):
            value = supabase_section.get(name, "")
            if value:
                return clean(value)
        pwa_section = st.secrets.get("pwa", {})
        if isinstance(pwa_section, Mapping):
            value = pwa_section.get(name, "")
            if value:
                return clean(value)
    except Exception:
        pass

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        with secrets_path.open("rb") as file:
            settings = tomllib.load(file)
        return clean(
            settings.get(name)
            or settings.get("supabase", {}).get(name)
            or settings.get("pwa", {}).get(name)
            or ""
        )
    except Exception:
        return ""


def load_vapid_private_key() -> str:
    key = load_setting("VAPID_PRIVATE_KEY")
    if key:
        return normalize_pem_private_key(key)
    if LOCAL_VAPID_PRIVATE_FILE.exists():
        try:
            return normalize_pem_private_key(
                LOCAL_VAPID_PRIVATE_FILE.read_text(encoding="utf-8").strip()
            )
        except Exception:
            return ""
    return ""


def normalize_pem_private_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    begin = "-----BEGIN PRIVATE KEY-----"
    end = "-----END PRIVATE KEY-----"

    if begin not in text or end not in text:
        return text

    body = text.split(begin, 1)[1].split(end, 1)[0]
    body = re.sub(r"\s+", "", body)
    lines = [body[index:index + 64] for index in range(0, len(body), 64)]
    return "\n".join([begin, *lines, end])


def _supabase_headers(prefer: str = "") -> dict[str, str]:
    _supabase_url, service_role_key = get_supabase_config()
    headers = {
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    if service_role_key and not service_role_key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {service_role_key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _supabase_request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str = "",
) -> Any:
    supabase_url, _service_role_key = get_supabase_config()
    response = requests.request(
        method,
        f"{supabase_url.rstrip('/')}/rest/v1/{table}",
        headers=_supabase_headers(prefer),
        params=params,
        json=payload,
        timeout=60,
    )
    raise_for_supabase_error(response)
    if not response.content:
        return []
    return response.json()


def _load_subscriptions(courier_id: str | int) -> list[dict[str, Any]]:
    clean_id = str(courier_id or "").strip()
    if not clean_id:
        return []
    return _supabase_request(
        "GET",
        PUSH_SUBSCRIPTION_TABLE,
        params={
            "select": "id,courier_id,endpoint,p256dh,auth",
            "courier_id": f"eq.{clean_id}",
            "active": "eq.true",
            "order": "updated_at.desc",
            "limit": "100",
        },
    )


def load_active_push_subscribers() -> dict[str, dict[str, Any]]:
    rows = _supabase_request(
        "GET",
        PUSH_SUBSCRIPTION_TABLE,
        params={
            "select": "courier_id,courier_name,updated_at,last_seen_at",
            "active": "eq.true",
            "order": "courier_id.asc,updated_at.desc",
            "limit": "10000",
        },
    )
    subscribers: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        courier_id = str(row.get("courier_id") or "").strip()
        if not courier_id:
            continue
        item = subscribers.setdefault(
            courier_id,
            {
                "courier_id": courier_id,
                "courier_name": str(row.get("courier_name") or "").strip(),
                "subscription_count": 0,
                "last_seen_at": "",
                "updated_at": "",
            },
        )
        item["subscription_count"] += 1
        for field in ("last_seen_at", "updated_at"):
            value = str(row.get(field) or "").strip()
            if value and value > str(item.get(field) or ""):
                item[field] = value
        if not item.get("courier_name") and row.get("courier_name"):
            item["courier_name"] = str(row.get("courier_name") or "").strip()
    return subscribers


def _deactivate_subscription(subscription_id: Any) -> None:
    clean_id = str(subscription_id or "").strip()
    if not clean_id:
        return
    _supabase_request(
        "PATCH",
        PUSH_SUBSCRIPTION_TABLE,
        params={"id": f"eq.{clean_id}"},
        payload={
            "active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def _log_delivery(
    *,
    courier_id: str | int,
    notification_type: str,
    status: str,
    message: str,
    work_date: date | str | None = None,
) -> None:
    log_date = work_date or datetime.now(timezone.utc).date()
    if isinstance(log_date, date):
        log_date = log_date.isoformat()
    try:
        _supabase_request(
            "POST",
            PUSH_DELIVERY_TABLE,
            payload={
                "courier_id": int(courier_id),
                "work_date": str(log_date)[:10],
                "notification_type": notification_type,
                "status": status,
                "message": str(message or "")[:2000],
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )
    except Exception:
        # A push kuldes fontosabb, mint a naplozas. Ha a courier_master FK
        # miatt nem lehet logolni, attol meg a folyamat ne alljon meg.
        return


def load_latest_delivery_message(
    *,
    courier_id: str | int,
    notification_type: str,
) -> str:
    clean_id = str(courier_id or "").strip()
    clean_type = str(notification_type or "").strip()
    if not clean_id or not clean_type:
        return ""
    try:
        rows = _supabase_request(
            "GET",
            PUSH_DELIVERY_TABLE,
            params={
                "select": "status,message,sent_at",
                "courier_id": f"eq.{int(clean_id)}",
                "notification_type": f"eq.{clean_type}",
                "order": "sent_at.desc",
                "limit": "1",
            },
        )
    except Exception:
        return ""
    if not rows:
        return ""
    row = rows[0]
    status = str(row.get("status") or "").strip()
    message = str(row.get("message") or "").strip()
    return f"{status}: {message}" if status else message


def send_push_to_courier(
    *,
    courier_id: str | int,
    title: str,
    body: str,
    tag: str,
    url: str = "/",
    notification_type: str = "generic",
    work_date: date | str | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    vapid_private_key = load_vapid_private_key()
    vapid_subject = load_setting("VAPID_SUBJECT") or "mailto:admin@giriton.local"
    if not vapid_private_key:
        _log_delivery(
            courier_id=courier_id,
            notification_type=notification_type,
            status="failed",
            message="Hianyzik a VAPID_PRIVATE_KEY beallitas.",
            work_date=work_date,
        )
        return "missing_vapid"

    subscriptions = _load_subscriptions(courier_id)
    if not subscriptions:
        _log_delivery(
            courier_id=courier_id,
            notification_type=notification_type,
            status="failed",
            message="A futarnak nincs aktiv PWA push feliratkozasa.",
            work_date=work_date,
        )
        return "no_subscription"

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "tag": tag,
            "url": url,
            "renotify": False,
            "data": data or {},
        },
        ensure_ascii=False,
    )

    success = False
    errors: list[str] = []
    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.get("endpoint"),
            "keys": {
                "p256dh": subscription.get("p256dh"),
                "auth": subscription.get("auth"),
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_subject},
                ttl=12 * 60 * 60,
            )
            success = True
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            errors.append(f"subscription={subscription.get('id')} status={status_code} error={exc}")
            if status_code in {404, 410}:
                _deactivate_subscription(subscription.get("id"))
        except Exception as exc:
            errors.append(f"subscription={subscription.get('id')} error={exc}")

    if success:
        _log_delivery(
            courier_id=courier_id,
            notification_type=notification_type,
            status="sent",
            message=body,
            work_date=work_date,
        )
        return "sent"

    error_text = " | ".join(errors) or "Ismeretlen push hiba."
    _log_delivery(
        courier_id=courier_id,
        notification_type=notification_type,
        status="failed",
        message=error_text,
        work_date=work_date,
    )
    return "failed"


def notify_new_peopleforce_document(
    *,
    courier_id: str | int,
    document_type: str,
    document_month: date | str,
    title: str,
    file_name: str,
) -> str:
    type_labels = {
        "settlement": "elszámolás",
        "tig": "TIG",
        "invoice": "számla",
        "complaint_response": "reklamációs válasz",
    }
    clean_type = str(document_type or "").strip()
    clean_month = str(document_month or "")[:7]
    label = type_labels.get(clean_type, "dokumentum")
    visible_title = str(title or file_name or label).strip()
    notification_title = "Új dokumentum érkezett"
    notification_body = f"Új {label} érkezett ({clean_month}): {visible_title}"
    notification_tag = f"new-document-{courier_id}-{clean_type}-{clean_month}"
    notification_type = "new_document"
    if clean_type == "complaint_response":
        notification_title = "Válasz érkezett a reklamációdra"
        notification_body = f"A reklamációdra válasz érkezett ({clean_month})."
        notification_tag = f"complaint-response-{courier_id}-{clean_month}"
        notification_type = "complaint_response"
        return send_push_to_courier(
            courier_id=courier_id,
            title=notification_title,
            body=notification_body,
            tag=notification_tag,
            url="/?tab=settlement",
            notification_type=notification_type,
            work_date=f"{clean_month}-01" if len(clean_month) == 7 else None,
            data={
                "section": "settlement",
                "documentType": clean_type,
                "documentMonth": clean_month,
            },
        )
    return send_push_to_courier(
        courier_id=courier_id,
        title="Új dokumentum érkezett",
        body=f"Új {label} érkezett ({clean_month}): {visible_title}",
        tag=notification_tag,
        url="/?tab=settlement",
        notification_type=notification_type,
        work_date=f"{clean_month}-01" if len(clean_month) == 7 else None,
        data={
            "section": "settlement",
            "documentType": clean_type,
            "documentMonth": clean_month,
        },
    )
