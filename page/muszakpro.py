from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.courier_master_db import read_courier_master
from resources.foglalasok_db import (
    read_foglalasok_raw,
    read_muszakpro_events,
)
from resources.muszakpro_db import (
    book_shift,
    build_daily_shift_view,
    cancel_booking,
    clean,
    normalize_email,
    read_shift_capacity,
)


def _format_dataframe(df, columns, labels):
    visible_columns = [
        column
        for column in columns
        if column in df.columns
    ]

    if not visible_columns:
        return pd.DataFrame()

    return df[visible_columns].rename(
        columns=labels
    )


def _render_setup_box():
    with st.expander(
        "DB atvezetes es import",
        expanded=False,
    ):
        st.markdown(
            """
1. Supabase SQL Editorban futtasd: `docs/supabase_muszakpro_live.sql`
2. A regi `beo` kapacitasok importja:

```powershell
python scripts\\load_muszakpro_capacity.py --dry-run
python scripts\\load_muszakpro_capacity.py
```

3. A regi `Foglalasok` importja, ha kell:

```powershell
python scripts\\load_foglalasok_raw.py
```

Fontos: a regi Google Sheet tovabbra is csak forras/import. A sajat Streamlit
MuszakPro mar a Supabase tablakat hasznalja.
"""
        )


def _status_badge(text, tone):
    colors = {
        "green": ("#dcfce7", "#166534"),
        "yellow": ("#fef9c3", "#854d0e"),
        "red": ("#fee2e2", "#991b1b"),
        "gray": ("#f1f5f9", "#475569"),
    }
    background, color = colors.get(
        tone,
        colors["gray"],
    )
    return (
        f"<span style='display:inline-block;padding:4px 10px;"
        f"border-radius:999px;background:{background};color:{color};"
        f"font-weight:700;font-size:12px'>{text}</span>"
    )


def _render_shift_card(row, selected_courier, actor_email):
    shift_text = clean(row.get("shift_text"))
    warehouse = clean(row.get("warehouse"))
    work_date = clean(row.get("work_date"))
    is_mine = bool(row.get("is_mine"))
    booked_count = int(row.get("booked_count") or 0)
    limit_count = int(row.get("limit_count") or 0)
    free_count = int(row.get("free_count") or 0)
    booking_code = clean(row.get("booking_code"))
    status_tone = "green"
    status_text = "Szabad"

    if is_mine:
        status_tone = "yellow" if booking_code.startswith("TF-") else "green"
        status_text = f"Foglalva ({booking_code or '-'})"
    elif free_count <= 0:
        status_tone = "red"
        status_text = "Betelt / varolista"

    st.markdown(
        f"""
<div style="border:1px solid #dbeafe;border-radius:10px;padding:14px 16px;
background:linear-gradient(135deg,#ffffff,#f8fafc);min-height:140px">
  <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
    <div>
      <div style="font-size:20px;font-weight:800;color:#0f172a">{shift_text}</div>
      <div style="font-size:13px;color:#64748b;margin-top:4px">{warehouse} | {work_date}</div>
    </div>
    {_status_badge(status_text, status_tone)}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px">
    <div><b>{limit_count}</b><br><span style="color:#64748b;font-size:12px">Limit</span></div>
    <div><b>{booked_count}</b><br><span style="color:#64748b;font-size:12px">Foglalt</span></div>
    <div><b>{free_count}</b><br><span style="color:#64748b;font-size:12px">Szabad</span></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    key_base = (
        f"{work_date}_{warehouse}_{shift_text}_"
        f"{selected_courier.get('email', '')}_{booking_code}"
    ).replace(" ", "_")

    if is_mine:
        if col1.button(
            "Torles",
            key=f"cancel_{key_base}",
            use_container_width=True,
        ):
            result = cancel_booking(
                work_date,
                selected_courier.get("email"),
                shift_text,
                warehouse,
                actor_email=actor_email,
            )
            if result.get("ok"):
                st.success(
                    result.get("message")
                )
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(
                    result.get("message")
                )
    else:
        if col1.button(
            "Foglalas",
            key=f"book_{key_base}",
            use_container_width=True,
            type="primary",
        ):
            result = book_shift(
                work_date,
                selected_courier.get("email"),
                shift_text,
                warehouse,
                actor_email=actor_email,
                courier=selected_courier,
            )
            if result.get("ok"):
                st.success(
                    result.get("message")
                )
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(
                    result.get("message")
                )


def _courier_options():
    try:
        master = read_courier_master()
    except Exception:
        master = pd.DataFrame()

    if master.empty:
        return pd.DataFrame()

    if "email" not in master.columns:
        master["email"] = ""

    master = master[
        master["email"].fillna("").astype(str).str.contains("@", regex=False)
    ].copy()

    if master.empty:
        return master

    master["label"] = (
        master["courier_name"].fillna("").astype(str)
        + " | #"
        + master["courier_id"].fillna("").astype(str)
        + " | "
        + master["email"].fillna("").astype(str)
    )
    return master.sort_values(
        ["courier_name", "courier_id"],
        kind="stable",
    )


def _selected_courier_from_form():
    user = st.session_state.get(
        "user",
        {},
    )
    actor_email = normalize_email(
        user.get("email") or user.get("username")
    )
    master = _courier_options()

    if master.empty:
        st.warning(
            "Nincs courier_master adat e-mail cimmel. Kezi e-mail megadasra valtottam."
        )
        email = st.text_input(
            "Futar e-mail",
            key="muszakpro_manual_email",
        )
        return {
            "email": normalize_email(email),
            "courier_name": clean(email),
            "courier_id": None,
        }, actor_email

    selected_label = st.selectbox(
        "Melyik futarnak foglalunk?",
        options=master["label"].tolist(),
        key="muszakpro_selected_courier",
    )
    row = master[
        master["label"] == selected_label
    ].iloc[0]

    return {
        "email": normalize_email(row.get("email")),
        "courier_name": clean(row.get("courier_name")),
        "name": clean(row.get("courier_name")),
        "courier_id": row.get("courier_id"),
        "warehouse": clean(row.get("warehouse_name")),
    }, actor_email


def _render_daily_booking_tab():
    st.subheader("Napi foglalas")
    selected_courier, actor_email = _selected_courier_from_form()
    col1, col2, col3 = st.columns([1, 1, 2])
    work_date = col1.date_input(
        "Datum",
        value=date.today(),
        key="muszakpro_daily_date",
    )
    warehouse = col2.selectbox(
        "Raktar",
        options=["Mind", "BUD1", "BUD2"],
        key="muszakpro_daily_warehouse",
    )

    with col3:
        st.info(
            f"Futar: {selected_courier.get('courier_name') or '-'} | "
            f"{selected_courier.get('email') or 'nincs e-mail'}"
        )

    if st.button(
        "Kapacitas frissitese a DB-bol",
        key="muszakpro_refresh",
        use_container_width=True,
    ):
        st.cache_data.clear()
        st.rerun()

    if not selected_courier.get("email"):
        st.error(
            "Foglalashoz kell e-mail cim. Eloszor a courier_master/Felhasznalok adatot javitsuk."
        )
        return

    try:
        daily = build_daily_shift_view(
            work_date,
            user_email=selected_courier.get("email"),
            warehouse_filter=warehouse,
        )
    except Exception as exc:
        st.error(
            f"MuszakPro napi adatok olvasasi hiba: {exc}"
        )
        return

    if daily.empty:
        st.warning(
            "Nincs megnyitott kapacitas erre a napra. Futtasd: python scripts\\load_muszakpro_capacity.py"
        )
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric(
        "Muszak",
        len(daily),
    )
    metric_cols[1].metric(
        "Ossz limit",
        int(daily["limit_count"].sum()),
    )
    metric_cols[2].metric(
        "Foglalt",
        int(daily["booked_count"].sum()),
    )
    metric_cols[3].metric(
        "Sajat foglalas",
        int(daily["is_mine"].sum()),
    )

    for warehouse_name, group in daily.groupby(
        "warehouse",
        sort=False,
    ):
        st.markdown(
            f"### {warehouse_name}"
        )
        rows = group.to_dict(
            "records"
        )

        for index in range(0, len(rows), 3):
            cols = st.columns(3)

            for col, row in zip(cols, rows[index:index + 3]):
                with col:
                    _render_shift_card(
                        row,
                        selected_courier,
                        actor_email,
                    )


def _render_bookings_tab(start_date, end_date):
    try:
        bookings = read_foglalasok_raw(
            start_date=start_date,
            end_date=end_date,
            limit=50000,
        )
    except Exception as exc:
        st.error(
            f"MuszakPro foglalas olvasasi hiba: {exc}"
        )
        return pd.DataFrame()

    if bookings.empty:
        st.info(
            "Nincs megjelenitheto foglalas."
        )
        return bookings

    names = sorted(
        name
        for name in bookings.get(
            "courier_name",
            pd.Series(dtype=str),
        ).dropna().unique()
        if str(name).strip()
    )
    warehouses = sorted(
        warehouse
        for warehouse in bookings.get(
            "warehouse",
            pd.Series(dtype=str),
        ).dropna().unique()
        if str(warehouse).strip()
    )

    filter_col1, filter_col2 = st.columns(2)
    selected_name = filter_col1.selectbox(
        "Futar",
        options=["Mind"] + names,
        key="muszakpro_name_filter",
    )
    selected_warehouse = filter_col2.selectbox(
        "Raktar",
        options=["Mind"] + warehouses,
        key="muszakpro_warehouse_filter",
    )

    visible_df = bookings.copy()

    if selected_name != "Mind":
        visible_df = visible_df[
            visible_df["courier_name"] == selected_name
        ]

    if selected_warehouse != "Mind":
        visible_df = visible_df[
            visible_df["warehouse"] == selected_warehouse
        ]

    st.dataframe(
        _format_dataframe(
            visible_df,
            [
                "work_date",
                "shift_text",
                "warehouse",
                "courier_name",
                "courier_id",
                "email",
                "booking_code",
                "serial",
                "fetched_at",
            ],
            {
                "work_date": "Datum",
                "shift_text": "Muszak",
                "warehouse": "Raktar",
                "courier_name": "Futar",
                "courier_id": "Courier ID",
                "email": "E-mail",
                "booking_code": "Foglalasi kod",
                "serial": "Sorszam",
                "fetched_at": "DB frissites",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )
    return bookings


def _render_events_tab(start_date, end_date):
    try:
        events = read_muszakpro_events(
            start_date=start_date,
            end_date=end_date,
            limit=5000,
        )
    except Exception as exc:
        st.warning(
            f"MuszakPro esemenynaplo nem olvashato: {exc}"
        )
        return

    if events.empty:
        st.info(
            "Meg nincs MuszakPro DB esemeny vagy az esemenytabla nincs letrehozva."
        )
        return

    st.dataframe(
        _format_dataframe(
            events,
            [
                "created_at",
                "action_type",
                "work_date",
                "shift_text",
                "warehouse",
                "email",
                "actor_email",
                "booking_code",
            ],
            {
                "created_at": "Idopont",
                "action_type": "Muvelet",
                "work_date": "Datum",
                "shift_text": "Muszak",
                "warehouse": "Raktar",
                "email": "Futar e-mail",
                "actor_email": "Muvelet vegzoje",
                "booking_code": "Foglalasi kod",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_capacity_tab(start_date, end_date):
    try:
        capacity = read_shift_capacity(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        st.error(
            f"Kapacitas tabla olvasasi hiba: {exc}"
        )
        return

    if capacity.empty:
        st.warning(
            "Meg nincs kapacitas adat a raw_muszakpro_shift_capacity tablaban."
        )
        return

    st.dataframe(
        _format_dataframe(
            capacity,
            [
                "work_date",
                "warehouse",
                "shift_text",
                "limit_count",
                "booked_count",
                "slack_quota",
                "active",
                "fetched_at",
            ],
            {
                "work_date": "Datum",
                "warehouse": "Raktar",
                "shift_text": "Muszak",
                "limit_count": "Limit",
                "booked_count": "Regi foglalt",
                "slack_quota": "Slack extra",
                "active": "Aktiv",
                "fetched_at": "DB frissites",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )


def show_muszakpro_page():
    st.title("MuszakPro")
    st.caption(
        "Sajat Python/Streamlit MuszakPro felulet Supabase alapon."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdo datum",
        value=today,
        key="muszakpro_start",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today + timedelta(days=10),
        key="muszakpro_end",
    )

    _render_setup_box()

    tab_daily, tab_bookings, tab_capacity, tab_events, tab_debug = st.tabs(
        [
            "Napi foglalas",
            "Foglalasok",
            "Kapacitas",
            "Esemenynaplo",
            "Ellenorzes",
        ]
    )

    with tab_daily:
        _render_daily_booking_tab()

    with tab_bookings:
        bookings = _render_bookings_tab(
            start_date,
            end_date,
        )

    with tab_capacity:
        _render_capacity_tab(
            start_date,
            end_date,
        )

    with tab_events:
        _render_events_tab(
            start_date,
            end_date,
        )

    with tab_debug:
        st.subheader("Gyors ellenorzes")
        st.markdown(
            """
- Foglalas tabla: `raw_muszakpro_bookings`
- Kapacitas tabla: `raw_muszakpro_shift_capacity`
- Esemeny tabla: `ops_muszakpro_events`
- Torlesnel nincs fizikai torles: a sor `status = CANCELLED` allapotot kap.
- A regi megosztott Google Sheetet a Python oldal csak importforraskent hasznalja.
"""
        )

        if "bookings" in locals() and not bookings.empty:
            missing_id_count = (
                bookings["courier_id"].isna().sum()
                if "courier_id" in bookings.columns
                else 0
            )
            missing_serial_count = (
                (bookings["serial"].fillna("").astype(str).str.strip() == "").sum()
                if "serial" in bookings.columns
                else 0
            )
            col1, col2 = st.columns(2)
            col1.metric(
                "Hianyzo courier ID",
                int(missing_id_count),
            )
            col2.metric(
                "Hianyzo sorszam",
                int(missing_serial_count),
            )
