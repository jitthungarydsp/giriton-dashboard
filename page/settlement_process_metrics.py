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
    response = requests.get(
        f"{require_supabase().rstrip('/')}/rest/v1/{table}",
        headers=_api_headers(schema),
        params=params or {},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json() or []
    return data if isinstance(data, list) else []


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


def calculate_monthly_process_metrics(period_start: date) -> dict[str, Any]:
    """Calculate a monthly summary from immutable workflow audit events."""
    month = _month_start(period_start)
    month_text = month.isoformat()
    openings = _read_rows(
        "peopleforce_card_statuses",
        params={
            "select": "courier_id,courier_name,updated_at",
            "document_month": f"eq.{month_text}",
            "action_key": "eq.individual_monthly_billing",
            "status": "eq.done",
            "limit": "10000",
        },
    )
    acceptances = _read_rows(
        "pwa_workflow_acceptance_snapshots",
        schema=SUMMARY_SCHEMA,
        params={
            "select": "courier_id,courier_name,action_key,accepted_at",
            "period_start": f"eq.{month_text}",
            "limit": "10000",
        },
    )
    invoices = _read_rows(
        "peopleforce_documents",
        params={
            "select": "courier_id,courier_name,uploaded_at",
            "document_month": f"eq.{month_text}",
            "document_type": "eq.invoice",
            "limit": "10000",
        },
    )
    closures = _read_rows(
        "courier_monthly_closure",
        schema=SUMMARY_SCHEMA,
        params={
            "select": "courier_id,courier_name,closed_at,snapshot",
            "period_start": f"eq.{month_text}",
            "status": "eq.done",
            "limit": "10000",
        },
    )
    complaints = _read_rows(
        "peopleforce_complaints",
        params={
            "select": "id,courier_id,document_type,created_at,responded_at",
            "document_month": f"eq.{month_text}",
            "status": "neq.deleted",
            "limit": "10000",
        },
    )
    financial_complaints = [
        row for row in complaints
        if str(row.get("document_type") or "").strip().casefold() in FINANCIAL_COMPLAINT_TYPES
    ]
    acceptance_by_courier = _group_by_courier(acceptances)
    invoices_by_courier = _group_by_courier(invoices)
    closures_by_courier = _group_by_courier(closures)
    complaints_by_courier = _group_by_courier(financial_complaints)

    completed_flows: list[dict[str, Any]] = []
    response_hours: list[float] = []
    stage_hours: dict[str, list[float]] = {
        "opening_to_settlement": [],
        "settlement_to_tig": [],
        "tig_to_invoice": [],
        "invoice_to_paid": [],
        "opening_to_paid": [],
    }
    source_times: list[datetime] = []
    for opening in openings:
        courier_id = str(opening.get("courier_id") or "").strip()
        opened_at = _timestamp(opening.get("updated_at"))
        if not courier_id or opened_at is None:
            continue
        source_times.append(opened_at)
        acceptance_rows = acceptance_by_courier.get(courier_id, [])
        settlement = _first_after(
            [row for row in acceptance_rows if str(row.get("action_key") or "").casefold() == "settlement"],
            "accepted_at",
            opened_at,
        )
        settlement_at = _timestamp((settlement or {}).get("accepted_at"))
        opening_to_settlement = _hours_between(opened_at, settlement_at)
        if opening_to_settlement is not None:
            stage_hours["opening_to_settlement"].append(opening_to_settlement)
        tig = _first_after(
            [row for row in acceptance_rows if str(row.get("action_key") or "").casefold() == "tig"],
            "accepted_at",
            settlement_at,
        ) if settlement_at else None
        tig_at = _timestamp((tig or {}).get("accepted_at"))
        settlement_to_tig = _hours_between(settlement_at, tig_at)
        if settlement_to_tig is not None:
            stage_hours["settlement_to_tig"].append(settlement_to_tig)
        invoice = _first_after(invoices_by_courier.get(courier_id, []), "uploaded_at", tig_at) if tig_at else None
        invoice_at = _timestamp((invoice or {}).get("uploaded_at"))
        tig_to_invoice = _hours_between(tig_at, invoice_at)
        if tig_to_invoice is not None:
            stage_hours["tig_to_invoice"].append(tig_to_invoice)
        closure = _first_after(closures_by_courier.get(courier_id, []), "closed_at", invoice_at) if invoice_at else None
        paid_at = _timestamp((closure or {}).get("closed_at"))
        invoice_to_paid = _hours_between(invoice_at, paid_at)
        if invoice_to_paid is not None:
            stage_hours["invoice_to_paid"].append(invoice_to_paid)
        opening_to_paid = _hours_between(opened_at, paid_at)
        if opening_to_paid is not None:
            stage_hours["opening_to_paid"].append(opening_to_paid)
        if not all((settlement_at, tig_at, invoice_at, paid_at)):
            continue
        source_times.extend((settlement_at, tig_at, invoice_at, paid_at))
        flow_complaints = [
            row for row in complaints_by_courier.get(courier_id, [])
            if (created_at := _timestamp(row.get("created_at"))) is not None
            and opened_at <= created_at <= paid_at
        ]
        for complaint in flow_complaints:
            response_time = _hours_between(complaint.get("created_at"), complaint.get("responded_at"))
            if response_time is not None:
                response_hours.append(response_time)
        snapshot = (closure or {}).get("snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        malus_huf = abs(_number(snapshot.get("malus_huf")))
        other_deductions_huf = sum(abs(_number(snapshot.get(key))) for key in (
            "atm_deduction_huf", "insurance_fee_huf", "other_expense_huf",
            "salary_advance_huf", "reserve_addition_huf",
        ))
        completed_flows.append({
            "complaint_count": len(flow_complaints),
            "malus_huf": malus_huf,
            "other_deductions_huf": other_deductions_huf,
            "deductions_huf": malus_huf + other_deductions_huf,
        })

    completed_count = len(completed_flows)
    complaint_total = sum(int(row["complaint_count"]) for row in completed_flows)
    deductions_total = sum(float(row["deductions_huf"]) for row in completed_flows)
    complaint_group = [row for row in completed_flows if int(row["complaint_count"]) > 0]
    no_complaint_group = [row for row in completed_flows if int(row["complaint_count"]) == 0]

    def group_totals(rows: list[dict[str, Any]]) -> tuple[int, float, float]:
        total = sum(float(row["deductions_huf"]) for row in rows)
        return len(rows), total, total / len(rows) if rows else 0.0

    with_complaint_count, with_complaint_total, with_complaint_average = group_totals(complaint_group)
    without_complaint_count, without_complaint_total, without_complaint_average = group_totals(no_complaint_group)
    return {
        "period_start": month_text,
        "completed_flow_count": completed_count,
        "complaint_flow_count": sum(1 for row in completed_flows if row["complaint_count"] > 0),
        "complaint_total": complaint_total,
        "complaints_average": complaint_total / completed_count if completed_count else 0.0,
        "response_count": len(response_hours),
        "response_average_hours": sum(response_hours) / len(response_hours) if response_hours else 0.0,
        "response_median_hours": float(median(response_hours)) if response_hours else 0.0,
        "deductions_total_huf": deductions_total,
        "malus_total_huf": sum(float(row["malus_huf"]) for row in completed_flows),
        "other_deductions_total_huf": sum(float(row["other_deductions_huf"]) for row in completed_flows),
        "deductions_average_huf": deductions_total / completed_count if completed_count else 0.0,
        "opening_to_settlement": _duration_summary(stage_hours["opening_to_settlement"]),
        "settlement_to_tig": _duration_summary(stage_hours["settlement_to_tig"]),
        "tig_to_invoice": _duration_summary(stage_hours["tig_to_invoice"]),
        "invoice_to_paid": _duration_summary(stage_hours["invoice_to_paid"]),
        "opening_to_paid": _duration_summary(stage_hours["opening_to_paid"]),
        "with_complaint_flow_count": with_complaint_count,
        "with_complaint_deductions_huf": with_complaint_total,
        "with_complaint_deductions_average_huf": with_complaint_average,
        "without_complaint_flow_count": without_complaint_count,
        "without_complaint_deductions_huf": without_complaint_total,
        "without_complaint_deductions_average_huf": without_complaint_average,
        "source_updated_at": max(source_times).isoformat() if source_times else None,
        "source_counts": {
            "openings": len(openings), "acceptances": len(acceptances),
            "invoices": len(invoices), "closures": len(closures),
            "financial_complaints": len(financial_complaints),
        },
    }


def save_monthly_process_metrics(metrics: dict[str, Any], actor: str) -> dict[str, Any]:
    payload = {
        **metrics,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "calculated_by": str(actor or "PWA"),
        "definition_version": "2026-11-14-v1",
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
        _metric_card("Elszámolási reklamáció", f"{_number(summary.get('complaints_average')):.2f} db", f"{int(summary.get('complaint_total') or 0)} reklamáció · {complaint_flows} folyamat", "A lezárt folyamatok alatt indított elszámolási, Teljesítés-összesítő- vagy számlaügyek átlaga. A túrával kapcsolatos reklamációk nem szerepelnek benne.", "amber"),
        _metric_card("Reklamáció válaszideje", f"{_number(summary.get('response_average_hours')):.1f} óra", f"{_number(summary.get('response_median_hours')):.1f} óra medián · {int(summary.get('response_count') or 0)} válasz", "A reklamáció létrehozásától az admin rögzített válaszáig eltelt idő. Csak válaszolt reklamáció számít.", "amber"),
        _metric_card("Levonás / folyamat", _format_huf(summary.get("deductions_average_huf")), f"Összesen {_format_huf(summary.get('deductions_total_huf'))}", "A kifizetéskor mentett pénzügyi snapshot malusz- és egyéb levonási sorainak átlaga. Későbbi újraszámítás nem írja át ezt a mutatót.", "red"),
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
            summary = save_monthly_process_metrics(
                calculate_monthly_process_metrics(selected_month),
                str(user.get("username") or "PWA"),
            )
            st.toast("Az első havi főmutató-összesítő adatbázisba mentve.")
        except requests.RequestException as exc:
            st.error("Az első havi főmutató-összesítő mentése sikertelen.")
            st.caption(str(exc))
            return

    if st.button("Fő mutatók újraszámítása és mentése", type="primary", use_container_width=True):
        try:
            summary = save_monthly_process_metrics(
                calculate_monthly_process_metrics(selected_month),
                str(user.get("username") or "PWA"),
            )
            st.success("A havi főmutatók kiszámolva és adatbázisba mentve.")
        except requests.RequestException as exc:
            st.error("A főmutatók mentése sikertelen.")
            st.caption(str(exc))
            return

    _render_cards(summary)
    calculated_at = _timestamp(summary.get("calculated_at"))
    if calculated_at:
        st.caption(f"Utoljára mentve: {calculated_at.astimezone(LOCAL_TIMEZONE).strftime('%Y. %m. %d. %H:%M')} · adatbázisban tárolt havi érték")
