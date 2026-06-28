import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from resources.api import (
    load_attendance,
    load_departure_dashboard,
)
from resources.users import load_users
from resources.waiting_courier_log_sheet import sync_waiting_courier_log


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
WAREHOUSE_NAMES = {
    1: "BUD1",
    2: "BUD2",
    "1": "BUD1",
    "2": "BUD2",
}


def local_now():
    return datetime.now(
        LOCAL_TIMEZONE
    ).replace(tzinfo=None)


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


def format_time(value):
    parsed = parse_datetime(
        value
    )

    if parsed:
        return parsed.strftime("%H:%M")

    return ""


def minutes_since(value):
    parsed = parse_datetime(
        value
    )

    if not parsed:
        return ""

    return max(
        int(
            (
                local_now() - parsed
            ).total_seconds() // 60
        ),
        0,
    )


def get_visible_couriers(user, couriers):
    if user["role"] == "admin":
        return couriers

    if user["role"] == "trainer":
        users_data = load_users()
        trainer_courier_ids = {
            str(portal_user.get("courierId"))
            for portal_user in users_data["users"]
            if portal_user.get("trainer") == user["username"]
        }

        return [
            courier
            for courier in couriers
            if str(courier.get("courier_id")) in trainer_courier_ids
        ]

    return [
        courier
        for courier in couriers
        if str(courier.get("courier_id")) == str(user.get("courierId"))
    ]


def get_attendance_by_courier_id(couriers):
    return {
        str(courier.get("courierId")): courier
        for courier in couriers
        if courier.get("courierId") is not None
    }


def get_waiting_shift(attendance_courier):
    if not attendance_courier:
        return {}

    shifts = attendance_courier.get(
        "shifts",
        [],
    )
    available_shifts = []

    for shift in shifts:
        available_since = shift.get(
            "availableForShiftSince"
        )
        parsed_available_since = parse_datetime(
            available_since
        )

        if parsed_available_since:
            available_shifts.append(
                (
                    parsed_available_since,
                    shift,
                )
            )

    if not available_shifts:
        return {}

    available_shifts.sort(
        key=lambda item: item[0]
    )

    return available_shifts[-1][1]


def get_waiting_since(attendance_courier):
    waiting_shift = get_waiting_shift(
        attendance_courier
    )

    return waiting_shift.get(
        "availableForShiftSince",
        "",
    )


def get_temperature(courier):
    temperature = courier.get(
        "temperature"
    )

    if not isinstance(temperature, dict):
        return "", ""

    return (
        temperature.get("temperature", ""),
        temperature.get("last_measurement_timestamp", ""),
    )


def temperature_kind(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "danger"

    if value < 0 or value > 5:
        return "danger"

    return "ok"


def build_waiting_record(courier, attendance_courier):
    temperature, measurement_time = get_temperature(
        courier
    )
    waiting_shift = get_waiting_shift(
        attendance_courier
    )
    waiting_since = get_waiting_since(
        attendance_courier
    )
    temperature_block = courier.get(
        "temperature_block"
    )
    warehouse_id = courier.get(
        "warehouse_id",
        "",
    )
    warehouse = WAREHOUSE_NAMES.get(
        warehouse_id,
        f"Raktar {warehouse_id}" if warehouse_id else "",
    )

    return {
        "work_date": local_now().strftime("%Y-%m-%d"),
        "driver_id": courier.get("courier_id", ""),
        "driver_name": courier.get("courier_name", ""),
        "warehouse": warehouse,
        "shift_id": waiting_shift.get("shiftId", ""),
        "shift_name": waiting_shift.get("shiftName", ""),
        "waiting_since": waiting_since,
        "waiting_since_local": format_time(waiting_since),
        "waiting_minutes": minutes_since(waiting_since),
        "temperature": temperature,
        "last_measurement": format_time(measurement_time),
        "temperature_block": temperature_block or "",
        "status": "active",
    }


def pill(value, kind="muted"):
    classes = {
        "ok": "pill-ok",
        "warn": "pill-warn",
        "danger": "pill-danger",
        "muted": "pill-muted",
    }
    css_class = classes.get(
        kind,
        "pill-muted",
    )

    return f'<span class="status-pill {css_class}">{html.escape(str(value))}</span>'


def render_table(rows):
    headers = [
        "Courier",
        "Courier ID",
        "Raktár",
        "Temperature in the queue",
        "Last measurement",
        "Courier blocked to join the queue due to temperature",
        "Shift ID",
        "Shift",
        "Várakozás kezdete",
        "Mióta vár",
    ]
    table_rows = []

    for row in rows:
        cells = []

        for header in headers:
            value = row.get(
                header,
                "",
            )

            if header == "Temperature in the queue":
                value = pill(
                    value or "—",
                    row.get("_temperature_kind", "muted"),
                )
            elif header == "Courier ID":
                value = f'<span class="id-link">#{html.escape(str(value))}</span>'
            else:
                value = html.escape(
                    str(value)
                )

            cells.append(
                f"<td>{value}</td>"
            )

        table_rows.append(
            "<tr>" + "".join(cells) + "</tr>"
        )

    header_html = "".join(
        f"<th>{html.escape(header)}</th>"
        for header in headers
    )

    st.markdown(
        f"""
<style>
.waiting-table-wrap {{
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    overflow-x: auto;
    background: #ffffff;
}}
.waiting-table {{
    border-collapse: collapse;
    width: 100%;
    min-width: 1080px;
    font-size: 14px;
}}
.waiting-table th {{
    color: #475569;
    font-weight: 700;
    padding: 13px 16px;
    text-align: left;
    border-bottom: 1px solid #e5e7eb;
    background: #f8fafc;
}}
.waiting-table td {{
    padding: 14px 16px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: middle;
}}
.waiting-table tr:hover td {{
    background: #f8fafc;
}}
.status-pill {{
    border-radius: 999px;
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    line-height: 1;
    padding: 7px 12px;
    white-space: nowrap;
}}
.pill-ok {{
    background: #16a34a;
    color: #ffffff;
}}
.pill-danger {{
    background: #ef4444;
    color: #ffffff;
}}
.pill-muted {{
    background: #f1f5f9;
    color: #334155;
}}
.id-link {{
    color: #1d4ed8;
    font-weight: 700;
}}
</style>
<div class="waiting-table-wrap">
    <table class="waiting-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(table_rows)}</tbody>
    </table>
</div>
""",
        unsafe_allow_html=True,
    )


def show_waiting_couriers_page():
    st.title("Várakozó futárok")
    st.caption(
        "Forrás: departure-dashboard couriers_without_route. A várakozás kezdete az attendance availableForShiftSince mezőből egészül ki, ha elérhető."
    )

    user = st.session_state["user"]
    departure_data = load_departure_dashboard()
    attendance_data = load_attendance()
    attendance_by_courier_id = get_attendance_by_courier_id(
        attendance_data.get(
            "couriers",
            [],
        )
    )
    couriers = departure_data.get(
        "couriers_without_route",
        [],
    )
    waiting_records = []

    for courier in couriers:
        attendance_courier = attendance_by_courier_id.get(
            str(courier.get("courier_id"))
        )
        waiting_records.append(
            build_waiting_record(
                courier,
                attendance_courier,
            )
        )

    try:
        sync_waiting_courier_log(
            waiting_records
        )
    except Exception as exc:
        st.warning(
            f"VĂˇrakozĂˇsi log Google Sheet frissĂ­tĂ©s sikertelen: {exc}"
        )

    visible_couriers = get_visible_couriers(
        user,
        couriers,
    )

    if not visible_couriers:
        st.info(
            "Most nincs várakozó, még route nélküli futár."
        )
        return

    rows = []

    for courier in visible_couriers:
        temperature, measurement_time = get_temperature(
            courier
        )
        attendance_courier = attendance_by_courier_id.get(
            str(courier.get("courier_id"))
        )
        waiting_shift = get_waiting_shift(
            attendance_courier
        )
        waiting_since = get_waiting_since(
            attendance_courier
        )
        waiting_minutes = minutes_since(
            waiting_since
        )
        temperature_block = courier.get(
            "temperature_block"
        )
        warehouse_id = courier.get(
            "warehouse_id",
            "",
        )
        warehouse = WAREHOUSE_NAMES.get(
            warehouse_id,
            f"Raktár {warehouse_id}" if warehouse_id else "",
        )

        rows.append({
            "Courier": courier.get("courier_name", ""),
            "Courier ID": courier.get("courier_id", ""),
            "Raktár": warehouse,
            "Temperature in the queue": (
                f"{temperature}°C"
                if temperature not in [None, ""]
                else "—"
            ),
            "Last measurement": format_time(
                measurement_time
            ),
            "Courier blocked to join the queue due to temperature": (
                temperature_block or "—"
            ),
            "Shift ID": waiting_shift.get(
                "shiftId",
                "—",
            ),
            "Shift": waiting_shift.get(
                "shiftName",
                "—",
            ),
            "Várakozás kezdete": format_time(
                waiting_since
            ),
            "Mióta vár": (
                f"{waiting_minutes} perc"
                if waiting_minutes != ""
                else "—"
            ),
            "_temperature_kind": temperature_kind(
                temperature
            ),
        })

    top1, top2, top3 = st.columns(3)
    top1.metric(
        "Várakozó futárok",
        len(rows),
    )
    top2.metric(
        "Hőmérséklet riasztás",
        sum(
            1
            for row in rows
            if row["_temperature_kind"] == "danger"
        ),
    )
    top3.metric(
        "Raktárak",
        len({
            row["Raktár"]
            for row in rows
            if row["Raktár"]
        }),
    )

    render_table(
        rows
    )
