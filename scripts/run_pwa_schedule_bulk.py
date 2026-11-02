"""Run one explicitly selected daily Hub batch; never retry uncertain mutations."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]


def storage_record(request_id, record=None):
    request_id = str(UUID(request_id))
    prefix = "authenticated/" if record is None else ""
    url = os.environ["SUPABASE_URL"].rstrip("/") + f"/storage/v1/object/{prefix}pwa-attachments/schedule-bulk-actions/{request_id}.json"
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": token, "Authorization": "Bearer " + token}
    data = None
    if record is not None:
        data = json.dumps(record, ensure_ascii=False).encode()
        headers.update({"Content-Type": "application/octet-stream", "x-upsert": "true"})
    with urlopen(Request(url, data=data, headers=headers, method="POST" if data else "GET"), timeout=30) as response:
        content = response.read()
    return record if data else json.loads(content)


def execute_item(item):
    script = "courier_hub_api_delete_shift.py" if item["action"] == "delete" else "courier_hub_api_book_shift.py"
    args = [sys.executable, str(ROOT / "scripts" / script), "--date", item["work_date"],
            "--warehouse", item["warehouse"], "--dsp-id", "8", "--shift-template-id", str(item["shift_template_id"]),
            "--slot-from", item["slot_from"], "--courier-id", str(item["courier_id"]),
            "--courier-name", item["courier_name"], "--live"]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
    # Persist concise feedback, never raw authentication errors or headers.
    output = result.stdout or ""
    marker = "HUB_API_DELETE_OK" if item["action"] == "delete" else "HUB_API_BOOK_OK"
    if result.returncode == 0 and marker in output:
        return "succeeded", "A Hub API visszaigazolta a műveletet."
    rejected = re.search(r"HUB_API_BOOK_REJECTED[^\n]*reason=([a-zA-Z0-9_-]+)", output)
    return "failed", (f"A Hub elutasította: {rejected[1].upper()}." if rejected else "A Hub művelet sikere nem igazolható. Ellenőrizd a háttérfeladatot és az aktuális foglalást.")


def run_items(record, save, execute=execute_item):
    if record.get("status") != "queued":
        # Includes manual GitHub re-runs. An interrupted 'running' item is uncertain.
        return record
    record["status"] = "running"
    save(record)
    for item in record["items"]:
        item["status"] = "running"
        save(record)  # If this journal write fails, no external mutation is made.
        try:
            item["status"], item["message"] = execute(item)
        except Exception:
            item["status"] = "uncertain"
            item["message"] = "A kérés megszakadt; a Hub állapotát ellenőrizni kell. Nem próbáltuk újra automatikusan."
        save(record)
    record["status"] = "refreshing"
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(record)
    return record


def refresh_day(record):
    warehouse_id = record["warehouse"][-1]
    commands = [
        ["sync_courier_hub_shift_blocks.py", "--warehouse-ids", warehouse_id, "--dsp-id", "8", "--start-date", record["work_date"], "--end-date", record["work_date"]],
        ["refresh_pwa_schedule_capacity_calendar.py", "--warehouse-ids", warehouse_id, "--dsp-id", "8", "--start-date", record["work_date"], "--lookahead-days", "0", "--refresh-source", "PWA_SCHEDULE_BULK"],
    ]
    for script, *args in commands:
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, check=True, timeout=240)


def main():
    request_id = str(UUID(os.environ["PWA_BATCH_ID"]))
    record = storage_record(request_id)
    save = lambda data: storage_record(request_id, data)
    if record.get("status") != "queued":
        print("Batch already started; refusing automatic re-execution.")
        return 0
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts/refresh_courier_hub_auth.py"),
                        "--cache-file", os.environ["COURIER_HUB_AUTH_CACHE_FILE"],
                        "--debug-dir", "results/pwa-schedule-bulk/auth",
                        "--probe-path", f"/services/courier-hub-service/external/warehouses/{record['warehouse'][-1]}/dsps/8/shift-blocks?dateFrom={record['work_date']}&dateTo={record['work_date']}"],
                       cwd=ROOT, check=True, timeout=180)
    except Exception:
        record["status"] = "failed"
        for item in record["items"]:
            item.update(status="failed", message="A Hub hitelesítése nem sikerült; a művelet nem indult el.")
        save(record)
        return 1
    run_items(record, save)
    # Publishing terminal status happens after refresh so the UI does not fetch stale DB data.
    record["status"] = "refreshing"
    save(record)
    try:
        refresh_day(record)
        record["refreshStatus"] = "succeeded"
    except Exception:
        record["refreshStatus"] = "failed"
    record["status"] = "completed"
    save(record)
    return 0 if all(item["status"] == "succeeded" for item in record["items"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
