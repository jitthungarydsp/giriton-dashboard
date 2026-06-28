from datetime import datetime, time
from html import escape
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from resources.muszakpro_sheet import (
    build_foglalas_lookup,
    build_giriton_lookup,
    foglalas_key,
    read_giriton_email_name_lookup,
    read_foglalasok_records,
    read_giriton_records,
    record_key,
)
from resources.today_shift_log_sheet import write_today_shift_log


BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DEPOT_ID = "JIT"
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def request_json(url):
    try:
        response = requests.get(
            url,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
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

    if not shifts:
        return {}

    return min(
        shifts,
        key=lambda shift: abs(
            (
                parse_datetime(shift.get("shiftStart")) or start_at
            )
            - start_at
        ),
    )


def get_checkin_state(start_at, available_since):
    checkin_at = parse_datetime(
        available_since
    )

    if checkin_at and start_at and checkin_at <= start_at:
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


def merge_source(sources, key, updates):
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
    giriton_records,
    foglalas_records,
    email_name_lookup=None,
):
    sources = {}
    email_name_lookup = build_email_name_lookup(
        giriton_records,
        email_name_lookup,
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
                "start": start,
                "end": assignment.get("End", ""),
                "assignment": assignment,
                "assignment_index": index,
            },
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
                "start": record.get("start"),
                "warehouse": record.get("warehouse"),
                "email": record.get("email"),
                "foglalas_record": record,
            },
        )

    return list(
        sources.values()
    )


def build_rows(
    assignments,
    attendance_data,
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
    rows = []
    vehicle_suggestions = build_vehicle_suggestions(
        assignments,
        work_date,
    )
    shift_sources = build_shift_sources(
        assignments,
        giriton_records,
        foglalas_records,
        email_name_lookup,
    )

    for index, source in enumerate(shift_sources):
        name = source.get(
            "name",
            "",
        ).strip()
        start_at = parse_assignment_datetime(
            work_date,
            source.get("start"),
        )
        courier = attendance_lookup.get(
            normalize_name(name)
        )
        shift = find_matching_shift(
            courier,
            start_at,
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

        state = get_checkin_state(
            start_at,
            shift.get("availableForShiftSince"),
        )
        has_muszakpro = bool(
            foglalas_record
        )
        has_giriton = bool(
            giriton_record
        )
        is_checked_in = state["label"] == "Bejelentkezett"
        email_key = (
            f"today_shift_email_{work_date.isoformat()}_"
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
            "muszakpro": ok_pill() if has_muszakpro else "-",
            "giriton": ok_pill() if has_giriton else "-",
            "checkin": status_pill(state),
            "checkin_time": state["time"],
            "current_plate": assignment.get("License Plate", ""),
            "car_code": assignment.get("Car", ""),
            "suggested_plate": vehicle_suggestions.get(
                assignment_index,
                assignment.get("License Plate", ""),
            ),
            "email": source.get("email", ""),
            "email_sent": ok_pill() if email_sent else "-",
            "_email_key": email_key,
            "_start_at": start_at or datetime.max,
            "_has_muszakpro": has_muszakpro,
            "_has_giriton": has_giriton,
            "_is_checked_in": is_checked_in,
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
    top: 0;
    z-index: 20;
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
}
.shift-cell-danger {
    color: #b91c1c;
    font-size: 13px;
    font-weight: 800;
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

        for value_index, (col, value) in enumerate(zip(cols[:11], values)):
            with col:
                render_cell(
                    value,
                    (
                        "shift-cell-danger"
                        if value_index == 0 and not row.get("_is_checked_in")
                        else "shift-cell"
                    ),
                )

        with cols[11]:
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

        with cols[12]:
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

    vehicle_data = load_vehicle_assignments()
    attendance_data = load_attendance_for_date(
        work_date_text
    )

    try:
        giriton_records = read_giriton_records(
            work_date_text
        )
        foglalas_records = read_foglalasok_records(
            work_date_text
        )
        email_name_lookup = read_giriton_email_name_lookup()
        giriton_lookup = build_giriton_lookup(
            giriton_records
        )
        foglalas_lookup = build_foglalas_lookup(
            foglalas_records
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

    render_table(
        rows
    )
