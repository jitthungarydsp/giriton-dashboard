import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from resources.alert_log_sheet import write_alert_logs
from resources.api import (
    load_attendance,
    load_driver_details,
    load_drivers,
)
from resources.route_statistics_sheet import write_route_statistics
from resources.users import load_users


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def local_now():
    return datetime.now(
        LOCAL_TIMEZONE
    ).replace(tzinfo=None)


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current in [None, ""]:
            return default

    return current


def first_nested_value(data, paths, default=""):
    for path in paths:
        value = nested_get(
            data,
            path,
            None,
        )

        if value not in [None, ""]:
            return value

    return default


def parse_datetime(value):
    if value in [None, ""]:
        return None

    value = str(value).strip()

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo:
            parsed = parsed.astimezone(
                LOCAL_TIMEZONE
            ).replace(tzinfo=None)

        return parsed
    except ValueError:
        pass

    for date_format in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]:
        try:
            parsed = datetime.strptime(
                value,
                date_format,
            )

            if parsed.year == 1900:
                now = local_now()
                parsed = parsed.replace(
                    year=now.year,
                    month=now.month,
                    day=now.day,
                )

            return parsed
        except ValueError:
            pass

    return None


def format_time(value):
    parsed = parse_datetime(
        value
    )

    if parsed:
        return parsed.strftime("%H:%M")

    return value or ""


def format_datetime_display(value):
    parsed = parse_datetime(
        value
    )

    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M")

    return value or "-"


def format_time_window(start, end):
    start_text = format_time(
        start
    )
    end_text = format_time(
        end
    )

    if start_text and end_text:
        return f"{start_text} - {end_text}"

    return start_text or end_text or "-"


def minutes_until(value):
    parsed = parse_datetime(
        value
    )

    if not parsed:
        return None

    return int(
        (
            parsed - local_now()
        ).total_seconds() // 60
    )


def get_visible_drivers(user, drivers):
    if user["role"] == "admin":
        return drivers

    if user["role"] == "trainer":
        users_data = load_users()
        trainer_courier_ids = {
            str(portal_user.get("courierId"))
            for portal_user in users_data["users"]
            if portal_user.get("trainer") == user["username"]
        }

        return [
            driver
            for driver in drivers
            if str(driver.get("driver_id")) in trainer_courier_ids
        ]

    return [
        driver
        for driver in drivers
        if str(driver.get("driver_id")) == str(user.get("courierId"))
    ]


def get_attendance_by_courier_id(couriers):
    return {
        str(courier.get("courierId")): courier
        for courier in couriers
        if courier.get("courierId") is not None
    }


def get_matching_shift(driver, attendance_courier):
    if not attendance_courier:
        return {}

    shifts = attendance_courier.get(
        "shifts",
        [],
    )
    current_shift_start = nested_get(
        driver,
        ["current_shift", "start"],
        "",
    )
    current_shift_end = nested_get(
        driver,
        ["current_shift", "end"],
        "",
    )

    for shift in shifts:
        if (
            shift.get("shiftStart") == current_shift_start
            and
            shift.get("shiftEnd") == current_shift_end
        ):
            return shift

    now = local_now()

    for shift in shifts:
        shift_start = parse_datetime(
            shift.get("shiftStart")
        )
        shift_end = parse_datetime(
            shift.get("shiftEnd")
        )

        if shift_start and shift_end and shift_start <= now <= shift_end:
            return shift

    available_shifts = [
        shift
        for shift in shifts
        if shift.get("availableForShiftSince")
    ]

    if available_shifts:
        return available_shifts[-1]

    if shifts:
        return shifts[0]

    return {}


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def get_route_id(driver):
    return first_nested_value(
        driver,
        [
            ["route", "id"],
            ["route", "route_id"],
            ["route", "routeId"],
            ["route_id"],
            ["routeId"],
            ["status", "route_id"],
            ["status", "routeId"],
        ],
    )


def get_route_assigned_raw(driver):
    return first_nested_value(
        driver,
        [
            ["status", "assignedAt"],
            ["status", "assigned_at"],
            ["route", "assignedAt"],
            ["route", "assigned_at"],
            ["route", "route_assigned_at"],
            ["route_assigned_at"],
            ["status", "loading_finished_at"],
        ],
    )


def get_route_detail_for_driver(driver):
    try:
        return load_driver_details(
            driver.get("driver_id")
        )
    except Exception:
        return {}


def parse_sortable_datetime(value):
    parsed = parse_datetime(
        value
    )

    if parsed:
        return parsed

    return datetime.min


def get_matching_route_from_detail(driver, driver_detail):
    routes = driver_detail.get(
        "routes",
        [],
    )

    if not routes:
        return {}

    assigned_at = get_route_assigned_raw(
        driver
    )

    if assigned_at:
        for route in routes:
            if route.get("assignedAt") == assigned_at:
                return route

    open_routes = [
        route
        for route in routes
        if not route.get("realReturn")
    ]

    if open_routes:
        return sorted(
            open_routes,
            key=lambda route: parse_sortable_datetime(
                route.get("assignedAt")
            ),
        )[-1]

    return sorted(
        routes,
        key=lambda route: parse_sortable_datetime(
            route.get("assignedAt")
        ),
    )[-1]


def get_route_sort_datetime(route):
    candidates = [
        route.get("realDeparture"),
        route.get("plannedDeparture"),
        route.get("assignedAt"),
        route.get("plannedReturn"),
        route.get("realReturn"),
    ]

    parsed_candidates = [
        parse_sortable_datetime(value)
        for value in candidates
        if value
    ]

    if not parsed_candidates:
        return datetime.min

    return max(parsed_candidates)


def sort_routes_latest_first(routes):
    return sorted(
        routes,
        key=get_route_sort_datetime,
        reverse=True,
    )


def get_route_id_for_driver(driver, driver_detail=None):
    route_id = get_route_id(
        driver
    )

    if route_id:
        return route_id

    if not driver_detail:
        return ""

    route = get_matching_route_from_detail(
        driver,
        driver_detail,
    )

    return route.get(
        "id",
        "",
    )


def get_delivery_count(driver):
    value = first_nested_value(
        driver,
        [
            ["route", "statistics", "parcels_delivered"],
            ["route", "statistics", "parcels_total"],
            ["status", "deliveries_completed"],
            ["numDeliveredOrders"],
            ["route", "numDeliveredOrders"],
        ],
        "",
    )

    return value


def get_order_count(driver):
    return first_nested_value(
        driver,
        [
            ["orders_in_route"],
            ["route", "orders_in_route"],
            ["route", "statistics", "parcels_total"],
            ["route", "numTotalOrders"],
            ["numTotalOrders"],
            ["status", "orders_in_route"],
        ],
        "",
    )


def get_route_assigned_at(driver):
    return format_time(
        get_route_assigned_raw(driver)
    )


def get_departure_time(driver):
    return format_time(
        first_nested_value(
            driver,
            [
                ["status", "warehouse_departure_real"],
                ["status", "realDeparture"],
                ["route", "realDeparture"],
            ],
        )
    )


def get_planned_departure_time(driver):
    return format_time(
        first_nested_value(
            driver,
            [
                ["status", "plannedDeparture"],
                ["status", "planned_departure"],
                ["status", "warehouse_departure_planned"],
                ["route", "plannedDeparture"],
                ["route", "planned_departure"],
                ["current_shift", "planned_departure"],
            ],
        )
    )


def get_shift_status(driver, shift):
    delay = as_int(
        nested_get(
            driver,
            ["status", "delay_minutes"],
            0,
        )
    )
    current_state = nested_get(
        driver,
        ["status", "current_state"],
        "",
    )
    shift_start = shift.get(
        "shiftStart",
        nested_get(
            driver,
            ["current_shift", "start"],
            "",
        ),
    )
    minutes_to_start = minutes_until(
        shift_start
    )

    if delay > 0:
        return "Late", "danger"

    if current_state in ["Delivering", "Idle"]:
        return "On time", "ok"

    if minutes_to_start is not None and minutes_to_start > 0:
        return "Before shift", "warn"

    return "On time", "ok"


def get_driver_status(driver):
    active = driver.get(
        "active",
        False,
    )
    current_state = nested_get(
        driver,
        ["status", "current_state"],
        "",
    )

    if not active:
        return "Off Duty", "muted"

    if current_state == "Delivering":
        return "Delivering", "ok"

    if current_state == "Idle":
        return "Waiting", "warn"

    return current_state or "Unknown", "muted"


def get_false_departure_report(driver):
    value = first_nested_value(
        driver,
        [
            ["status", "false_departure_report"],
            ["false_departure_report"],
            ["status", "is_false_departure_report"],
        ],
        "",
    )

    if value in [True, "true", "True", 1, "1"]:
        return "Yes"

    return "—"


def build_alert_records(drivers):
    work_date = local_now().strftime("%Y-%m-%d")
    records = []

    for driver in drivers:
        driver_id = driver.get("driver_id", "")
        driver_name = nested_get(
            driver,
            ["personal_info", "name"],
        )
        route_id = get_route_id(driver)

        warehouse = nested_get(
            driver,
            ["personal_info", "warehouse_name"],
        )
        license_plate = nested_get(
            driver,
            ["vehicle", "license_plate"],
        )
        status = nested_get(
            driver,
            ["status", "current_state"],
        )
        delay = as_int(
            nested_get(
                driver,
                ["status", "delay_minutes"],
                0,
            )
        )
        temperature = nested_get(
            driver,
            ["vehicle", "temperature"],
            "",
        )
        is_departure_delayed = nested_get(
            driver,
            ["status", "is_departure_delayed"],
            False,
        )
        false_report = get_false_departure_report(
            driver
        )

        base = {
            "work_date": work_date,
            "driver_id": driver_id,
            "driver_name": driver_name,
            "route_id": route_id,
            "status": status,
            "warehouse": warehouse,
            "license_plate": license_plate,
        }

        if delay > 0:
            records.append({
                **base,
                "issue_type": "delay",
                "issue": "Késés",
                "value": f"+{delay} perc",
            })

        try:
            temperature_value = float(temperature)
        except (TypeError, ValueError):
            temperature_value = None

        if temperature_value is not None and temperature_value > 10:
            records.append({
                **base,
                "issue_type": "temperature",
                "issue": "Huto 10 fok felett",
                "value": f"{temperature_value:g} °C",
            })

        if is_departure_delayed in [True, "true", "True", 1, "1"]:
            records.append({
                **base,
                "issue_type": "departure_delay",
                "issue": "Indulási késés",
                "value": get_departure_time(driver),
            })

        if false_report == "Yes":
            records.append({
                **base,
                "issue_type": "false_departure_report",
                "issue": "False departure report",
                "value": "Yes",
            })

    return records


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


def render_table_styles():
    st.markdown(
        """
<style>
.courier-table-header {
    align-items: center;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 8px 8px 0 0;
    color: #475569;
    display: flex;
    font-size: 12px;
    font-weight: 700;
    min-width: 1540px;
    padding: 10px 12px;
}
.courier-row-wrap {
    border: 1px solid #e5e7eb;
    border-top: 0;
    background: #ffffff;
    min-width: 1540px;
    padding: 6px 12px;
}
.courier-row-wrap:hover {
    background: #f8fafc;
}
.courier-table-scroll {
    overflow-x: auto;
    width: 100%;
}
.courier-cell {
    color: #0f172a;
    font-size: 13px;
    overflow-wrap: anywhere;
}
.courier-head-cell {
    color: #475569;
    font-size: 12px;
    font-weight: 700;
}
.status-pill {
    border-radius: 999px;
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    line-height: 1;
    padding: 7px 11px;
    white-space: nowrap;
}
.pill-ok {
    background: #dcfce7;
    color: #166534;
}
.pill-warn {
    background: #fef3c7;
    color: #92400e;
}
.pill-danger {
    background: #fee2e2;
    color: #b91c1c;
}
.pill-muted {
    background: #f1f5f9;
    color: #0f172a;
}
.id-link {
    color: #1d4ed8;
    font-weight: 700;
}
div[data-testid="stButton"] > button {
    padding: 0.25rem 0.55rem;
    min-height: 2rem;
}
div[data-testid="stDialog"] div[role="dialog"],
div[data-testid="stModal"] div[role="dialog"] {
    max-height: 92vh;
    max-width: 96vw;
    overflow-y: auto;
    width: min(96vw, 1600px);
}
div[data-testid="stDialog"] div[role="dialog"] > div,
div[data-testid="stModal"] div[role="dialog"] > div {
    max-height: calc(92vh - 24px);
    overflow-y: auto;
}
div[data-testid="stDialog"] .stDataFrame,
div[data-testid="stModal"] .stDataFrame {
    max-height: 58vh;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_cell(value, css_class="courier-cell"):
    st.markdown(
        f'<div class="{css_class}">{value}</div>',
        unsafe_allow_html=True,
    )


def render_table(rows):
    render_table_styles()

    headers = [
        "Courier ID",
        "Name",
        "Warehouse",
        "Status",
        "Delay",
        "Route ID",
        "Rákerült",
        "Deliveries",
        "Vehicle",
        "License",
        "Tervezett",
        "Indulás",
        "Shift start",
        "Shift",
        "Temp",
        "Last temp",
        "False dep.",
    ]
    column_widths = [
        0.8,
        1.7,
        0.8,
        1.0,
        0.7,
        1.0,
        0.9,
        0.8,
        0.8,
        1.0,
        0.9,
        0.8,
        0.9,
        1.0,
        0.8,
        0.9,
        0.9,
    ]

    st.markdown('<div class="courier-table-scroll">', unsafe_allow_html=True)

    header_columns = st.columns(column_widths)

    for column, header in zip(header_columns, headers):
        with column:
            render_cell(
                html.escape(header),
                "courier-head-cell",
            )

    for index, row in enumerate(rows):
        st.markdown('<div class="courier-row-wrap">', unsafe_allow_html=True)
        columns = st.columns(column_widths)

        with columns[0]:
            render_cell(
                f'<span class="id-link">#{html.escape(str(row.get("Courier ID", "")))}</span>'
            )
        with columns[1]:
            render_cell(
                html.escape(str(row.get("Name", "")))
            )
        with columns[2]:
            render_cell(
                html.escape(str(row.get("Warehouse", "")))
            )
        with columns[3]:
            render_cell(
                pill(
                    row.get("Status", ""),
                    row.get("_status_kind", "muted"),
                )
            )
        with columns[4]:
            if row.get("_delay_minutes", 0) > 0:
                render_cell(
                    pill(
                        f'+{row.get("_delay_minutes")}',
                        "danger",
                    )
                )
            else:
                render_cell("—")
        with columns[5]:
            route_id = row.get(
                "Route ID",
                "",
            )
            driver_id = row.get(
                "_driver_id"
            )
            button_label = str(route_id or "Útvonal")

            if st.button(
                button_label,
                key=f"today_orders_{driver_id}_{index}",
                help="Route útvonal megnyitása. A route ID a felugró ablakban töltődik be.",
                use_container_width=True,
                disabled=not bool(driver_id),
            ):
                st.session_state["today_selected_route_driver_id"] = row.get(
                    "_driver_id"
                )
        with columns[6]:
            render_cell(
                html.escape(str(row.get("Rákerült", "")))
            )
        with columns[7]:
            render_cell(
                html.escape(str(row.get("Deliveries", "")))
            )
        with columns[8]:
            render_cell(
                html.escape(str(row.get("Vehicle Type", "")))
            )
        with columns[9]:
            render_cell(
                html.escape(str(row.get("License Plate", "")))
            )
        with columns[10]:
            render_cell(
                html.escape(str(row.get("Tervezett indulás", "")))
            )
        with columns[11]:
            render_cell(
                html.escape(str(row.get("Departure Time", "")))
            )
        with columns[12]:
            render_cell(
                html.escape(str(row.get("Current Shift Start", "")))
            )
        with columns[13]:
            render_cell(
                pill(
                    row.get("Current Shift Status", ""),
                    row.get("_shift_kind", "muted"),
                )
            )
        with columns[14]:
            if row.get("_temperature_alert"):
                render_cell(
                    pill(
                        row.get("Temperature", ""),
                        "danger",
                    )
                )
            else:
                render_cell(
                    html.escape(str(row.get("Temperature", "")))
                )
        with columns[15]:
            render_cell(
                html.escape(str(row.get("Last measurement timestamp", "")))
            )
        with columns[16]:
            render_cell(
                html.escape(str(row.get("False departure report", "")))
            )

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def build_checkpoint_rows(route):
    checkpoint_rows = []

    for checkpoint in route.get(
        "checkpoints",
        [],
    ):
        checkpoint_rows.append({
            "Poz": checkpoint.get("position"),
            "Cím": checkpoint.get("address"),
            "Időablak": format_time_window(
                checkpoint.get("deliverSince"),
                checkpoint.get("deliverTill"),
            ),
            "Tervezett": format_datetime_display(
                checkpoint.get("plannedArrivalTime")
            ),
            "Becsült": format_datetime_display(
                checkpoint.get("estimatedArrivalTime")
            ),
            "Valós": format_datetime_display(
                checkpoint.get("realArrivalTime")
            ),
        })

    return checkpoint_rows


def render_selected_route_details(selected_driver_id):
    try:
        driver_data = load_driver_details(
            selected_driver_id
        )
    except Exception as exc:
        st.warning(
            f"Útvonal betöltése sikertelen: {exc}"
        )
        return

    routes = driver_data.get(
        "routes",
        [],
    )

    if not routes:
        st.info(
            "Ehhez a futárhoz most nincs részletes route/checkpoint adat."
        )
        return

    routes = sort_routes_latest_first(
        routes
    )

    if st.button(
        "Útvonal bezárása",
        key="today_close_selected_route",
    ):
        st.session_state.pop(
            "today_selected_route_driver_id",
            None,
        )
        st.rerun()

    for index, route in enumerate(routes):
        statistics = route.get(
            "statistics",
            {},
        )

        with st.expander(
            f"Route {route.get('id', '')}",
            expanded=index == 0,
        ):
            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Összes rendelés",
                route.get(
                    "numTotalOrders",
                    statistics.get("parcels_total", 0),
                ),
            )
            c2.metric(
                "Kiszállított",
                route.get(
                    "numDeliveredOrders",
                    statistics.get("parcels_delivered", 0),
                ),
            )
            c3.metric(
                "Késő",
                route.get(
                    "numDelayedOrdersEstimate",
                    0,
                ),
            )
            c4.metric(
                "Route ID",
                route.get(
                    "id",
                    "",
                ),
            )

            st.markdown(
                f"""
**Tervezett indulás:** {format_datetime_display(route.get('plannedDeparture'))}

**Valós indulás:** {format_datetime_display(route.get('realDeparture'))}

**Tervezett vissza:** {format_datetime_display(route.get('plannedReturn'))}

**Valós vissza:** {format_datetime_display(route.get('realReturn'))}
"""
            )

            checkpoint_rows = build_checkpoint_rows(
                route
            )

            if checkpoint_rows:
                st.dataframe(
                    checkpoint_rows,
                    use_container_width=True,
                    hide_index=True,
                    height=560,
                )
            else:
                st.info(
                    "Ehhez a route-hoz nincs checkpoint lista."
                )


def show_selected_route_details():
    selected_driver_id = st.session_state.get(
        "today_selected_route_driver_id"
    )

    if not selected_driver_id:
        return

    if hasattr(st, "dialog"):
        @st.dialog(
            f"Route útvonal - futár #{selected_driver_id}",
            width="large",
        )
        def route_details_dialog():
            _, close_column = st.columns([8, 1])

            with close_column:
                if st.button(
                    "X",
                    key="today_close_selected_route_x",
                    use_container_width=True,
                ):
                    st.session_state.pop(
                        "today_selected_route_driver_id",
                        None,
                    )
                    st.rerun()

            render_selected_route_details(
                selected_driver_id
            )

        route_details_dialog()
        return

    st.divider()
    st.subheader(
        f"Route útvonal - futár #{selected_driver_id}"
    )
    render_selected_route_details(
        selected_driver_id
    )


def show_today_couriers_page():
    st.title("Mai futárok")

    user = st.session_state["user"]
    should_sync_sheets = st.session_state.pop(
        "manual_refresh_requested",
        False,
    )

    drivers_data = load_drivers()
    drivers = drivers_data.get(
        "drivers",
        [],
    )
    attendance_data = load_attendance()
    attendance_couriers = attendance_data.get(
        "couriers",
        [],
    )
    attendance_by_courier_id = get_attendance_by_courier_id(
        attendance_couriers
    )

    if not drivers:
        st.warning(
            "Ma nincs futár adat a fetch-drivers API válaszban."
        )
        return

    visible_drivers = get_visible_drivers(
        user,
        drivers,
    )

    if not visible_drivers:
        st.warning(
            "Nincs megjeleníthető futár."
        )
        return

    rows = []

    for driver in visible_drivers:
        attendance_courier = attendance_by_courier_id.get(
            str(driver.get("driver_id"))
        )
        attendance_shift = get_matching_shift(
            driver,
            attendance_courier,
        )
        status_label, status_kind = get_driver_status(
            driver
        )
        shift_status, shift_kind = get_shift_status(
            driver,
            attendance_shift,
        )
        delay_minutes = as_int(
            nested_get(
                driver,
                ["status", "delay_minutes"],
                0,
            )
        )
        temperature = nested_get(
            driver,
            ["vehicle", "temperature"],
            "",
        )

        try:
            temperature_value = float(temperature)
            temperature_alert = temperature_value > 10
            temperature_label = f"{temperature_value:g}°C"
        except (TypeError, ValueError):
            temperature_alert = False
            temperature_label = "Unknown"

        rows.append({
            "_driver_id": driver.get("driver_id", ""),
            "Courier ID": driver.get("driver_id", ""),
            "Name": nested_get(
                driver,
                ["personal_info", "name"],
            ),
            "Warehouse": nested_get(
                driver,
                ["personal_info", "warehouse_name"],
            ),
            "Status": status_label,
            "Delay": "—" if delay_minutes <= 0 else f"+{delay_minutes}",
            "Route ID": get_route_id(driver),
            "Rákerült": get_route_assigned_at(
                driver
            ),
            "Deliveries": get_delivery_count(
                driver
            ),
            "Vehicle Type": nested_get(
                driver,
                ["vehicle", "type"],
            ),
            "License Plate": nested_get(
                driver,
                ["vehicle", "license_plate"],
            ),
            "Tervezett indulás": get_planned_departure_time(
                driver
            ),
            "Departure Time": get_departure_time(
                driver
            ),
            "Current Shift Start": format_time(
                attendance_shift.get(
                    "shiftStart",
                    nested_get(
                        driver,
                        ["current_shift", "start"],
                    ),
                )
            ),
            "Current Shift Status": shift_status,
            "Temperature": temperature_label,
            "Last measurement timestamp": format_time(
                nested_get(
                    driver,
                    ["vehicle", "last_measurement_timestamp"],
                )
            ),
            "False departure report": get_false_departure_report(
                driver
            ),
            "_status_kind": status_kind,
            "_shift_kind": shift_kind,
            "_delay_minutes": delay_minutes,
            "_temperature_alert": temperature_alert,
        })

    render_table(
        rows
    )

    show_selected_route_details()

    if should_sync_sheets:
        try:
            write_route_statistics(
                drivers
            )
        except Exception as exc:
            st.warning(
                f"Route statisztika Google Sheet frissítés sikertelen: {exc}"
            )

        alert_records = build_alert_records(
            drivers
        )

        try:
            write_alert_logs(
                alert_records
            )
        except Exception as exc:
            st.warning(
                f"Riasztás log Google Sheet frissítés sikertelen: {exc}"
            )

    st.caption(
        "Adatforrás: fetch-drivers + fetch-attendance. A Google Sheet frissítés a Frissítés gombbal fut."
    )
