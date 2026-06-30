from datetime import date
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from resources.dsp_dashboard_statistics import (
    build_statistics,
    normalize_id,
)
from resources.shift_reconciliation_sheet import (
    read_shift_reconciliation_records,
)

EXPRESS_MAX_FEE = 6516
NORMAL_CITY_MAX_FEE = 13000
DAILY_CACHE_SECONDS = 24 * 60 * 60


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
@media (max-width: 900px) {
    .courier-hero {
        grid-template-columns: 1fr;
    }
    .stat-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
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
    work_date_text = today.isoformat()
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


def render_today_shifts(row, user):
    today = date.today()
    shifts = get_today_shift_rows(
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


def calculate_route_mix(details, row):
    customers = details.get("customers", pd.DataFrame())
    courier_id = normalize_id(row.get("courier_id"))

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


def render_stat_cards(row, details):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))
    route_mix = calculate_route_mix(
        details,
        row,
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


def show_courier_dashboard_page():
    render_styles()

    user = st.session_state["user"]
    today = date.today()
    default_start = today.replace(day=1)

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
    render_stat_cards(row, details)
    render_charts(row)
    render_extra_metrics(row)
