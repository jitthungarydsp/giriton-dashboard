"""Read completed Courier Hub operations for the coordinator results page."""

import re


BOOKING_STATUSES = ("COURIER_ADDED", "HUB_AUTOBOOK_ERROR", "HUB_API_ERROR")
REJECTION_PREFIX = "HUB_API_REJECTED_"
ALREADY_ASSIGNED = f"{REJECTION_PREFIX}ALREADY_ASSIGNED"
REJECTION_REASONS = {
    "OVERLAP": "Átfedés egy másik műszakkal.",
    "NO_FREE_SLOT": "Nincs szabad hely a műszakon.",
    "ALREADY_BOOKED": "A futárnak már van foglalása erre a műszakra.",
}


def read_pages(read, table, params):
    page_size = 1000
    offset = 0
    while True:
        page = read(table, {**params, "limit": str(page_size), "offset": str(offset)})
        yield from page
        if len(page) < page_size:
            return
        offset += len(page)


def operation_error(status, message):
    if status.startswith(REJECTION_PREFIX):
        code = status.removeprefix(REJECTION_PREFIX)
        if code in REJECTION_REASONS:
            return REJECTION_REASONS[code]
        if re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            return f"A Courier Hub elutasította a foglalást ({code})."
        return "A Courier Hub elutasította a foglalást."
    if "past shift blocks are read-only" in message.lower():
        return "A műszak elmúlt, a Courier Hubban már nem módosítható."
    if status == "not_found":
        if "műszak nem egyezik" in message.lower():
            return "A futárnak ezen a napon van aktív Hub-foglalása, de másik műszakra."
        return "Nem található egyező aktív Courier Hub-foglalás."
    http_error = re.search(r"\bHTTP(?:Error:)?\s+(\d{3})\b", message, flags=re.IGNORECASE)
    if http_error:
        return f"API-hiba (HTTP {http_error.group(1)})."
    if re.search(r"timeout|timed out|időtúllépés", message, flags=re.IGNORECASE):
        return "A kérés időtúllépés miatt megszakadt."
    if re.search(r"connectionerror|connection refused|kapcsolati hiba", message, flags=re.IGNORECASE):
        return "Kapcsolati hiba miatt a művelet megszakadt."
    # The upstream message can contain e-mail addresses, request URLs and API payloads.
    return "A napló nem tartalmaz megjeleníthető hibaokot."


def shift_operation_results(read, operation, warehouses, start, end, dsp_id):
    is_booking = operation == "booking"
    timestamp = "created_at" if is_booking else "processed_at"
    status_field = "status" if is_booking else "deletion_status"
    id_field = "courier_id" if is_booking else "hub_courier_id"
    name_field = "courier_name" if is_booking else "hub_courier_name"
    table = "ops_giriton_auto_booking_log" if is_booking else "external_shift_deletion_requests"
    params = {
        "select": f"warehouse,work_date,shift_start,email,{id_field},{name_field},{status_field},message,{timestamp}",
        "warehouse": f"in.({','.join(warehouses)})",
        "and": f"(work_date.gte.{start},work_date.lt.{end})",
        "order": f"{timestamp}.desc,id.desc",
    }
    if is_booking:
        params["response_json->>booking_engine"] = "eq.hub_api"
        params["status"] = f"neq.{ALREADY_ASSIGNED}"
        params["or"] = f"(status.in.({','.join(BOOKING_STATUSES)}),status.like.{REJECTION_PREFIX}*)"
    else:
        params["deletion_status"] = "in.(deleted,not_found,error)"
        params["source_name"] = "eq.kulso_torles_log_sheet"

    by_warehouse = {
        warehouse: {"warehouse": warehouse, "succeeded": 0, "failed": 0, "failures": []}
        for warehouse in warehouses
    }
    unresolved = []
    for row in read_pages(read, table, params):
        result = by_warehouse.get(row.get("warehouse"))
        if result is None:
            continue
        status = str(row.get(status_field) or "")
        if status == ("COURIER_ADDED" if is_booking else "deleted"):
            result["succeeded"] += 1
            continue
        is_failure = (
            status != ALREADY_ASSIGNED and (status in BOOKING_STATUSES[1:] or status.startswith(REJECTION_PREFIX))
            if is_booking else status in {"not_found", "error"}
        )
        if not is_failure:
            continue
        result["failed"] += 1
        name = str(row.get(name_field) or "").strip()
        failure = {
            "courierName": name,
            "workDate": row.get("work_date"),
            "shiftStart": str(row.get("shift_start") or "")[:5],
            "processedAt": row.get(timestamp),
            "reason": operation_error(status, str(row.get("message") or "")),
        }
        result["failures"].append(failure)
        if not name:
            unresolved.append((failure, str(row.get(id_field) or ""), str(row.get("email") or "").strip().casefold()))

    if unresolved:
        names_by_id, names_by_email = {}, {}
        for row in read_pages(read, "courier_hub_courier_identity_raw", {
            "select": "courier_id,email,name_without_identifier",
            "dsp_id": f"eq.{dsp_id}",
            "order": "id.asc",
        }):
            name = str(row.get("name_without_identifier") or "").strip()
            if name:
                names_by_id.setdefault(str(row.get("courier_id") or ""), set()).add(name)
                names_by_email.setdefault(str(row.get("email") or "").strip().casefold(), set()).add(name)
        for failure, courier_id, email in unresolved:
            matches = (courier_id and names_by_id.get(courier_id)) or (email and names_by_email.get(email))
            if matches and len(matches) == 1:
                failure["courierName"] = next(iter(matches))
            else:
                failure["courierName"] = f"Futár #{courier_id}" if courier_id.isdigit() else "Ismeretlen futár"

    return list(by_warehouse.values())
