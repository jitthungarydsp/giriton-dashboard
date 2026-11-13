"""Workflow reset and courier notification for a changed finance snapshot."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import requests

from resources.email_sender import send_custom_email
from resources.email_templates_db import courier_email_from_profile, log_email_event
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


WORKFLOW_ACTIONS = ("settlement", "tig", "invoice_submit", "invoice_check", "invoice_payment")
EMAIL_SUBJECT = "Elszámolás frissült"
EMAIL_BODY = (
    "Tisztelt Partnerünk!\n\n"
    "Tájékoztatjuk, hogy az elszámolása frissült és kérjük tekintse át azt, "
    "lehetséges, hogy az áttekintés után el kell fogadja azt, csak utána tud továbblépni "
    "az elszámolási folyamatban.\n\n"
    "Köszönettel:\nJitt Pénzügyi Team"
)


def _headers(prefer: str = "") -> dict[str, str]:
    _url, key = get_supabase_config()
    key = str(key or "").strip()
    if not key:
        raise RuntimeError("Hiányzik a SUPABASE_SERVICE_ROLE_KEY beállítás.")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _status_url() -> str:
    url, _key = get_supabase_config()
    url = str(url or "").rstrip("/")
    if not url:
        raise RuntimeError("Hiányzik a SUPABASE_URL beállítás.")
    return f"{url}/rest/v1/peopleforce_card_statuses"


def _document_url() -> str:
    url, _key = get_supabase_config()
    url = str(url or "").rstrip("/")
    if not url:
        raise RuntimeError("Hiányzik a SUPABASE_URL beállítás.")
    return f"{url}/rest/v1/peopleforce_documents"


def _remove_superseded_automatic_tig(*, courier_id: str, month: str) -> int:
    """Remove only the previous automatically created TIG for this version.

    A later acceptance must generate a new TIG from the new financial snapshot.
    Manually uploaded documents are deliberately preserved.
    """
    response = requests.get(
        _document_url(),
        params={
            "select": "id,note,uploaded_by",
            "courier_id": f"eq.{courier_id}",
            "document_month": f"eq.{month}",
            "document_type": "eq.tig",
            "uploaded_by": "eq.PWA automata",
        },
        headers=_headers(),
        timeout=30,
    )
    raise_for_supabase_error(response)
    deleted = 0
    for row in response.json() or []:
        note = str(row.get("note") or "")
        document_id = str(row.get("id") or "").strip()
        if not document_id or "Automatikus Teljesítés-összesítő generálás elszámolás elfogadása után." not in note:
            continue
        delete_response = requests.delete(
            _document_url(),
            params={"id": f"eq.{document_id}"},
            headers=_headers("return=minimal"),
            timeout=30,
        )
        raise_for_supabase_error(delete_response)
        deleted += 1
    return deleted


def reset_workflow_for_finance_snapshot(
    *,
    courier_id: str,
    courier_name: str,
    period_start: date,
    snapshot_id: str,
    previous_snapshot_id: str = "",
    snapshot_source: str = "",
) -> dict[str, Any]:
    """Require a new settlement acceptance after a replacement snapshot.

    Every saved snapshot moves the whole monthly workflow back to the
    settlement-acceptance step, even if the courier had already progressed to
    invoice handling or payment.
    """
    clean_courier_id = str(courier_id or "").strip()
    clean_name = str(courier_name or "").strip() or clean_courier_id
    if not clean_courier_id:
        return {"reset": False, "emailSent": False, "reason": "missing_courier"}
    month = period_start.replace(day=1).isoformat()
    note = (
        f"Új pénzügyi snapshot érkezett ({str(snapshot_id or '')[:8]}); "
        "az elszámolást ismét át kell tekinteni és el kell fogadni."
    )
    now = datetime.now(timezone.utc).isoformat()
    for action in WORKFLOW_ACTIONS:
        response = requests.post(
            _status_url(),
            params={"on_conflict": "courier_id,document_month,action_key"},
            headers=_headers("resolution=merge-duplicates,return=minimal"),
            json={
                "courier_id": clean_courier_id,
                "courier_name": clean_name,
                "action_key": action,
                "document_month": month,
                "status": "open",
                "status_note": note if action == "settlement" else "Új elszámolási verzió miatt ismét az elszámolás elfogadására vár.",
                "updated_by": "finance-snapshot-refresh",
                "updated_at": now,
            },
            timeout=30,
        )
        raise_for_supabase_error(response)

    removed_tig_count = _remove_superseded_automatic_tig(courier_id=clean_courier_id, month=month)

    recipient = courier_email_from_profile(clean_courier_id)
    subject = f"{EMAIL_SUBJECT} – {period_start:%Y-%m}"
    try:
        if not recipient:
            raise ValueError("A futárhoz nincs rögzített e-mail-cím.")
        result = send_custom_email(recipient, subject, EMAIL_BODY)
        log_email_event(
            courier_id=clean_courier_id, courier_name=clean_name, recipient_email=recipient,
            template_key="finance_snapshot_updated", subject=subject, body=EMAIL_BODY,
            status="sent", sent_by="finance-snapshot-refresh",
            context={"snapshot_id": snapshot_id, "previous_snapshot_id": previous_snapshot_id, "source": snapshot_source},
        )
        return {
            "reset": True,
            "emailSent": True,
            "recipient": recipient,
            "result": result,
            "removedAutomaticTigCount": removed_tig_count,
        }
    except Exception as exc:
        log_email_event(
            courier_id=clean_courier_id, courier_name=clean_name, recipient_email=recipient,
            template_key="finance_snapshot_updated", subject=subject, body=EMAIL_BODY,
            status="failed", error_message=str(exc), sent_by="finance-snapshot-refresh",
            context={"snapshot_id": snapshot_id, "previous_snapshot_id": previous_snapshot_id, "source": snapshot_source},
        )
        return {
            "reset": True,
            "emailSent": False,
            "error": str(exc),
            "removedAutomaticTigCount": removed_tig_count,
        }
