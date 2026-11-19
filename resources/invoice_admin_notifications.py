"""Deliver the settlement invoice notices captured by the database."""

from datetime import datetime, timezone
import logging
from threading import Event, Thread
from zoneinfo import ZoneInfo


RECIPIENT = "bagoly.zoltan@jitt.hu"
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
    body = "\n\n".join(filter(None, ("Szia Zoltán!", heading, "\n".join(lines), "Üdv,\nJITT Pénzügy")))
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
            send_email(RECIPIENT, subject, body)
            state = "sent"
            sent += 1
        except Exception:
            logger.warning("Invoice notification delivery uncertain (id=%s)", delivery["id"])
        rest("PATCH", "invoice_notification_delivery", schema="settlement",
             params={"id": "eq." + delivery["id"], "state": "eq.sending"},
             payload={"state": state, "finished_at": datetime.now(timezone.utc).isoformat()},
             prefer="return=minimal")
    return sent


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
