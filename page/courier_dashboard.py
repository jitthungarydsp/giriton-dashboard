from datetime import date
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from resources.dsp_dashboard_statistics import (
    build_statistics,
    normalize_id,
)


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
    name = escape(str(row.get("name") or user.get("username") or "Kifli futar"))
    courier_id = escape(str(row.get("courier_id") or user.get("courierId") or "-"))
    warehouse = escape(str(row.get("warehouse") or "Kifli palya"))

    st.markdown(
        f"""
<div class="courier-hero">
  <div>
    <div class="courier-plate-label">Kifli futar cockpit</div>
    <h1>Szia, {name}!</h1>
    <p>Itt van a sajat teljesitmeny-kartyad: cimek, korok, normal es expressz aranyok, varakozasok es azok az apro szamok, amikbol a nap vegen latszik, hogy ment a palya.</p>
  </div>
  <div class="courier-plate">
    <div class="courier-plate-label">Futar azonosito</div>
    <div class="courier-plate-value">#{courier_id}</div>
    <div class="stat-note">Raktar: {warehouse}</div>
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


def render_stat_cards(row):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))

    cards = [
        stat_card("Kivitt cimek", delivered, "Ennyi csomag talalt gazdara."),
        stat_card("Korok", routes, "Teljesitett route-ok."),
        stat_card("Dolgozott napok", worked_days, "Aktiv napok a szuresben."),
        stat_card("Atlag cim / kor", format_number(row.get("avg_orders_per_route")), "Minel stabilabb, annal szebb."),
        stat_card("Normal cimek", int(row.get("normal_address_count", 0)), format_percent(row.get("normal_address_rate"))),
        stat_card("Expressz cimek", int(row.get("express_address_count", 0)), format_percent(row.get("express_address_rate"))),
        stat_card("Idoablak pontos", max(total_addresses - int(row.get("late_address_count", 0)) - int(row.get("early_address_count", 0)), 0), "Nem korai, nem keso."),
        stat_card("Atlag varakozas", format_minutes(row.get("avg_wait_minutes")), "Sorban allas, de szamokban."),
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
        st.subheader("Normal vs expressz")
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
        st.subheader("Idoablak fegyelem")
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
    st.subheader("Hasznos aprosagok")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Atlag tura hossz", format_minutes(row.get("avg_route_minutes")))
    col2.metric("Valos bepakolas", format_minutes(row.get("avg_real_loading_minutes")))
    col3.metric("Keso normal cim", f"{int(row.get('normal_late_address_count', 0))} ({format_percent(row.get('normal_late_address_rate'))})")
    col4.metric("Keso expressz cim", f"{int(row.get('express_late_address_count', 0))} ({format_percent(row.get('express_late_address_rate'))})")

    late_shift_count = int(row.get("late_shift_count", 0))
    if late_shift_count:
        text = f"{late_shift_count} keseses muszak latszik a szuresben. Ez nem drama, csak egy sarga lampacska a muszerfalon."
    else:
        text = "Keseses muszak nincs a szuresben. A Kifli-univerzum most elegedetten hummog."

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
        "Futar kivalasztasa",
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
        "Idoszak kezdete",
        value=default_start,
    )
    selected_end = end_date.date_input(
        "Idoszak vege",
        value=today,
    )

    with st.spinner("Sajat Kifli-kartya osszerakasa..."):
        summary_df, _ = build_statistics(
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
    render_stat_cards(row)
    render_charts(row)
    render_extra_metrics(row)
