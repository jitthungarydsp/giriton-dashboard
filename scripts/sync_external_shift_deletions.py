#!/usr/bin/env python3
"""HUB_JOB_AUTODELETE: delete matching active Hub bookings from the KULSO_TORLES_LOG sheet."""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

from resources.google_auth import get_client  # noqa: E402
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402
from scripts.courier_hub_api_book_shift import hub_request, normalize_time, normalize_warehouse_id  # noqa: E402
from scripts.courier_hub_api_delete_shift import build_delete_url, response_payload  # noqa: E402
from scripts.sync_courier_financial_overview import courier_hub_auth_configured, raise_for_response  # noqa: E402
from scripts.sync_courier_hub_master import DEFAULT_BASE_URL, clean_text  # noqa: E402


DEFAULT_SHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
DEFAULT_WORKSHEET_GID = 965356959
REQUEST_TABLE = "external_shift_deletion_requests"
HUB_BOOKINGS_TABLE = "courier_hub_shift_bookings_raw"
SHEET_DONE_STATUS = "törölve"


@dataclass
class SheetDeletionRow:
    row_number: int
    requested_at_text: str
    work_date: str
    shift_text: str
    email: str
    warehouse: str
    sheet_status: str

    @property
    def source_key(self) -> str:
        return f"hub_job_autodelete:{DEFAULT_SHEET_ID}:{DEFAULT_WORKSHEET_GID}:{self.row_number}"


def supabase_config() -> tuple[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY hianyzik.")
    return url.rstrip("/"), key


def supabase_headers(prefer: str = "return=representation") -> dict[str, str]:
    _url, key = supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_get(table: str, params: dict[str, str] | list[tuple[str, str]]) -> list[dict[str, Any]]:
    url, _key = supabase_config()
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(""),
        params=params,
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload if isinstance(payload, list) else []


def supabase_upsert(table: str, row: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    url, _key = supabase_config()
    response = requests.post(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers("resolution=merge-duplicates,return=representation"),
        params={"on_conflict": on_conflict},
        json=row,
        timeout=60,
    )
    raise_for_supabase_error(response)
    payload = response.json()
    return payload[0] if isinstance(payload, list) and payload else {}


def supabase_patch(table: str, filters: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
    url, _key = supabase_config()
    response = requests.patch(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers("return=representation"),
        params=filters,
        json=payload,
        timeout=60,
    )
    raise_for_supabase_error(response)
    result = response.json()
    return result if isinstance(result, list) else []


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_status(value: Any) -> str:
    return normalize_key(value).replace(" ", "_")


def pending_status(value: Any) -> bool:
    normalized = normalize_status(value)
    return normalized in {"torlesre_var", "torlesrevar", "torles_var", "torlesvar", "pending"}


def parse_work_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    for pattern in ("%Y-%m-%d", "%Y.%m.%d.", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], pattern).date().isoformat()
        except ValueError:
            pass
    return text[:10]


def shift_start_from_text(value: Any) -> str:
    match = re.search(r"(\d{1,2}:\d{2})", clean_text(value))
    return normalize_time(match.group(1)) if match else ""


def slot_text(value: Any) -> str:
    return normalize_time(value)


def read_sheet_rows(sheet_id: str, worksheet_gid: int) -> list[SheetDeletionRow]:
    worksheet = get_client().open_by_key(sheet_id).get_worksheet_by_id(int(worksheet_gid))
    values = worksheet.get_all_values()
    rows: list[SheetDeletionRow] = []
    for row_number, cells in enumerate(values, start=1):
        cells = list(cells)
        requested_at_text = clean_text(cells[0] if len(cells) > 0 else "")
        work_date = parse_work_date(cells[1] if len(cells) > 1 else "")
        shift_text = clean_text(cells[2] if len(cells) > 2 else "")
        email = clean_text(cells[3] if len(cells) > 3 else "").casefold()
        warehouse = clean_text(cells[4] if len(cells) > 4 else "").upper()
        sheet_status = clean_text(cells[5] if len(cells) > 5 else "")
        if not any([requested_at_text, work_date, shift_text, email, warehouse, sheet_status]):
            continue
        if not all([work_date, shift_text, email, warehouse]):
            continue
        rows.append(SheetDeletionRow(
            row_number=row_number,
            requested_at_text=requested_at_text,
            work_date=work_date,
            shift_text=shift_text,
            email=email,
            warehouse=warehouse,
            sheet_status=sheet_status,
        ))
    return rows


def request_payload(row: SheetDeletionRow, sheet_id: str, worksheet_gid: int) -> dict[str, Any]:
    return {
        "source_name": "kulso_torles_log_sheet",
        "source_sheet_id": sheet_id,
        "source_gid": int(worksheet_gid),
        "source_row": row.row_number,
        "source_key": f"hub_job_autodelete:{sheet_id}:{worksheet_gid}:{row.row_number}",
        "requested_at_text": row.requested_at_text,
        "work_date": row.work_date,
        "shift_text": row.shift_text,
        "shift_start": shift_start_from_text(row.shift_text) or None,
        "email": row.email,
        "warehouse": row.warehouse,
        "sheet_status": row.sheet_status,
        "deletion_status": "pending",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_active_hub_candidates(row: SheetDeletionRow, dsp_id: int) -> list[dict[str, Any]]:
    warehouse_id = normalize_warehouse_id(row.warehouse)
    return supabase_get(
        HUB_BOOKINGS_TABLE,
        [
            ("select", (
                "id,work_date,warehouse_id,warehouse_code,dsp_id,courier_id,courier_name,email,"
                "block_key,shift_template_id,shift_text,slot_from,slot_to,status,active,movement_type"
            )),
            ("work_date", f"eq.{row.work_date}"),
            ("warehouse_id", f"eq.{warehouse_id}"),
            ("dsp_id", f"eq.{int(dsp_id)}"),
            ("email", f"eq.{row.email}"),
            ("active", "eq.true"),
            ("limit", "50"),
        ],
    )


def candidate_score(row: SheetDeletionRow, candidate: dict[str, Any]) -> int:
    requested_start = shift_start_from_text(row.shift_text)
    candidate_slot = slot_text(candidate.get("slot_from"))
    requested_shift_key = normalize_key(row.shift_text)
    candidate_shift_key = normalize_key(candidate.get("shift_text"))
    score = 0
    if requested_start and candidate_slot == requested_start:
        score += 100
    if requested_shift_key and candidate_shift_key == requested_shift_key:
        score += 50
    if requested_start and requested_start in normalize_time(candidate.get("shift_text")):
        score += 20
    return score


def find_matching_hub_booking(row: SheetDeletionRow, dsp_id: int) -> tuple[dict[str, Any] | None, str]:
    candidates = load_active_hub_candidates(row, dsp_id)
    if not candidates:
        return None, "Nincs aktív Hub foglalás ezzel a dátum/email/raktár kulccsal."

    scored = sorted(
        ((candidate_score(row, item), item) for item in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score <= 0:
        return None, "Van aktív Hub foglalás erre a futárra és napra, de a műszak nem egyezik."
    same_best = [item for score, item in scored if score == best_score]
    if len(same_best) > 1:
        return None, f"Több egyező aktív Hub foglalás van ({len(same_best)} db), kézi ellenőrzés kell."
    return best, "OK"


def update_request(source_key: str, status: str, message: str, booking: dict[str, Any] | None = None, response: Any = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "deletion_status": status,
        "message": message[:2000],
        "processed_at": now,
        "updated_at": now,
    }
    if booking:
        payload.update({
            "hub_booking_id": booking.get("id"),
            "hub_courier_id": booking.get("courier_id"),
            "hub_courier_name": booking.get("courier_name"),
            "hub_shift_template_id": booking.get("shift_template_id"),
            "hub_slot_from": slot_text(booking.get("slot_from")) or None,
            "hub_block_key": booking.get("block_key"),
        })
    if response is not None:
        payload["hub_response"] = response if isinstance(response, dict) else {"response": response}
    supabase_patch(REQUEST_TABLE, {"source_key": f"eq.{source_key}"}, payload)


def mark_hub_booking_deleted(booking: dict[str, Any], response: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase_patch(
        HUB_BOOKINGS_TABLE,
        {"id": f"eq.{booking.get('id')}"},
        {
            "movement_type": "DELETE",
            "active": False,
            "deleted_at": now,
            "last_seen_at": now,
            "updated_at": now,
            "status": "DELETED",
        },
    )


def delete_hub_booking(row: SheetDeletionRow, booking: dict[str, Any], *, dsp_id: int, base_url: str, live_delete: bool) -> tuple[bool, Any, str]:
    shift_template_id = int(booking.get("shift_template_id") or 0)
    courier_id = int(booking.get("courier_id") or 0)
    slot_from = slot_text(booking.get("slot_from"))
    if not shift_template_id or not courier_id or not slot_from:
        return False, {}, "A Hub raw sorból hiányzik shift_template_id/courier_id/slot_from."

    request_body = {
        "date": row.work_date,
        "shiftTemplateId": shift_template_id,
        "slotFrom": slot_from,
        "courierIds": [courier_id],
    }
    if not live_delete:
        return True, {"dryRun": True, "request": request_body}, "DRY-RUN: Hub API törlés kihagyva."

    warehouse_id = normalize_warehouse_id(row.warehouse)
    url = build_delete_url(base_url, warehouse_id, int(dsp_id), 0)
    response = hub_request("DELETE", url, json=request_body)
    payload = response_payload(response)
    if response.ok:
        return True, payload, "Hub API törlés sikeres."
    raise_for_response(response, "Courier Hub shift delete")
    return False, payload, "Hub API törlés sikertelen."


def write_done_status_to_sheet(sheet_id: str, worksheet_gid: int, row_numbers: list[int]) -> None:
    if not row_numbers:
        return
    worksheet = get_client().open_by_key(sheet_id).get_worksheet_by_id(int(worksheet_gid))
    updates = [
        {"range": f"F{int(row_number)}", "values": [[SHEET_DONE_STATUS]]}
        for row_number in row_numbers
    ]
    worksheet.batch_update(updates, value_input_option="USER_ENTERED")


def mark_sheet_written(source_keys: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for source_key in source_keys:
        supabase_patch(
            REQUEST_TABLE,
            {"source_key": f"eq.{source_key}"},
            {"sheet_written_at": now, "updated_at": now},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="HUB_JOB_AUTODELETE Google Sheet -> Hub shift deletion sync.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--gid", type=int, default=DEFAULT_WORKSHEET_GID)
    parser.add_argument("--dsp-id", type=int, default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"))
    parser.add_argument("--base-url", default=os.getenv("COURIER_HUB_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="DB és Sheet írás engedélyezése.")
    parser.add_argument("--live-delete", action="store_true", help="Valódi Courier Hub API törlés.")
    parser.add_argument("--dry-run", action="store_true", help="Sem DB, sem Hub, sem Sheet írás nem történik.")
    args = parser.parse_args()

    if args.live_delete and not courier_hub_auth_configured():
        raise RuntimeError("Hianyzik a Courier Hub auth. COURIER_HUB_COOKIE vagy auth cache szukseges.")

    rows = [row for row in read_sheet_rows(args.sheet_id, args.gid) if pending_status(row.sheet_status)]
    if args.limit > 0:
        rows = rows[: args.limit]

    print(f"HUB_JOB_AUTODELETE_PENDING_ROWS={len(rows)}")
    if args.dry_run:
        args.apply = False
        args.live_delete = False

    done_sheet_rows: list[int] = []
    done_source_keys: list[str] = []
    deleted_count = 0
    not_found_count = 0
    error_count = 0

    for row in rows:
        source_key = f"hub_job_autodelete:{args.sheet_id}:{args.gid}:{row.row_number}"
        print(
            "HUB_JOB_AUTODELETE_ROW "
            f"row={row.row_number} date={row.work_date} warehouse={row.warehouse} "
            f"shift={row.shift_text!r} email={row.email}",
            flush=True,
        )
        if args.apply:
            supabase_upsert(REQUEST_TABLE, request_payload(row, args.sheet_id, args.gid), "source_key")

        try:
            booking, match_message = find_matching_hub_booking(row, args.dsp_id)
            if not booking:
                not_found_count += 1
                print(f"HUB_JOB_AUTODELETE_NOT_FOUND row={row.row_number} message={match_message}", flush=True)
                if args.apply:
                    update_request(source_key, "not_found", match_message)
                continue

            ok, payload, message = delete_hub_booking(
                row,
                booking,
                dsp_id=args.dsp_id,
                base_url=args.base_url,
                live_delete=args.live_delete,
            )
            if not ok:
                error_count += 1
                if args.apply:
                    update_request(source_key, "error", message, booking, payload)
                continue

            deleted_count += 1
            print(f"HUB_JOB_AUTODELETE_OK row={row.row_number} courier_id={booking.get('courier_id')}", flush=True)
            if args.apply:
                mark_hub_booking_deleted(booking, payload)
                update_request(source_key, "deleted", message, booking, payload)
                done_sheet_rows.append(row.row_number)
                done_source_keys.append(source_key)
        except Exception as exc:
            error_count += 1
            message = f"{type(exc).__name__}: {str(exc)[:1500]}"
            print(f"HUB_JOB_AUTODELETE_ERROR row={row.row_number} {message}", flush=True)
            if args.apply:
                update_request(source_key, "error", message)

    if args.apply and done_sheet_rows:
        write_done_status_to_sheet(args.sheet_id, args.gid, done_sheet_rows)
        mark_sheet_written(done_source_keys)

    print(
        "HUB_JOB_AUTODELETE_DONE "
        f"deleted={deleted_count} not_found={not_found_count} errors={error_count} "
        f"sheet_updated={len(done_sheet_rows) if args.apply else 0} "
        f"mode={'live' if args.live_delete else 'dry-run'}",
        flush=True,
    )
    return 1 if error_count and not deleted_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
