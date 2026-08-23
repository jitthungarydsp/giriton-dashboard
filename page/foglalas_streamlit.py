from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
import sys

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_auto_booking import read_giriton_booking_log
from resources.giriton_shifts_db import read_giriton_shifts_raw
from resources.shift_comparison_db import read_next_5_day_shift_comparison


def _clean(value) -> str:
    return str(value or "").strip()


def _format_latest(value: str) -> str:
    text = _clean(value)
    if not text:
        return "-"

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y.%m.%d. %H:%M:%S")
    except ValueError:
        return text


def _latest(df: pd.DataFrame, column: str) -> str:
    if df.empty or column not in df.columns:
        return "-"

    values = [
        _clean(value)
        for value in df[column].dropna().astype(str).tolist()
        if _clean(value)
    ]
    return _format_latest(max(values)) if values else "-"


def _normalize_time(value) -> str:
    text = _clean(value)
    if not text:
        return ""

    parts = text.split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            return text

    return text


def _shift_start(shift_text) -> str:
    text = _clean(shift_text)
    if not text:
        return ""

    if "_" in text:
        return _normalize_time(text.split("_", 1)[1])

    match = re.search(r"(\d{1,2}:\d{2})", text)
    if match:
        return _normalize_time(match.group(1))

    return ""


def _parse_time(value) -> time | None:
    text = _normalize_time(value)
    if not text:
        return None

    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def _in_time_range(value, start_time: time, end_time: time) -> bool:
    parsed = _parse_time(value)
    if parsed is None:
        return True

    if start_time <= end_time:
        return start_time <= parsed <= end_time

    return parsed >= start_time or parsed <= end_time


def _filter_time(df: pd.DataFrame, column: str, start_time: time, end_time: time) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df

    return df[df[column].map(lambda value: _in_time_range(value, start_time, end_time))]


def _apply_worker(df: pd.DataFrame, worker: str) -> pd.DataFrame:
    if worker == "Összes dolgozó" or df.empty or "courier_name" not in df.columns:
        return df

    return df[df["courier_name"].fillna("").astype(str) == worker]


def _worker_options(*frames: pd.DataFrame) -> list[str]:
    names: set[str] = set()
    for df in frames:
        if not df.empty and "courier_name" in df.columns:
            names.update(
                _clean(value)
                for value in df["courier_name"].dropna().unique()
                if _clean(value)
            )

    return ["Összes dolgozó", *sorted(names)]


def _status_count(df: pd.DataFrame, value: str) -> int:
    if df.empty or "missing_source" not in df.columns:
        return 0

    has_missing = df["missing_source"].fillna("").astype(str).str.strip() != ""
    return int(has_missing.sum()) if value == "missing" else int((~has_missing).sum())


def _format_frame(df: pd.DataFrame, columns: list[str], labels: dict[str, str]) -> pd.DataFrame:
    visible_columns = [column for column in columns if column in df.columns]
    if not visible_columns:
        return pd.DataFrame()

    return df[visible_columns].rename(columns=labels)


def _display_table(df: pd.DataFrame, columns: list[str], labels: dict[str, str], empty_text: str) -> None:
    table = _format_frame(df, columns, labels)
    if table.empty:
        st.info(empty_text)
        return

    st.dataframe(table, width="stretch", hide_index=True)


def _muszakpro_columns() -> tuple[list[str], dict[str, str]]:
    return (
        [
            "work_date",
            "courier_name",
            "warehouse",
            "shift_text",
            "shift_start",
            "booking_code",
            "serial",
            "fetched_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_text": "MűszakPro műszak",
            "shift_start": "Kezdés",
            "booking_code": "Kód",
            "serial": "Sorszám",
            "fetched_at": "Frissítve",
        },
    )


def _giriton_columns() -> tuple[list[str], dict[str, str]]:
    return (
        [
            "work_date",
            "courier_name",
            "warehouse",
            "start_time",
            "end_time",
            "occupancy",
            "booked",
            "maximum",
            "status",
            "serial",
            "fetched_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "start_time": "Kezdés",
            "end_time": "Vége",
            "occupancy": "Foglaltság",
            "booked": "Foglalt",
            "maximum": "Maximum",
            "status": "Státusz",
            "serial": "Sorszám",
            "fetched_at": "Frissítve",
        },
    )


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f7f9fb; color: #151f2f; }
        [data-testid="stSidebar"] {
            background: #f1f6f8;
            border-right: 1px solid #dce5ea;
        }
        .block-container { padding-top: 1.2rem; max-width: 1500px; }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stButton"] button {
            border-radius: 7px;
            min-height: 42px;
            font-weight: 700;
        }
        .source-status {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 10px 0 18px;
        }
        .source-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: #ffffff;
            color: #344257;
            padding: 8px 11px;
            font-size: 0.9rem;
        }
        .source-chip strong { color: #172033; }
        .kpi {
            min-height: 92px;
            padding: 18px 20px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: white;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
        }
        .kpi-label { color: #536173; font-size: 0.95rem; margin-bottom: 8px; }
        .kpi-value { font-size: 2rem; font-weight: 760; color: #1d66c1; }
        .kpi-green .kpi-value { color: #18834b; }
        .kpi-red .kpi-value { color: #c42b2b; }
        .section-card {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
            margin-bottom: 12px;
        }
        .section-title {
            font-size: 1.12rem;
            font-weight: 760;
            color: #172033;
            margin-bottom: 2px;
        }
        .section-subtitle {
            color: #64748b;
            font-size: 0.9rem;
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_kpi(label: str, value: int, tone: str = "blue") -> None:
    st.markdown(
        f"""
        <div class="kpi kpi-{tone}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_next_5_days():
    return pd.DataFrame(read_next_5_day_shift_comparison(limit=20000))


@st.cache_data(show_spinner=False, ttl=300)
def _load_raw_data(start_date: date, end_date: date):
    muszakpro_df = read_foglalasok_raw(
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )
    giriton_df = read_giriton_shifts_raw(
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )
    log_df = read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=1000,
    )
    return muszakpro_df, giriton_df, log_df


def _sidebar() -> tuple[str, date, date, time, time]:
    st.sidebar.title("foglalas_streamlit.py")
    view = st.sidebar.radio(
        "Nézet",
        ["Összes", "Dolgozónként", "Eltérések", "Napló"],
        index=0,
        key="foglalas_view",
    )
    st.sidebar.divider()
    today = date.today()
    start_date = st.sidebar.date_input(
        "Kezdő dátum",
        value=today,
        key="foglalas_start_date",
    )
    end_date = st.sidebar.date_input(
        "Záró dátum",
        value=today + timedelta(days=5),
        key="foglalas_end_date",
    )
    st.sidebar.write("Időtartomány")
    start_col, end_col = st.sidebar.columns(2)
    start_time = start_col.time_input(
        "Kezdete",
        value=time(0, 0),
        step=900,
        key="foglalas_start_time",
    )
    end_time = end_col.time_input(
        "Vége",
        value=time(23, 59),
        step=900,
        key="foglalas_end_time",
    )
    st.sidebar.write("Források")
    st.sidebar.toggle("MűszakPro", value=True, disabled=True)
    st.sidebar.toggle("Giriton", value=True, disabled=True)
    if st.sidebar.button("Adatok újraolvasása", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    return view, start_date, end_date, start_time, end_time


def _render_source_tables(muszakpro_df: pd.DataFrame, giriton_df: pd.DataFrame) -> None:
    muszakpro_columns, muszakpro_labels = _muszakpro_columns()
    giriton_columns, giriton_labels = _giriton_columns()

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">MűszakPro adatok</div>
                <div class="section-subtitle">A MűszakPro-ból érkezett foglalt műszakok</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _display_table(
            muszakpro_df,
            muszakpro_columns,
            muszakpro_labels,
            "Nincs MűszakPro adat ebben a szűrésben.",
        )

    with right:
        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">Giriton adatok</div>
                <div class="section-subtitle">A Giriton rendszerből érkezett műszakok</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _display_table(
            giriton_df,
            giriton_columns,
            giriton_labels,
            "Nincs Giriton adat ebben a szűrésben.",
        )


def _render_worker_view(muszakpro_df: pd.DataFrame, giriton_df: pd.DataFrame) -> None:
    workers = _worker_options(muszakpro_df, giriton_df)
    worker = st.selectbox("Dolgozó részletes nézete", workers)
    _render_source_tables(
        _apply_worker(muszakpro_df, worker),
        _apply_worker(giriton_df, worker),
    )


def _render_differences(comparison_df: pd.DataFrame) -> None:
    if comparison_df.empty or "missing_source" not in comparison_df.columns:
        st.info("Nincs egyeztetési adat a következő 5 napra.")
        return

    has_missing = comparison_df["missing_source"].fillna("").astype(str).str.strip() != ""
    differences = comparison_df[has_missing]
    if differences.empty:
        st.success("A következő 5 nap egyeztetésében nincs eltérés.")
        return

    _display_table(
        differences,
        [
            "work_date",
            "courier_name",
            "warehouse",
            "shift_start",
            "shift_end",
            "giriton_status",
            "muszakpro_status",
            "missing_source",
            "updated_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_start": "Kezdés",
            "shift_end": "Vége",
            "giriton_status": "Giriton",
            "muszakpro_status": "MűszakPro",
            "missing_source": "Hiány",
            "updated_at": "Frissítve",
        },
        "Nincs eltérés ebben a szűrésben.",
    )


def _render_log(log_df: pd.DataFrame) -> None:
    if log_df.empty:
        st.info("Nincs napló ebben az időszakban.")
        return

    _display_table(
        log_df,
        [
            "created_at",
            "work_date",
            "courier_name",
            "warehouse",
            "shift_start",
            "status",
            "message",
            "serial",
        ],
        {
            "created_at": "Időpont",
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_start": "Kezdés",
            "status": "Státusz",
            "message": "Üzenet",
            "serial": "Sorszám",
        },
        "Nincs megjeleníthető napló.",
    )


def show_foglalas_streamlit_page() -> None:
    _apply_styles()
    view, start_date, end_date, start_time, end_time = _sidebar()

    if end_date < start_date:
        st.error("A záró dátum nem lehet korábbi, mint a kezdő dátum.")
        return

    try:
        comparison_df = _load_next_5_days()
        muszakpro_df, giriton_df, log_df = _load_raw_data(start_date, end_date)
    except Exception as exc:
        st.title("Műszak egyeztetés")
        st.error(f"DB olvasási hiba: {exc}")
        return

    if not muszakpro_df.empty:
        muszakpro_df = muszakpro_df.copy()
        muszakpro_df["shift_start"] = muszakpro_df.get(
            "shift_text",
            pd.Series(dtype=str),
        ).map(_shift_start)

    comparison_df = _filter_time(comparison_df, "shift_start", start_time, end_time)
    muszakpro_df = _filter_time(muszakpro_df, "shift_start", start_time, end_time)
    giriton_df = _filter_time(giriton_df, "start_time", start_time, end_time)

    st.title("Műszak egyeztetés")
    st.caption(
        f"Szűrt időszak: {start_date} - {end_date}, "
        f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}. "
        "Csak adatnézet, foglalás nincs bekötve."
    )
    st.markdown(
        f"""
        <div class="source-status">
            <div class="source-chip"><strong>MűszakPro</strong> utolsó frissítés: {_latest(muszakpro_df, "fetched_at")}</div>
            <div class="source-chip"><strong>Giriton</strong> utolsó frissítés: {_latest(giriton_df, "fetched_at")}</div>
            <div class="source-chip"><strong>Egyeztetés</strong> frissítve: {_latest(comparison_df, "updated_at")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _render_kpi("MűszakPro sor", len(muszakpro_df), "blue")
    with c2:
        _render_kpi("Giriton sor", len(giriton_df), "blue")
    with c3:
        _render_kpi("Egyező sor", _status_count(comparison_df, "ok"), "green")
    with c4:
        _render_kpi("Eltérés / hiány", _status_count(comparison_df, "missing"), "red")

    st.write("")
    if view == "Összes":
        _render_source_tables(muszakpro_df, giriton_df)
    elif view == "Dolgozónként":
        _render_worker_view(muszakpro_df, giriton_df)
    elif view == "Eltérések":
        _render_differences(comparison_df)
    else:
        _render_log(log_df)


if __name__ == "__main__":
    show_foglalas_streamlit_page()
