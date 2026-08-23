from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re

import pandas as pd
import streamlit as st

from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_auto_booking import read_giriton_booking_log
from resources.giriton_shifts_db import read_giriton_shifts_raw
from resources.shift_comparison_db import read_next_5_day_shift_comparison


def _clean(value) -> str:
    return str(value or "").strip()


def _parse_time(value) -> time | None:
    text = _clean(value)
    if not text:
        return None

    for date_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text[:8], date_format).time()
        except ValueError:
            pass

    return None


def _normalize_time(value) -> str:
    text = _clean(value)
    if not text:
        return ""

    parts = text.split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0])}:{int(parts[1]):02d}"
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


def _in_time_range(value, start_time: time, end_time: time) -> bool:
    parsed = _parse_time(value)
    if parsed is None:
        return True

    if start_time <= end_time:
        return start_time <= parsed <= end_time

    return parsed >= start_time or parsed <= end_time


def _latest(df: pd.DataFrame, column: str) -> str:
    if df.empty or column not in df.columns:
        return "-"

    values = [
        _clean(value)
        for value in df[column].dropna().astype(str).tolist()
        if _clean(value)
    ]
    return max(values) if values else "-"


def _filter_time(df: pd.DataFrame, column: str, start_time: time, end_time: time) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df

    return df[df[column].map(lambda value: _in_time_range(value, start_time, end_time))]


def _apply_worker(df: pd.DataFrame, worker: str) -> pd.DataFrame:
    if worker == "Összes dolgozó" or df.empty or "courier_name" not in df.columns:
        return df

    return df[df["courier_name"].fillna("").astype(str) == worker]


def _display(df: pd.DataFrame, columns: list[str], labels: dict[str, str]) -> None:
    visible_columns = [column for column in columns if column in df.columns]
    if not visible_columns:
        st.info("Nincs megjeleníthető oszlop.")
        return

    st.dataframe(
        df[visible_columns].rename(columns=labels),
        width="stretch",
        hide_index=True,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_next_5_days():
    return pd.DataFrame(
        read_next_5_day_shift_comparison(limit=20000)
    )


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


def _missing_count(df: pd.DataFrame) -> int:
    if df.empty or "missing_source" not in df.columns:
        return 0

    return int(
        (
            df["missing_source"]
            .fillna("")
            .astype(str)
            .str.strip()
            != ""
        ).sum()
    )


def _ok_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    giriton_ok = (
        df.get("giriton_status", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .str.upper()
        == "OK"
    )
    muszakpro_ok = (
        df.get("muszakpro_status", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .str.upper()
        == "OK"
    )
    return int((giriton_ok & muszakpro_ok).sum())


def show_foglalas_streamlit_page() -> None:
    st.title("Foglalás egyeztetés")
    st.caption(
        "Csak olvasós adatnézet. A következő 5 nap MűszakPro és Giriton adatai látszanak, foglalás nincs bekötve."
    )

    today = date.today()
    raw_start = st.sidebar.date_input(
        "Nyers adatok kezdő dátuma",
        value=today,
        key="foglalas_raw_start",
    )
    raw_end = st.sidebar.date_input(
        "Nyers adatok záró dátuma",
        value=today + timedelta(days=5),
        key="foglalas_raw_end",
    )
    st.sidebar.write("Időtartomány")
    col_start, col_end = st.sidebar.columns(2)
    start_time = col_start.time_input(
        "Kezdete",
        value=time(0, 0),
        step=900,
        key="foglalas_start_time",
    )
    end_time = col_end.time_input(
        "Vége",
        value=time(23, 59),
        step=900,
        key="foglalas_end_time",
    )

    if st.sidebar.button("Adatok újraolvasása", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    if raw_end < raw_start:
        st.error("A záró dátum nem lehet korábbi, mint a kezdő dátum.")
        return

    try:
        comparison_df = _load_next_5_days()
        muszakpro_df, giriton_df, log_df = _load_raw_data(raw_start, raw_end)
    except Exception as exc:
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

    worker = st.sidebar.selectbox(
        "Dolgozó",
        _worker_options(comparison_df, muszakpro_df, giriton_df),
    )
    comparison_df = _apply_worker(comparison_df, worker)
    muszakpro_df = _apply_worker(muszakpro_df, worker)
    giriton_df = _apply_worker(giriton_df, worker)

    status_filter = st.sidebar.multiselect(
        "Egyeztetés állapot",
        ["OK", "Eltérés / hiány"],
        default=["OK", "Eltérés / hiány"],
    )
    if not comparison_df.empty and status_filter != ["OK", "Eltérés / hiány"]:
        has_missing = (
            comparison_df.get("missing_source", pd.Series(dtype=str))
            .fillna("")
            .astype(str)
            .str.strip()
            != ""
        )
        if status_filter == ["OK"]:
            comparison_df = comparison_df[~has_missing]
        elif status_filter == ["Eltérés / hiány"]:
            comparison_df = comparison_df[has_missing]

    source_col1, source_col2, source_col3 = st.columns(3)
    source_col1.info(f"MűszakPro utolsó frissítés: {_latest(muszakpro_df, 'fetched_at')}")
    source_col2.info(f"Giriton utolsó frissítés: {_latest(giriton_df, 'fetched_at')}")
    source_col3.info(f"Egyeztetés frissítve: {_latest(comparison_df, 'updated_at')}")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Következő 5 nap sor", len(comparison_df))
    metric2.metric("Teljes egyezés", _ok_count(comparison_df))
    metric3.metric("Eltérés / hiány", _missing_count(comparison_df))
    metric4.metric("Giriton nyers sor", len(giriton_df))

    tab_compare, tab_muszakpro, tab_giriton, tab_log = st.tabs(
        [
            "Következő 5 nap",
            "MűszakPro adatok",
            "Giriton adatok",
            "Napló",
        ]
    )

    with tab_compare:
        if comparison_df.empty:
            st.info("Nincs egyeztetési adat a következő 5 napra ebben a szűrésben.")
        else:
            _display(
                comparison_df,
                [
                    "work_date",
                    "courier_name",
                    "email",
                    "warehouse",
                    "shift_start",
                    "shift_end",
                    "giriton_status",
                    "muszakpro_status",
                    "missing_source",
                    "giriton_check",
                    "muszakpro_booking_code",
                    "updated_at",
                ],
                {
                    "work_date": "Dátum",
                    "courier_name": "Dolgozó",
                    "email": "E-mail",
                    "warehouse": "Raktár",
                    "shift_start": "Kezdés",
                    "shift_end": "Vége",
                    "giriton_status": "Giriton",
                    "muszakpro_status": "MűszakPro",
                    "missing_source": "Hiányzó forrás",
                    "giriton_check": "Giriton ellenőrzés",
                    "muszakpro_booking_code": "MűszakPro kód",
                    "updated_at": "Frissítve",
                },
            )

    with tab_muszakpro:
        if muszakpro_df.empty:
            st.info("Nincs MűszakPro adat ebben a szűrésben.")
        else:
            _display(
                muszakpro_df,
                [
                    "work_date",
                    "courier_name",
                    "email",
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
                    "email": "E-mail",
                    "warehouse": "Raktár",
                    "shift_text": "Műszak",
                    "shift_start": "Kezdés",
                    "booking_code": "Foglalási kód",
                    "serial": "Sorszám",
                    "fetched_at": "DB frissítés",
                },
            )

    with tab_giriton:
        if giriton_df.empty:
            st.info("Nincs Giriton adat ebben a szűrésben.")
        else:
            _display(
                giriton_df,
                [
                    "work_date",
                    "courier_name",
                    "email",
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
                    "email": "E-mail",
                    "warehouse": "Raktár",
                    "start_time": "Kezdés",
                    "end_time": "Vége",
                    "occupancy": "Foglaltság",
                    "booked": "Foglalt",
                    "maximum": "Maximum",
                    "status": "Státusz",
                    "serial": "Sorszám",
                    "fetched_at": "DB frissítés",
                },
            )

    with tab_log:
        if log_df.empty:
            st.info("Nincs auto booking napló ebben az időszakban.")
        else:
            _display(
                log_df,
                [
                    "created_at",
                    "work_date",
                    "courier_name",
                    "email",
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
                    "email": "E-mail",
                    "warehouse": "Raktár",
                    "shift_start": "Kezdés",
                    "status": "Státusz",
                    "message": "Üzenet",
                    "serial": "Sorszám",
                },
            )
