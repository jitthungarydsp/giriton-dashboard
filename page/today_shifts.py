from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from resources.api import (
    load_attendance_for_date,
    load_vehicle_assignments,
)
from resources.muszakpro_sheet import (
    build_foglalas_lookup,
    build_giriton_lookup,
    foglalas_key,
    read_foglalasok_records,
    read_giriton_records,
    record_key,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


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


def build_rows(
    assignments,
    attendance_data,
    work_date,
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

    for index, assignment in enumerate(assignments):
        name = assignment.get(
            "Driver",
            "",
        ).strip()
        start_at = parse_assignment_datetime(
            work_date,
            assignment.get("Start"),
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
                assignment.get("Start"),
            ),
            {},
        )
        foglalas_record = {}

        if giriton_record:
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
        email_key = (
            f"today_shift_email_{work_date.isoformat()}_"
            f"{name}_{assignment.get('Start')}"
        )

        rows.append({
            "name": name,
            "start": format_time(start_at),
            "end": str(assignment.get("End", ""))[:5],
            "muszakpro": ok_pill() if foglalas_record else "-",
            "giriton": ok_pill() if giriton_record else "-",
            "checkin": status_pill(state),
            "checkin_time": state["time"],
            "current_plate": assignment.get("License Plate", ""),
            "car_code": assignment.get("Car", ""),
            "suggested_plate": vehicle_suggestions.get(
                index,
                assignment.get("License Plate", ""),
            ),
            "email": giriton_record.get("email", ""),
            "email_sent": ok_pill() if st.session_state.get(email_key) else "-",
            "_email_key": email_key,
            "_start_at": start_at or datetime.max,
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
.shift-head {
    color: #475569;
    font-size: 12px;
    font-weight: 700;
}
.shift-cell {
    color: #0f172a;
    font-size: 13px;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_cell(value, css_class="shift-cell"):
    st.markdown(
        f"<div class='{css_class}'>{value}</div>",
        unsafe_allow_html=True,
    )


def render_table(rows):
    render_styles()

    headers = [
        "Név",
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

    header_cols = st.columns(
        widths
    )

    for col, header in zip(header_cols, headers):
        with col:
            render_cell(
                header,
                "shift-head",
            )

    st.divider()

    for index, row in enumerate(rows):
        cols = st.columns(
            widths
        )
        values = [
            row["name"],
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

        for col, value in zip(cols[:10], values):
            with col:
                render_cell(
                    value
                )

        with cols[10]:
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

        with cols[11]:
            render_cell(
                row["email_sent"]
            )

        st.divider()


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
        giriton_lookup = build_giriton_lookup(
            giriton_records
        )
        foglalas_lookup = build_foglalas_lookup(
            foglalas_records
        )
    except Exception as exc:
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
            "Erre a napra nincs vehicle assignment adat."
        )
        return

    rows = build_rows(
        assignments,
        attendance_data,
        selected_date,
        giriton_lookup,
        foglalas_lookup,
    )

    top1, top2, top3 = st.columns(3)
    top1.metric(
        "Műszakok",
        len(rows),
    )
    top2.metric(
        "Bejelentkezett",
        sum("Bejelentkezett" in row["checkin"] for row in rows),
    )
    top3.metric(
        "E-mail jelzés",
        sum(row["email_sent"] != "-" for row in rows),
    )

    st.caption(
        "Forrás: vehicle assignments + attendance. A Giriton robot és a valós e-mail küldés következő körben köthető rá."
    )

    render_table(
        rows
    )
