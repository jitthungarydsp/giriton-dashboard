from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Iterable

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class WorkerPlan:
    worker: str
    area: str
    planned: tuple[str, ...]
    booked: bool = False


@dataclass(frozen=True)
class MatchResult:
    worker: str
    area: str
    planned: tuple[str, ...]
    suggested: tuple[str, ...]
    offset_minutes: int | None
    status: str
    reason: str
    alternatives: tuple[tuple[str, ...], ...]
    booked: bool


PLANS = [
    WorkerPlan("Kovács László", "Budapest - Központ", ("06:15", "11:00", "16:00")),
    WorkerPlan("Nagy Anna", "Budapest - Dél", ("07:00", "12:00"), booked=False),
    WorkerPlan("Tóth Péter", "Győr", ("08:30",)),
    WorkerPlan("Szabó Éva", "Budapest - Nyugat", ("06:00", "14:00"), booked=True),
    WorkerPlan("Horváth Márk", "Szeged", ("13:00", "21:00")),
    WorkerPlan("Varga Zoltán", "Pécs", ("22:00",)),
    WorkerPlan("Kiss Nóra", "Debrecen", ("09:15", "15:15")),
    WorkerPlan("Farkas Dénes", "Miskolc", ("10:00", "18:00")),
]

GIRITON_AVAILABLE = {
    "Kovács László": ("06:00", "06:30", "10:45", "11:15", "15:45", "16:30"),
    "Nagy Anna": ("07:00", "12:00", "12:30"),
    "Tóth Péter": ("09:15", "10:00"),
    "Szabó Éva": ("06:00", "14:00"),
    "Horváth Márk": ("13:45", "21:45"),
    "Varga Zoltán": ("22:00",),
    "Kiss Nóra": ("09:00", "15:00", "15:45"),
    "Farkas Dénes": ("10:00", "17:30", "18:30"),
}


def now_label() -> str:
    return datetime.now().strftime("%Y.%m.%d. %H:%M:%S")


def ensure_refresh_state() -> None:
    initial = now_label()
    st.session_state.setdefault(
        "last_refresh",
        {
            "muszakproba": initial,
            "giriton": initial,
        },
    )
    st.session_state.setdefault("refresh_log", [])
    st.session_state.setdefault("auto_refresh_last_check", datetime.now())


def refresh_source(source: str) -> None:
    labels = {
        "muszakproba": "MűszakPro",
        "giriton": "Giriton",
    }
    refreshed_at = now_label()
    st.session_state.last_refresh[source] = refreshed_at
    st.session_state.refresh_log.insert(
        0,
        {
            "Időpont": refreshed_at,
            "Forrás": labels[source],
            "Esemény": "Kézi frissítés",
            "Állapot": "Sikeres",
        },
    )


def refresh_all_sources(event: str = "Kézi frissítés") -> None:
    refreshed_at = now_label()
    st.session_state.last_refresh["muszakproba"] = refreshed_at
    st.session_state.last_refresh["giriton"] = refreshed_at
    st.session_state.refresh_log.insert(
        0,
        {
            "Időpont": refreshed_at,
            "Forrás": "MűszakPro + Giriton",
            "Esemény": event,
            "Állapot": "Sikeres",
        },
    )


def maybe_auto_refresh(interval_minutes: int) -> None:
    last_check = st.session_state.auto_refresh_last_check
    elapsed = datetime.now() - last_check
    if elapsed >= timedelta(minutes=interval_minutes):
        refresh_all_sources("Automatikus frissítés")
        st.session_state.auto_refresh_last_check = datetime.now()


def parse_time(value: str) -> datetime:
    parsed = datetime.strptime(value, "%H:%M").time()
    return datetime.combine(date.today(), parsed)


def format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    if minutes == 0:
        return "0 perc"
    sign = "+" if minutes > 0 else ""
    return f"{sign}{minutes} perc"


def shift_time(value: str, minutes: int) -> str:
    return (parse_time(value) + timedelta(minutes=minutes)).strftime("%H:%M")


def diff_minutes(candidate: str, planned: str) -> int:
    return int((parse_time(candidate) - parse_time(planned)).total_seconds() / 60)


def is_in_time_range(value: str, start_time: time, end_time: time) -> bool:
    current = datetime.strptime(value, "%H:%M").time()
    if start_time <= end_time:
        return start_time <= current <= end_time
    return current >= start_time or current <= end_time


def apply_time_range(
    plans: list[WorkerPlan], start_time: time, end_time: time
) -> list[WorkerPlan]:
    filtered: list[WorkerPlan] = []
    for plan in plans:
        planned = tuple(
            item for item in plan.planned if is_in_time_range(item, start_time, end_time)
        )
        if planned:
            filtered.append(replace(plan, planned=planned))
    return filtered


def nearby_options(planned: str, available: Iterable[str], tolerance: int) -> list[str]:
    matches = [
        value
        for value in available
        if abs(diff_minutes(value, planned)) <= tolerance
    ]
    return sorted(matches, key=lambda item: (abs(diff_minutes(item, planned)), item))


def build_chained_match(plan: WorkerPlan, tolerance: int) -> MatchResult:
    available = tuple(GIRITON_AVAILABLE.get(plan.worker, ()))
    offset_candidates = sorted(
        {
            diff_minutes(candidate, plan.planned[0])
            for candidate in nearby_options(plan.planned[0], available, tolerance)
        },
        key=lambda value: (abs(value), value),
    )

    alternatives: list[tuple[str, ...]] = []
    for offset in offset_candidates:
        sequence = tuple(shift_time(item, offset) for item in plan.planned)
        if all(item in available for item in sequence):
            alternatives.append(sequence)

    if plan.booked:
        return MatchResult(
            worker=plan.worker,
            area=plan.area,
            planned=plan.planned,
            suggested=plan.planned,
            offset_minutes=0,
            status="Lefoglalva",
            reason="Már lefoglalt sorozat",
            alternatives=tuple(alternatives),
            booked=True,
        )

    if plan.planned and all(item in available for item in plan.planned):
        return MatchResult(
            worker=plan.worker,
            area=plan.area,
            planned=plan.planned,
            suggested=plan.planned,
            offset_minutes=0,
            status="Egyezés",
            reason="Pontos egyezés",
            alternatives=tuple(alternatives),
            booked=False,
        )

    if alternatives:
        best = alternatives[0]
        offset = diff_minutes(best[0], plan.planned[0])
        return MatchResult(
            worker=plan.worker,
            area=plan.area,
            planned=plan.planned,
            suggested=best,
            offset_minutes=offset,
            status="Alternatíva",
            reason="Láncolt eltolással foglalható",
            alternatives=tuple(alternatives),
            booked=False,
        )

    first_options = nearby_options(plan.planned[0], available, tolerance)
    reason = "Nincs Giriton műszak ±30 percen belül"
    if first_options:
        reason = "Ütköző láncolt eltolás"
    return MatchResult(
        worker=plan.worker,
        area=plan.area,
        planned=plan.planned,
        suggested=(),
        offset_minutes=None,
        status="Sikertelen",
        reason=reason,
        alternatives=tuple(),
        booked=False,
    )


def status_badge(status: str) -> str:
    colors = {
        "Egyezés": ("#e9f9ef", "#147a3d"),
        "Alternatíva": ("#fff5df", "#a15a00"),
        "Sikertelen": ("#fff0f0", "#c02121"),
        "Lefoglalva": ("#eaf2ff", "#155fc1"),
    }
    background, color = colors.get(status, ("#f4f5f7", "#243044"))
    return (
        f"<span class='status-pill' style='background:{background};"
        f"color:{color};border-color:{color}33'>{status}</span>"
    )


def result_rows(results: list[MatchResult]) -> list[dict[str, str]]:
    rows = []
    for item in results:
        action = {
            "Egyezés": "Foglalás",
            "Alternatíva": "Ellenőrzés",
            "Sikertelen": "Kézi döntés",
            "Lefoglalva": "Kész",
        }[item.status]
        rows.append(
            {
                "Dolgozó": item.worker,
                "MűszakPro": ", ".join(item.planned),
                "Giriton ajánlat": ", ".join(item.suggested) if item.suggested else "nincs találat",
                "Eltérés": format_minutes(item.offset_minutes),
                "Állapot": status_badge(item.status),
                "Következő lépés": f"<span class='action-pill action-{item.status.lower()}'>{action}</span>",
            }
        )
    return rows


def render_kpi(label: str, value: int, tone: str) -> None:
    st.markdown(
        f"""
        <div class="kpi kpi-{tone}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_timeline(result: MatchResult) -> None:
    planned = "".join(
        f"<div class='sequence-cell'><div class='time-card planned'>{item}</div></div>"
        for item in result.planned
    )
    suggested = "".join(
        f"<div class='sequence-cell'><div class='time-card suggested'>{item}<small>Elérhető</small></div></div>"
        for item in result.suggested
    )
    offset = format_minutes(result.offset_minutes)
    st.markdown(
        f"""
        <div class="timeline-card">
            <div class="timeline-title">Időpont egyeztetés</div>
            <div class="timeline-row">
                <div class="timeline-label">MűszakPro<br><span>tervezett</span></div>
                <div class="timeline-items timeline-grid">{planned}</div>
            </div>
            <div class="timeline-row">
                <div class="timeline-label">Giriton<br><span>elérhető</span></div>
                <div class="timeline-items timeline-grid">{suggested or "<div class='empty-state'>Nincs foglalható sorozat</div>"}</div>
            </div>
            <div class="shift-warning">Láncolt eltolás: {offset}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f7f9fb; color: #151f2f; }
        [data-testid="stSidebar"] { background: #f1f6f8; border-right: 1px solid #dce5ea; }
        h1, h2, h3 { letter-spacing: 0; }
        .block-container { padding-top: 1.1rem; max-width: 1480px; }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 14px 16px;
        }
        div[data-testid="stButton"] button {
            border-radius: 7px;
            min-height: 42px;
            font-weight: 700;
        }
        .kpi {
            min-height: 92px;
            padding: 18px 20px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: white;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
        }
        .kpi-label { color: #536173; font-size: 0.95rem; margin-bottom: 8px; }
        .kpi-value { font-size: 2rem; font-weight: 760; }
        .kpi-green .kpi-value { color: #18834b; }
        .kpi-amber .kpi-value { color: #c27605; }
        .kpi-red .kpi-value { color: #c42b2b; }
        .kpi-blue .kpi-value { color: #1d66c1; }
        .section-card, .timeline-card {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 18px 20px;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
        }
        .timeline-title { font-weight: 760; font-size: 1.25rem; margin-bottom: 16px; }
        .timeline-row { display: grid; grid-template-columns: 116px 1fr; gap: 14px; align-items: center; margin: 14px 0; }
        .timeline-label { font-weight: 700; color: #1f2a3a; }
        .timeline-label span { font-weight: 500; color: #667386; }
        .timeline-items { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
        .timeline-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(92px, 1fr));
            gap: 12px;
            max-width: 520px;
        }
        .sequence-cell {
            position: relative;
            display: flex;
            justify-content: center;
        }
        .sequence-cell:not(:last-child)::after {
            content: "";
            position: absolute;
            top: 50%;
            right: -12px;
            width: 12px;
            height: 2px;
            background: #9fb5c5;
        }
        .time-card {
            width: 100%;
            min-width: 92px;
            min-height: 58px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            font-size: 1.35rem;
            font-weight: 760;
        }
        .planned { border: 1px solid #1f66d1; color: #155fc1; background: #f6faff; }
        .suggested { border: 1px solid #28a15b; color: #147a3d; background: #f3fbf5; }
        .suggested small { font-size: 0.72rem; margin-top: 4px; font-weight: 650; }
        .shift-warning {
            display: inline-block;
            margin-top: 8px;
            padding: 8px 14px;
            border: 1px solid #e4a62d;
            border-radius: 8px;
            color: #925000;
            background: #fff7e8;
            font-weight: 700;
        }
        .status-pill {
            display: inline-block;
            padding: 4px 10px;
            border: 1px solid;
            border-radius: 8px;
            font-weight: 700;
            min-width: 84px;
            text-align: center;
        }
        .action-pill {
            display: inline-block;
            min-width: 86px;
            text-align: center;
            border-radius: 7px;
            padding: 5px 10px;
            border: 1px solid #0796a3;
            color: #057783;
            background: #f0fbfc;
            font-weight: 750;
        }
        .action-sikertelen {
            border-color: #dc4b4b;
            color: #c02121;
            background: #fff5f5;
        }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            overflow: hidden;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: #ffffff;
            font-size: 0.94rem;
        }
        th {
            background: #f3f7f9;
            color: #263246;
            font-weight: 760;
            text-align: left;
            padding: 10px 11px;
            border-bottom: 1px solid #dce5ea;
            font-size: 0.85rem;
        }
        td {
            padding: 10px 11px;
            border-bottom: 1px solid #e7edf1;
            color: #172033;
            vertical-align: middle;
            word-break: normal;
        }
        tr:last-child td { border-bottom: 0; }
        .summary-box {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 18px;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
        }
        .summary-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 9px 0;
            border-bottom: 1px solid #edf2f5;
        }
        .summary-row:last-child { border-bottom: 0; }
        .summary-row strong { font-size: 1.1rem; }
        .summary-green { color: #18834b; }
        .summary-amber { color: #c27605; }
        .summary-red { color: #c42b2b; }
        .source-status {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 6px 0 12px;
        }
        .source-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: #ffffff;
            color: #344257;
            padding: 7px 10px;
            font-size: 0.9rem;
        }
        .source-chip strong { color: #172033; }
        .empty-state { color: #8a1f1f; font-weight: 700; }
        .small-muted { color: #64748b; font-size: 0.92rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar() -> tuple[str, int, list[str], str, time, time]:
    ensure_refresh_state()
    st.sidebar.title("foglalas_streamlit.py")
    pending_view = st.session_state.pop("pending_view", None)
    if pending_view:
        st.session_state.view_picker = pending_view
    view = st.sidebar.radio(
        "Nézet",
        ["Összes", "Dolgozónként", "Sikertelenek", "Napló"],
        index=0,
        key="view_picker",
    )
    st.sidebar.divider()
    st.sidebar.date_input("Dátum", value=date(2025, 5, 21))
    st.sidebar.write("Adatfrissítés")
    auto_refresh = st.sidebar.toggle("Automatikus frissítés", value=True)
    refresh_interval = st.sidebar.number_input(
        "Frissítési időköz (perc)",
        min_value=1,
        max_value=120,
        value=5,
        step=1,
    )
    if auto_refresh:
        maybe_auto_refresh(int(refresh_interval))
    st.sidebar.caption(
        f"MűszakPro: {st.session_state.last_refresh['muszakproba']}"
    )
    st.sidebar.caption(f"Giriton: {st.session_state.last_refresh['giriton']}")
    refresh_col_1, refresh_col_2 = st.sidebar.columns(2)
    with refresh_col_1:
        if st.button("MűszakPro", width="stretch"):
            refresh_source("muszakproba")
            st.rerun()
    with refresh_col_2:
        if st.button("Giriton", width="stretch"):
            refresh_source("giriton")
            st.rerun()
    if st.sidebar.button("Mindkettő frissítése", width="stretch"):
        refresh_all_sources()
        st.rerun()
    st.sidebar.write("Időtartomány")
    range_start, range_end = st.sidebar.columns(2)
    with range_start:
        start_time = st.time_input("Kezdete", value=time(0, 0), step=900)
    with range_end:
        end_time = st.time_input("Vége", value=time(23, 59), step=900)
    selected_worker = st.sidebar.selectbox(
        "Dolgozó",
        ["Összes dolgozó", *[plan.worker for plan in PLANS]],
    )
    st.sidebar.write("Források")
    st.sidebar.toggle("MűszakPro", value=True)
    st.sidebar.toggle("Giriton", value=True)
    tolerance = st.sidebar.slider("Eltérés: ±30 perc", 5, 120, 30, step=5)
    st.sidebar.divider()
    st.sidebar.write("Foglalási állapot")
    selected_statuses = []
    for status in ["Egyezés", "Alternatíva", "Sikertelen", "Lefoglalva"]:
        if st.sidebar.checkbox(status, value=True):
            selected_statuses.append(status)
    if st.sidebar.button("Frissítés", width="stretch"):
        refresh_all_sources()
        st.rerun()
    return view, tolerance, selected_statuses, selected_worker, start_time, end_time


def filtered_results(
    results: list[MatchResult], statuses: list[str], selected_worker: str
) -> list[MatchResult]:
    filtered = [item for item in results if item.status in statuses]
    if selected_worker != "Összes dolgozó":
        filtered = [item for item in filtered if item.worker == selected_worker]
    return filtered


def render_result_table(results: list[MatchResult]) -> None:
    rows = result_rows(results)
    table = pd.DataFrame(rows)
    if table.empty:
        st.info("Nincs megjeleníthető sor ebben a szűrésben.")
        return
    st.markdown(table.to_html(escape=False, index=False), unsafe_allow_html=True)


def render_mass_view(results: list[MatchResult]) -> None:
    total_bookable = len([item for item in results if item.status == "Egyezés"])
    already_done = len([item for item in results if item.status == "Lefoglalva"])
    exact_target = total_bookable + already_done
    progress_value = min(already_done / max(exact_target, 1), 1.0)

    top, side = st.columns([4.2, 1.35], gap="large")
    with top:
        st.markdown("## Tömeges foglalás")
        st.caption("Egyező műszakok automatikus foglalása, problémás esetek külön listában")
        st.progress(
            progress_value,
            text=f"Folyamatban: {already_done} / {exact_target} lefoglalva",
        )
        st.markdown("### Összesített foglalási lista")
        render_result_table(results)
        st.markdown("### Sikertelen foglalások")
        failed = [item for item in results if item.status == "Sikertelen"]
        if failed:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Dolgozó": item.worker,
                        "MűszakPro": ", ".join(item.planned),
                        "Giriton ajánlat": "nincs találat",
                        "Ok": item.reason,
                        "Javasolt lépés": "Kézi döntés",
                    }
                    for item in failed
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("Nincs sikertelen foglalás.")

    with side:
        st.markdown("### Tömeges művelet")
        alternative_count = len([item for item in results if item.status == "Alternatíva"])
        failed_count = len([item for item in results if item.status == "Sikertelen"])
        st.markdown(
            f"""
            <div class="summary-box">
                <div class="summary-row"><span>Foglalható egyezések</span><strong class="summary-green">{total_bookable}</strong></div>
                <div class="summary-row"><span>Alternatívával foglalható</span><strong class="summary-amber">{alternative_count}</strong></div>
                <div class="summary-row"><span>Sikertelen</span><strong class="summary-red">{failed_count}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        exact_only = st.checkbox("Csak pontos egyezéseket foglaljon", value=True)
        approve_alternatives = st.checkbox("Alternatívákat külön jóváhagyással", value=True)
        st.checkbox("Sikerteleneket tegye külön szűrőbe", value=True)
        if st.button("Tömeges foglalás indítása", type="primary", width="stretch"):
            bookable_statuses = {"Egyezés"}
            if not exact_only and not approve_alternatives:
                bookable_statuses.add("Alternatíva")
            booked_workers = set(st.session_state.get("booked_workers", set()))
            booked_workers.update(item.worker for item in results if item.status in bookable_statuses)
            st.session_state.booked_workers = booked_workers
            st.toast("A foglalható egyezések lefoglalva.")
            st.rerun()
        if st.button("Sikertelenek megnyitása", width="stretch"):
            st.session_state.pending_view = "Sikertelenek"
            st.rerun()
        st.info("A tömeges foglalás során az egyező műszakok automatikusan lefoglalásra kerülnek a Giriton rendszerben.")


def render_worker_view(results: list[MatchResult]) -> None:
    if not results:
        st.info("Ebben az időtartományban nincs egyeztethető műszak.")
        return
    worker = st.selectbox("Dolgozó részletes egyeztetése", [item.worker for item in results])
    selected = next(item for item in results if item.worker == worker)
    left, right = st.columns([2.2, 1], gap="large")
    with left:
        render_timeline(selected)
        st.markdown("### Javasolt foglalási terv")
        rows = []
        for index, planned in enumerate(selected.planned, start=1):
            suggested = selected.suggested[index - 1] if index <= len(selected.suggested) else "-"
            rows.append(
                {
                    "Sorrend": index,
                    "MűszakPro idő": planned,
                    "Giriton ajánlat": suggested,
                    "Eltérés": format_minutes(diff_minutes(suggested, planned)) if suggested != "-" else "-",
                    "Státusz": "Ajánlott" if index == 1 else "Eltolva",
                    "Művelet": "Foglalás" if suggested != "-" else "Kézi döntés",
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with right:
        st.markdown("### Ajánlott megoldás")
        if selected.status in {"Egyezés", "Alternatíva", "Lefoglalva"}:
            st.success("Teljes sorozat foglalható")
            st.write(f"Eltolás: {format_minutes(selected.offset_minutes)}")
            st.write("Szabály: előtte/utána 30 perc")
            st.write(f"Eredeti: {', '.join(selected.planned)}")
            st.write(f"Giriton: {', '.join(selected.suggested)}")
            st.button("Teljes sorozat foglalása", type="primary", width="stretch")
        else:
            st.error(selected.reason)
            st.button("Kézi döntés", width="stretch")
        st.button("Alternatívák megnyitása", width="stretch")


def render_failed_view(results: list[MatchResult]) -> None:
    st.markdown("## Sikertelenek")
    failed = [item for item in results if item.status == "Sikertelen"]
    if not failed:
        st.success("Nincs sikertelen foglalás.")
        return
    st.dataframe(
        pd.DataFrame(
            {
                "Dolgozó": item.worker,
                "Terület": item.area,
                "MűszakPro": ", ".join(item.planned),
                "Ok": item.reason,
                "Javasolt lépés": "Kézi döntés",
            }
            for item in failed
        ),
        width="stretch",
        hide_index=True,
    )


def render_log_view(results: list[MatchResult]) -> None:
    st.markdown("## Napló")
    now = datetime.combine(date.today(), time(9, 14))
    log_rows = list(st.session_state.get("refresh_log", []))
    for index, item in enumerate(results, start=1):
        log_rows.append(
            {
                "Időpont": (now - timedelta(minutes=index * 2)).strftime("%Y.%m.%d. %H:%M:%S"),
                "Dolgozó": item.worker,
                "Esemény": item.reason,
                "Állapot": item.status,
            }
        )
    st.dataframe(pd.DataFrame(log_rows), width="stretch", hide_index=True)


def show_foglalas_streamlit_page() -> None:
    apply_styles()
    ensure_refresh_state()
    st.session_state.setdefault(
        "booked_workers",
        {plan.worker for plan in PLANS if plan.booked},
    )
    view, tolerance, selected_statuses, selected_worker, start_time, end_time = sidebar()
    effective_plans = [
        replace(plan, booked=plan.booked or plan.worker in st.session_state.booked_workers)
        for plan in PLANS
    ]
    effective_plans = apply_time_range(effective_plans, start_time, end_time)
    results = [build_chained_match(plan, tolerance) for plan in effective_plans]
    results = filtered_results(results, selected_statuses, selected_worker)

    st.title("Műszak egyeztetés")
    st.caption(f"Szűrt időtartomány: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
    st.markdown(
        f"""
        <div class="source-status">
            <div class="source-chip"><strong>MűszakPro</strong> utolsó frissítés: {st.session_state.last_refresh['muszakproba']}</div>
            <div class="source-chip"><strong>Giriton</strong> utolsó frissítés: {st.session_state.last_refresh['giriton']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi("Dolgozók", len({item.worker for item in results}), "blue")
    with c2:
        render_kpi("Műszakok", sum(len(item.planned) for item in results), "blue")
    with c3:
        render_kpi("Egyezés", len([item for item in results if item.status == "Egyezés"]), "green")
    with c4:
        render_kpi("Sikertelen", len([item for item in results if item.status == "Sikertelen"]), "red")
    with c5:
        render_kpi("Lefoglalva", len([item for item in results if item.status == "Lefoglalva"]), "blue")

    st.write("")
    if view == "Összes":
        render_mass_view(results)
    elif view == "Dolgozónként":
        render_worker_view(results)
    elif view == "Sikertelenek":
        render_failed_view(results)
    else:
        render_log_view(results)


def main() -> None:
    st.set_page_config(
        page_title="foglalas_streamlit.py",
        page_icon="calendar",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    show_foglalas_streamlit_page()


if __name__ == "__main__":
    main()

