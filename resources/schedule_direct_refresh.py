"""Run the PWA Hub refresh on the application server."""

from datetime import date
import json

from resources.schedule_bulk import update_record
from scripts.run_pwa_schedule_bulk import refresh_schedule
from scripts.shared_courier_hub_session import session_headers, stored_session_environment


REFRESH_PREFIX = "schedule-hub-refresh"


def refresh_from_hub(client, record):
    record["status"] = "in_progress"
    update_record(client, record, prefix=REFRESH_PREFIX)
    try:
        headers = session_headers(json.loads(client.storage.from_("hub-session-cache").download("session.json")))
    except Exception:
        headers = {}
    if headers:
        try:
            start, end = record["startDate"], record["endDate"]
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            warehouses = ",".join(str(value) for value in record["warehouse_ids"])
            with stored_session_environment(headers) as env:
                refresh_schedule(warehouses, start, end, days, source="PWA_SCHEDULE_REFRESH", env=env)
            record["conclusion"] = "success"
        except Exception:
            record.update(conclusion="failure", detail="A Hub-adatok letöltése vagy mentése sikertelen.")
    else:
        record.update(conclusion="failure", detail="A mentett Hub-munkamenet nem érhető el.")
    record["status"] = "completed"
    update_record(client, record, prefix=REFRESH_PREFIX)
