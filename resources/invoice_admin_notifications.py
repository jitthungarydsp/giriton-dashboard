"""Deliver the settlement invoice notices captured by the database."""

from datetime import datetime, timezone
import logging
from threading import Event, Thread
from zoneinfo import ZoneInfo
from uuid import UUID


RECIPIENT = "zoltan.bagoly@jitt.hu"
DIGEST_RECIPIENTS = (RECIPIENT, "balazs.gurzo@jitt.hu")
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
DOCUMENTS = {
    "invoice": "Számla feltöltve", "cash_invoice": "KP-számla feltöltve",
    "kp_invoice": "KP-számla feltöltve", "settlement": "Elszámolás feltöltve",
    "tig": "Teljesítés-összesítő feltöltve", "complaint_response": "Reklamációs válasz feltöltve",
}
WORKFLOW = {
    "settlement": ("Elszámolás elfogadásra vár", "Elszámolás elfogadva"),
    "tig": ("Teljesítés-összesítő áttekintésre vár", "Teljesítés-összesítő elfogadva"),
    "invoice_submit": ("Számlafeltöltésre vár", "Számla feltöltve"),
    "invoice_check": ("Számlaellenőrzésre vár", "Számlaellenőrzés kész"),
    "invoice_payment": ("Kifizetésre vár", "Kifizetés lezárva"),
}
COMPLAINT_STATUS = {
    "new": "Új", "open": "Nyitott", "in_progress": "Vizsgálat alatt",
    "resolved": "Megoldva", "closed": "Lezárva", "deleted": "Törölve",
}
logger = logging.getLogger(__name__)


def event_text(event):
    kind, _, key = event["kind"].partition(":")
    detail = event["detail"]
    if kind == "document":
        label = DOCUMENTS.get(key, "KP-számla feltöltve" if key.startswith("process:kp_invoice_") else "Dokumentum feltöltve")
        return f"{label} ({detail})" if detail else label
    if kind == "status":
        return WORKFLOW[key][int(detail == "done")]
    return f"Reklamáció – {COMPLAINT_STATUS.get(detail, detail)}"


def build_invoice_admin_message(delivery):
    events = delivery["events"]
    if delivery["kind"] == "digest":
        subject = f"Számlák és elszámolási státuszok – {delivery['digest_day']}"
        heading = "A reggeli összefoglalóban ezek a számlák és státuszváltozások szerepelnek."
    else:
        first = events[0]
        name = " ".join(first["courier_name"].split())[:100]
        label = "Lezárt havi esemény" if any(event["historical"] for event in events) else "Számlaértesítés"
        subject = f"{label} – {name} ({first['period_start'][:7]})"
        heading = "Az alábbi változást rögzítettük az elszámolásban."
    lines = []
    for event in events:
        when = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).astimezone(LOCAL_TIMEZONE)
        text = event_text(event)
        lines.append(f"• {when:%m.%d. %H:%M} | {event['courier_name']} (#{event['courier_id']}) | "
                     f"{event['period_start'][:7]} | {text}")
    if not lines:
        heading = "Az előző összefoglaló óta nem érkezett jelentendő számla vagy státuszváltozás."
    greeting = "Sziasztok!" if delivery["kind"] == "digest" else "Szia Zoltán!"
    body = "\n\n".join(filter(None, (greeting, heading, "\n".join(lines), "Üdv,\nJITT Pénzügy")))
    return subject, body


def send_pending_invoice_notifications(rest, send_email, *, limit=10):
    sent = 0
    for _ in range(limit):
        rows = rest("POST", "rpc/claim_invoice_notification", schema="settlement", payload={}) or []
        if not rows:
            break
        delivery = rows[0]
        state = "uncertain"
        try:
            subject, body = build_invoice_admin_message(delivery)
            recipients = DIGEST_RECIPIENTS if delivery["kind"] == "digest" else RECIPIENT
            send_email(recipients, subject, body)
            state = "sent"
            sent += 1
        except Exception:
            logger.warning("Invoice notification delivery uncertain (id=%s)", delivery["id"])
        rest("PATCH", "invoice_notification_delivery", schema="settlement",
             params={"id": "eq." + delivery["id"], "state": "eq.sending"},
             payload={"state": state, "finished_at": datetime.now(timezone.utc).isoformat()},
             prefer="return=minimal")
    return sent


def retry_invoice_digest(rest, send_email, delivery_id):
    """Explicitly authorized retry of one saved digest; never requeue other mail."""
    delivery_id = str(UUID(str(delivery_id)))
    rows = rest('GET', 'invoice_notification_delivery', schema='settlement',
                params={'select': '*', 'id': 'eq.' + delivery_id, 'limit': '1'}) or []
    if not rows or rows[0].get('kind') != 'digest':
        raise ValueError('A mentett napi riport nem található.')
    delivery = rows[0]
    if delivery['state'] == 'sent':
        return {'id': delivery_id, 'state': 'sent', 'already_sent': True}
    if delivery['state'] != 'uncertain':
        raise ValueError('Csak a nem igazolt küldésű riport indítható újra.')
    subject, body = build_invoice_admin_message(delivery)
    started = datetime.now(timezone.utc).isoformat()
    claimed = rest('PATCH', 'invoice_notification_delivery', schema='settlement',
        params={'id': 'eq.' + delivery_id, 'state': 'eq.uncertain',
                'started_at': 'eq.' + str(delivery['started_at'])},
        payload={'state': 'sending', 'started_at': started, 'finished_at': None}, prefer='return=representation') or []
    if len(claimed) != 1:
        raise RuntimeError('A riport közben megváltozott; nem indult levélküldés.')
    state, error_type = 'sent', ''
    try:
        send_email(DIGEST_RECIPIENTS, subject, body)
    except Exception as exc:
        state, error_type = 'uncertain', type(exc).__name__
        logger.warning('Invoice digest retry uncertain id=%s error_type=%s', delivery_id, error_type)
    confirmed = rest('PATCH', 'invoice_notification_delivery', schema='settlement',
        params={'id': 'eq.' + delivery_id, 'state': 'eq.sending', 'started_at': 'eq.' + str(claimed[0]['started_at'])},
        payload={'state': state, 'finished_at': datetime.now(timezone.utc).isoformat()}, prefer='return=representation') or []
    if len(confirmed) != 1 or confirmed[0].get('state') != state:
        raise RuntimeError('A küldés eredménye nem menthető; automatikus újraküldés nem indulhat.')
    return {'id': delivery_id, 'state': state, 'error_type': error_type, 'already_sent': False}


def start_invoice_admin_notifier(rest):
    stop = Event()
    ready = Event()

    def run():
        from resources.email_sender import send_custom_email, smtp_config

        while not stop.is_set():
            delay = 15
            try:
                smtp_config()
                send_pending_invoice_notifications(rest, send_custom_email)
                ready.set()
            except Exception:
                ready.clear()
                logger.warning("Invoice notification worker unavailable")
                delay = 60
            stop.wait(delay)

    Thread(target=run, name="invoice-admin-notifier", daemon=True).start()
    return stop, ready
