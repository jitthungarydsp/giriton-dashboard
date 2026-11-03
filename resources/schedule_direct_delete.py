"""Delete PWA schedule assignments using the stored Hub session."""

import json
import os
from datetime import time, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from resources.schedule_bulk import BUCKET, object_path
from scripts.run_pwa_schedule_bulk import refresh_day, run_items
from scripts.shared_courier_hub_session import session_headers


def delete_batch(client, record):
    def save(current):
        client.storage.from_(BUCKET).update(
            object_path(current["id"]), json.dumps(current, ensure_ascii=False).encode(),
            file_options={"content-type": "application/octet-stream"},
        )

    try:
        headers = session_headers(json.loads(client.storage.from_("hub-session-cache").download("session.json")))
    except Exception:
        headers = {}
    if not headers:
        for item in record["items"]:
            item.update(status="failed", message="A mentett Hub-munkamenet nem érhető el.")
        record.update(status="completed", finished_at=datetime.now(timezone.utc).isoformat())
        save(record)
        return

    base = (
        "https://courier-hub.kifli.hu/services/courier-hub-service/external"
        f"/warehouses/{int(record['warehouse'][-1])}/dsps/8/shift-blocks"
    )
    day = record["work_date"]

    def assigned(item):
        response = requests.get(
            base, params={"dateFrom": day, "dateTo": day},
            headers={"Accept": "application/json", **headers}, timeout=8, allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Hub shift read failed")
        payload = response.json()
        blocks = payload.get("content") if isinstance(payload, dict) else payload
        for block in blocks:
            if (
                str(block.get("shiftTemplateId")) != str(item["shift_template_id"])
                or not block.get("slotFrom")
                or time.fromisoformat(block["slotFrom"]).isoformat() != item["slot_from"]
                or block.get("date", day) != day
            ):
                continue
            assignments = block["assignments"]
            if not isinstance(assignments, list):
                raise ValueError("Hub assignments missing")
            for assignment in assignments:
                courier = assignment.get("courier") or {}
                courier_id = assignment.get("courierId") or assignment.get("courier_id")
                courier_id = courier_id or courier.get("courierId") or courier.get("courier_id")
                if courier_id is None:
                    raise ValueError("Hub assignment courier missing")
                if str(courier_id) == str(item["courier_id"]):
                    return True
            return False
        raise ValueError("Hub shift missing")

    def execute(item):
        try:
            if not assigned(item):
                return "succeeded", "A futár már nem szerepel a Hub műszakban."
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return "failed", "A Hub műszak nem olvasható. A törlés nem indult el."

        try:
            requests.delete(
                f"{base}/0/assignments", headers={"Accept": "application/json", **headers},
                json={"date": day, "shiftTemplateId": item["shift_template_id"],
                      "slotFrom": item["slot_from"], "courierIds": [item["courier_id"]]},
                timeout=8, allow_redirects=False,
            )
        except requests.RequestException:
            pass  # A timeout may still have applied the deletion.
        if assigned(item):
            return "uncertain", "A futár a visszaolvasáskor még szerepelt a Hub műszakban."
        return "succeeded", "A Hub műszak visszaolvasása igazolta a törlést."

    run_items(record, save, execute=execute)
    if any(item["status"] in {"succeeded", "uncertain"} for item in record["items"]):
        try:
            with TemporaryDirectory() as directory:
                cache = Path(directory) / "session.json"
                cache.write_text(json.dumps({"headers": headers}), encoding="utf-8")
                env = {**os.environ, "COURIER_HUB_AUTH_CACHE_FILE": str(cache),
                       "KIFLI_COURIER_HUB_AUTH_CACHE_FILE": str(cache)}
                for key in ("COURIER_HUB_AUTH_REFRESH_COMMAND", "KIFLI_COURIER_HUB_AUTH_REFRESH_COMMAND",
                            "COURIER_HUB_USERNAME", "COURIER_HUB_PASSWORD",
                            "KIFLI_COURIER_HUB_USERNAME", "KIFLI_COURIER_HUB_PASSWORD"):
                    env.pop(key, None)
                refresh_day(record, env=env)
            record["refreshStatus"] = "succeeded"
        except Exception:
            record["refreshStatus"] = "failed"
    record["status"] = "completed"
    save(record)
