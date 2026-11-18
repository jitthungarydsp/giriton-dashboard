"""Persistent internal complaint assignments and their e-mail outbox.

The existing unique courier/month/action key is the assignment's compare-and-swap
record. Internal records never participate in the courier's settlement workflow.
No new database table, financial recalculation or background browser is needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Event, Thread

PREFIX = "internal_complaint_assignment:"
logger = logging.getLogger(__name__)


def assignment_value(row):
    try:
        value = json.loads(row.get("status_note") or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        return None
    if row.get("action_key") != PREFIX + str(value.get("complaintId") or ""):
        return None
    if str(row.get("courier_id")) != value.get("courierId") or str(row.get("document_month"))[:7] != value.get("month"):
        return None
    return value


def notification_message(value):
    subject = f"Reklamáció kijelölve: {value['courierName']} · {value['month']}"
    subject = subject.replace("\r", " ").replace("\n", " ")[:240]
    body = (
        f"Kedves {value['assignee']['name']}!\n\n"
        "Az alábbi reklamáció ügyintézésére téged jelöltek ki.\n\n"
        f"Futár: {value['courierName']} (#{value['courierId']})\n"
        f"Elszámolási hónap: {value['month']}\n"
        f"Ügyazonosító: {value['complaintId']}\n"
        f"Kijelölte: {value['assignedBy']}\n\n"
        f"A reklamáció szövege:\n{value.get('complaintMessage', '')}\n\n"
        f"Ügy megnyitása (admin bejelentkezés szükséges):\n{value['hubUrl']}\n\n"
        "Köszönettel:\nJITT Pénzügyi Team\n"
    )
    return subject, body


def verified_recipient(rest, value):
    person = value.get("assignee") or {}
    if person.get("key") == "bagoly_zoltan" and person.get("email") == "zoltan.bagoly@jitt.hu":
        return person["email"]
    if person.get("key") == "gurzo_balazs":
        rows = rest("GET", "pwa_users", params={"courier_id": "eq.7644", "active": "eq.true", "select": "email,role", "limit": "1"})
        if rows and str(rows[0].get("role", "")).lower() in {"admin", "superadmin"}:
            if person.get("email") and person["email"].strip().casefold() == str(rows[0].get("email") or "").strip().casefold():
                return person["email"].strip()
    raise ValueError("A felelős e-mail-címe nem igazolható.")


def save_delivery(rest, row, value, now, status):
    previous_time = datetime.fromisoformat(str(row['updated_at']).replace('Z', '+00:00'))
    if now <= previous_time:
        now = previous_time + timedelta(microseconds=1)
    payload = {"status_note": json.dumps(value, ensure_ascii=False), "status": status,
               "updated_at": now.isoformat(), "updated_by": "complaint-assignment-notifier"}
    rows = rest("PATCH", "peopleforce_card_statuses", params={
        "id": f"eq.{row['id']}", "updated_at": f"eq.{row['updated_at']}", "status": f"eq.{row['status']}"
    }, payload=payload, prefer="return=representation")
    return rows[0] if len(rows or []) == 1 else None


def process_pending_assignments(rest, send_email, *, validate_config=lambda: None, now=None):
    now = now or datetime.now(timezone.utc)
    rows = rest("GET", "peopleforce_card_statuses", params={
        "select": "id,courier_id,document_month,action_key,status,status_note,updated_at",
        "action_key": f"like.{PREFIX}*", "status": "eq.open", "order": "updated_at.asc", "limit": "100",
    })
    sent = 0
    for row in rows:
        value = assignment_value(row)
        if not value:
            continue
        notification = value.get("notification") or {}
        if notification.get("status") == "sending":
            try:
                started = datetime.fromisoformat(notification["startedAt"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                started = now - timedelta(hours=1)
            if now - started > timedelta(minutes=15):
                value["notification"] = {**notification, "status": "uncertain"}
                save_delivery(rest, row, value, now, "done")
            continue
        if notification.get("status") != "pending":
            continue
        try:
            recipient = verified_recipient(rest, value)
            validate_config()
            subject, body = notification_message(value)
        except Exception:
            value["notification"] = {**notification, "status": "failed", "error": "Az e-mail-cím vagy a levélküldés beállítása nem ellenőrizhető."}
            save_delivery(rest, row, value, now, "done")
            continue
        value["notification"] = {**notification, "status": "sending", "startedAt": now.isoformat()}
        claimed = save_delivery(rest, row, value, now, "open")
        if not claimed:
            continue  # Another worker/administrator changed the same assignment.
        try:
            send_email(recipient, subject, body)
        except Exception:
            value["notification"] = {**value["notification"], "status": "uncertain", "error": "A levélküldés sikere nem igazolt. Újrapróbálás előtt ellenőrizd a kézbesítést."}
        else:
            value["notification"] = {**value["notification"], "status": "sent", "sentAt": datetime.now(timezone.utc).isoformat()}
            sent += 1
        if not save_delivery(rest, claimed, value, datetime.now(timezone.utc), "done"):
            logger.warning("Complaint assignment delivery result could not be persisted")
    return sent


def start_assignment_notifier(rest):
    stop = Event()

    def run():
        from resources.email_sender import send_custom_email, smtp_config
        while not stop.is_set():
            try:
                process_pending_assignments(rest, send_custom_email, validate_config=smtp_config)
            except Exception:
                logger.warning("Complaint assignment notification pass unavailable")
            stop.wait(15)

    Thread(target=run, name="complaint-assignment-notifier", daemon=True).start()
    return stop
