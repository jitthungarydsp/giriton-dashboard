import calendar
import re
from datetime import date

import pandas as pd
import streamlit as st

from page.invoice_summary import filter_by_worksheet
from page.monthly_invoice_tasks import (
    _current_amounts_by_name,
    _latest_document_amount,
)
from resources.invoice_summary import (
    build_driver_invoice_summary,
    normalize_person_key,
    read_invoice_data,
)
from resources.peopleforce_documents import read_peopleforce_card_statuses_for_month


def extract_payment_amount(status_note):
    text = " ".join(str(status_note or "").split())
    if not text:
        return 0
    labelled = re.findall(
        r"(?:kifizet(?:ett|es|és)?|elutal(?:t|as|ás)?|utal(?:t|as|ás)?|osszeg|összeg)"
        r"[^0-9]{0,30}([0-9][0-9 .\u00a0]*)\s*(?:ft|huf)",
        text,
        flags=re.IGNORECASE,
    )
    explicit_amount = re.findall(
        r"(?:osszeg|összeg)\s*[:=]?\s*([0-9][0-9 \u00a0]*)"
        r"(?:\s*(?:ft|huf))?",
        text,
        flags=re.IGNORECASE,
    )
    candidates = labelled or explicit_amount or re.findall(
        r"([0-9][0-9 .\u00a0]*)\s*(?:ft|huf)", text, flags=re.IGNORECASE
    )
    amounts = []
    for value in candidates:
        digits = re.sub(r"\D", "", value)
        if digits:
            amounts.append(int(digits))
    return max(amounts, default=0)


def read_closed_reconciliation_statuses(document_month):
    statuses = read_peopleforce_card_statuses_for_month(document_month)
    if statuses.empty:
        return []
    done = statuses[
        statuses["action_key"].astype(str).str.strip().str.lower().isin(
            ["invoice_payment", "monthly_close"]
        )
        & statuses["status"].astype(str).str.strip().str.lower().eq("done")
    ].copy()
    result = {}
    for _, row in done.iterrows():
        item = row.to_dict()
        courier_id = str(item.get("courier_id") or "").strip()
        courier_name = str(item.get("courier_name") or "").strip()
        key = courier_id or normalize_person_key(courier_name)
        if not key:
            continue
        current = result.setdefault(key, item.copy())
        if str(item.get("updated_at") or "") > str(current.get("updated_at") or ""):
            payment_note = current.get("_payment_status_note")
            result[key] = item.copy()
            current = result[key]
            if payment_note:
                current["_payment_status_note"] = payment_note
        if str(item.get("action_key") or "").strip().lower() == "invoice_payment":
            current["_payment_status_note"] = str(item.get("status_note") or "")
    return sorted(
        result.values(), key=lambda row: str(row.get("courier_name") or "").casefold()
    )


def build_reconciliation_rows(driver_summary, closed_couriers, document_month, amount_loader):
    current_by_name = _current_amounts_by_name(driver_summary)
    rows = []
    for closed in closed_couriers:
        courier_id = str(closed.get("courier_id") or "").strip()
        courier_name = str(closed.get("courier_name") or "").strip()
        current_amount = current_by_name.get(normalize_person_key(courier_name), 0)

        try:
            tig_amount, tig_file = amount_loader(courier_id, document_month, "tig")
        except Exception as exc:
            tig_amount, tig_file = 0, f"TIG hiba: {exc}"

        payment_note = closed.get("_payment_status_note") or closed.get("status_note")
        payment_amount = extract_payment_amount(payment_note)
        if payment_amount:
            reference_amount = payment_amount
            reference_source = "Kifizetési státusz"
        elif tig_amount:
            reference_amount = tig_amount
            reference_source = "TIG"
        else:
            reference_amount = 0
            reference_source = "Hiányzik"

        difference = reference_amount - current_amount if reference_amount else 0
        reference_found = bool(reference_amount)
        matches = reference_found and difference == 0
        rows.append(
            {
                "Futár": courier_name or "Ismeretlen",
                "Courier ID": courier_id or "-",
                "Újraszámolt végösszeg": current_amount,
                "TIG összege": tig_amount,
                "Kifizetett összeg": payment_amount,
                "Viszonyítási alap": reference_source,
                "Eltérés": difference,
                "Eltérés %": (
                    difference / current_amount * 100
                    if reference_found and current_amount
                    else None
                ),
                "Ellenőrzés": "Egyezik" if matches else "Eltérés" if reference_found else "Hiányzó adat",
                "Lezárási státusz": str(closed.get("action_key") or "-"),
                "Lezárva": str(closed.get("updated_at") or "-")[:19],
                "TIG dokumentum": tig_file,
                "Kifizetési megjegyzés": str(payment_note or "-"),
                "_reference_found": reference_found,
                "_matches": matches,
            }
        )
    return pd.DataFrame(rows)


def _build_current_summary(data, selected_sheet, month_start):
    final_df = filter_by_worksheet(data.get("final", pd.DataFrame()), selected_sheet)
    return build_driver_invoice_summary(
        final_df,
        bonus_df=data.get("bonus", pd.DataFrame()),
        penalty_df=data.get("penalties", pd.DataFrame()),
        manual_df=data.get("manual", pd.DataFrame()),
        day_rates_df=data.get("day_rates", pd.DataFrame()),
        raw_route_df=data.get("routes", pd.DataFrame()),
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=data.get("atm_balance", pd.DataFrame()),
        customer_rating_df=data.get("customer_rating", pd.DataFrame()),
        monthly_adjustment_df=data.get("monthly_adjustments", pd.DataFrame()),
        target_reserve_df=data.get("target_reserve", pd.DataFrame()),
        period_start=month_start,
    )


def show_amount_reconciliation_page():
    st.title("Összeg ellenőrzés")
    st.caption(
        "Az aktuálisan újraszámolt végösszeget összeveti a TIG-gel vagy a "
        "kifizetési státuszban rögzített összeggel."
    )

    today = date.today()
    col1, col2 = st.columns(2)
    selected_date = col1.date_input(
        "Hónap", value=today.replace(day=1), key="amount_reconciliation_month"
    )
    selected_sheet = col2.selectbox(
        "Raktár", ["Mind", "BUD1_JIT", "BUD2_JIT"], key="amount_reconciliation_sheet"
    )
    month_start = selected_date.replace(day=1)
    month_end = selected_date.replace(
        day=calendar.monthrange(selected_date.year, selected_date.month)[1]
    )
    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    if not st.button(
        "Összesített ellenőrzés futtatása",
        type="primary",
        use_container_width=True,
        key=f"run_amount_reconciliation_{month_start}_{selected_sheet}",
    ):
        st.info("Válaszd ki a hónapot, majd indítsd el az ellenőrzést.")
        return

    with st.spinner("Aktuális összegek, TIG-ek és kifizetések ellenőrzése..."):
        try:
            data = read_invoice_data(month_start, month_end)
            driver_summary = _build_current_summary(data, selected_sheet, month_start)
            closed_couriers = read_closed_reconciliation_statuses(month_start)
            if selected_sheet != "Mind" and not driver_summary.empty:
                allowed_names = set(driver_summary["driver_name"].map(normalize_person_key))
                closed_couriers = [
                    row for row in closed_couriers
                    if normalize_person_key(row.get("courier_name")) in allowed_names
                ]
            result = build_reconciliation_rows(
                driver_summary, closed_couriers, month_start, _latest_document_amount
            )
        except Exception as exc:
            st.error(f"Az összegellenőrzés nem futtatható: {exc}")
            return

    if result.empty:
        st.info("A kiválasztott hónapban nincs lezárt vagy kifizetett futár.")
        return

    checked = result["_reference_found"].astype(bool)
    matches = result["_matches"].astype(bool)
    mismatch = checked & ~matches
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Lezárt futár", len(result))
    m2.metric("Egyezik", int(matches.sum()))
    m3.metric("Eltérés", int(mismatch.sum()))
    m4.metric(
        "Abszolút eltérés összesen",
        f"{int(result.loc[mismatch, 'Eltérés'].abs().sum()):,} Ft".replace(",", " "),
    )

    view_filter = st.radio(
        "Megjelenítés",
        ["Minden lezárt", "Csak eltérés", "Csak hiányzó adat"],
        horizontal=True,
        key="amount_reconciliation_filter",
    )
    visible = result.copy()
    if view_filter == "Csak eltérés":
        visible = visible[visible["_reference_found"] & ~visible["_matches"]]
    elif view_filter == "Csak hiányzó adat":
        visible = visible[~visible["_reference_found"]]

    def style_row(row):
        if row.get("Ellenőrzés") == "Egyezik":
            color = "background-color: #dcfce7; color: #14532d;"
        elif row.get("Ellenőrzés") == "Eltérés":
            color = "background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"
        else:
            color = "background-color: #fef9c3; color: #713f12;"
        return [color] * len(row)

    display = visible.drop(columns=["_reference_found", "_matches"], errors="ignore")
    st.dataframe(
        display.style.apply(style_row, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Újraszámolt végösszeg": st.column_config.NumberColumn(format="%d Ft"),
            "TIG összege": st.column_config.NumberColumn(format="%d Ft"),
            "Kifizetett összeg": st.column_config.NumberColumn(format="%d Ft"),
            "Eltérés": st.column_config.NumberColumn(format="%d Ft"),
            "Eltérés %": st.column_config.NumberColumn(format="%.2f %%"),
        },
    )
