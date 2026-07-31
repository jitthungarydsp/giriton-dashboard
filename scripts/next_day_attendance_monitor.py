import argparse
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DSP_ID = "JIT"
API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
SNAPSHOT_SOURCE = "next-day-shift-snapshot"
CHECK_SOURCE = "next-day-attendance-check"
TARGET_TABLE_CANDIDATES = ["raw_dsp_attendance", "dsp_attendance_raw"]


def parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_date(value):
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def iso_datetime(value):
    return value.isoformat() if value else None


def attendance_url(work_date):
    return (
        f"{API_BASE_URL}/fetch-attendance/{DSP_ID}/{work_date.isoformat()}"
        f"?organizationId={ORGANIZATION_ID}"
    )


def fetch_attendance(work_date):
    response = requests.get(attendance_url(work_date), timeout=60)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("couriers"), list):
        raise RuntimeError("Az attendance API valasza nem tartalmaz couriers listat.")
    return payload


def flatten_snapshot(payload, snapshot_date, work_date, fetched_at):
    rows = []
    for courier in payload.get("couriers", []) or []:
        courier_id = courier.get("courierId")
        if courier_id is None:
            continue
        for shift in courier.get("shifts", []) or []:
            shift_id = shift.get("shiftId")
            shift_start = parse_datetime(shift.get("shiftStart"))
            if shift_id is None or shift_start is None:
                continue
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "work_date": work_date,
                    "snapshot_fetched_at": fetched_at,
                    "organization_id": ORGANIZATION_ID,
                    "dsp_id": str(payload.get("dspId") or DSP_ID),
                    "dsp_name": payload.get("dspName"),
                    "courier_id": int(courier_id),
                    "courier_name": courier.get("courierName"),
                    "warehouse_name": courier.get("warehouseName"),
                    "shift_id": int(shift_id),
                    "shift_name": shift.get("shiftName"),
                    "shift_start": shift_start,
                    "shift_end": parse_datetime(shift.get("shiftEnd")),
                }
            )
    return rows


def supabase_config():
    url = str(os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY.")
    return url, key


def supabase_headers(extra=None):
    _url, key = supabase_config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if extra:
        headers.update(extra)
    return headers


def resolve_table():
    url, _key = supabase_config()
    for table in TARGET_TABLE_CANDIDATES:
        response = requests.get(
            f"{url}/rest/v1/{table}",
            headers=supabase_headers(),
            params={"select": "work_date", "limit": "1"},
            timeout=30,
        )
        if response.status_code in (400, 404) and (
            "PGRST205" in response.text or "does not exist" in response.text
        ):
            continue
        response.raise_for_status()
        return table
    raise RuntimeError("Nem talalhato raw DSP attendance tabla.")


def upsert_record(source_name, work_date, request_url, response_json, fetched_at):
    url, _key = supabase_config()
    table = resolve_table()
    row = {
        "source_name": source_name,
        "organization_id": ORGANIZATION_ID,
        "dsp_id": DSP_ID,
        "work_date": work_date.isoformat(),
        "request_url": request_url,
        "status_code": 200,
        "response_json": response_json,
        "fetched_at": iso_datetime(fetched_at),
    }
    response = requests.post(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(
            {
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }
        ),
        params={"on_conflict": "source_name,dsp_id,work_date"},
        json=row,
        timeout=60,
    )
    response.raise_for_status()
    return table


def load_snapshot(work_date):
    url, _key = supabase_config()
    table = resolve_table()
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(),
        params={
            "select": "response_json,fetched_at",
            "source_name": f"eq.{SNAPSHOT_SOURCE}",
            "dsp_id": f"eq.{DSP_ID}",
            "work_date": f"eq.{work_date.isoformat()}",
            "order": "fetched_at.desc",
            "limit": "1",
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    return rows[0].get("response_json") or {}


def current_maps(payload):
    shifts = {}
    routes = {}
    for courier in payload.get("couriers", []) or []:
        courier_id = courier.get("courierId")
        if courier_id is None:
            continue
        courier_id = int(courier_id)
        routes[courier_id] = courier.get("routes", []) or []
        for shift in courier.get("shifts", []) or []:
            shift_id = shift.get("shiftId")
            if shift_id is not None:
                shifts[(courier_id, int(shift_id))] = shift
    return shifts, routes


def route_evidence(route_rows, shift_start, shift_end):
    window_start = shift_start - timedelta(minutes=90)
    window_end = (shift_end or shift_start + timedelta(hours=6)) + timedelta(minutes=30)
    evidence = []
    for route in route_rows or []:
        timestamps = [
            parse_datetime(route.get("courierRegisteredAt")),
            parse_datetime(route.get("assignedAt")),
            parse_datetime(route.get("realDeparture")),
        ]
        if any(value and window_start <= value <= window_end for value in timestamps):
            evidence.append(route.get("routeId"))
    return [value for value in evidence if value is not None]


def build_checks(snapshot_rows, payload, checked_at, grace_minutes):
    shift_map, route_map = current_maps(payload)
    checks = []
    for row in snapshot_rows:
        current_shift = shift_map.get((row["courier_id"], row["shift_id"]))
        shift_start = row["shift_start"]
        shift_end = row["shift_end"]
        eligible_at = shift_start + timedelta(minutes=grace_minutes)
        minutes_after_start = int((checked_at - shift_start).total_seconds() // 60)
        available_at = parse_datetime(
            current_shift.get("availableForShiftSince") if current_shift else None
        )
        evidence_routes = route_evidence(
            route_map.get(row["courier_id"], []), shift_start, shift_end
        )

        if current_shift is None:
            status = "missing_from_current_list"
            reason = "A tegnapi snapshot muszak ma mar nem szerepel az API-ban."
        elif checked_at < eligible_at:
            status = "pending"
            reason = "A muszak kezdete es a turelmi ido meg nem telt le."
        elif available_at or evidence_routes:
            status = "present"
            reason = "Belepesi ido vagy a muszakhoz illeszkedo route talalhato."
        else:
            status = "no_show"
            reason = "A turelmi ido utan sincs belepesi ido vagy route bizonyitek."

        checks.append(
            {
                "snapshot_date": row["snapshot_date"].isoformat(),
                "work_date": row["work_date"].isoformat(),
                "snapshot_fetched_at": iso_datetime(row["snapshot_fetched_at"]),
                "checked_at": iso_datetime(checked_at),
                "organization_id": row["organization_id"],
                "dsp_id": row["dsp_id"],
                "courier_id": row["courier_id"],
                "courier_name": row["courier_name"],
                "warehouse_name": row["warehouse_name"],
                "shift_id": row["shift_id"],
                "shift_name": row["shift_name"],
                "shift_start": iso_datetime(shift_start),
                "shift_end": iso_datetime(shift_end),
                "current_shift_found": current_shift is not None,
                "available_for_shift_since": iso_datetime(available_at),
                "evidence_route_ids": evidence_routes,
                "grace_minutes": grace_minutes,
                "minutes_after_start": minutes_after_start,
                "attendance_status": status,
                "status_reason": reason,
            }
        )
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["snapshot", "compare"], required=True)
    parser.add_argument("--date", help="Celnap YYYY-MM-DD; alapertelmezett: holnap/ma.")
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Snapshot modban hany napot toltsunk le a kezdodattol.",
    )
    parser.add_argument("--grace-minutes", type=int, default=30)
    parser.add_argument(
        "--allow-missing-snapshot",
        action="store_true",
        help="Compare modban ne hibazzon, ha meg nincs elozo snapshot az adott napra.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now_local = datetime.now(LOCAL_TIMEZONE)
    target_date = parse_date(args.date) if args.date else (
        now_local.date() + timedelta(days=1)
        if args.mode == "snapshot"
        else now_local.date()
    )
    if args.mode == "snapshot":
        days = max(1, args.days)
        total_days = 0
        total_couriers = 0
        total_shifts = 0

        for offset in range(days):
            work_date = target_date + timedelta(days=offset)
            fetched_at = datetime.now(timezone.utc)
            payload = fetch_attendance(work_date)
            rows = flatten_snapshot(
                payload,
                now_local.date(),
                work_date,
                fetched_at,
            )

            if not rows:
                print(f"SNAPSHOT_EMPTY date={work_date}")
                continue

            couriers = len({row["courier_id"] for row in rows})
            shifts = len(rows)
            total_days += 1
            total_couriers += couriers
            total_shifts += shifts

            print(
                f"SNAPSHOT date={work_date} "
                f"couriers={couriers} shifts={shifts}"
            )

            if args.dry_run:
                continue

            snapshot_json = {
                "kind": SNAPSHOT_SOURCE,
                "snapshot_date": now_local.date().isoformat(),
                "work_date": work_date.isoformat(),
                "snapshot_fetched_at": iso_datetime(fetched_at),
                "courier_count": couriers,
                "shift_count": shifts,
                "api_payload": payload,
            }
            table = upsert_record(
                SNAPSHOT_SOURCE,
                work_date,
                attendance_url(work_date),
                snapshot_json,
                fetched_at,
            )
            print(f"SNAPSHOT_OK date={work_date} table={table}")

        if args.dry_run:
            print("DRY_RUN no DB write")

        print(
            f"SNAPSHOT_SUMMARY requested_days={days} "
            f"stored_days={total_days} couriers_total={total_couriers} "
            f"shifts_total={total_shifts}"
        )
        return

    fetched_at = datetime.now(timezone.utc)
    payload = fetch_attendance(target_date)
    snapshot_json = load_snapshot(target_date)
    if not snapshot_json:
        if args.allow_missing_snapshot:
            print(f"COMPARE_SKIPPED missing_snapshot date={target_date}")
            return
        raise RuntimeError(f"Nincs elozo napi snapshot ehhez a naphoz: {target_date}")
    snapshot_rows = flatten_snapshot(
        snapshot_json.get("api_payload") or {},
        parse_date(snapshot_json["snapshot_date"]),
        target_date,
        parse_datetime(snapshot_json["snapshot_fetched_at"]),
    )
    checks = build_checks(
        snapshot_rows, payload, fetched_at, max(0, args.grace_minutes)
    )
    counts = Counter(row["attendance_status"] for row in checks)
    result_json = {
        "kind": CHECK_SOURCE,
        "work_date": target_date.isoformat(),
        "snapshot_date": snapshot_json.get("snapshot_date"),
        "snapshot_fetched_at": snapshot_json.get("snapshot_fetched_at"),
        "checked_at": iso_datetime(fetched_at),
        "grace_minutes": max(0, args.grace_minutes),
        "counts": dict(counts),
        "checks": checks,
    }
    if not args.dry_run:
        table = upsert_record(
            CHECK_SOURCE,
            target_date,
            attendance_url(target_date),
            result_json,
            fetched_at,
        )
        print(f"COMPARE_TABLE table={table}")

    print(
        "COMPARE_OK "
        f"date={target_date} total={len(checks)} "
        + " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    )
    no_shows = sorted(
        {
            (row["courier_id"], row["courier_name"])
            for row in checks
            if row["attendance_status"] == "no_show"
        }
    )
    for courier_id, courier_name in no_shows:
        print(f"NO_SHOW courier_id={courier_id} courier_name={courier_name}")


if __name__ == "__main__":
    main()
