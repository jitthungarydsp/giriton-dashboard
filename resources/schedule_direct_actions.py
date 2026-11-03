"""Change PWA schedule assignments using the stored Hub session."""

from datetime import time, datetime, timezone

import requests

from resources.schedule_bulk import update_record
from scripts.run_pwa_schedule_bulk import refresh_day, run_items
from scripts.shared_courier_hub_session import read_pwa_session, stored_session_environment


def execute_direct_batch(client, record):
    def save(current):
        update_record(client, current)

    warehouse_id = int(record["warehouse"][-1])
    day = record["work_date"]
    headers = read_pwa_session(client, [warehouse_id], day, day)
    if not headers:
        for item in record["items"]:
            item.update(status="failed", message="A Hub nem érhető el a mentett munkamenettel.")
        record.update(status="completed", finished_at=datetime.now(timezone.utc).isoformat())
        save(record)
        return

    base = (
        "https://courier-hub.kifli.hu/services/courier-hub-service/external"
        f"/warehouses/{warehouse_id}/dsps/8/shift-blocks"
    )

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
                or time.fromisoformat(block["slotFrom"]) != time.fromisoformat(item["slot_from"])
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
        book = item["action"] == "book"
        operation = "foglalás" if book else "törlés"
        try:
            if assigned(item) == book:
                message = ("A futár már szerepel a Hub műszakban." if book
                           else "A futár már nem szerepel a Hub műszakban.")
                return "succeeded", message
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return "failed", f"A Hub műszak nem olvasható. A {operation} nem indult el."

        response = None
        try:
            response = requests.request(
                "POST" if book else "DELETE", f"{base}/assign" if book else f"{base}/0/assignments",
                headers={"Accept": "application/json", **headers},
                json={"date": day, "shiftTemplateId": item["shift_template_id"],
                      "slotFrom": time.fromisoformat(item["slot_from"]).isoformat(),
                      "courierIds": [item["courier_id"]]},
                timeout=8, allow_redirects=False,
            )
        except requests.RequestException:
            pass  # A timeout may still have applied the mutation.
        if assigned(item) == book:
            return "succeeded", f"A Hub műszak visszaolvasása igazolta a műveletet ({operation})."
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            decisions = payload.get("results") if isinstance(payload, dict) else None
            if isinstance(decisions, list) and any(
                isinstance(result, dict) and str(result.get("decision", "")).upper() == "REJECTED"
                for result in decisions
            ):
                return "failed", f"A Hub elutasította a műveletet ({operation})."
        return "uncertain", f"A Hub visszaolvasása nem igazolta a műveletet ({operation})."

    run_items(record, save, execute=execute)
    if any(item["status"] in {"succeeded", "uncertain"} for item in record["items"]):
        try:
            with stored_session_environment(headers) as env:
                refresh_day(record, env=env)
            record["refreshStatus"] = "succeeded"
        except Exception:
            record["refreshStatus"] = "failed"
    record["status"] = "completed"
    save(record)
