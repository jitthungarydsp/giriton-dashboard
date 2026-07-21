import calendar
from datetime import date

import pandas as pd
import streamlit as st

from page.invoice_summary import filter_by_worksheet, render_monthly_invoice_tasks
from resources.invoice_summary import (
    build_driver_invoice_summary,
    normalize_person_key,
    read_invoice_data,
)


def _driver_names(final_df):
    if final_df is None or final_df.empty or "driver_name" not in final_df.columns:
        return []
    names_by_key = {}
    for value in final_df["driver_name"].dropna().astype(str):
        name = value.strip()
        key = normalize_person_key(name)
        if name and key:
            names_by_key[key] = name
    return sorted(names_by_key.values(), key=normalize_person_key)


def show_monthly_invoice_tasks_page():
    st.title("Havi feladatok")
    st.caption(
        "A még intézendő futárok, a havi dokumentumfolyamat és a számla–TIG ellenőrzés külön nézete."
    )

    today = date.today()
    selected_date = st.date_input(
        "Hónap",
        value=today.replace(day=1),
        key="monthly_tasks_month",
    )
    selected_sheet = st.selectbox(
        "Raktár fül",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="monthly_tasks_sheet",
    )
    month_start = selected_date.replace(day=1)
    month_end = selected_date.replace(
        day=calendar.monthrange(selected_date.year, selected_date.month)[1]
    )
    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    try:
        data = read_invoice_data(month_start, month_end)
    except Exception as exc:
        st.error(f"A havi elszámolási adatok nem tölthetők be: {exc}")
        return

    final_df = filter_by_worksheet(data.get("final", pd.DataFrame()), selected_sheet)
    bonus_df = data.get("bonus", pd.DataFrame())
    penalty_df = data.get("penalties", pd.DataFrame())
    manual_df = data.get("manual", pd.DataFrame())
    atm_balance_df = data.get("atm_balance", pd.DataFrame())
    customer_rating_df = data.get("customer_rating", pd.DataFrame())
    monthly_adjustment_df = data.get("monthly_adjustments", pd.DataFrame())

    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df=bonus_df,
        penalty_df=penalty_df,
        manual_df=manual_df,
        day_rates_df=data.get("day_rates", pd.DataFrame()),
        raw_route_df=data.get("routes", pd.DataFrame()),
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=atm_balance_df,
        customer_rating_df=customer_rating_df,
        monthly_adjustment_df=monthly_adjustment_df,
        period_start=month_start,
    )

    render_monthly_invoice_tasks(
        _driver_names(final_df),
        month_start,
        driver_summary,
    )
