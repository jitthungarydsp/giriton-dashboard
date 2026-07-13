from calendar import monthrange
from datetime import date, timedelta
import html

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


def _inject_muszakpro_css():
    st.markdown(
        """
<style>
.mpro-shell {
    background: #f1f5f9;
    border: 1px solid #dbe3ef;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 18px 45px rgba(15, 23, 42, 0.12);
}
.mpro-header {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 16px 18px 12px;
}
.mpro-top {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
}
.mpro-logo {
    font-size: 26px;
    font-weight: 950;
    font-style: italic;
    letter-spacing: -1px;
    color: #0f172a;
}
.mpro-logo span {
    color: #2563eb;
}
.mpro-user-pill {
    max-width: 360px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: #f8fafc;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 900;
}
.mpro-layout {
    display: grid;
    grid-template-columns: minmax(290px, 350px) minmax(0, 1fr);
    gap: 0;
}
.mpro-side {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
    padding: 16px;
}
.mpro-main {
    padding: 18px;
}
.mpro-month-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}
.mpro-month-label {
    font-size: 13px;
    color: #2563eb;
    font-weight: 950;
    text-transform: uppercase;
}
.mpro-week-head,
.mpro-calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 4px;
}
.mpro-week-head div {
    text-align: center;
    font-size: 10px;
    color: #94a3b8;
    font-weight: 950;
    text-transform: uppercase;
}
.mpro-day-note {
    text-align: center;
    font-size: 9px;
    min-height: 14px;
    color: #2563eb;
    font-weight: 900;
    margin-top: -8px;
    margin-bottom: 4px;
}
.mpro-admin-box {
    margin-top: 14px;
    background: #f8fafc;
    border: 1px solid #dbe3ef;
    border-radius: 16px;
    padding: 12px;
}
.mpro-admin-title {
    font-size: 10px;
    font-weight: 950;
    color: #64748b;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.mpro-summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 16px;
}
.mpro-summary-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 12px;
}
.mpro-summary-card b {
    font-size: 22px;
    color: #0f172a;
}
.mpro-summary-card span {
    display: block;
    font-size: 10px;
    color: #64748b;
    font-weight: 900;
    text-transform: uppercase;
}
.mpro-shift-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(275px, 1fr));
    gap: 12px;
}
.mpro-shift-card {
    min-height: 94px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
}
.mpro-shift-card.mine {
    border: 2px solid #2563eb;
    background: #eff6ff;
}
.mpro-shift-card.waiting {
    border: 2px solid #f59e0b;
    background: #fffbeb;
}
.mpro-shift-card.conflict {
    opacity: 0.55;
    filter: grayscale(1);
}
.mpro-shift-card.expired {
    opacity: 0.62;
}
.mpro-shift-title {
    color: #0f172a;
    font-size: 16px;
    font-weight: 950;
    font-style: italic;
    text-transform: uppercase;
}
.mpro-shift-card.mine .mpro-shift-title {
    color: #2563eb;
}
.mpro-shift-meta {
    margin-top: 4px;
    color: #64748b;
    font-size: 11px;
    font-weight: 800;
}
.mpro-status {
    margin-top: 8px;
    font-size: 11px;
    font-weight: 950;
    text-transform: uppercase;
}
.mpro-status.ok { color: #2563eb; }
.mpro-status.wait { color: #b45309; }
.mpro-status.full { color: #1d4ed8; }
.mpro-status.bad { color: #991b1b; }
.mpro-action-note {
    margin-top: 10px;
    font-size: 10px;
    color: #64748b;
    font-weight: 700;
}
@media (max-width: 900px) {
    .mpro-layout {
        grid-template-columns: 1fr;
    }
    .mpro-side {
        border-right: none;
        border-bottom: 1px solid #e2e8f0;
    }
    .mpro-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
""",
        unsafe_allow_html=True,
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


def _month_name(month):
    names = [
        "Január",
        "Február",
        "Március",
        "Aprilis",
        "Május",
        "Junius",
        "Julius",
        "Augusztus",
        "Szeptember",
        "Október",
        "November",
        "December",
    ]
    return names[month - 1]


def _safe(value):
    return html.escape(
        str(value or "")
    )


def _calendar_month_bounds(month_date):
    first_day = date(
        month_date.year,
        month_date.month,
        1,
    )
    last_day = date(
        month_date.year,
        month_date.month,
        monthrange(month_date.year, month_date.month)[1],
    )
    return first_day, last_day


def _read_booking_day_counts(month_date, email):
    first_day, last_day = _calendar_month_bounds(
        month_date
    )

    try:
        bookings = read_foglalasok_raw(
            start_date=first_day,
            end_date=last_day,
            limit=50000,
        )
    except Exception:
        return {}

    if bookings.empty:
        return {}

    email_norm = normalize_email(
        email
    )

    if email_norm and "email" in bookings.columns:
        bookings = bookings[
            bookings["email"].fillna("").astype(str).map(normalize_email)
            == email_norm
        ]

    if bookings.empty or "work_date" not in bookings.columns:
        return {}

    counts = {}

    for work_date, group in bookings.groupby("work_date"):
        counts[str(work_date)[:10]] = len(group)

    return counts


def _render_wh_selector():
    selected = st.session_state.setdefault(
        "muszakpro_wh",
        "BUD1",
    )
    col1, col2 = st.columns(2)

    if col1.button(
        "BUD1",
        key="mpro_wh_bud1",
        type="primary" if selected == "BUD1" else "secondary",
        use_container_width=True,
    ):
        st.session_state["muszakpro_wh"] = "BUD1"
        st.rerun()

    if col2.button(
        "BUD2",
        key="mpro_wh_bud2",
        type="primary" if selected == "BUD2" else "secondary",
        use_container_width=True,
    ):
        st.session_state["muszakpro_wh"] = "BUD2"
        st.rerun()

    return st.session_state["muszakpro_wh"]


def _render_calendar_legacy(selected_date, selected_email):
    month_date = st.session_state.setdefault(
        "muszakpro_view_month",
        date(selected_date.year, selected_date.month, 1),
    )
    first_day, last_day = _calendar_month_bounds(
        month_date
    )
    counts = _read_booking_day_counts(
        month_date,
        selected_email,
    )

    col_prev, col_label, col_next = st.columns([1, 4, 1])

    if col_prev.button(
        "«",
        key="mpro_month_prev",
        use_container_width=True,
    ):
        prev_month = (first_day - timedelta(days=1)).replace(day=1)
        st.session_state["muszakpro_view_month"] = prev_month
        st.session_state["muszakpro_daily_date"] = prev_month
        st.rerun()

    col_label.markdown(
        f"<div class='mpro-month-label'>{_month_name(month_date.month)} {month_date.year}</div>",
        unsafe_allow_html=True,
    )

    if col_next.button(
        "»",
        key="mpro_month_next",
        use_container_width=True,
    ):
        next_month = (last_day + timedelta(days=1)).replace(day=1)
        st.session_state["muszakpro_view_month"] = next_month
        st.session_state["muszakpro_daily_date"] = next_month
        st.rerun()

    st.markdown(
        """
<div class="mpro-week-head">
  <div>He</div><div>Ke</div><div>Sze</div><div>Cs</div><div>Pe</div><div>Szo</div><div>Va</div>
</div>
""",
        unsafe_allow_html=True,
    )

    offset = first_day.weekday()
    days = [None] * offset + [
        date(month_date.year, month_date.month, day)
        for day in range(1, last_day.day + 1)
    ]

    while len(days) % 7 != 0:
        days.append(None)

    for row_index in range(0, len(days), 7):
        cols = st.columns(7)

        for col, day_value in zip(cols, days[row_index:row_index + 7]):
            if day_value is None:
                col.markdown("&nbsp;", unsafe_allow_html=True)
                continue

            day_key = day_value.isoformat()
            count = counts.get(
                day_key,
                0,
            )
            label = str(day_value.day)

            if count:
                label = f"{day_value.day}\n{count} műszak"

            if col.button(
                label,
                key=f"mpro_day_{day_key}",
                type="primary" if day_value == selected_date else "secondary",
                use_container_width=True,
            ):
                st.session_state["muszakpro_daily_date"] = day_value
                st.session_state["muszakpro_view_month"] = date(
                    day_value.year,
                    day_value.month,
                    1,
                )
                st.rerun()

            if count:
                col.markdown(
                    f"<div class='mpro-day-note'>{count} MUSZAK</div>",
                    unsafe_allow_html=True,
                )


def _render_calendar(selected_date, selected_email):
    month_date = st.session_state.setdefault(
        "muszakpro_view_month",
        date(selected_date.year, selected_date.month, 1),
    )
    first_day, last_day = _calendar_month_bounds(
        month_date
    )
    counts = _read_booking_day_counts(
        month_date,
        selected_email,
    )

    col_prev, col_label, col_next = st.columns([1, 4, 1])

    if col_prev.button(
        "‹",
        key="mpro_month_prev_clean",
        use_container_width=True,
    ):
        prev_month = (first_day - timedelta(days=1)).replace(day=1)
        st.session_state["muszakpro_view_month"] = prev_month
        st.session_state["muszakpro_daily_date"] = prev_month
        st.rerun()

    col_label.markdown(
        f"<div class='mpro-month-label'>{_month_name(month_date.month)} {month_date.year}</div>",
        unsafe_allow_html=True,
    )

    if col_next.button(
        "›",
        key="mpro_month_next_clean",
        use_container_width=True,
    ):
        next_month = (last_day + timedelta(days=1)).replace(day=1)
        st.session_state["muszakpro_view_month"] = next_month
        st.session_state["muszakpro_daily_date"] = next_month
        st.rerun()

    st.markdown(
        """
<div class="mpro-week-head">
  <div>He</div><div>Ke</div><div>Sze</div><div>Cs</div><div>Pe</div><div>Szo</div><div>Va</div>
</div>
""",
        unsafe_allow_html=True,
    )

    offset = first_day.weekday()
    days = [None] * offset + [
        date(month_date.year, month_date.month, day)
        for day in range(1, last_day.day + 1)
    ]

    while len(days) % 7 != 0:
        days.append(None)

    for row_index in range(0, len(days), 7):
        cols = st.columns(7)

        for col, day_value in zip(cols, days[row_index:row_index + 7]):
            if day_value is None:
                col.markdown("&nbsp;", unsafe_allow_html=True)
                continue

            day_key = day_value.isoformat()
            count = counts.get(
                day_key,
                0,
            )
            label = str(day_value.day)

            if count:
                label = f"{day_value.day}\n{count} műszak"

            if col.button(
                label,
                key=f"mpro_day_clean_{day_key}",
                type="primary" if day_value == selected_date else "secondary",
                use_container_width=True,
            ):
                st.session_state["muszakpro_daily_date"] = day_value
                st.session_state["muszakpro_view_month"] = date(
                    day_value.year,
                    day_value.month,
                    1,
                )
                st.rerun()

            if count:
                col.markdown(
                    f"<div class='mpro-day-note'>{count} MŰSZAK</div>",
                    unsafe_allow_html=True,
                )


def _render_summary_cards(daily):
    st.markdown(
        f"""
<div class="mpro-summary">
  <div class="mpro-summary-card"><b>{len(daily)}</b><span>Műszak</span></div>
  <div class="mpro-summary-card"><b>{int(daily["limit_count"].sum())}</b><span>Össz limit</span></div>
  <div class="mpro-summary-card"><b>{int(daily["booked_count"].sum())}</b><span>Foglalt</span></div>
  <div class="mpro-summary-card"><b>{int(daily["is_mine"].sum())}</b><span>Saját foglalás</span></div>
</div>
""",
        unsafe_allow_html=True,
    )


def _shift_card_class(row):
    classes = ["mpro-shift-card"]

    if bool(row.get("is_mine")):
        classes.append(
            "waiting" if bool(row.get("is_waiting")) else "mine"
        )

    if bool(row.get("conflict")):
        classes.append("conflict")

    if bool(row.get("is_expired")) and not bool(row.get("is_mine")):
        classes.append("expired")

    return " ".join(classes)


def _shift_status_text(row):
    is_mine = bool(row.get("is_mine"))
    is_waiting = bool(row.get("is_waiting"))
    is_expired = bool(row.get("is_expired"))
    conflict = bool(row.get("conflict"))
    booked = int(row.get("booked_count") or 0)
    limit = int(row.get("limit_count") or 0)

    if is_mine and is_waiting:
        return "VÁRÓLISTÁN VAGY", "wait"

    if is_mine:
        return "FIXÁLVA", "ok"

    if is_expired:
        return "MÁR ELMÚLT", "bad"

    if conflict:
        return "ÜTKÖZÉS - NEM FOGLALHATÓ", "bad"

    if booked >= limit:
        return f"{booked}/{limit} HELY - VÁRÓLISTA", "full"

    return f"{booked}/{limit} HELY", "ok"


def _render_shift_card(row, selected_courier, actor_email):
    shift_text = clean(row.get("shift_text"))
    warehouse = clean(row.get("warehouse"))
    work_date = clean(row.get("work_date"))
    is_mine = bool(row.get("is_mine"))
    booked_count = int(row.get("booked_count") or 0)
    limit_count = int(row.get("limit_count") or 0)
    free_count = int(row.get("free_count") or 0)
    booking_code = clean(row.get("booking_code"))
    status_text, status_class = _shift_status_text(
        row
    )
    disabled = bool(row.get("conflict")) or (
        bool(row.get("is_expired")) and not is_mine
    )
    action_label = "✕" if is_mine else ("🔨" if booked_count >= limit_count else "✓")

    st.markdown(
        f"""
<div class="{_shift_card_class(row)}">
  <div class="mpro-shift-title">{_safe(shift_text)}</div>
  <div class="mpro-shift-meta">{_safe(warehouse)} | {_safe(work_date)} | szabad: {free_count}</div>
  <div class="mpro-status {status_class}">{_safe(status_text)}</div>
  <div class="mpro-action-note">Kod: {_safe(booking_code or "-")} | Limit: {limit_count} | Foglalt: {booked_count}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if disabled:
        st.button(
            action_label,
            key=f"disabled_{work_date}_{warehouse}_{shift_text}_{selected_courier.get('email', '')}",
            use_container_width=True,
            disabled=True,
        )
        return

    if is_mine:
        if st.button(
            action_label,
            key=f"cancel_{work_date}_{warehouse}_{shift_text}_{selected_courier.get('email', '')}_{booking_code}",
            use_container_width=True,
            type="secondary",
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
            st.error(
                result.get("message")
            )
    else:
        if st.button(
            action_label,
            key=f"book_{work_date}_{warehouse}_{shift_text}_{selected_courier.get('email', '')}",
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
            st.error(
                result.get("message")
            )


def _render_legacy_shell_open(selected_courier):
    st.markdown(
        f"""
<div class="mpro-shell">
  <div class="mpro-header">
    <div class="mpro-top">
      <div class="mpro-logo">M&Uuml;SZAK<span>PRO</span></div>
      <div class="mpro-user-pill">{_safe(selected_courier.get("email") or "Betoltes...")}</div>
    </div>
  </div>
  <div class="mpro-layout">
    <div class="mpro-side">
</div>
""",
        unsafe_allow_html=True,
    )


def _render_shift_grid(daily, selected_courier, actor_email):
    rows = daily.to_dict(
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
    selected_courier, actor_email = _selected_courier_from_form()

    if "muszakpro_daily_date" not in st.session_state:
        st.session_state["muszakpro_daily_date"] = date.today()

    selected_date = st.session_state["muszakpro_daily_date"]

    if not hasattr(selected_date, "year"):
        selected_date = date.fromisoformat(
            str(selected_date)[:10]
        )
        st.session_state["muszakpro_daily_date"] = selected_date

    if "muszakpro_view_month" not in st.session_state:
        st.session_state["muszakpro_view_month"] = date(
            selected_date.year,
            selected_date.month,
            1,
        )

    st.markdown(
        f"""
<div class="mpro-shell">
  <div class="mpro-header">
    <div class="mpro-top">
      <div>
        <div class="mpro-logo">M&Uuml;SZAK<span>PRO</span></div>
        <div style="font-size:11px;color:#64748b;font-weight:800;margin-top:2px">
          Saját Python felület, a régi Google Sheet-es logikával.
        </div>
      </div>
      <div class="mpro-user-pill">{_safe(selected_courier.get("email") or "nincs e-mail")}</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    side, main = st.columns([0.32, 0.68])

    with side:
        warehouse = _render_wh_selector()
        _render_calendar(
            selected_date,
            selected_courier.get("email"),
        )
        st.markdown(
            "<div class='mpro-admin-box'><div class='mpro-admin-title'>Admin mód</div>",
            unsafe_allow_html=True,
        )
        jump_date = st.date_input(
            "Gyors dátum",
            value=selected_date,
            key="muszakpro_jump_date",
        )

        if jump_date != selected_date:
            st.session_state["muszakpro_daily_date"] = jump_date
            st.session_state["muszakpro_view_month"] = date(
                jump_date.year,
                jump_date.month,
                1,
            )
            st.rerun()

        st.markdown(
            f"""
<div style="font-size:11px;color:#64748b;font-weight:800;margin-top:8px">
  Fut&aacute;r: <b>{_safe(selected_courier.get("courier_name") or "-")}</b><br>
  E-mail: {_safe(selected_courier.get("email") or "-")}
</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with main:
        top_cols = st.columns([2, 1])
        top_cols[0].markdown(
            f"### {selected_date.isoformat()} | {warehouse}"
        )

        if top_cols[1].button(
            "Frissítés",
            key="muszakpro_refresh",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.rerun()

        if not selected_courier.get("email"):
            st.error(
                "Foglaláshoz kell e-mail cím. Először a courier_master/Felhasználók adatot javítsuk."
            )
            return

        try:
            daily = build_daily_shift_view(
                selected_date,
                user_email=selected_courier.get("email"),
                warehouse_filter=warehouse,
            )
        except Exception as exc:
            st.error(
                f"MűszakPro napi adatok olvasási hiba: {exc}"
            )
            return

        if daily.empty:
            st.warning(
                "Nincs megnyitott kapacitás erre a napra. Futtasd: python scripts\\load_muszakpro_capacity.py"
            )
            return

        daily = daily.sort_values(
            [
                "is_mine",
                "is_expired",
                "conflict",
                "booked_count",
                "start",
            ],
            ascending=[False, True, True, True, True],
            kind="stable",
        )
        _render_summary_cards(
            daily
        )
        _render_shift_grid(
            daily,
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
    _inject_muszakpro_css()
    st.title("MűszakPro")
    st.caption(
        "Saját Python/Streamlit MűszakPro felület Supabase alapon."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "Kezdő dátum",
        value=today,
        key="muszakpro_start",
    )
    end_date = col2.date_input(
        "Záró dátum",
        value=today + timedelta(days=10),
        key="muszakpro_end",
    )

    _render_setup_box()

    tab_daily, tab_bookings, tab_capacity, tab_events, tab_debug = st.tabs(
        [
            "Napi foglalás",
            "Foglalások",
            "Kapacitás",
            "Eseménynapló",
            "Ellenőrzés",
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
        st.subheader("Gyors ellenőrzés")
        st.markdown(
            """
- Foglalás tábla: `raw_muszakpro_bookings`
- Kapacitás tábla: `raw_muszakpro_shift_capacity`
- Esemény tábla: `ops_muszakpro_events`
- Törlésnél nincs fizikai törlés: a sor `status = CANCELLED` állapotot kap.
- A régi megosztott Google Sheetet a Python oldal csak importforrásként használja.
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
                "Hiányzó courier ID",
                int(missing_id_count),
            )
            col2.metric(
                "Hiányzó sorszám",
                int(missing_serial_count),
            )
