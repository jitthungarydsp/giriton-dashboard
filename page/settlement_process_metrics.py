"""Persisted, management-only PWA cards for the monthly settlement process."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from resources.peopleforce_documents import require_supabase, supabase_headers


SUMMARY_SCHEMA = "settlement"
SUMMARY_TABLE = "monthly_process_metric_summary"
DETAIL_TABLE = "courier_monthly_process_metric"
FINANCIAL_COMPLAINT_TYPES = {
    "settlement",
    "tig",
    "invoice",
    "invoice_submit",
    "invoice_check",
}
METRIC_ROLES = {"admin", "superadmin", "finance", "accountant", "bookkeeper", "pénzügy", "könyvelő"}
HUNGARIAN_MONTHS = (
    "január", "február", "március", "április", "május", "június",
    "július", "augusztus", "szeptember", "október", "november", "december",
)
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
ANSWERED_COMPLAINT_STATUSES = {"closed", "resolved"}


def can_view_settlement_process_metrics(user: dict[str, Any] | None) -> bool:
    return str((user or {}).get("role") or "").strip().casefold() in METRIC_ROLES


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    text = text.replace("Ft", "").replace("HUF", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_huf(value: object) -> str:
    return f"{int(round(_number(value))):,} Ft".replace(",", " ")


def _api_headers(schema: str | None = None, *, write: bool = False) -> dict[str, str]:
    headers = dict(supabase_headers(prefer_return=write))
    if schema:
        headers["Accept-Profile"] = schema
        if write:
            headers["Content-Profile"] = schema
    return headers


def _read_rows(table: str, *, schema: str | None = None, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    query = dict(params or {})
    requested_limit = int(query.pop('limit', 100000))
    rows = []
    while len(rows) < requested_limit:
        size = min(500, requested_limit - len(rows))
        response = requests.get(
            f"{require_supabase().rstrip('/')}/rest/v1/{table}",
            headers=_api_headers(schema),
            params={**query, 'order': query.get('order', {'monthly_process_metric_summary':'period_start.asc','courier_monthly_process_metric':'courier_metric_id.asc','vw_courier_month_profile_snapshot':'courier_id.asc','mobile_settlement_period_config':'period_start.asc'}.get(table, 'id.asc')), 'limit': size, 'offset': len(rows)},
            timeout=60,
        )
        response.raise_for_status()
        batch = response.json() or []
        rows.extend(batch)
        if len(batch) < size:
            break
    return rows


def _read_one_summary(period_start: date) -> dict[str, Any] | None:
    rows = _read_rows(
        SUMMARY_TABLE,
        schema=SUMMARY_SCHEMA,
        params={
            "select": "*",
            "period_start": f"eq.{_month_start(period_start).isoformat()}",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def _first_after(rows: list[dict[str, Any]], key: str, after: datetime | None) -> dict[str, Any] | None:
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        event_at = _timestamp(row.get(key))
        if event_at is not None and (after is None or event_at >= after):
            candidates.append((event_at, row))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _group_by_courier(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        courier_id = str(row.get("courier_id") or "").strip()
        if courier_id:
            grouped.setdefault(courier_id, []).append(row)
    return grouped


def _hours_between(start: object, end: object) -> float | None:
    start_at = _timestamp(start)
    end_at = _timestamp(end)
    if start_at is None or end_at is None:
        return None
    hours = (end_at - start_at).total_seconds() / 3600
    return hours if hours >= 0 else None


def _duration_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "average_hours": sum(values) / len(values) if values else 0.0,
        "median_hours": float(median(values)) if values else 0.0,
    }


def _complaint_is_answered(row: dict[str, Any]) -> bool:
    """Return the business outcome, not merely whether a response timestamp exists.

    PeopleForce historically stored many completed answers as ``closed`` or
    ``resolved`` without filling ``responded_at`` / ``admin_response``.  Those
    records are answered complaints too.  The timestamp is still used only for
    calculating a measurable response duration.
    """
    status = str(row.get("status") or "").strip().casefold()
    return (
        status in ANSWERED_COMPLAINT_STATUSES
        or _timestamp(row.get("responded_at")) is not None
        or bool(str(row.get("admin_response") or "").strip())
    )


def calculate_monthly_process_metric_bundle(period_start: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rebuild all courier-month rows and their exact monthly roll-up."""
    from resources.settlement_metric_repository import load_bundle
    return load_bundle(_month_start(period_start).isoformat(), _read_rows)


def calculate_monthly_process_metrics(period_start: date) -> dict[str, Any]:
    """Backward-compatible monthly roll-up calculation."""
    summary, _details = calculate_monthly_process_metric_bundle(period_start)
    return summary


def save_monthly_process_metrics(metrics: dict[str, Any], actor: str) -> dict[str, Any]:
    payload = {
        **metrics,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "calculated_by": str(actor or "PWA"),
        "definition_version": "2026-11-16-v2-all-courier-months",
    }
    response = requests.post(
        f"{require_supabase().rstrip('/')}/rest/v1/{SUMMARY_TABLE}",
        headers={**_api_headers(SUMMARY_SCHEMA, write=True), "Prefer": "resolution=merge-duplicates,return=representation"},
        params={"on_conflict": "period_start"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    saved = response.json() or []
    return saved[0] if isinstance(saved, list) and saved else payload


def save_courier_monthly_process_metrics(
    summary: dict[str, Any], courier_metrics: list[dict[str, Any]], actor: str,
) -> None:
    """Persist one deterministic completed workflow row for each courier/month."""
    summary_id = str(summary.get("summary_id") or "").strip()
    if not summary_id:
        raise RuntimeError("A havi mutatóhoz nincs summary_id. Futtasd a futár-hónap mutató SQL-migrációját.")
    period_start = str(summary.get("period_start") or "").strip()
    if not period_start:
        raise RuntimeError("A mentett havi mutatóhoz hiányzik a hónap azonosítója.")
    existing_rows = _read_rows(
        DETAIL_TABLE,
        schema=SUMMARY_SCHEMA,
        params={"select": "courier_id", "period_start": f"eq.{period_start}", "limit": "10000"},
    )
    if not courier_metrics:
        for row in existing_rows:
            courier_id = str(row.get("courier_id") or "").strip()
            if courier_id:
                requests.delete(
                    f"{require_supabase().rstrip('/')}/rest/v1/{DETAIL_TABLE}",
                    headers=_api_headers(SUMMARY_SCHEMA, write=True),
                    params={"period_start": f"eq.{period_start}", "courier_id": f"eq.{courier_id}"},
                    timeout=30,
                ).raise_for_status()
        return
    calculated_at = datetime.now(timezone.utc).isoformat()
    payload = [
        {
            **metric,
            "summary_id": summary_id,
            "calculated_at": calculated_at,
            "calculated_by": str(actor or "PWA"),
        }
        for metric in courier_metrics
    ]
    response = requests.post(
        f"{require_supabase().rstrip('/')}/rest/v1/{DETAIL_TABLE}",
        headers={**_api_headers(SUMMARY_SCHEMA, write=True), "Prefer": "resolution=merge-duplicates,return=minimal"},
        params={"on_conflict": "period_start,courier_id"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    current_ids = {str(metric["courier_id"]) for metric in courier_metrics}
    for row in existing_rows:
        courier_id = str(row.get("courier_id") or "").strip()
        if courier_id and courier_id not in current_ids:
            requests.delete(
                f"{require_supabase().rstrip('/')}/rest/v1/{DETAIL_TABLE}",
                headers=_api_headers(SUMMARY_SCHEMA, write=True),
                params={"period_start": f"eq.{period_start}", "courier_id": f"eq.{courier_id}"},
                timeout=30,
            ).raise_for_status()


def recalculate_and_save_monthly_process_metrics(period_start: date, actor: str) -> dict[str, Any]:
    """Save both linked metric tables from the same immutable source events."""
    summary, courier_metrics = calculate_monthly_process_metric_bundle(period_start)
    saved_summary = save_monthly_process_metrics(summary, actor)
    save_courier_monthly_process_metrics(saved_summary, courier_metrics, actor)
    return saved_summary


def _metric_card(label: str, value: str, note: str, description: str, tone: str = "green") -> str:
    return (
        f'<div class="process-kpi-card process-kpi-{escape(tone)}">'
        f'<span class="process-kpi-label">{escape(label)} '
        f'<span class="process-help" title="{escape(description)}" aria-label="Súgó: {escape(description)}">?</span></span>'
        f"<strong>{escape(value)}</strong><small>{escape(note)}</small></div>"
    )


def _render_cards(summary: dict[str, Any]) -> None:
    st.markdown(
        """
        <style>
        .process-kpi-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0 8px;}
        .process-kpi-card {background:#fff;border:1px solid #dbe4d7;border-radius:16px;padding:16px;min-height:112px;box-shadow:0 4px 16px rgba(20,40,80,.05);}
        .process-kpi-card strong {display:block;color:#152b1d;font-size:27px;line-height:1.1;margin-top:9px;}
        .process-kpi-card small {display:block;color:#66746c;font-size:12px;margin-top:8px;}
        .process-kpi-label {color:#66746c;font-size:13px;font-weight:700;}
        .process-help {display:inline-flex;justify-content:center;align-items:center;width:17px;height:17px;border-radius:50%;background:#e7f0e9;color:#285f3a;cursor:help;font-weight:900;font-size:11px;}
        .process-kpi-amber {border-color:#efd5a8}.process-kpi-amber strong {color:#9a6010;}
        .process-kpi-red {border-color:#ecc8cc}.process-kpi-red strong {color:#ad3d49;}
        @media(max-width:1000px){.process-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
        @media(max-width:600px){.process-kpi-grid{grid-template-columns:1fr;}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    completed = int(summary.get("completed_flow_count") or 0)
    complaint_flows = int(summary.get("complaint_flow_count") or 0)
    cards = [
        _metric_card("Lezárt folyamat", f"{completed} db", "Teljes, időrendben követhető folyamat", "Csak azok a futár-hónap folyamatok szerepelnek, ahol a megnyitás, két elfogadás, számlafeltöltés és kifizetés időpontja is megvan."),
        _metric_card("Elszámolási reklamáció", f"{_number(summary.get('complaints_average')):.2f} db", f"{int(summary.get('complaint_total') or 0)} reklamáció · {complaint_flows} folyamat", "Az adott elszámolási hónap összes aktív pénzügyi reklamációja osztva a havi futársorok számával. A törölt és külön előlegfolyamatok nem szerepelnek benne.", "amber"),
        _metric_card("Reklamáció válaszideje", f"{_number(summary.get('response_average_hours')):.1f} óra", f"{_number(summary.get('response_median_hours')):.1f} óra medián · {int(summary.get('response_count') or 0)} megválaszolt/lezárt", "A megválaszolt/lezárt reklamációk száma státuszból vagy rögzített válaszból jön. A válaszidő csak ott számolható, ahol a válasz időpontja is rögzített.", "amber"),
        _metric_card("Levonás / folyamat", _format_huf(summary.get("deductions_average_huf")), f"Összesen {_format_huf(summary.get('deductions_total_huf'))}", "A legutóbbi mentett PWA pénzügyi snapshot negatív tételei és korrekciói osztva a havi futársorok számával. A forrás nélküli futárokat a lefedettség jelzi.", "red"),
    ]
    st.markdown('<div class="process-kpi-grid">' + ''.join(cards) + "</div>", unsafe_allow_html=True)


def _available_months() -> list[date]:
    months: set[date] = set()
    for table, schema, column in (
        (SUMMARY_TABLE, SUMMARY_SCHEMA, "period_start"),
        ("mobile_settlement_period_config", SUMMARY_SCHEMA, "period_start"),
        ("peopleforce_card_statuses", None, "document_month"),
    ):
        try:
            rows = _read_rows(table, schema=schema, params={"select": column, "order": f"{column}.desc", "limit": "60"})
        except requests.RequestException:
            continue
        for row in rows:
            try:
                months.add(_month_start(date.fromisoformat(str(row.get(column) or "")[:10])))
            except ValueError:
                continue
    if not months:
        today = datetime.now(LOCAL_TIMEZONE).date()
        months.add(_month_start(today - timedelta(days=today.day)))
    return sorted(months, reverse=True)


def show_settlement_process_metrics_page(user: dict[str, Any]) -> None:
    """Render the persisted main indicators in a dedicated PWA menu item."""
    if not can_view_settlement_process_metrics(user):
        st.error("Ehhez a menühöz pénzügyi vagy admin jogosultság szükséges.")
        return
    st.title("Elszámolási folyamat – fő mutatók")
    st.caption("A kártyák havi, adatbázisban mentett összesítések. Nincs automatikus percenkénti frissítés.")
    months = _available_months()
    labels = {month: f"{month.year}. {HUNGARIAN_MONTHS[month.month - 1]}" for month in months}
    selected_month = st.selectbox("Elszámolási hónap", months, format_func=lambda value: labels[value], key="pwa_process_metric_month")

    try:
        summary = _read_one_summary(selected_month)
    except requests.RequestException as exc:
        st.error("A mentett havi főmutatók nem olvashatók. Előbb telepíteni kell a DB-migrációt.")
        st.caption(str(exc))
        return

    if not summary:
        try:
            summary = recalculate_and_save_monthly_process_metrics(
                selected_month, str(user.get("username") or "PWA"),
            )
            st.toast("A havi és a futár–hónap bontású mutatók adatbázisba mentve.")
        except (requests.RequestException, RuntimeError) as exc:
            st.error("Az első havi főmutató-összesítő mentése sikertelen.")
            st.caption(str(exc))
            return

    if st.button("Fő mutatók újraszámítása és mentése", type="primary", use_container_width=True):
        try:
            summary = recalculate_and_save_monthly_process_metrics(
                selected_month, str(user.get("username") or "PWA"),
            )
            st.success("A havi és a futár–hónap bontású mutatók kiszámolva és adatbázisba mentve.")
        except (requests.RequestException, RuntimeError) as exc:
            st.error("A főmutatók mentése sikertelen.")
            st.caption(str(exc))
            return

    st.caption(f"Havi futársorok: {summary.get('source_counts', {}).get('courier_month_count', '—')} · Pénzügyi forrás: {summary.get('source_counts', {}).get('finance_covered_couriers', '—')} · Időbélyeges válaszok: {summary.get('source_counts', {}).get('response_timed_count', '—')}")
    _render_cards(summary)
    calculated_at = _timestamp(summary.get("calculated_at"))
    if calculated_at:
        st.caption(f"Utoljára mentve: {calculated_at.astimezone(LOCAL_TIMEZONE).strftime('%Y. %m. %d. %H:%M')} · adatbázisban tárolt havi érték")
