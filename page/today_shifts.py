from datetime import datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from resources.muszakpro_sheet import (
    build_foglalas_lookup,
    build_giriton_lookup,
    foglalas_key,
    read_giriton_email_name_lookup,
    record_key,
)
from resources.shift_reconciliation_sheet import (
    read_shift_reconciliation_records,
    rebuild_shift_reconciliation,
)
from resources.today_shift_log_sheet import write_today_shift_log


BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DEPOT_ID = "JIT"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


@st.cache_data(
    show_spinner=False,
)
def fetch_json(url):
    response = requests.get(
        url,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def request_json(url):
    try:
        return fetch_json(
            url
        )
    except requests.RequestException as exc:
        st.error(
            f"API hiba: {exc}"
        )
    except ValueError:
        st.error(
            "API hiba: a válasz nem érvényes JSON."
        )

    return {}


def load_attendance_for_date(work_date):
    url = (
        f"{BASE_URL}/"
        f"fetch-attendance/{DEPOT_ID}/{work_date}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    return request_json(
        url
    )


def load_vehicle_assignments():
    url = (
        f"{BASE_URL}/"
        f"fetch-vehicle-assignments"
        f"?id={DEPOT_ID}"
        f"&organizationId={ORGANIZATION_ID}"
    )

    return request_json(
        url
    )


def load_drivers():
    url = (
        f"{BASE_URL}/"
        f"fetch-drivers"
        f"?id={DEPOT_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )

    return request_json(
        url
    )


@st.cache_data(
    show_spinner=False,
)
def load_driver_details_for_date(driver_id, work_date_text):
    url = (
        f"{BASE_URL}/"
        f"fetch-drivers-detail/{driver_id}/{work_date_text}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    return request_json(
        url
    )


@st.cache_data(
    show_spinner=False,
)
def load_shift_sheet_data(work_date_text):
    reconciliation_records = read_shift_reconciliation_records(
        work_date_text
    )
    giriton_records = reconciliation_to_giriton_records(
        reconciliation_records
    )
    foglalas_records = reconciliation_to_foglalas_records(
        reconciliation_records
    )
    email_name_lookup = read_giriton_email_name_lookup()

    return (
        giriton_records,
        foglalas_records,
        email_name_lookup,
        build_giriton_lookup(
            giriton_records
        ),
        build_foglalas_lookup(
            foglalas_records
        ),
    )


def reconciliation_to_giriton_records(records):
    return [
        {
            "work_date": record.get("work_date", ""),
            "start": record.get("start", ""),
            "end": record.get("end", ""),
            "warehouse": record.get("warehouse", ""),
            "name": record.get("name", ""),
            "email": record.get("email", ""),
            "check": record.get("giriton_check", ""),
        }
        for record in records
        if record.get("giriton") == "OK"
    ]


def reconciliation_to_foglalas_records(records):
    return [
        {
            "created_at": record.get("updated_at", ""),
            "work_date": record.get("work_date", ""),
            "email": record.get("email", ""),
            "shift": (
                f"{record.get('warehouse', '')}_"
                f"{record.get('start', '')}"
            ),
            "warehouse": record.get("warehouse", ""),
            "start": record.get("start", ""),
            "code": record.get("muszakpro_code", ""),
        }
        for record in records
        if record.get("muszakpro") == "OK"
    ]


def local_now():
    return datetime.now(
        LOCAL_TIMEZONE
    ).replace(tzinfo=None)


def normalize_name(value):
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def parse_datetime(value):
    if value in [None, ""]:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if parsed.tzinfo:
            parsed = parsed.astimezone(
                LOCAL_TIMEZONE
            ).replace(tzinfo=None)

        return parsed
    except ValueError:
        return None


def parse_assignment_datetime(work_date, value):
    if not value:
        return None

    try:
        hour, minute, *_ = str(value).split(":")
        return datetime.combine(
            work_date,
            time(
                int(hour),
                int(minute),
            ),
        )
    except (TypeError, ValueError):
        return None


def parse_work_date(value, fallback):
    if not value:
        return fallback

    try:
        return datetime.strptime(
            str(value),
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return fallback


def normalize_start_from_datetime(value):
    parsed = parse_datetime(
        value
    )

    if not parsed:
        return ""

    return parsed.strftime(
        "%H:%M"
    )


def format_time(value):
    if isinstance(value, datetime):
        return value.strftime("%H:%M")

    parsed = parse_datetime(
        value
    )

    if parsed:
        return parsed.strftime("%H:%M")

    return value or ""


def get_assignments_for_date(data, work_date_text):
    for day in data.get(
        "assignmentsForDate",
        [],
    ):
        if day.get("Date") == work_date_text:
            return day.get(
                "Assignments",
                [],
            )

    return []


def build_attendance_lookup(couriers):
    return {
        normalize_name(courier.get("courierName")): courier
        for courier in couriers
    }


def build_driver_id_lookup(drivers_data):
    lookup = {}

    for driver in drivers_data.get("drivers", []):
        personal_info = driver.get("personal_info", {})
        name = personal_info.get("name", "")
        driver_id = driver.get("driver_id")

        if name and driver_id:
            lookup[normalize_name(name)] = driver_id

    return lookup


def get_route_registered_at(driver_id, work_date_text, start_at, end_at=None):
    if not driver_id:
        return None

    details = load_driver_details_for_date(
        driver_id,
        work_date_text,
    )
    candidates = []

    for route in details.get("routes", []):
        registered_at = parse_datetime(
            route.get("courierRegisteredAt")
        )

        if not registered_at:
            continue

        planned_departure = parse_datetime(
            route.get("plannedDeparture")
        )
        assigned_at = parse_datetime(
            route.get("assignedAt")
        )
        route_marker = planned_departure or assigned_at or registered_at

        if start_at and end_at and route_marker:
            if not (
                start_at - timedelta(hours=1)
                <= route_marker
                <= end_at + timedelta(hours=1)
            ):
                continue

        candidates.append(registered_at)

    if not candidates:
        return None

    return min(candidates)


def find_matching_shift(courier, start_at):
    if not courier or not start_at:
        return {}

    shifts = courier.get(
        "shifts",
        [],
    )

    for shift in shifts:
        shift_start = parse_datetime(
            shift.get("shiftStart")
        )

        if shift_start and shift_start == start_at:
            return shift

    close_matches = [
        shift
        for shift in shifts
        if parse_datetime(shift.get("shiftStart"))
        and abs(
            (
                parse_datetime(shift.get("shiftStart")) - start_at
            ).total_seconds()
        )
        <= 120
    ]

    if close_matches:
        return close_matches[0]

    return {}


def is_first_shift(courier, start_at):
    if not courier or not start_at:
        return False

    shift_starts = [
        parse_datetime(
            shift.get("shiftStart")
        )
        for shift in courier.get("shifts", [])
    ]
    shift_starts = [
        value
        for value in shift_starts
        if value
    ]

    if not shift_starts:
        return False

    return min(shift_starts) == start_at


def get_checkin_state(start_at, available_since, end_at=None):
    checkin_at = parse_datetime(
        available_since
    )

    if checkin_at:
        if start_at:
            earliest_valid_checkin = start_at - timedelta(
                minutes=40
            )
            latest_valid_checkin = (
                end_at + timedelta(minutes=30)
                if end_at
                else start_at + timedelta(hours=5)
            )

            if not (
                earliest_valid_checkin
                <= checkin_at
                <= latest_valid_checkin
            ):
                checkin_at = None

    if checkin_at:
        return {
            "label": "Bejelentkezett",
            "color": "green",
            "time": format_time(checkin_at),
        }

    if not start_at:
        return {
            "label": "Nincs muszak",
            "color": "gray",
            "time": "",
        }

    minutes_to_start = int(
        (start_at - local_now()).total_seconds() // 60
    )

    if minutes_to_start > 30:
        return {
            "label": "30+ perc",
            "color": "yellow",
            "time": "",
        }

    if 15 <= minutes_to_start <= 30:
        return {
            "label": "15-30 perc",
            "color": "red",
            "time": "",
        }

    return {
        "label": "15 perc alatt",
        "color": "black",
        "time": "",
    }


def status_pill(state):
    colors = {
        "green": ("#dcfce7", "#166534"),
        "yellow": ("#fef3c7", "#92400e"),
        "red": ("#fee2e2", "#b91c1c"),
        "black": ("#111827", "#ffffff"),
        "gray": ("#f1f5f9", "#475569"),
    }
    bg, fg = colors.get(
        state["color"],
        colors["gray"],
    )

    return (
        f'<span style="background:{bg};color:{fg};'
        'border-radius:999px;padding:6px 10px;font-weight:700;'
        'display:inline-block;white-space:nowrap;">'
        f'{state["label"]}</span>'
    )


def ok_pill(label="✓"):
    return (
        '<span style="background:#dcfce7;color:#166534;'
        'border-radius:999px;padding:5px 9px;font-weight:800;'
        'display:inline-block;">'
        f'{label}</span>'
    )


def exp_pill():
    return (
        '<span style="background:#ede9fe;color:#5b21b6;'
        'border-radius:999px;padding:5px 9px;font-weight:800;'
        'display:inline-block;">EXP</span>'
    )


def build_vehicle_suggestions(assignments, work_date):
    available_at_by_plate = {}
    suggestions = {}
    parsed_assignments = []

    for index, assignment in enumerate(assignments):
        start_at = parse_assignment_datetime(
            work_date,
            assignment.get("Start"),
        )
        end_at = parse_assignment_datetime(
            work_date,
            assignment.get("End"),
        )
        parsed_assignments.append(
            (
                start_at or datetime.max,
                index,
                assignment,
                end_at,
            )
        )

    for start_at, index, assignment, end_at in sorted(parsed_assignments):
        current_plate = assignment.get(
            "License Plate",
            "",
        )
        candidates = [
            (
                available_at,
                plate,
            )
            for plate, available_at in available_at_by_plate.items()
            if available_at <= start_at
        ]

        if candidates:
            _, suggested_plate = max(
                candidates,
                key=lambda item: item[0],
            )
        else:
            suggested_plate = current_plate

        suggestions[index] = suggested_plate

        if suggested_plate:
            available_at_by_plate[suggested_plate] = end_at or start_at

        if current_plate and current_plate not in available_at_by_plate:
            available_at_by_plate[current_plate] = end_at or start_at

    return suggestions


def build_email_name_lookup(giriton_records, base_lookup=None):
    lookup = dict(
        base_lookup or {}
    )

    for record in giriton_records:
        email = str(
            record.get("email", "")
        ).strip().casefold()

        if email and record.get("name"):
            lookup[email] = record.get("name")

    return lookup


def merge_source(sources, key, updates, create=True):
    if key not in sources and not create:
        return

    if key not in sources:
        sources[key] = {}

    sources[key].update(
        {
            name: value
            for name, value in updates.items()
            if value not in [None, ""]
        }
    )


def build_shift_sources(
    assignments,
    attendance_data,
    giriton_records,
    foglalas_records,
    email_name_lookup=None,
):
    sources = {}
    email_name_lookup = build_email_name_lookup(
        giriton_records,
        email_name_lookup,
    )

    for record in giriton_records:
        name = record.get(
            "name",
            "",
        ).strip()
        key = record_key(
            name,
            record.get("start"),
        )
        merge_source(
            sources,
            key,
            {
                "name": name,
                "work_date": record.get("work_date"),
                "start": record.get("start"),
                "end": record.get("end"),
                "warehouse": record.get("warehouse"),
                "email": record.get("email"),
                "giriton_record": record,
            },
        )

    for record in foglalas_records:
        email = str(
            record.get("email", "")
        ).strip().casefold()
        name = email_name_lookup.get(
            email,
            record.get("email", ""),
        )
        key = record_key(
            name,
            record.get("start"),
        )
        merge_source(
            sources,
            key,
            {
                "name": name,
                "work_date": record.get("work_date"),
                "start": record.get("start"),
                "warehouse": record.get("warehouse"),
                "email": record.get("email"),
                "foglalas_record": record,
            },
        )

    for index, assignment in enumerate(assignments):
        name = assignment.get(
            "Driver",
            "",
        ).strip()
        start = assignment.get(
            "Start",
            "",
        )
        key = record_key(
            name,
            start,
        )
        merge_source(
            sources,
            key,
            {
                "name": name,
                "work_date": assignment.get("Date"),
                "start": start,
                "end": assignment.get("End", ""),
                "assignment": assignment,
                "assignment_index": index,
            },
            create=False,
        )

    for courier in attendance_data.get("couriers", []):
        name = str(
            courier.get("courierName", "")
        ).strip()

        for shift in courier.get("shifts", []):
            start = normalize_start_from_datetime(
                shift.get("shiftStart")
            )
            key = record_key(
                name,
                start,
            )
            merge_source(
                sources,
                key,
                {
                    "name": name,
                    "work_date": (
                        parse_datetime(shift.get("shiftStart")).date().isoformat()
                        if parse_datetime(shift.get("shiftStart"))
                        else ""
                    ),
                    "start": start,
                    "end": normalize_start_from_datetime(
                        shift.get("shiftEnd")
                    ),
                    "warehouse": courier.get("warehouseName"),
                    "attendance_courier": courier,
                    "attendance_shift": shift,
                    "is_exp": "EXP" in str(
                        shift.get("shiftName", "")
                    ).upper(),
                },
                create=False,
            )

    return list(
        sources.values()
    )


def build_rows(
    assignments,
    attendance_data,
    drivers_data,
    work_date,
    giriton_records,
    foglalas_records,
    email_name_lookup,
    giriton_lookup,
    foglalas_lookup,
):
    attendance_lookup = build_attendance_lookup(
        attendance_data.get(
            "couriers",
            [],
        )
    )
    driver_id_lookup = build_driver_id_lookup(
        drivers_data
    )
    rows = []
    vehicle_suggestions = build_vehicle_suggestions(
        assignments,
        work_date,
    )
    shift_sources = build_shift_sources(
        assignments,
        attendance_data,
        giriton_records,
        foglalas_records,
        email_name_lookup,
    )

    for index, source in enumerate(shift_sources):
        name = source.get(
            "name",
            "",
        ).strip()
        row_work_date = parse_work_date(
            source.get("work_date"),
            work_date,
        )
        start_at = parse_assignment_datetime(
            row_work_date,
            source.get("start"),
        )
        end_at = parse_assignment_datetime(
            row_work_date,
            source.get("end"),
        ) if source.get("end") else None

        if end_at and start_at and end_at <= start_at:
            end_at = end_at + timedelta(days=1)

        courier = attendance_lookup.get(
            normalize_name(name)
        )
        shift = find_matching_shift(
            courier,
            start_at,
        )
        attendance_shift = source.get(
            "attendance_shift",
            {},
        ) or shift
        is_exp = bool(
            source.get("is_exp")
            or "EXP" in str(
                attendance_shift.get("shiftName", "")
            ).upper()
        )
        giriton_record = giriton_lookup.get(
            record_key(
                name,
                source.get("start"),
            ),
            source.get("giriton_record", {}),
        )
        foglalas_record = source.get(
            "foglalas_record",
            {},
        )

        if giriton_record and not foglalas_record:
            foglalas_record = foglalas_lookup.get(
                foglalas_key(
                    giriton_record.get("email"),
                    giriton_record.get("warehouse"),
                    giriton_record.get("start"),
                ),
                {},
            )

        checkin_source = attendance_shift.get("availableForShiftSince")

        should_check_route_registration = (
            start_at
            and local_now() >= start_at - timedelta(minutes=40)
        )

        if not checkin_source and should_check_route_registration:
            checkin_source = get_route_registered_at(
                driver_id_lookup.get(normalize_name(name)),
                row_work_date.isoformat(),
                start_at,
                end_at,
            )

        state = get_checkin_state(
            start_at,
            checkin_source,
            end_at,
        )
        has_muszakpro = bool(
            foglalas_record
        ) or is_exp
        has_giriton = bool(
            giriton_record
        )
        is_checked_in = state["label"] == "Bejelentkezett"
        current_plate = (
            assignment.get("License Plate", "")
            if is_checked_in
            else ""
        )
        current_car_code = (
            assignment.get("Car", "")
            if is_checked_in
            else ""
        )
        first_shift_missing = (
            is_first_shift(
                courier,
                start_at,
            )
            and not is_checked_in
            and start_at
            and local_now() >= start_at
        )
        email_key = (
            f"today_shift_email_{row_work_date.isoformat()}_"
            f"{name}_{source.get('start')}"
        )
        email_sent = bool(
            st.session_state.get(email_key)
        )
        assignment = source.get(
            "assignment",
            {},
        )
        assignment_index = source.get(
            "assignment_index"
        )

        rows.append({
            "name": name,
            "warehouse": (
                assignment.get("Warehouse")
                or source.get("warehouse")
                or giriton_record.get("warehouse")
                or foglalas_record.get("warehouse")
                or ""
            ),
            "start": format_time(start_at),
            "end": format_time(source.get("end")),
            "muszakpro": exp_pill() if is_exp else ok_pill() if has_muszakpro else "-",
            "muszakpro_text": "EXP" if is_exp else "OK" if has_muszakpro else "-",
            "giriton": ok_pill() if has_giriton else "-",
            "giriton_text": "OK" if has_giriton else "-",
            "checkin": status_pill(state),
            "checkin_text": state["label"],
            "checkin_time": state["time"],
            "current_plate": current_plate,
            "car_code": current_car_code,
            "suggested_plate": vehicle_suggestions.get(
                assignment_index,
                assignment.get("License Plate", ""),
            ) if not is_exp else "",
            "email": source.get("email", ""),
            "email_sent": ok_pill() if email_sent else "-",
            "_email_key": email_key,
            "_row_key": f"{normalize_name(name)}_{format_time(start_at)}",
            "_work_date": row_work_date.isoformat(),
            "_start_at": start_at or datetime.max,
            "_has_muszakpro": has_muszakpro,
            "_has_giriton": has_giriton,
            "_is_checked_in": is_checked_in,
            "_first_shift_missing": first_shift_missing,
            "_is_exp": is_exp,
            "_email_sent": email_sent,
        })

    return sorted(
        rows,
        key=lambda row: (
            normalize_name(row["name"]),
            row["_start_at"],
        ),
    )


def render_styles():
    st.markdown(
        """
<style>
.shift-table-header {
    position: sticky;
    top: 3.75rem;
    z-index: 999;
    display: grid;
    align-items: center;
    gap: 16px;
    padding: 10px 0;
    background: rgba(255, 255, 255, 0.98);
    border-bottom: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}
.shift-head {
    color: #475569;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.25;
}
.shift-cell {
    color: #0f172a;
    font-size: 13px;
    overflow-wrap: anywhere;
}
.shift-cell-danger {
    color: #b91c1c;
    font-size: 13px;
    font-weight: 800;
}
.shift-cell-black {
    color: #020617;
    font-size: 13px;
    font-weight: 900;
}
.shift-alert-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 14px;
}
.shift-alert-chip {
    background: #fee2e2;
    color: #991b1b;
    border: 1px solid #fecaca;
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 800;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_header(headers, widths):
    total = sum(widths)
    grid_columns = " ".join(
        f"{width / total:.4f}fr"
        for width in widths
    )
    cells = "".join(
        f"<div class='shift-head'>{escape(header)}</div>"
        for header in headers
    )

    st.markdown(
        (
            "<div class='shift-table-header' "
            f"style='grid-template-columns: {grid_columns};'>"
            f"{cells}</div>"
        ),
        unsafe_allow_html=True,
    )


def render_cell(value, css_class="shift-cell"):
    st.markdown(
        f"<div class='{css_class}'>{value}</div>",
        unsafe_allow_html=True,
    )


def selection_key(row, index):
    return f"shift_selected_{row['_row_key']}_{index}"


def get_selected_rows(rows):
    return [
        row
        for index, row in enumerate(rows)
        if st.session_state.get(
            selection_key(
                row,
                index,
            )
        )
    ]


def build_editor_dataframe(rows):
    return pd.DataFrame(
        [
            {
                "Kiv.": False,
                "Név": (
                    f"!!! {row['name']}"
                    if row.get("_first_shift_missing")
                    else f"! {row['name']}"
                    if not row.get("_is_checked_in")
                    else row["name"]
                ),
                "Raktár": row.get("warehouse", ""),
                "Kezdés": row.get("start", ""),
                "Vége": row.get("end", ""),
                "MűszakPro": row.get("muszakpro_text", "-"),
                "Giriton": row.get("giriton_text", "-"),
                "Bejelentkezés": row.get("checkin_text", ""),
                "Bej. idő": row.get("checkin_time", ""),
                "Aktuális auto": row.get("current_plate", ""),
                "Auto kód": row.get("car_code", ""),
                "Javasolt auto": row.get("suggested_plate", ""),
                "E-mail jelzés": "OK" if row.get("_email_sent") else "-",
                "_row_key": row.get("_row_key", ""),
            }
            for row in rows
        ]
    )


def style_shift_dataframe(dataframe):
    def style_row(row):
        styles = [
            ""
            for _ in row
        ]

        if row["MűszakPro"] == "EXP":
            styles[dataframe.columns.get_loc("MűszakPro")] = (
                "background-color: #ede9fe; color: #5b21b6; font-weight: 800;"
            )
        elif row["MűszakPro"] == "OK":
            styles[dataframe.columns.get_loc("MűszakPro")] = (
                "background-color: #dcfce7; color: #166534; font-weight: 800;"
            )
        elif row["MűszakPro"] == "-":
            styles[dataframe.columns.get_loc("MűszakPro")] = (
                "background-color: #fee2e2; color: #991b1b; font-weight: 800;"
            )

        if row["Giriton"] == "OK":
            styles[dataframe.columns.get_loc("Giriton")] = (
                "background-color: #dcfce7; color: #166534; font-weight: 800;"
            )
        elif row["Giriton"] == "-":
            styles[dataframe.columns.get_loc("Giriton")] = (
                "background-color: #fee2e2; color: #991b1b; font-weight: 800;"
            )

        checkin = row["Bejelentkezés"]
        checkin_index = dataframe.columns.get_loc("Bejelentkezés")

        if checkin == "Bejelentkezett":
            styles[checkin_index] = "background-color: #dcfce7; color: #166534; font-weight: 800;"
        elif checkin == "30+ perc":
            styles[checkin_index] = "background-color: #fef3c7; color: #92400e; font-weight: 800;"
        elif checkin == "15-30 perc":
            styles[checkin_index] = "background-color: #fee2e2; color: #b91c1c; font-weight: 800;"
        elif checkin == "15 perc alatt":
            styles[checkin_index] = "background-color: #111827; color: #ffffff; font-weight: 800;"

        name = str(row["Név"])
        name_index = dataframe.columns.get_loc("Név")

        if name.startswith("!!!"):
            styles[name_index] = "color: #020617; font-weight: 900;"
        elif name.startswith("!"):
            styles[name_index] = "color: #b91c1c; font-weight: 800;"

        return styles

    return dataframe.style.apply(
        style_row,
        axis=1,
    )


def render_shift_table(rows):
    dataframe = build_editor_dataframe(
        rows
    ).drop(
        columns=["Kiv."]
    )

    dataframe = dataframe.drop(
        columns=["_row_key"]
    )

    st.dataframe(
        style_shift_dataframe(
            dataframe
        ),
        use_container_width=True,
        hide_index=True,
        height=620,
    )


def build_missing_source_alerts(rows):
    alerts = []

    for row in rows:
        missing = []

        if not row.get("_has_giriton"):
            missing.append("Giriton")

        if not row.get("_has_muszakpro"):
            missing.append("MűszakPro")

        if missing:
            alerts.append(
                f"{row['name']} {row['start']} - hiányzik: {', '.join(missing)}"
            )

    return alerts


def render_missing_source_alerts(rows):
    render_styles()
    alerts = build_missing_source_alerts(
        rows
    )

    if not alerts:
        st.success(
            "Minden műszak megvan Giritonban és MűszakProban is."
        )
        return

    chips = "".join(
        f"<span class='shift-alert-chip'>❗ {escape(alert)}</span>"
        for alert in alerts
    )

    st.markdown(
        f"<div class='shift-alert-list'>{chips}</div>",
        unsafe_allow_html=True,
    )


def render_table(rows):
    render_styles()

    headers = [
        "Kiv.",
        "Név",
        "Raktár",
        "Műszak kezdése",
        "Műszak vége",
        "MűszakPro",
        "Giriton",
        "Bejelentkezett-e",
        "Bejelentkezés ideje",
        "Aktuális auto",
        "Auto kód",
        "Javasolt auto",
        "E-mail küldése",
        "E-mail jelzés",
    ]
    widths = [
        0.45,
        1.8,
        0.8,
        0.9,
        0.8,
        0.7,
        0.7,
        1.4,
        0.9,
        1.0,
        0.8,
        1.0,
        1.1,
        0.8,
    ]

    render_header(
        headers,
        widths,
    )

    for index, row in enumerate(rows):
        cols = st.columns(
            widths
        )
        with cols[0]:
            st.checkbox(
                "",
                key=selection_key(
                    row,
                    index,
                ),
                label_visibility="collapsed",
            )

        values = [
            (
                f"❗ {escape(row['name'])}"
                if not row.get("_is_checked_in")
                else escape(row["name"])
            ),
            row["warehouse"],
            row["start"],
            row["end"],
            row["muszakpro"],
            row["giriton"],
            row["checkin"],
            row["checkin_time"],
            row["current_plate"],
            row["car_code"],
            row["suggested_plate"],
        ]

        for value_index, (col, value) in enumerate(zip(cols[1:12], values)):
            with col:
                name_class = "shift-cell"

                if value_index == 0 and row.get("_first_shift_missing"):
                    name_class = "shift-cell-black"
                elif value_index == 0 and not row.get("_is_checked_in"):
                    name_class = "shift-cell-danger"

                render_cell(
                    value,
                    name_class,
                )

        with cols[12]:
            if st.button(
                "E-mail",
                key=f"send_email_notice_{index}",
                use_container_width=True,
            ):
                st.session_state[row["_email_key"]] = True
                st.toast(
                    "E-mail jelzés rögzítve. A tényleges küldést később kötjük rá."
                )
                st.rerun()

        with cols[13]:
            render_cell(
                row["email_sent"]
            )

        st.divider()


def calculate_shift_statistics(rows):
    total = len(rows)
    uploaded = sum(
        row["giriton"] != "-"
        for row in rows
    )
    muszakpro = sum(
        row["muszakpro"] != "-"
        for row in rows
    )
    checked_in = sum(
        row.get("_is_checked_in")
        for row in rows
    )
    email_sent = sum(
        row["email_sent"] != "-"
        for row in rows
    )
    percent = round(
        uploaded / total * 100,
        1,
    ) if total else 0
    checked_in_percent = round(
        checked_in / total * 100,
        1,
    ) if total else 0

    return {
        "total": total,
        "uploaded": uploaded,
        "muszakpro": muszakpro,
        "checked_in": checked_in,
        "checked_in_percent": checked_in_percent,
        "email_sent": email_sent,
        "percent": percent,
    }


def build_driver_contact_lookup(drivers_data):
    lookup = {}

    for driver in drivers_data.get("drivers", []):
        personal_info = driver.get(
            "personal_info",
            {},
        )
        name = personal_info.get(
            "name",
            "",
        )

        if not name:
            continue

        lookup[normalize_name(name)] = {
            "phone": personal_info.get("contact_number", ""),
            "warehouse": personal_info.get("warehouse_name", ""),
            "driver_id": driver.get("driver_id", ""),
        }

    return lookup


def shifts_overlap(first_start, first_end, second_start, second_end):
    if not all([first_start, first_end, second_start, second_end]):
        return False

    return first_start < second_end and second_start < first_end


def has_shift_capacity(courier, target_start, target_end):
    for shift in courier.get("shifts", []):
        shift_start = parse_datetime(
            shift.get("shiftStart")
        )
        shift_end = parse_datetime(
            shift.get("shiftEnd")
        )

        if shifts_overlap(
            target_start,
            target_end,
            shift_start,
            shift_end,
        ):
            return False

    return True


def find_replacement_candidates(selected_rows, attendance_data, drivers_data):
    if not selected_rows:
        return []

    contact_lookup = build_driver_contact_lookup(
        drivers_data
    )
    candidates_by_name = {}

    attendance_names = {
        normalize_name(
            courier.get("courierName")
        )
        for courier in attendance_data.get("couriers", [])
    }

    for selected in selected_rows:
        target_warehouse = selected.get("warehouse", "")
        target_start = selected.get("_start_at")

        if not isinstance(target_start, datetime) or target_start == datetime.max:
            continue

        target_end = parse_assignment_datetime(
            target_start.date(),
            selected.get("end"),
        ) if isinstance(target_start, datetime) and selected.get("end") else None

        if target_end and target_end <= target_start:
            target_end = target_end + timedelta(
                days=1
            )

        if not target_end and isinstance(target_start, datetime):
            target_end = target_start + timedelta(
                hours=4
            )

        for courier in attendance_data.get("couriers", []):
            name = str(
                courier.get("courierName", "")
            ).strip()

            if not name or normalize_name(name) == normalize_name(selected.get("name")):
                continue

            warehouse = courier.get(
                "warehouseName",
                "",
            )
            contact = contact_lookup.get(
                normalize_name(name),
                {},
            )
            usual_warehouse = warehouse or contact.get(
                "warehouse",
                "",
            )

            if (
                target_warehouse
                and usual_warehouse
                and target_warehouse != usual_warehouse
            ):
                continue

            if not has_shift_capacity(
                courier,
                target_start,
                target_end,
            ):
                continue

            reason = (
                "szabadnapos"
                if not courier.get("shifts")
                else "nincs ütköző műszak"
            )

            candidates_by_name[normalize_name(name)] = {
                "Név": name,
                "Telefon": contact.get("phone", ""),
                "Raktár": usual_warehouse,
                "Ok": reason,
            }

        for driver in drivers_data.get("drivers", []):
            personal_info = driver.get(
                "personal_info",
                {},
            )
            name = str(
                personal_info.get("name", "")
            ).strip()
            normalized = normalize_name(
                name
            )

            if (
                not name
                or normalized in attendance_names
                or normalized == normalize_name(selected.get("name"))
                or normalized in candidates_by_name
            ):
                continue

            usual_warehouse = personal_info.get(
                "warehouse_name",
                "",
            )

            if (
                target_warehouse
                and usual_warehouse
                and target_warehouse != usual_warehouse
            ):
                continue

            candidates_by_name[normalized] = {
                "Név": name,
                "Telefon": personal_info.get("contact_number", ""),
                "Raktár": usual_warehouse,
                "Ok": "szabadnapos",
            }

    return sorted(
        candidates_by_name.values(),
        key=lambda row: normalize_name(row["Név"]),
    )


def render_replacement_search(rows, attendance_data):
    st.subheader(
        "Műszak pótlás keresése"
    )

    option_by_label = {
        (
            f"{row.get('name', '')} | "
            f"{row.get('warehouse', '')} | "
            f"{row.get('start', '')}-{row.get('end', '')}"
        ): row
        for row in rows
    }

    selected_labels = st.multiselect(
        "Melyik műszakra keressünk pótlást?",
        options=list(option_by_label.keys()),
        key="replacement_shift_selector",
    )
    selected_rows = [
        option_by_label[label]
        for label in selected_labels
    ]

    if not selected_rows:
        st.info(
            "Válassz ki egy vagy több műszakot a kereséshez."
        )
        return

    st.caption(
        f"Kijelölt műszakok: {len(selected_rows)}"
    )

    if st.button(
        "Keresés",
        use_container_width=True,
    ):
        with st.spinner(
            "Pótlás keresése..."
        ):
            drivers_data = load_drivers()
            candidates = find_replacement_candidates(
                selected_rows,
                attendance_data,
                drivers_data,
            )
        st.session_state["replacement_candidates"] = candidates
        st.session_state["replacement_search_done"] = True

    candidates = st.session_state.get(
        "replacement_candidates",
        [],
    )

    if candidates:
        st.dataframe(
            candidates,
            use_container_width=True,
            hide_index=True,
        )
    elif st.session_state.get("replacement_search_done"):
        st.warning(
            "Nem találtam olyan futárt, aki raktár és műszakütközés alapján alkalmas lenne."
        )


def show_today_shifts_page():
    st.title("Mai műszakok")

    selected_date = st.date_input(
        "Dátum",
        value=local_now().date(),
        key="today_shifts_date",
    )
    work_date_text = selected_date.strftime(
        "%Y-%m-%d"
    )

    if st.button(
        "Műszak ellenőrzés újraépítése",
        use_container_width=True,
    ):
        with st.spinner(
            "Giriton és MűszakPro ellenőrzés frissítése..."
        ):
            rebuild_shift_reconciliation(
                start_date=selected_date,
                days=10,
            )
            load_shift_sheet_data.clear()
        st.success(
            "Műszak ellenőrzés frissítve."
        )

    vehicle_data = load_vehicle_assignments()
    attendance_data = load_attendance_for_date(
        work_date_text
    )
    drivers_data = load_drivers()

    try:
        (
            giriton_records,
            foglalas_records,
            email_name_lookup,
            giriton_lookup,
            foglalas_lookup,
        ) = load_shift_sheet_data(
            work_date_text
        )
    except Exception as exc:
        giriton_records = []
        foglalas_records = []
        email_name_lookup = {}
        giriton_lookup = {}
        foglalas_lookup = {}
        st.warning(
            f"MűszakPro/Giriton Google Sheet olvasás sikertelen: {exc}"
        )

    assignments = get_assignments_for_date(
        vehicle_data,
        work_date_text,
    )

    if not assignments:
        st.warning(
            "Erre a napra nincs vehicle assignment adat, a lista Giriton/MűszakPro alapján épül."
        )

    rows = build_rows(
        assignments,
        attendance_data,
        drivers_data,
        selected_date,
        giriton_records,
        foglalas_records,
        email_name_lookup,
        giriton_lookup,
        foglalas_lookup,
    )

    stats = calculate_shift_statistics(
        rows
    )

    top1, top2, top3, top4, top5, top6 = st.columns(6)
    top1.metric(
        "Összes műszak",
        stats["total"],
    )
    top2.metric(
        "Feltöltve",
        stats["uploaded"],
    )
    top3.metric(
        "Feltöltöttség",
        f"{stats['percent']}%",
    )
    top4.metric(
        "MűszakPro",
        stats["muszakpro"],
    )
    top5.metric(
        "Bejelentkezett",
        stats["checked_in"],
    )
    top6.metric(
        "Bejel. arány",
        f"{stats['checked_in_percent']}%",
    )

    st.caption(
        f"E-mail jelzés: {stats['email_sent']}"
    )
    st.caption(
        "Feltöltve = Giritonban megtalált műszakok száma az összes mai műszakhoz képest."
    )

    st.caption(
        "Forrás: vehicle assignments + attendance. A Giriton robot és a valós e-mail küldés következő körben köthető rá."
    )

    render_missing_source_alerts(
        rows
    )

    if st.button(
        "Nap végi log mentése",
        use_container_width=True,
    ):
        try:
            written_rows = write_today_shift_log(
                work_date_text,
                rows,
            )
            st.success(
                f"Nap végi log mentve: {written_rows} sor."
            )
        except Exception as exc:
            st.error(
                f"Nap végi log mentése sikertelen: {exc}"
            )

    render_replacement_search(
        rows,
        attendance_data,
    )

    render_shift_table(
        rows
    )
