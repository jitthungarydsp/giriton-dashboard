from calendar import monthrange
from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from resources.dsp_dashboard_statistics import (
    build_statistics,
    normalize_id,
    read_sheet_dataframe,
)
from resources.api import (
    load_attendance,
    load_driver_details,
    load_drivers,
)
from resources.shift_reconciliation_sheet import (
    read_shift_reconciliation_records,
)

EXPRESS_MAX_FEE = 6516
NORMAL_CITY_MAX_FEE = 13000
DAILY_CACHE_SECONDS = 24 * 60 * 60
LIVE_CACHE_SECONDS = 60
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def format_number(value, decimals=1):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "0"


def format_percent(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def format_minutes(value):
    try:
        return f"{float(value):.1f} perc"
    except (TypeError, ValueError):
        return "0.0 perc"


def format_currency(value):
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        amount = 0

    return f"{amount:,} Ft".replace(",", " ")


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_courier_statistics(start_date, end_date, user):
    return build_statistics(
        start_date=start_date,
        end_date=end_date,
        user=user,
    )


def render_styles():
    st.markdown(
        """
<style>
.courier-hero {
    background: linear-gradient(135deg, #6cab2f 0%, #8bd346 45%, #f5fbea 100%);
    border-radius: 18px;
    color: #10240d;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(0, 1.8fr) minmax(220px, 0.9fr);
    margin-bottom: 18px;
    overflow: hidden;
    padding: 26px;
    position: relative;
}
.courier-hero h1 {
    font-size: 34px;
    line-height: 1.1;
    margin: 0 0 8px;
}
.courier-hero p {
    font-size: 16px;
    margin: 0;
    max-width: 720px;
}
.courier-plate {
    align-self: center;
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(16, 36, 13, 0.14);
    border-radius: 14px;
    box-shadow: 0 14px 30px rgba(36, 74, 20, 0.14);
    padding: 18px;
}
.courier-plate-label {
    color: #45603b;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
}
.courier-plate-value {
    color: #10240d;
    font-size: 30px;
    font-weight: 900;
    line-height: 1.2;
}
.stat-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: 12px 0 18px;
}
.stat-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
    padding: 16px;
}
.stat-label {
    color: #64748b;
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
}
.stat-value {
    color: #0f172a;
    font-size: 28px;
    font-weight: 900;
    line-height: 1.25;
    margin-top: 6px;
}
.stat-note {
    color: #64748b;
    font-size: 12px;
    margin-top: 5px;
}
.fun-note {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 14px;
    color: #7c2d12;
    font-weight: 700;
    margin: 8px 0 18px;
    padding: 14px 16px;
}
.today-shift-card {
    background: linear-gradient(135deg, #ecfccb 0%, #ffffff 65%);
    border: 1px solid #bbf7d0;
    border-radius: 16px;
    margin: 8px 0 18px;
    padding: 18px;
}
.today-shift-title {
    color: #166534;
    font-size: 18px;
    font-weight: 900;
    margin-bottom: 10px;
}
.today-shift-row {
    align-items: center;
    border-top: 1px solid rgba(34, 197, 94, 0.18);
    display: grid;
    gap: 10px;
    grid-template-columns: 1fr 1fr 1fr 1fr;
    padding: 10px 0;
}
.today-pill {
    border-radius: 999px;
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    padding: 6px 10px;
}
.today-ok {
    background: #dcfce7;
    color: #166534;
}
.today-missing {
    background: #fee2e2;
    color: #991b1b;
}
.route-road-card {
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
    margin: 10px 0 18px;
    padding: 18px;
}
.route-road-head {
    align-items: center;
    display: flex;
    gap: 12px;
    justify-content: space-between;
    margin-bottom: 18px;
}
.route-brand {
    align-items: center;
    display: flex;
    gap: 10px;
    font-weight: 900;
}
.route-brand-logo {
    align-items: center;
    background: #6cab2f;
    border-radius: 14px;
    color: #ffffff;
    display: inline-flex;
    font-size: 22px;
    height: 44px;
    justify-content: center;
    width: 44px;
}
.route-road-title {
    color: #0f172a;
    font-size: 18px;
    font-weight: 900;
}
.route-road-subtitle {
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
}
.route-road-track {
    align-items: center;
    display: grid;
    gap: 0;
    grid-template-columns: repeat(var(--stop-count), minmax(64px, 1fr)) 82px;
    min-height: 118px;
    overflow-x: auto;
    padding: 10px 0 4px;
    position: relative;
}
.route-road-track:before {
    background: linear-gradient(90deg, #cbd5e1 0%, #94a3b8 100%);
    border-radius: 999px;
    content: "";
    height: 8px;
    left: 32px;
    position: absolute;
    right: 44px;
    top: 48px;
}
.route-stop {
    min-width: 74px;
    position: relative;
    text-align: center;
    z-index: 1;
}
.route-stop-dot {
    align-items: center;
    border: 4px solid #ffffff;
    border-radius: 999px;
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
    color: #ffffff;
    display: inline-flex;
    font-size: 13px;
    font-weight: 900;
    height: 40px;
    justify-content: center;
    width: 40px;
}
.route-stop-current .route-stop-dot {
    background: #16a34a;
}
.route-stop-waiting .route-stop-dot {
    background: #facc15;
    color: #713f12;
}
.route-stop-label {
    color: #334155;
    font-size: 11px;
    font-weight: 800;
    line-height: 1.25;
    margin-top: 8px;
}
.route-depot {
    position: relative;
    text-align: center;
    z-index: 1;
}
.route-depot-icon {
    align-items: center;
    background: #0f172a;
    border: 4px solid #ffffff;
    border-radius: 16px;
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.20);
    color: #ffffff;
    display: inline-flex;
    font-size: 20px;
    height: 48px;
    justify-content: center;
    width: 48px;
}
.bag-alert-preview {
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
    border-radius: 14px;
    display: grid;
    gap: 12px;
    grid-template-columns: 1.2fr .8fr;
    margin-top: 14px;
    padding: 14px;
}
.bag-alert-title {
    color: #166534;
    font-size: 15px;
    font-weight: 900;
}
.bag-alert-copy {
    color: #334155;
    font-size: 13px;
    line-height: 1.45;
    margin-top: 4px;
}
.bag-alert-button {
    align-self: center;
    background: #16a34a;
    border-radius: 12px;
    color: #ffffff;
    font-weight: 900;
    padding: 12px 14px;
    text-align: center;
}
.route-empty-note {
    text-align: center;
}
.route-help-button {
    background: #16a34a;
    border-radius: 12px;
    color: #ffffff;
    display: inline-block;
    font-weight: 900;
    margin-top: 10px;
    padding: 12px 18px;
}
.route-stop-home .route-stop-dot {
    background: #ffffff;
    color: #166534;
}
.route-stop-alert .route-stop-dot {
    background: #f97316;
    color: #ffffff;
}
@media (max-width: 900px) {
    .courier-hero {
        grid-template-columns: 1fr;
    }
    .stat-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .bag-alert-preview {
        grid-template-columns: 1fr;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_hero(row, user):
    name = escape(str(row.get("name") or user.get("username") or "Kifli futár"))
    courier_id = escape(str(row.get("courier_id") or user.get("courierId") or "-"))
    warehouse = escape(str(row.get("warehouse") or "Kifli pálya"))

    st.markdown(
        f"""
<div class="courier-hero">
  <div>
    <div class="courier-plate-label">Kifli futar cockpit</div>
    <h1>Szia, {name}!</h1>
    <p>Itt van a saját teljesítmény-kártyád: címek, körök, normál és expressz arányok, várakozások és azok az apró számok, amikből a nap végén látszik, hogy ment a pálya.</p>
  </div>
  <div class="courier-plate">
    <div class="courier-plate-label">Futár azonosító</div>
    <div class="courier-plate-value">#{courier_id}</div>
    <div class="stat-note">Raktár: {warehouse}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def stat_card(label, value, note=""):
    return f"""
<div class="stat-card">
  <div class="stat-label">{label}</div>
  <div class="stat-value">{value}</div>
  <div class="stat-note">{note}</div>
</div>
"""


def normalize_name(value):
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def status_pill(value):
    value = str(value or "").strip()
    css_class = "today-ok" if value == "OK" else "today-missing"
    label = "OK" if value == "OK" else "Hiányzik"

    return f'<span class="today-pill {css_class}">{label}</span>'


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_today_shift_records(work_date_text):
    return read_shift_reconciliation_records(
        work_date_text
    )


def get_today_shift_rows(row, user, today):
    return get_shift_rows_for_date(row, user, today)


def get_shift_rows_for_date(row, user, work_date):
    work_date_text = work_date.isoformat()
    courier_name = normalize_name(row.get("name") or user.get("username"))
    records = load_today_shift_records(
        work_date_text
    )

    shifts = []

    for record in records:
        if normalize_name(record.get("name")) != courier_name:
            continue

        shifts.append(record)

    return sorted(
        shifts,
        key=lambda item: str(item.get("start", "")),
    )


def get_next_sheet_shift_rows(row, user, start_date, days=14):
    for offset in range(1, days + 1):
        work_date = start_date + timedelta(days=offset)
        shifts = get_shift_rows_for_date(row, user, work_date)

        if shifts:
            return work_date, shifts

    return None, []


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def parse_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return parsed.astimezone(LOCAL_TIMEZONE)


def format_time(value):
    parsed = parse_datetime(value) if isinstance(value, str) else value

    if not parsed:
        return ""

    return parsed.strftime("%H:%M")


@st.cache_data(show_spinner=False, ttl=LIVE_CACHE_SECONDS)
def load_live_courier_sources():
    return load_attendance(), load_drivers()


@st.cache_data(show_spinner=False, ttl=LIVE_CACHE_SECONDS)
def load_live_driver_detail(driver_id):
    if not driver_id:
        return {}

    return load_driver_details(driver_id)


def find_attendance_courier(attendance_data, courier_id):
    courier_id = normalize_id(courier_id)

    for courier in attendance_data.get("couriers", []):
        if normalize_id(courier.get("courierId")) == courier_id:
            return courier

    return {}


def find_driver(drivers_data, courier_id):
    courier_id = normalize_id(courier_id)

    for driver in drivers_data.get("drivers", []):
        if normalize_id(driver.get("driver_id")) == courier_id:
            return driver

    return {}


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def first_nested_value(data, paths, default=""):
    for path in paths:
        value = nested_get(data, path, "")

        if value not in ["", None]:
            return value

    return default


def get_driver_route_id(driver):
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


def get_driver_assigned_at(driver):
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


def get_live_driver_state(driver):
    return str(
        nested_get(
            driver,
            ["status", "current_state"],
            "",
        )
    )


def get_current_shift(attendance_courier):
    shifts = get_shift_items(attendance_courier)

    if not shifts:
        return {}

    now = local_now()

    for shift in shifts:
        end_at = shift.get("end_at")
        if end_at and end_at >= now - timedelta(minutes=15):
            return shift

    return {}


def get_shift_items(attendance_courier):
    shifts = []

    for shift in attendance_courier.get("shifts", []):
        start_at = parse_datetime(shift.get("shiftStart"))
        end_at = parse_datetime(shift.get("shiftEnd"))

        if not start_at:
            continue

        shifts.append(
            {
                "raw": shift,
                "start_at": start_at,
                "end_at": end_at,
            }
        )

    return sorted(shifts, key=lambda item: item["start_at"])


def get_next_shift(attendance_courier):
    now = local_now()

    for shift in get_shift_items(attendance_courier):
        end_at = shift.get("end_at")
        if end_at and end_at >= now - timedelta(minutes=15):
            return shift

    return {}


def get_future_shift(attendance_courier):
    now = local_now()

    for shift in get_shift_items(attendance_courier):
        start_at = shift.get("start_at")
        if start_at and start_at > now:
            return shift

    return {}


def get_best_route(driver, driver_detail):
    routes = driver_detail.get("routes", [])

    if not routes:
        return {}

    driver_route_id = normalize_id(get_driver_route_id(driver))
    if driver_route_id:
        for route in routes:
            if normalize_id(route.get("id") or route.get("routeId")) == driver_route_id:
                return route

    assigned_at = get_driver_assigned_at(driver)
    if assigned_at:
        for route in routes:
            if route.get("assignedAt") == assigned_at:
                return route

    open_routes = [
        route
        for route in routes
        if not route.get("realReturn")
    ]

    candidates = open_routes or routes

    return sorted(
        candidates,
        key=lambda route: parse_datetime(route.get("assignedAt")) or datetime.min.replace(tzinfo=LOCAL_TIMEZONE),
    )[-1]


def render_today_shifts(row, user):
    today = date.today()
    _next_shift_date = None
    shifts = get_today_shift_rows(
        row,
        user,
        today,
    )

    if not shifts:
        _next_shift_date, shifts = get_next_sheet_shift_rows(
            row,
            user,
            today,
        )

    if shifts:
        rows_html = []

        for shift in shifts:
            rows_html.append(
                f"""
<div class="today-shift-row">
  <div><strong>{escape(str(shift.get("start", "")))}</strong> - {escape(str(shift.get("end", "")))}</div>
  <div>{escape(str(shift.get("warehouse", "")))}</div>
  <div>Giriton: {status_pill(shift.get("giriton"))}</div>
  <div>MűszakPro: {status_pill(shift.get("muszakpro"))}</div>
</div>
"""
            )

        body = "".join(rows_html)
        title = "Ma dolgozol"
        if _next_shift_date:
            title = "Kovetkezo muszakod"
        note = "A mai műszakod a feltöltött Giriton és MűszakPro adatok alapján."
    else:
        body = """
<div class="today-shift-row">
  <div><strong>Nincs mai műszak</strong></div>
  <div>-</div>
  <div>Giriton: <span class="today-pill today-missing">Nincs adat</span></div>
  <div>MűszakPro: <span class="today-pill today-missing">Nincs adat</span></div>
</div>
"""
        title = "Ma nem látok műszakot"
        note = "Ha mégis dolgozol, akkor valószínűleg a robot frissítése vagy a feltöltés hiányzik."

    st.markdown(
        f"""
<div class="today-shift-card">
  <div class="today-shift-title">{title}</div>
  <div class="stat-note">{note}</div>
  {body}
</div>
""",
        unsafe_allow_html=True,
    )


def get_route_road_stops(row, details):
    customers = details.get("customers", pd.DataFrame())
    courier_id = normalize_id(row.get("courier_id"))

    if customers.empty or not courier_id or "courierId" not in customers.columns:
        return []

    customers = customers.copy()
    customers = customers[
        customers["courierId"].apply(normalize_id) == courier_id
    ]

    if customers.empty:
        return []

    if "date" in customers.columns:
        customers["date_dt"] = pd.to_datetime(
            customers["date"],
            errors="coerce",
        ).dt.date
        today = date.today()
        today_rows = customers[customers["date_dt"] == today]
        if not today_rows.empty:
            customers = today_rows
        else:
            return []

    if "routeId" in customers.columns:
        route_ids = customers["routeId"].dropna().astype(str)
        if not route_ids.empty:
            latest_route_id = route_ids.iloc[-1]
            customers = customers[
                customers["routeId"].astype(str) == latest_route_id
            ]

    if "position" in customers.columns:
        customers["position_sort"] = pd.to_numeric(
            customers["position"],
            errors="coerce",
        ).fillna(9999)
        customers = customers.sort_values("position_sort")

    stops = []
    current_index = None

    for index, (_, customer) in enumerate(customers.head(8).iterrows()):
        real_arrival = str(customer.get("realArrivalTime", "") or "").strip()
        if current_index is None and not real_arrival:
            current_index = index

        address = str(customer.get("address", "") or "").strip()
        position = str(customer.get("position", index + 1) or index + 1)
        stops.append(
            {
                "position": position,
                "address": address or f"Cim {position}",
            }
        )

    if stops and current_index is None:
        current_index = len(stops) - 1

    for index, stop in enumerate(stops):
        stop["current"] = index == current_index

    return stops


def render_shift_state_road(title, subtitle, dot_label, dot_text, note, show_help=False):
    help_html = (
        '<div class="route-help-button">Elakadtam, segítség kell</div>'
        if show_help
        else ""
    )

    st.markdown(
        f"""
<div class="route-road-card">
  <div class="route-road-head">
    <div class="route-brand">
      <div class="route-brand-logo">K</div>
      <div>
        <div class="route-road-title">{escape(title)}</div>
        <div class="route-road-subtitle">{escape(subtitle)}</div>
      </div>
    </div>
    <div class="route-road-subtitle">A depó készen áll</div>
  </div>
  <div class="route-road-track" style="--stop-count: 2;">
    <div class="route-stop route-stop-home">
      <div class="route-stop-dot">H</div>
      <div class="route-stop-label">Otthon</div>
    </div>
    <div class="route-stop route-stop-waiting">
      <div class="route-stop-dot">{escape(dot_label)}</div>
      <div class="route-stop-label">{escape(dot_text)}</div>
    </div>
    <div class="route-depot">
      <div class="route-depot-icon">D</div>
      <div class="route-stop-label">Depó</div>
    </div>
  </div>
  <div class="fun-note route-empty-note">{escape(note)}{help_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_no_shift_road():
    render_shift_state_road(
        "Műszakra várunk",
        "Ma még nem látok műszakot a neveden.",
        "?",
        "Pihenő mód",
        "Ma még nincs műszakod. A futárcipő pihen, a kávé pedig jogosan lassú.",
    )


def render_before_shift_road(minutes_to_start):
    minutes_to_start = max(minutes_to_start, 0)

    if minutes_to_start > 40:
        render_shift_state_road(
            "Lassan kezdődik a műszakod",
            f"Még körülbelül {minutes_to_start} perc van a kezdésig.",
            "40+",
            "Készülődés",
            "Még van idő összerakni magad, de a műszak már integet a távolból.",
        )
        return

    render_shift_state_road(
        "Ideje Giritonba bejelentkezni",
        f"Még körülbelül {minutes_to_start} perc van a kezdésig.",
        "!",
        "Depó felé",
        "Jelentkezz be Giritonba. Ha valami nem áll össze, kérj segítséget.",
        show_help=True,
    )


def render_checked_in_waiting_road(next_shift=None):
    subtitle = "Amint route kerül a nevedre, frissítés után megjelenik az útvonal."
    note = "Bent vagy a rendszerben. Most már csak a route-nak kell megérkeznie."

    if next_shift:
        start_text = next_shift["start_at"].strftime("%H:%M")
        end_text = (
            next_shift["end_at"].strftime("%H:%M")
            if next_shift.get("end_at")
            else ""
        )
        subtitle = f"Következő műszak: {start_text} - {end_text}."
        note = "Visszaértél, és van még műszakod. Várjuk a következő túrát."

    render_shift_state_road(
        "Bejelentkezve, túrára vársz",
        subtitle,
        "OK",
        "Túrára vár",
        note,
    )


def render_day_done_road():
    render_shift_state_road(
        "Mára kész vagy",
        "Nem látok több mai műszakot a neveden.",
        "✓",
        "Nap lezárva",
        "Ha nincs új műszak, jöhet a pihenés. A futárcipő ma már letette a voksát a kanapé mellett.",
    )


def render_returned_to_depot_road():
    render_shift_state_road(
        "Visszaértél a depóba",
        "A route lezárult, jöhet a következő kör vagy egy kis levegő.",
        "✓",
        "Kör kész",
        "Szép munka. Ha új route kerül rád, frissítés után itt jelenik meg.",
    )


def get_route_checkpoint_stops(route):
    checkpoints = route.get("checkpoints", [])

    if not checkpoints:
        return []

    stops = []
    current_index = None

    for index, checkpoint in enumerate(checkpoints[:8]):
        left_stop = (
            checkpoint.get("realDepartureTime")
            or checkpoint.get("realArrivalTime")
        )

        if current_index is None and not left_stop:
            current_index = index

        position = str(checkpoint.get("position", index + 1) or index + 1)
        address = str(checkpoint.get("address", "") or "").strip()
        stops.append(
            {
                "position": position,
                "address": address or f"Cím {position}",
            }
        )

    if stops and current_index is None:
        current_index = len(stops) - 1

    for index, stop in enumerate(stops):
        stop["current"] = index == current_index

    return stops


def get_current_route_stop(route):
    stops = get_route_checkpoint_stops(route)

    if not stops:
        return {}

    return next(
        (stop for stop in stops if stop.get("current")),
        stops[-1],
    )


def render_route_road(row, details):
    courier_id = normalize_id(row.get("courier_id"))
    attendance_data, drivers_data = load_live_courier_sources()
    attendance_courier = find_attendance_courier(
        attendance_data,
        courier_id,
    )
    driver = find_driver(
        drivers_data,
        courier_id,
    )
    is_active = driver.get("active")

    if is_active is False:
        future_shift = get_future_shift(attendance_courier)

        if future_shift:
            minutes_to_start = int(
                (future_shift["start_at"] - local_now()).total_seconds() // 60
            )
            render_before_shift_road(minutes_to_start)
        else:
            render_day_done_road()

        return

    current_shift = get_current_shift(attendance_courier)

    if not current_shift:
        if get_shift_items(attendance_courier):
            render_day_done_road()
        else:
            render_no_shift_road()
        return

    shift = current_shift["raw"]
    start_at = current_shift["start_at"]
    minutes_to_start = int(
        (start_at - local_now()).total_seconds() // 60
    )
    checked_in = bool(shift.get("availableForShiftSince"))
    driver_detail = load_live_driver_detail(courier_id)
    open_route = get_best_route(driver, driver_detail)
    live_state = get_live_driver_state(driver)
    live_route_active = live_state == "Delivering"
    route_without_return = bool(open_route and not open_route.get("realReturn"))
    route_is_open = bool(
        open_route
        and (
            live_route_active
            or route_without_return
        )
    )

    if route_is_open:
        current_route_stop = get_current_route_stop(open_route)
        stops = [current_route_stop] if current_route_stop else []
    else:
        stops = []

    if not route_is_open and open_route and open_route.get("realReturn"):
        next_shift = get_next_shift(attendance_courier)
        if next_shift:
            render_checked_in_waiting_road(next_shift)
        else:
            render_day_done_road()
        return

    if not stops and route_is_open:
        stops = get_route_road_stops(row, details)

    if not stops:
        if checked_in:
            render_checked_in_waiting_road()
        else:
            render_before_shift_road(minutes_to_start)
        return

    current_stop = stops[0]
    current_address = escape(str(current_stop.get("address", "")))
    current_position = escape(str(current_stop.get("position", "")))
    short_address = (
        current_address[:42] + "..."
        if len(current_address) > 42
        else current_address
    )

    st.markdown(
        f"""
<div class="route-road-card">
  <div class="route-road-head">
    <div class="route-brand">
      <div class="route-brand-logo">K</div>
      <div>
        <div class="route-road-title">Mai útvonal</div>
        <div class="route-road-subtitle">Zöld jel = aktuális cím</div>
      </div>
    </div>
    <div class="route-road-subtitle">Depó a célban</div>
  </div>
  <div class="route-road-track" style="--stop-count: 1;">
    <div class="route-stop route-stop-current">
      <div class="route-stop-dot">{current_position}</div>
      <div class="route-stop-label">{short_address}</div>
    </div>
    <div class="route-depot">
      <div class="route-depot-icon">D</div>
      <div class="route-stop-label">Depó</div>
    </div>
  </div>
  <div class="bag-alert-preview">
    <div>
      <div class="bag-alert-title">Táska hiány bejelentés - design előnézet</div>
      <div class="bag-alert-copy">Aktuális cím: <strong>{current_address}</strong><br>Később innen indulhat majd a sablon e-mail és a kép csatolása az előre megadott címre.</div>
    </div>
    <div class="bag-alert-button">Táska hiány jelzése</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def calculate_route_mix(details, row, start_date=None, end_date=None):
    earnings = read_sheet_dataframe("DSP_Earning_Estimate")
    courier_id = normalize_id(row.get("courier_id"))

    if not earnings.empty and courier_id and "courierId" in earnings.columns:
        earnings = earnings.copy()
        earnings = earnings[
            earnings["courierId"].apply(normalize_id) == courier_id
        ]

        if "date" in earnings.columns:
            earnings["date_dt"] = pd.to_datetime(
                earnings["date"],
                errors="coerce",
            ).dt.date

            if start_date:
                earnings = earnings[
                    earnings["date_dt"] >= start_date
                ]
            if end_date:
                earnings = earnings[
                    earnings["date_dt"] <= end_date
                ]

        for column in [
            "normal_routes",
            "express_routes",
            "estimated_max_revenue",
            "total_routes",
        ]:
            if column not in earnings.columns:
                earnings[column] = 0
            earnings[column] = pd.to_numeric(
                earnings[column],
                errors="coerce",
            ).fillna(0)

        total_routes = int(earnings["total_routes"].sum())
        max_revenue = float(earnings["estimated_max_revenue"].sum())

        if total_routes:
            return {
                "express_routes": int(earnings["express_routes"].sum()),
                "normal_routes": int(earnings["normal_routes"].sum()),
                "max_revenue": max_revenue,
                "avg_revenue_per_route": max_revenue / total_routes,
            }

    customers = details.get("customers", pd.DataFrame())

    if customers.empty or "routeId" not in customers.columns:
        express_routes = int(row.get("express_address_count", 0) > 0)
        total_routes = int(row.get("routes", 0))
        normal_routes = max(total_routes - express_routes, 0)
    else:
        if "courierId" in customers.columns and courier_id:
            customers = customers[
                customers["courierId"].apply(normalize_id) == courier_id
            ]

        route_groups = customers.groupby("routeId").agg(
            express_addresses=("express_address_count", "sum"),
        )
        express_routes = int(
            (route_groups["express_addresses"] > 0).sum()
        )
        total_routes = int(
            route_groups.shape[0]
        )
        normal_routes = max(
            total_routes - express_routes,
            0,
        )

    max_revenue = (
        express_routes * EXPRESS_MAX_FEE
        + normal_routes * NORMAL_CITY_MAX_FEE
    )
    avg_revenue_per_route = (
        max_revenue / (express_routes + normal_routes)
        if express_routes + normal_routes
        else 0
    )

    return {
        "express_routes": express_routes,
        "normal_routes": normal_routes,
        "max_revenue": max_revenue,
        "avg_revenue_per_route": avg_revenue_per_route,
    }


def calculate_month_revenue(row, start_date, end_date):
    earnings = read_sheet_dataframe("DSP_Earning_Estimate")
    courier_id = normalize_id(row.get("courier_id"))

    if earnings.empty or not courier_id or "courierId" not in earnings.columns:
        return 0

    earnings = earnings.copy()
    earnings = earnings[
        earnings["courierId"].apply(normalize_id) == courier_id
    ]

    if earnings.empty or "date" not in earnings.columns:
        return 0

    earnings["date_dt"] = pd.to_datetime(
        earnings["date"],
        errors="coerce",
    ).dt.date
    earnings = earnings[
        (earnings["date_dt"] >= start_date)
        & (earnings["date_dt"] <= end_date)
    ]

    if earnings.empty or "estimated_max_revenue" not in earnings.columns:
        return 0

    return float(
        pd.to_numeric(
            earnings["estimated_max_revenue"],
            errors="coerce",
        ).fillna(0).sum()
    )


def month_bounds(reference_date):
    current_start = reference_date.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    return current_start, previous_start, previous_end


def selected_month_bounds(month_text, today):
    year_text, month_text = str(month_text).split("-")
    year = int(year_text)
    month = int(month_text)
    month_start = date(year, month, 1)
    month_end = date(
        year,
        month,
        monthrange(year, month)[1],
    )

    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    previous_end = month_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    return month_start, month_end, previous_start, previous_end


def render_stat_cards(row, details, start_date=None, end_date=None):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))
    today = date.today()
    selected_month_start = start_date or today.replace(day=1)
    selected_month_end = end_date or today
    previous_month_end = selected_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    selected_month_revenue = calculate_month_revenue(
        row,
        selected_month_start,
        selected_month_end,
    )
    previous_month_revenue = calculate_month_revenue(
        row,
        previous_month_start,
        previous_month_end,
    )
    route_mix = calculate_route_mix(
        details,
        row,
        start_date,
        end_date,
    )

    cards = [
        stat_card("Max bevétel lehetőség", format_currency(route_mix["max_revenue"]), "Képed alapján: expressz + city sáv / kör."),
        stat_card("Átlag / kör", format_currency(route_mix["avg_revenue_per_route"]), "Becsült kereseti lehetőség körönként."),
        stat_card("Normál körök", route_mix["normal_routes"], "City sávval becsülve."),
        stat_card("Expressz körök", route_mix["express_routes"], "Expressz sávval becsülve."),
        stat_card("Kivitt címek", delivered, "Ennyi csomag talált gazdára."),
        stat_card("Körök", routes, "Teljesített route-ok."),
        stat_card("Dolgozott napok", worked_days, "Aktív napok a szűrésben."),
        stat_card("Átlag cím / kör", format_number(row.get("avg_orders_per_route")), "Minél stabilabb, annál szebb."),
        stat_card("Időablak pontos", max(total_addresses - int(row.get("late_address_count", 0)) - int(row.get("early_address_count", 0)), 0), "Nem korai, nem késő."),
        stat_card("Átlag várakozás", format_minutes(row.get("avg_wait_minutes")), "Sorban állás, de számokban."),
    ]

    st.markdown(
        f"<div class=\"stat-grid\">{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def build_type_chart(row):
    return pd.DataFrame(
        [
            {
                "Tipus": "Normal",
                "Cimek": int(row.get("normal_address_count", 0)),
            },
            {
                "Tipus": "Expressz",
                "Cimek": int(row.get("express_address_count", 0)),
            },
        ]
    )


def build_timing_chart(row):
    total = int(row.get("total_address_count", 0))
    early = int(row.get("early_address_count", 0))
    late = int(row.get("late_address_count", 0))
    on_time = max(total - early - late, 0)

    return pd.DataFrame(
        [
            {"Statusz": "Idoben", "Cimek": on_time},
            {"Statusz": "Korai", "Cimek": early},
            {"Statusz": "Keso", "Cimek": late},
        ]
    )


def render_charts(row):
    type_df = build_type_chart(row)
    timing_df = build_timing_chart(row)

    left, right = st.columns(2)

    with left:
        st.subheader("Normál vs expressz")
        chart = (
            alt.Chart(type_df)
            .mark_arc(innerRadius=55)
            .encode(
                theta=alt.Theta("Cimek:Q"),
                color=alt.Color(
                    "Tipus:N",
                    scale=alt.Scale(range=["#6cab2f", "#f97316"]),
                ),
                tooltip=["Tipus", "Cimek"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("Időablak fegyelem")
        chart = (
            alt.Chart(timing_df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("Statusz:N", sort=None),
                y=alt.Y("Cimek:Q"),
                color=alt.Color(
                    "Statusz:N",
                    scale=alt.Scale(range=["#22c55e", "#38bdf8", "#ef4444"]),
                    legend=None,
                ),
                tooltip=["Statusz", "Cimek"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)


def render_stat_cards(row, details, start_date=None, end_date=None):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))
    today = date.today()
    current_month_start, previous_month_start, previous_month_end = month_bounds(today)
    current_month_revenue = calculate_month_revenue(
        row,
        current_month_start,
        today,
    )
    previous_month_revenue = calculate_month_revenue(
        row,
        previous_month_start,
        previous_month_end,
    )
    route_mix = calculate_route_mix(
        details,
        row,
        start_date,
        end_date,
    )
    on_time_addresses = max(
        total_addresses
        - int(row.get("late_address_count", 0))
        - int(row.get("early_address_count", 0)),
        0,
    )

    cards = [
        stat_card("Valasztott havi max", format_currency(selected_month_revenue), f"{selected_month_start:%Y-%m-%d} - {selected_month_end:%Y-%m-%d}"),
        stat_card("Elozo havi max", format_currency(previous_month_revenue), f"{previous_month_start:%Y-%m-%d} - {previous_month_end:%Y-%m-%d}"),
        stat_card("Atlag / kor", format_number(row.get("avg_orders_per_route")), "Osszes kivitt cim / teljesitett kor."),
        stat_card("Normal korok", route_mix["normal_routes"], "City savval becsulve."),
        stat_card("Expressz korok", route_mix["express_routes"], "Expressz savval becsulve."),
        stat_card("Kivitt cimek", delivered, "Ennyi csomag talalt gazdara."),
        stat_card("Korok", routes, "Teljesitett route-ok."),
        stat_card("Dolgozott napok", worked_days, "Aktiv napok a szuresben."),
        stat_card("Idoablak pontos", on_time_addresses, "Nem korai, nem keso."),
        stat_card("Atlag varakozas", format_minutes(row.get("avg_wait_minutes")), "Sorban allas, de szamokban."),
    ]

    st.markdown(
        f"<div class=\"stat-grid\">{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def render_extra_metrics(row):
    st.subheader("Hasznos apróságok")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Átlag túra hossz", format_minutes(row.get("avg_route_minutes")))
    col2.metric("Valós bepakolás", format_minutes(row.get("avg_real_loading_minutes")))
    col3.metric("Késő normál cím", f"{int(row.get('normal_late_address_count', 0))} ({format_percent(row.get('normal_late_address_rate'))})")
    col4.metric("Késő expressz cím", f"{int(row.get('express_late_address_count', 0))} ({format_percent(row.get('express_late_address_rate'))})")

    text = (
        "A bevételbecslés tájékoztató jellegű: a képen szereplő kiemelt expressz és city sávokkal számol, "
        "a tényleges elszámolást nem helyettesíti."
    )

    st.markdown(
        f"<div class=\"fun-note\">{text}</div>",
        unsafe_allow_html=True,
    )


def select_visible_courier(summary_df, user):
    if summary_df.empty:
        return None

    if user.get("role") == "user":
        courier_id = normalize_id(user.get("courierId"))
        match = summary_df[
            summary_df["courier_id"].apply(normalize_id) == courier_id
        ]
        return match.iloc[0] if not match.empty else None

    options = summary_df.sort_values("name")
    selected_id = st.selectbox(
        "Futár kiválasztása",
        options["courier_id"].tolist(),
        format_func=lambda courier_id: (
            options.loc[
                options["courier_id"] == courier_id,
                "name",
            ].iloc[0]
        ),
    )
    match = options[options["courier_id"] == selected_id]
    return match.iloc[0] if not match.empty else None


def _show_courier_dashboard_page_legacy_unused():
    render_styles()

    user = st.session_state["user"]
    today = date.today()
    default_month = today.strftime("%Y-%m")

    start_date, end_date = st.columns(2)
    selected_start = start_date.date_input(
        "Időszak kezdete",
        value=default_start,
    )
    selected_end = end_date.date_input(
        "Időszak vége",
        value=today,
    )

    with st.spinner("Saját Kifli-kártya összerakása..."):
        summary_df, details = load_courier_statistics(
            start_date=selected_start,
            end_date=selected_end,
            user=user,
        )

    if summary_df.empty:
        st.warning("Még nincs elég adat ehhez a futár-kártyához.")
        return

    row = select_visible_courier(summary_df, user)

    if row is None:
        st.warning("Ehhez a belépéshez nem találtam futár statisztikát.")
        return

    render_hero(row, user)
    render_today_shifts(row, user)
    render_route_road(row, details)
    render_stat_cards(
        row,
        details,
        selected_start,
        selected_end,
    )
    render_extra_metrics(row)


def show_courier_dashboard_page():
    render_styles()

    user = st.session_state["user"]
    today = date.today()
    default_month = today.strftime("%Y-%m")

    selected_month = st.text_input(
        "Honap",
        value=default_month,
        help="Formatum: EEEE-HH, peldaul 2026-07.",
    )

    try:
        selected_start, selected_end, _, _ = selected_month_bounds(
            selected_month,
            today,
        )
    except Exception:
        st.error("A honapot EEEE-HH formatumban add meg, peldaul: 2026-07.")
        return

    with st.spinner("Sajat Kifli-kartya osszerakasa..."):
        summary_df, details = load_courier_statistics(
            start_date=selected_start,
            end_date=selected_end,
            user=user,
        )

    if summary_df.empty:
        st.warning("Meg nincs eleg adat ehhez a futar-kartyahoz.")
        return

    row = select_visible_courier(summary_df, user)

    if row is None:
        st.warning("Ehhez a belepeshez nem talaltam futar statisztikat.")
        return

    render_hero(row, user)
    render_today_shifts(row, user)
    render_route_road(row, details)
    render_stat_cards(
        row,
        details,
        selected_start,
        selected_end,
    )
    render_extra_metrics(row)
