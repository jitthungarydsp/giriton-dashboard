import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    import psycopg2
except ImportError:
    psycopg2 = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.api import BASE_URL, DEPOT_ID, ORGANIZATION_ID, SUPABASE_ANON_KEY
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
TABLE_NAME = "ops_shift_rescue_suggestions"
DEFAULT_SHIFT_HOURS = 4.5
TABLE_SQL_PATH = PROJECT_ROOT / "docs" / "supabase_shift_rescue_suggestions.sql"


def normalize_id(value):
    text = "".join(character for character in str(value or "") if character.isdigit())
    return int(text) if text else None


def normalize_text(value):
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
    }
    text = str(value or "").strip().lower()

    for source, target in replacements.items():
        text = text.replace(source, target)

    return " ".join(text.split())


def normalize_warehouse(value):
    raw_value = str(value or "").strip().upper()
    compact_value = "".join(character for character in raw_value if character.isalnum())

    if compact_value in {"1", "BUD1", "BUD1JIT", "BUDAPEST"}:
        return "BUD1"

    if compact_value in {"2", "BUD2", "BUD2JIT"}:
        return "BUD2"

    if "BUD2" in compact_value:
        return "BUD2"

    if "BUD1" in compact_value or compact_value == "BUD":
        return "BUD1"

    return raw_value or ""


def parse_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed.astimezone(LOCAL_TIMEZONE)


def iso_datetime(value):
    if not value:
        return None

    return value.isoformat()


def minutes_between(start_at, end_at):
    if not start_at or not end_at:
        return None

    return int(round((end_at - start_at).total_seconds() / 60))


def request_json(method, url, **kwargs):
    response = requests.request(method, url, timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def fetch_attendance(work_date):
    url = (
        f"{BASE_URL}/fetch-attendance/{DEPOT_ID}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )
    return request_json("GET", url, headers={"apikey": SUPABASE_ANON_KEY})


def fetch_departure_dashboard():
    url = f"{BASE_URL}/departure-dashboard"
    payload = {
        "id": DEPOT_ID,
        "organizationId": ORGANIZATION_ID,
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
    }
    return request_json("POST", url, json=payload, headers=headers)


def fetch_driver_detail(courier_id, work_date):
    url = (
        f"{BASE_URL}/fetch-drivers-detail/{courier_id}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )
    return request_json("GET", url)


def route_id(route):
    return str(
        route.get("route_id")
        or route.get("routeId")
        or route.get("id")
        or ""
    ).strip()


def route_assigned_at(route):
    for key in ["assignedAt", "routeAssignedAt", "courierRegisteredAt", "plannedDeparture"]:
        parsed = parse_datetime(route.get(key))
        if parsed:
            return parsed

    return None


def route_expected_return_at(route):
    for key in ["realReturn", "expectedReturn", "plannedReturn"]:
        parsed = parse_datetime(route.get(key))
        if parsed:
            return parsed

    return None


def route_oldest_datetime(route):
    candidates = [
        parse_datetime(route.get(key))
        for key in ["createdAt", "courierRegisteredAt", "assignedAt", "plannedDeparture"]
    ]
    candidates = [candidate for candidate in candidates if candidate]
    return min(candidates) if candidates else datetime.max.replace(tzinfo=LOCAL_TIMEZONE)


def find_detail_route(driver_detail, dashboard_route_id):
    routes = driver_detail.get("routes", []) or []

    if not routes:
        return {}

    dashboard_route_id = str(dashboard_route_id or "").strip()

    for route in routes:
        if route_id(route) == dashboard_route_id:
            return route

    return sorted(routes, key=route_oldest_datetime)[0]


def dashboard_routes_by_courier(dashboard_data):
    result = {}

    for route in dashboard_data.get("routes", []) or []:
        courier_id = normalize_id(route.get("courier_id") or route.get("courierId"))
        current_route_id = route_id(route)

        if courier_id is None or not current_route_id:
            continue

        result[courier_id] = route

    return result


def parse_shift(shift):
    start_at = parse_datetime(shift.get("shiftStart"))
    end_at = parse_datetime(shift.get("shiftEnd"))

    if not start_at:
        return None

    return {
        "shift_id": str(shift.get("shiftId") or "").strip(),
        "shift_name": str(shift.get("shiftName") or "").strip(),
        "shift_start": start_at,
        "shift_end": end_at or start_at + timedelta(hours=DEFAULT_SHIFT_HOURS),
        "available_for_shift_since": parse_datetime(shift.get("availableForShiftSince")),
        "raw": shift,
    }


def parse_couriers(attendance_data):
    couriers = []

    for courier in attendance_data.get("couriers", []) or []:
        courier_id = normalize_id(courier.get("courierId"))

        if courier_id is None:
            continue

        shifts = [
            parsed
            for parsed in (parse_shift(shift) for shift in courier.get("shifts", []) or [])
            if parsed
        ]
        shifts = sorted(shifts, key=lambda item: item["shift_start"])

        couriers.append(
            {
                "courier_id": courier_id,
                "courier_name": str(courier.get("courierName") or "").strip(),
                "warehouse": normalize_warehouse(courier.get("warehouseName")),
                "shifts": shifts,
                "raw": courier,
            }
        )

    return couriers


def find_shift_at(shifts, timestamp):
    if not timestamp:
        return None

    for shift in shifts:
        if shift["shift_start"] <= timestamp < shift["shift_end"]:
            return shift

    previous = [shift for shift in shifts if shift["shift_start"] <= timestamp]
    return previous[-1] if previous else None


def find_next_shift(shifts, timestamp, exclude_shift_id=""):
    if not timestamp:
        return None

    for shift in shifts:
        if shift["shift_start"] > timestamp and shift["shift_id"] != exclude_shift_id:
            return shift

    return None


def shifts_overlap(first_start, first_end, second_start, second_end):
    if not all([first_start, first_end, second_start, second_end]):
        return False

    return first_start < second_end and second_start < first_end


def candidate_has_blocking_overlap(candidate, target_shift, replacement_return_at, now):
    for shift in candidate["shifts"]:
        has_overlap = shifts_overlap(
            target_shift["shift_start"],
            target_shift["shift_end"],
            shift["shift_start"],
            shift["shift_end"],
        )

        if not has_overlap:
            continue

        if (
            replacement_return_at
            and replacement_return_at <= target_shift["shift_start"]
            and shift["shift_start"] <= now
        ):
            continue

            return True

    return False


def candidate_has_started_working(candidate, replacement_context, now):
    if replacement_context.get("route_id"):
        return True

    for shift in candidate["shifts"]:
        if shift.get("available_for_shift_since"):
            return True

        shift_start = shift.get("shift_start")
        if shift_start and shift_start <= now:
            return True

    return False


def free_gap_for_target(candidate, target_shift, replacement_return_at=None):
    before = [
        shift
        for shift in candidate["shifts"]
        if shift["shift_end"] <= target_shift["shift_start"]
    ]
    after = [
        shift
        for shift in candidate["shifts"]
        if shift["shift_start"] >= target_shift["shift_end"]
    ]
    available_from = before[-1]["shift_end"] if before else None
    available_until = after[0]["shift_start"] if after else None

    if (
        replacement_return_at
        and replacement_return_at <= target_shift["shift_start"]
        and (not available_from or replacement_return_at > available_from)
    ):
        available_from = replacement_return_at

    if available_from and available_until:
        free_gap_minutes = minutes_between(available_from, available_until)
    elif not candidate["shifts"]:
        free_gap_minutes = 24 * 60
    else:
        free_gap_minutes = None

    return available_from, available_until, free_gap_minutes


def build_route_context(courier, dashboard_by_courier, detail_cache, work_date):
    dashboard_route = dashboard_by_courier.get(courier["courier_id"]) or {}
    current_route_id = route_id(dashboard_route)

    if not current_route_id:
        return {}

    if courier["courier_id"] not in detail_cache:
        detail_cache[courier["courier_id"]] = fetch_driver_detail(
            courier["courier_id"],
            work_date,
        )

    detail_route = find_detail_route(
        detail_cache[courier["courier_id"]],
        current_route_id,
    )
    source_route = detail_route or dashboard_route

    return {
        "route_id": current_route_id,
        "assigned_at": route_assigned_at(source_route),
        "expected_return_at": route_expected_return_at(source_route),
        "dashboard_route": dashboard_route,
        "detail_route": detail_route,
    }


def find_problem_shifts(couriers, dashboard_by_courier, work_date):
    detail_cache = {}
    problems = []

    for courier in couriers:
        route_context = build_route_context(
            courier,
            dashboard_by_courier,
            detail_cache,
            work_date,
        )

        if not route_context or not route_context.get("expected_return_at"):
            continue

        assigned_at = route_context.get("assigned_at")
        current_shift = find_shift_at(courier["shifts"], assigned_at)
        next_shift = find_next_shift(
            courier["shifts"],
            assigned_at,
            exclude_shift_id=(current_shift or {}).get("shift_id", ""),
        )

        if not next_shift:
            continue

        delay_minutes = minutes_between(
            next_shift["shift_start"],
            route_context["expected_return_at"],
        )

        if delay_minutes is None or delay_minutes <= 0:
            continue

        problems.append(
            {
                "courier": courier,
                "route_context": route_context,
                "current_shift": current_shift,
                "target_shift": next_shift,
                "delay_minutes": delay_minutes,
            }
        )

    return problems, detail_cache


def score_candidate(candidate, problem, replacement_context, gap_minutes):
    target_shift = problem["target_shift"]
    score = 100

    if candidate["warehouse"] == problem["courier"]["warehouse"]:
        score += 50

    if not candidate["shifts"]:
        score += 35

    if gap_minutes is not None and gap_minutes >= 300:
        score += 30

    expected_return_at = replacement_context.get("expected_return_at")
    if expected_return_at and expected_return_at <= target_shift["shift_start"]:
        score += 25

    if expected_return_at and expected_return_at > target_shift["shift_start"]:
        score -= 80

    return score


def build_replacement_rows(
    collection_id,
    collected_at,
    work_date,
    problems,
    couriers,
    dashboard_by_courier,
    detail_cache,
    max_candidates,
    minimum_gap_minutes,
    debug_courier="",
):
    rows = []
    debug_courier = normalize_text(debug_courier)

    for problem in problems:
        problem_courier = problem["courier"]
        target_shift = problem["target_shift"]
        now = datetime.now(LOCAL_TIMEZONE)

        candidates = []

        for candidate in couriers:
            debug_this_candidate = (
                debug_courier
                and (
                    debug_courier in normalize_text(candidate["courier_name"])
                    or debug_courier == str(candidate["courier_id"])
                )
            )

            if candidate["courier_id"] == problem_courier["courier_id"]:
                if debug_this_candidate:
                    print("DEBUG skip: sajat problem futar")
                continue

            if (
                problem_courier["warehouse"]
                and candidate["warehouse"]
                and candidate["warehouse"] != problem_courier["warehouse"]
            ):
                if debug_this_candidate:
                    print(
                        "DEBUG skip warehouse: "
                        f"problem={problem_courier['warehouse']} "
                        f"candidate={candidate['warehouse']}"
                    )
                continue

            replacement_context = build_route_context(
                candidate,
                dashboard_by_courier,
                detail_cache,
                work_date,
            )

            if not candidate_has_started_working(
                candidate,
                replacement_context,
                now,
            ):
                if debug_this_candidate:
                    print("DEBUG skip not started working")
                continue

            replacement_return_at = replacement_context.get("expected_return_at")

            if replacement_return_at and replacement_return_at > target_shift["shift_start"]:
                if debug_this_candidate:
                    print(
                        "DEBUG skip late return: "
                        f"return={replacement_return_at} "
                        f"target_start={target_shift['shift_start']}"
                )
                continue

            if candidate_has_blocking_overlap(
                candidate,
                target_shift,
                replacement_return_at,
                now,
            ):
                if debug_this_candidate:
                    print(
                        "DEBUG skip overlap: "
                        f"target={target_shift['shift_name']} "
                        f"{target_shift['shift_start']} - {target_shift['shift_end']} "
                        f"return={replacement_return_at}"
                    )
                continue

            available_from, available_until, gap_minutes = free_gap_for_target(
                candidate,
                target_shift,
                replacement_return_at=replacement_return_at,
            )

            if gap_minutes is not None and gap_minutes < minimum_gap_minutes:
                if debug_this_candidate:
                    print(
                        "DEBUG skip small gap: "
                        f"gap={gap_minutes} min required={minimum_gap_minutes}"
                    )
                continue

            if debug_this_candidate:
                print(
                    "DEBUG candidate accepted: "
                    f"{candidate['courier_name']} #{candidate['courier_id']} "
                    f"problem={problem_courier['courier_name']} "
                    f"target={target_shift['shift_name']} "
                    f"gap={gap_minutes} "
                    f"return={replacement_return_at}"
                )

            if candidate["shifts"]:
                reason = "nincs utkozo muszak"
                if gap_minutes is not None and gap_minutes >= minimum_gap_minutes:
                    reason = f"ket muszak kozott {gap_minutes} perc szabad ido"
            else:
                reason = "nincs aznapi muszak"

            score = score_candidate(
                candidate,
                problem,
                replacement_context,
                gap_minutes,
            )

            candidates.append(
                {
                    "candidate": candidate,
                    "route_context": replacement_context,
                    "available_from": available_from,
                    "available_until": available_until,
                    "gap_minutes": gap_minutes,
                    "reason": reason,
                    "score": score,
                }
            )

        candidates = sorted(
            candidates,
            key=lambda item: (-item["score"], item["candidate"]["courier_name"]),
        )[:max_candidates]

        for candidate_item in candidates:
            candidate = candidate_item["candidate"]
            replacement_context = candidate_item["route_context"]
            current_shift = problem.get("current_shift") or {}
            source_summary = {
                "problem": {
                    "route": problem["route_context"],
                    "current_shift": current_shift,
                    "target_shift": target_shift,
                },
                "replacement": {
                    "route": replacement_context,
                    "shifts": candidate["shifts"],
                },
            }

            rows.append(
                {
                    "collection_id": collection_id,
                    "work_date": work_date,
                    "warehouse": problem_courier["warehouse"],
                    "problem_courier_id": problem_courier["courier_id"],
                    "problem_courier_name": problem_courier["courier_name"],
                    "problem_route_id": problem["route_context"].get("route_id"),
                    "problem_route_assigned_at": iso_datetime(
                        problem["route_context"].get("assigned_at")
                    ),
                    "problem_expected_return_at": iso_datetime(
                        problem["route_context"].get("expected_return_at")
                    ),
                    "problem_current_shift_id": current_shift.get("shift_id"),
                    "problem_current_shift_name": current_shift.get("shift_name"),
                    "problem_current_shift_start": iso_datetime(
                        current_shift.get("shift_start")
                    ),
                    "problem_current_shift_end": iso_datetime(
                        current_shift.get("shift_end")
                    ),
                    "problem_target_shift_id": target_shift.get("shift_id"),
                    "problem_target_shift_name": target_shift.get("shift_name"),
                    "problem_target_shift_start": iso_datetime(
                        target_shift.get("shift_start")
                    ),
                    "problem_target_shift_end": iso_datetime(
                        target_shift.get("shift_end")
                    ),
                    "delay_minutes": problem["delay_minutes"],
                    "replacement_courier_id": candidate["courier_id"],
                    "replacement_courier_name": candidate["courier_name"],
                    "replacement_current_route_id": replacement_context.get("route_id"),
                    "replacement_expected_return_at": iso_datetime(
                        replacement_context.get("expected_return_at")
                    ),
                    "replacement_available_from": iso_datetime(
                        candidate_item["available_from"]
                    ),
                    "replacement_available_until": iso_datetime(
                        candidate_item["available_until"]
                    ),
                    "free_gap_minutes": candidate_item["gap_minutes"],
                    "replacement_reason": candidate_item["reason"],
                    "score": candidate_item["score"],
                    "status": "new",
                    "source_summary": serialize_for_json(source_summary),
                    "collected_at": collected_at,
                }
            )

    return rows


def serialize_for_json(value):
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: serialize_for_json(item)
            for key, item in value.items()
            if key != "raw"
        }

    if isinstance(value, list):
        return [serialize_for_json(item) for item in value]

    return value


def supabase_headers(extra=None):
    _supabase_url, service_role_key = get_supabase_config()

    if not service_role_key:
        raise RuntimeError("Hianyzik a SUPABASE_SERVICE_ROLE_KEY beallitas.")

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    headers.update(extra or {})
    return headers


def insert_rows(rows):
    if not rows:
        return 0

    supabase_url, _service_role_key = get_supabase_config()

    if not supabase_url:
        raise RuntimeError("Hianyzik a SUPABASE_URL beallitas.")

    response = requests.post(
        f"{supabase_url}/rest/v1/{TABLE_NAME}",
        headers=supabase_headers(
            {
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
        ),
        json=rows,
        timeout=60,
    )
    raise_for_supabase_error(response)
    return len(rows)


def ensure_table():
    database_url = str(os.getenv("DATABASE_URL") or "").strip()

    if not database_url:
        print("DATABASE_URL nincs beallitva, tabla letrehozas kihagyva.")
        return

    if psycopg2 is None:
        print("psycopg2 nincs telepitve, tabla letrehozas kihagyva.")
        return

    if not TABLE_SQL_PATH.exists():
        raise RuntimeError(f"Hianyzik az SQL fajl: {TABLE_SQL_PATH}")

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(TABLE_SQL_PATH.read_text(encoding="utf-8"))
        connection.commit()

    print(f"Tabla ellenorizve/letrehozva: {TABLE_NAME}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Dinamikus muszakmento/helyettes javaslatok szamitasa."
    )
    parser.add_argument(
        "--work-date",
        default=datetime.now(LOCAL_TIMEZONE).date().isoformat(),
        help="Vizsgalt nap YYYY-MM-DD formatumban. Alapertelmezes: mai nap.",
    )
    parser.add_argument(
        "--minimum-gap-minutes",
        type=int,
        default=300,
        help="Mekkora szabad ido legyen eleg ket muszak kozott. Alap: 300 perc.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum hany jeloltet irjon egy veszelyes muszakhoz.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak szamol es kiir, DB-be nem ir.",
    )
    parser.add_argument(
        "--skip-ensure-table",
        action="store_true",
        help="Ne probalja DATABASE_URL alapjan letrehozni/ellenorizni a tablat.",
    )
    parser.add_argument(
        "--debug-courier",
        default="",
        help="Nev vagy ID, amelynel kiirja, miert esik ki/kerul be jeloltkent.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    collection_id = str(uuid.uuid4())
    collected_at = datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds")

    attendance_data = fetch_attendance(args.work_date)
    dashboard_data = fetch_departure_dashboard()
    couriers = parse_couriers(attendance_data)
    dashboard_by_courier = dashboard_routes_by_courier(dashboard_data)
    problems, detail_cache = find_problem_shifts(
        couriers,
        dashboard_by_courier,
        args.work_date,
    )
    rows = build_replacement_rows(
        collection_id,
        collected_at,
        args.work_date,
        problems,
        couriers,
        dashboard_by_courier,
        detail_cache,
        args.max_candidates,
        args.minimum_gap_minutes,
        debug_courier=args.debug_courier,
    )

    print(
        f"work_date={args.work_date} couriers={len(couriers)} "
        f"active_routes={len(dashboard_by_courier)} problems={len(problems)} "
        f"suggestions={len(rows)} collection_id={collection_id}"
    )

    for row in rows[:50]:
        print(
            f"[{row['warehouse'] or '-'}] "
            f"{row['problem_courier_name']} #{row['problem_courier_id']} "
            f"{row['problem_target_shift_name']} delay={row['delay_minutes']}p -> "
            f"{row['replacement_courier_name']} #{row['replacement_courier_id']} "
            f"score={row['score']} reason={row['replacement_reason']}"
        )

    if args.dry_run:
        print("DRY RUN, DB iras kihagyva.")
        return

    if not args.skip_ensure_table:
        ensure_table()

    inserted = insert_rows(rows)
    print(f"DB_INSERT {TABLE_NAME} rows={inserted}")


if __name__ == "__main__":
    main()
