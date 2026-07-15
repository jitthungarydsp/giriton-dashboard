import argparse
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import Json, execute_values
import requests


ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DSP_ID = "JIT"
API_BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_SQL_PATH = PROJECT_ROOT / "docs" / "next_day_attendance_tables.sql"


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
                    "raw_shift": shift,
                }
            )
    return rows


def database_url():
    value = (os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("Hianyzik a DATABASE_URL vagy SUPABASE_DB_URL.")
    return value


def ensure_tables(cursor):
    cursor.execute(TABLE_SQL_PATH.read_text(encoding="utf-8"))


def save_snapshot(connection, rows, snapshot_date, work_date):
    with connection.cursor() as cursor:
        ensure_tables(cursor)
        cursor.execute(
            """
            delete from public.ops_dsp_next_day_shift_snapshots
            where snapshot_date = %s and work_date = %s
            """,
            (snapshot_date, work_date),
        )
        execute_values(
            cursor,
            """
            insert into public.ops_dsp_next_day_shift_snapshots (
                snapshot_date, work_date, snapshot_fetched_at,
                organization_id, dsp_id, dsp_name, courier_id, courier_name,
                warehouse_name, shift_id, shift_name, shift_start, shift_end,
                raw_shift, updated_at
            ) values %s
            """,
            [
                (
                    row["snapshot_date"], row["work_date"], row["snapshot_fetched_at"],
                    row["organization_id"], row["dsp_id"], row["dsp_name"],
                    row["courier_id"], row["courier_name"], row["warehouse_name"],
                    row["shift_id"], row["shift_name"], row["shift_start"],
                    row["shift_end"], Json(row["raw_shift"]), row["snapshot_fetched_at"],
                )
                for row in rows
            ],
        )


def load_snapshot(connection, work_date):
    with connection.cursor() as cursor:
        ensure_tables(cursor)
        cursor.execute(
            """
            select snapshot_date, work_date, snapshot_fetched_at,
                   organization_id, dsp_id, dsp_name, courier_id, courier_name,
                   warehouse_name, shift_id, shift_name, shift_start, shift_end
            from public.ops_dsp_next_day_shift_snapshots
            where work_date = %s
              and snapshot_date = (
                  select max(snapshot_date)
                  from public.ops_dsp_next_day_shift_snapshots
                  where work_date = %s
              )
            order by shift_start, courier_name
            """,
            (work_date, work_date),
        )
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


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
                **row,
                "checked_at": checked_at,
                "current_shift_found": current_shift is not None,
                "available_for_shift_since": available_at,
                "evidence_route_ids": evidence_routes,
                "grace_minutes": grace_minutes,
                "minutes_after_start": minutes_after_start,
                "attendance_status": status,
                "status_reason": reason,
            }
        )
    return checks


def save_checks(connection, checks):
    with connection.cursor() as cursor:
        ensure_tables(cursor)
        execute_values(
            cursor,
            """
            insert into public.ops_dsp_shift_attendance_checks (
                work_date, courier_id, shift_id, snapshot_date,
                snapshot_fetched_at, checked_at, organization_id, dsp_id,
                courier_name, warehouse_name, shift_name, shift_start, shift_end,
                current_shift_found, available_for_shift_since, evidence_route_ids,
                grace_minutes, minutes_after_start, attendance_status,
                status_reason, updated_at
            ) values %s
            on conflict (work_date, courier_id, shift_id) do update set
                snapshot_date = excluded.snapshot_date,
                snapshot_fetched_at = excluded.snapshot_fetched_at,
                checked_at = excluded.checked_at,
                courier_name = excluded.courier_name,
                warehouse_name = excluded.warehouse_name,
                shift_name = excluded.shift_name,
                shift_start = excluded.shift_start,
                shift_end = excluded.shift_end,
                current_shift_found = excluded.current_shift_found,
                available_for_shift_since = excluded.available_for_shift_since,
                evidence_route_ids = excluded.evidence_route_ids,
                grace_minutes = excluded.grace_minutes,
                minutes_after_start = excluded.minutes_after_start,
                attendance_status = excluded.attendance_status,
                status_reason = excluded.status_reason,
                updated_at = excluded.updated_at
            """,
            [
                (
                    row["work_date"], row["courier_id"], row["shift_id"],
                    row["snapshot_date"], row["snapshot_fetched_at"],
                    row["checked_at"], row["organization_id"], row["dsp_id"],
                    row["courier_name"], row["warehouse_name"], row["shift_name"],
                    row["shift_start"], row["shift_end"],
                    row["current_shift_found"], row["available_for_shift_since"],
                    Json(row["evidence_route_ids"]), row["grace_minutes"],
                    row["minutes_after_start"], row["attendance_status"],
                    row["status_reason"], row["checked_at"],
                )
                for row in checks
            ],
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["snapshot", "compare"], required=True)
    parser.add_argument("--date", help="Celnap YYYY-MM-DD; alapertelmezett: holnap/ma.")
    parser.add_argument("--grace-minutes", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now_local = datetime.now(LOCAL_TIMEZONE)
    target_date = parse_date(args.date) if args.date else (
        now_local.date() + timedelta(days=1)
        if args.mode == "snapshot"
        else now_local.date()
    )
    fetched_at = datetime.now(timezone.utc)
    payload = fetch_attendance(target_date)

    if args.mode == "snapshot":
        rows = flatten_snapshot(payload, now_local.date(), target_date, fetched_at)
        if not rows:
            raise RuntimeError(f"Az API nem adott vissza muszakot ehhez a naphoz: {target_date}")
        couriers = len({row["courier_id"] for row in rows})
        print(f"SNAPSHOT date={target_date} couriers={couriers} shifts={len(rows)}")
        if args.dry_run:
            print("DRY_RUN no DB write")
            return
        with psycopg2.connect(database_url()) as connection:
            save_snapshot(connection, rows, now_local.date(), target_date)
        print("SNAPSHOT_OK")
        return

    with psycopg2.connect(database_url()) as connection:
        snapshot_rows = load_snapshot(connection, target_date)
        if not snapshot_rows:
            raise RuntimeError(f"Nincs elozo napi snapshot ehhez a naphoz: {target_date}")
        checks = build_checks(
            snapshot_rows, payload, fetched_at, max(0, args.grace_minutes)
        )
        save_checks(connection, checks)

    counts = Counter(row["attendance_status"] for row in checks)
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
