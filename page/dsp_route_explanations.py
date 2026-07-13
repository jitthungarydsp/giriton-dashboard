from datetime import date
import unicodedata

import pandas as pd
import streamlit as st

from resources.dsp_route_explanations import (
    format_dt,
    format_minutes,
    format_percent,
    read_order_details_for_routes,
    read_performance_rows,
    read_route_stories,
    render_route_path_html,
    route_status_label,
    summarize_performance,
    summarize_story_rows,
)


def inject_styles():
    st.markdown(
        """
<style>
.perf-hero {
    background: linear-gradient(135deg, #f8fafc 0%, #eefdf3 100%);
    border: 1px solid #d9f99d;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.perf-hero h1 {
    margin: 0 0 6px 0;
    font-size: 30px;
    color: #0f172a;
}
.perf-hero p {
    margin: 0;
    color: #475569;
}
.perf-formula {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
    background: #ffffff;
    color: #334155;
    margin: 10px 0 16px 0;
}
.perf-status {
    display: inline-block;
    border-radius: 999px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 12px;
}
.perf-status-ok {
    background: #dcfce7;
    color: #166534;
}
.perf-status-warn {
    background: #fef3c7;
    color: #92400e;
}
.perf-status-bad {
    background: #fee2e2;
    color: #991b1b;
}
.perf-route-path {
    position: relative;
    margin: 14px 0 4px 0;
    padding-left: 24px;
}
.perf-route-path::before {
    content: "";
    position: absolute;
    top: 10px;
    bottom: 10px;
    left: 36px;
    width: 4px;
    border-radius: 999px;
    background: linear-gradient(180deg, #facc15, #84cc16, #22c55e);
}
.perf-stop {
    display: grid;
    grid-template-columns: 48px 1fr;
    gap: 14px;
    margin-bottom: 12px;
    position: relative;
}
.perf-stop-dot {
    width: 32px;
    height: 32px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    color: #111827;
    background: #facc15;
    box-shadow: 0 0 0 4px #fff, 0 8px 18px rgba(15, 23, 42, 0.18);
    z-index: 2;
}
.perf-stop-late .perf-stop-dot {
    background: #ef4444;
    color: #fff;
}
.perf-stop-early .perf-stop-dot {
    background: #fb923c;
    color: #fff;
}
.perf-stop-ok .perf-stop-dot {
    background: #22c55e;
    color: #fff;
}
.perf-stop-card {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px 12px;
    background: #fff;
}
.perf-stop-title {
    font-weight: 800;
    color: #0f172a;
}
.perf-stop-address {
    color: #111827;
    margin-top: 2px;
}
.perf-stop-meta {
    color: #64748b;
    font-size: 12px;
    margin-top: 3px;
}
.perf-stop-status {
    margin-top: 6px;
    font-weight: 700;
    color: #334155;
}
.perf-story {
    white-space: pre-wrap;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: #f8fafc;
    padding: 12px 14px;
    color: #0f172a;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 13px;
}
</style>
""",
        unsafe_allow_html=True,
    )


def metric_row(title, summary):
    st.subheader(title)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Műszak", int(summary.get("shifts", 0) or summary.get("shift_base", 0)))
    c2.metric("Order", int(summary.get("orders", 0)))
    c3.metric("Késő order", int(summary.get("delayed", 0)))
    c4.metric("Delay %", format_percent(summary.get("delay_percent", 0)))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "Late %",
        format_percent(summary.get("late_percent", 0)),
        help="A késve sorba állt / késve kezdett műszakok aránya.",
    )
    c6.metric(
        "No-show %",
        format_percent(summary.get("no_show_percent", 0)),
        help="Courier Hub performance API-ból jövő érték. Route-ból önmagában nem mindig vezethető vissza.",
    )
    c7.metric(
        "Compliance",
        format_percent(summary.get("compliance_score_percent", 0)),
        help="100 - (0.7 * no-show % + 0.3 * late %).",
    )
    c8.metric(
        "Compliance rossz %",
        format_percent(summary.get("compliance_bad_percent", 0)),
    )


def normalize_search_text(value):
    text = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def filter_dataframe_by_search(df, search_text, columns):
    if df.empty:
        return df

    needle = normalize_search_text(search_text)

    if not needle:
        return df

    mask = pd.Series(False, index=df.index)

    for column in columns:
        if column not in df.columns:
            continue

        values = df[column].fillna("").astype(str).map(normalize_search_text)
        mask = mask | values.str.contains(needle, na=False, regex=False)

    return df[mask].copy()


def build_performance_table(performance_df):
    if performance_df.empty:
        return pd.DataFrame()

    columns = [
        "date_from",
        "date_to",
        "warehouse_code",
        "courier_id",
        "courier_name",
        "shifts",
        "orders",
        "delayed",
        "delay_percent",
        "late_percent",
        "no_show_percent",
        "compliance_score_percent",
    ]
    columns = [column for column in columns if column in performance_df.columns]
    table = performance_df[columns].copy()

    for column in [
        "delay_percent",
        "late_percent",
        "no_show_percent",
        "compliance_score_percent",
    ]:
        if column in table.columns:
            table[column] = table[column].apply(format_percent)

    return table.rename(
        columns={
            "date_from": "Időszak kezdete",
            "date_to": "Időszak vége",
            "warehouse_code": "Raktár",
            "courier_id": "Courier ID",
            "courier_name": "Futár",
            "shifts": "Műszak",
            "orders": "Order",
            "delayed": "Késő order",
            "delay_percent": "Delay %",
            "late_percent": "Late %",
            "no_show_percent": "No-show %",
            "compliance_score_percent": "Compliance",
        }
    )


def build_story_table(stories_df):
    if stories_df.empty:
        return pd.DataFrame()

    columns = [
        "work_date",
        "courier_id",
        "courier_name",
        "warehouse_name",
        "route_id",
        "shift_name",
        "shift_start",
        "available_for_shift_since",
        "courier_registered_at",
        "assigned_at",
        "queue_entry_delta_minutes",
        "queue_wait_minutes",
        "planned_route_minutes",
        "real_route_minutes",
        "total_route_minutes",
        "gps_distance_km",
        "address_count",
        "planned_late_count",
        "time_window_late_count",
        "booking_shift_count",
    ]
    columns = [column for column in columns if column in stories_df.columns]
    table = stories_df[columns].copy()

    rename_map = {
        "work_date": "Dátum",
        "courier_id": "Courier ID",
        "courier_name": "Futár",
        "warehouse_name": "Raktár",
        "route_id": "Route ID",
        "shift_name": "Műszak",
        "shift_start": "Műszak kezdete",
        "available_for_shift_since": "Elérhető / sorba állt",
        "courier_registered_at": "Route regisztráció",
        "assigned_at": "Túrát kapott",
        "queue_entry_delta_minutes": "Sorba állás eltérés perc",
        "queue_wait_minutes": "Várakozás perc",
        "planned_route_minutes": "Tervezett túra perc",
        "real_route_minutes": "Valós túra perc",
        "total_route_minutes": "Összes túra perc",
        "gps_distance_km": "Km",
        "address_count": "Cím",
        "planned_late_count": "Tervhez késő cím",
        "time_window_late_count": "Időkapuhoz késő cím",
        "booking_shift_count": "Foglalás szerinti műszak",
    }

    for column in [
        "shift_start",
        "available_for_shift_since",
        "courier_registered_at",
        "assigned_at",
    ]:
        if column in table.columns:
            table[column] = table[column].apply(format_dt)

    return table.rename(columns=rename_map)


def render_formula_box():
    st.markdown(
        """
<div class="perf-formula">
    <b>Hogyan olvassuk?</b><br>
    Delay % = késő order / összes order. A késést itt a tervezett érkezéshez képest nézzük.<br>
    Late % = késve sorba állt vagy késve kezdett műszak / összes műszak.<br>
    Compliance = 100 - (0.7 × no-show % + 0.3 × late %).<br>
    Az availableForShiftSince és courierRegisteredAt azért látszik külön, mert ha ugyanaz, akkor a rendszer a sorba állást és route-regisztrációt ugyanarra az eseményre adta vissza.
</div>
""",
        unsafe_allow_html=True,
    )


def render_route_expanders(stories_df, orders_df):
    st.subheader("Route magyarázatok")

    if stories_df.empty:
        st.warning("Nincs route történet a kiválasztott szűrésre.")
        return

    for _, row in stories_df.iterrows():
        label_text, label_class = route_status_label(row)
        title = (
            f"{row.get('work_date')} | "
            f"#{row.get('courier_id')} {row.get('courier_name') or ''} | "
            f"Route {row.get('route_id')} | {label_text}"
        )

        with st.expander(title):
            st.markdown(
                f'<span class="perf-status perf-status-{label_class}">{label_text}</span>',
                unsafe_allow_html=True,
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sorba állás eltérés", format_minutes(row.get("queue_entry_delta_minutes")))
            c2.metric("Várakozás túrára", format_minutes(row.get("queue_wait_minutes")))
            c3.metric("Valós túra hossz", format_minutes(row.get("real_route_minutes")))
            c4.metric("Km", f"{float(row.get('gps_distance_km') or 0):.1f} km")

            st.markdown(
                f'<div class="perf-story">{str(row.get("story_text") or "")}</div>',
                unsafe_allow_html=True,
            )

            route_id = str(row.get("route_id") or "")
            route_orders = (
                orders_df[orders_df["route_id"].astype(str) == route_id].copy()
                if not orders_df.empty and "route_id" in orders_df.columns
                else pd.DataFrame()
            )

            if route_orders.empty:
                st.caption("Ehhez a route-hoz nincs cím/order bontás betöltve.")
                continue

            st.markdown(
                render_route_path_html(route_orders),
                unsafe_allow_html=True,
            )

            display_columns = [
                "position",
                "order_id",
                "address",
                "deliver_since",
                "deliver_till",
                "planned_arrival",
                "real_arrival",
                "planned_delta_minutes",
                "time_window_status",
                "time_window_delta_minutes",
            ]
            display_columns = [
                column for column in display_columns if column in route_orders.columns
            ]
            table = route_orders[display_columns].copy()

            for column in [
                "deliver_since",
                "deliver_till",
                "planned_arrival",
                "real_arrival",
            ]:
                if column in table.columns:
                    table[column] = table[column].apply(format_dt)

            st.dataframe(
                table.rename(
                    columns={
                        "position": "Poz",
                        "order_id": "Order",
                        "address": "Cím",
                        "deliver_since": "Időablak kezdete",
                        "deliver_till": "Időablak vége",
                        "planned_arrival": "Tervezett érkezés",
                        "real_arrival": "Valós érkezés",
                        "planned_delta_minutes": "Tervhez eltérés perc",
                        "time_window_status": "Időkapu státusz",
                        "time_window_delta_minutes": "Időkapu eltérés perc",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


def apply_soft_story_warehouse_filter(stories_df, warehouse):
    if stories_df.empty:
        return stories_df

    clean_warehouse = str(warehouse or "").strip()

    if not clean_warehouse or clean_warehouse in ["Mind", "Budapest"]:
        return stories_df

    mask = pd.Series(False, index=stories_df.index)

    for column in ["warehouse_name", "shift_name"]:
        if column in stories_df.columns:
            mask = mask | stories_df[column].astype(str).str.contains(
                clean_warehouse,
                case=False,
                na=False,
            )

    if mask.any():
        return stories_df[mask].copy()

    st.caption(
        f"A route story táblában nincs egyértelmű {clean_warehouse} jelölés, "
        "ezért a futár route-jait raktárszűrés nélkül mutatom."
    )
    return stories_df


def show_dsp_route_explanations_page():
    inject_styles()

    st.markdown(
        """
<div class="perf-hero">
    <h1>Courier performance magyarázat</h1>
    <p>Route és order szinten mutatjuk meg, miből jön ki a Courier Hub performance érték.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    today = date.today()
    default_start = today.replace(day=1)

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    start_date = c1.date_input("Kezdő dátum", value=default_start)
    end_date = c2.date_input("Záró dátum", value=today)
    warehouse = c3.selectbox("Raktár", ["Mind", "BUD1", "BUD2", "Budapest"])
    search_text = c4.text_input(
        "Keresés",
        value="",
        placeholder="Courier ID vagy név",
    )

    if start_date > end_date:
        st.error("A kezdő dátum nem lehet későbbi, mint a záró dátum.")
        return

    try:
        stories_df = read_route_stories(
            start_date=start_date,
            end_date=end_date,
            courier_id="",
            warehouse=warehouse,
        )
        performance_df = read_performance_rows(
            start_date=start_date,
            end_date=end_date,
            courier_id="",
            warehouse=warehouse,
        )
    except Exception as exc:
        st.error(f"Nem sikerült beolvasni a performance magyarázat adatait: {exc}")
        return

    stories_df = apply_soft_story_warehouse_filter(stories_df, warehouse)
    stories_df = filter_dataframe_by_search(
        stories_df,
        search_text,
        ["courier_id", "courier_name", "route_id", "shift_name"],
    )
    performance_df = filter_dataframe_by_search(
        performance_df,
        search_text,
        ["courier_id", "courier_name"],
    )

    st.caption(
        f"Találatok: Courier Hub sor {len(performance_df)}, "
        f"route story sor {len(stories_df)}."
    )

    if not performance_df.empty and stories_df.empty:
        st.warning(
            "Courier Hub performance adat van erre a szűrésre, de a route story "
            "táblában nincs hozzá tartozó sor. Ilyenkor a mart_dsp_route_stories "
            "frissítést kell lefuttatni erre a dátumtartományra."
        )

    performance_summary = summarize_performance(performance_df)
    story_summary = summarize_story_rows(
        stories_df,
        official_shifts=performance_summary.get("shifts", 0),
    )

    render_formula_box()

    left, right = st.columns(2)

    with left:
        metric_row("Courier Hub érték", performance_summary)

    with right:
        reconstructed = {
            "shifts": story_summary.get("shift_base", 0),
            "orders": story_summary.get("orders", 0),
            "delayed": story_summary.get("delayed", 0),
            "delay_percent": story_summary.get("delay_percent", 0),
            "late_percent": story_summary.get("late_percent", 0),
            "no_show_percent": performance_summary.get("no_show_percent", 0),
            "compliance_bad_percent": (
                0.7 * performance_summary.get("no_show_percent", 0)
                + 0.3 * story_summary.get("late_percent", 0)
            ),
            "compliance_score_percent": (
                100
                - (
                    0.7 * performance_summary.get("no_show_percent", 0)
                    + 0.3 * story_summary.get("late_percent", 0)
                )
            ),
        }
        metric_row("Route story alapján visszaépítve", reconstructed)

    st.divider()

    st.subheader("Courier Hub futár lista")
    st.dataframe(
        build_performance_table(performance_df),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Route lista")
    st.dataframe(
        build_story_table(stories_df),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    route_ids = (
        stories_df["route_id"].dropna().astype(str).unique().tolist()
        if not stories_df.empty and "route_id" in stories_df.columns
        else []
    )

    if not search_text.strip() and len(route_ids) > 30:
        st.info(
            "A cím/order bontáshoz adj meg Courier ID-t, különben túl sok raw JSON-t kellene egyszerre betölteni."
        )
        orders_df = pd.DataFrame()
    else:
        try:
            orders_df = read_order_details_for_routes(
                start_date=start_date,
                end_date=end_date,
                courier_id=search_text if search_text.strip().isdigit() else "",
                route_ids=route_ids,
            )
        except Exception as exc:
            st.warning(f"A cím/order bontás most nem tölthető be: {exc}")
            orders_df = pd.DataFrame()

    render_route_expanders(
        stories_df,
        orders_df,
    )
