"""Validation and private journal for explicitly selected Hub operations."""
from datetime import date, time
import hashlib
import json
from uuid import UUID

BUCKET = "pwa-attachments"
PREFIX = "schedule-bulk-actions"
TERMINAL = {"completed", "failed", "dispatch_uncertain"}


def normalize_batch(action, items, allowed):
    if action not in {"book", "delete"} or not 1 <= len(items) <= 100:
        raise ValueError("Válassz 1–100 műveletet, foglalásra vagy törlésre.")
    output, seen, scope = [], set(), None
    for item in items:
        day = date.fromisoformat(str(item.get("work_date") or ""))
        warehouse = str(item.get("warehouse") or "").upper().strip()
        if warehouse not in {f"BUD{i}" for i in allowed}:
            raise ValueError("Ehhez a raktárhoz nincs jogosultság.")
        current_scope = (day.isoformat(), warehouse)
        if scope is not None and scope != current_scope:
            raise ValueError("Egy műveletlista egy naphoz és egy raktárhoz tartozhat.")
        scope = current_scope
        start = time.fromisoformat(str(item.get("slot_from") or "")).strftime("%H:%M:%S")
        courier = int(item.get("courier_id") or 0)
        template = int(item.get("shift_template_id") or 0)
        if courier <= 0 or template <= 0:
            raise ValueError("Hiányzó futár- vagy műszaksablon-azonosító.")
        identity = (day.isoformat(), warehouse, template, start, courier)
        if identity in seen:
            raise ValueError("Ugyanaz a futár ugyanarra a slotra többször szerepel.")
        seen.add(identity)
        output.append(dict(action=action, work_date=day.isoformat(), warehouse=warehouse,
                           slot_from=start, shift_template_id=template, courier_id=courier,
                           courier_name=str(item.get("courier_name") or "")[:150], status="pending"))
    return output


def fingerprint(items):
    fields = ("action", "work_date", "warehouse", "slot_from", "shift_template_id", "courier_id")
    values = sorted(tuple(item[k] for k in fields) for item in items)
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def object_path(request_id, prefix=PREFIX):
    return f"{prefix}/{UUID(str(request_id))}.json"


def read_record(client, request_id, *, prefix=PREFIX):
    return json.loads(client.storage.from_(BUCKET).download(object_path(request_id, prefix)))


def create_record(client, record, *, prefix=PREFIX):
    bucket = client.storage.get_bucket(BUCKET)
    public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
    if public is not False:
        raise ValueError("A műveletlista privát tárhelyet igényel.")
    client.storage.from_(BUCKET).upload(object_path(record["id"], prefix), json.dumps(record, ensure_ascii=False).encode(),
                                      file_options={"content-type": "application/octet-stream", "upsert": "false"})


def update_record(client, record, *, prefix=PREFIX):
    client.storage.from_(BUCKET).update(
        object_path(record["id"], prefix), json.dumps(record, ensure_ascii=False).encode(),
        file_options={"content-type": "application/octet-stream"},
    )
