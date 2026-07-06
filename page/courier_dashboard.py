import base64
from calendar import monthrange
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
import re
from urllib.parse import quote_plus, urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from resources.dsp_dashboard_statistics import (
    build_statistics,
    normalize_id,
    read_sheet_dataframe,
)
from resources.db_driver_statistics import (
    build_db_statistics,
)
from resources.courier_card_db import (
    NUMERIC_COLUMNS as COURIER_CARD_NUMERIC_COLUMNS,
    read_courier_card_stats,
)
from resources.courier_master_db import read_courier_master
from resources.courier_card_snapshot import read_snapshot
from resources.app_settings import load_app_settings
from resources.discord_notifier import notify_route_assigned_once
from resources.discord_routes import read_latest_discord_route
from resources.api import (
    load_attendance,
    load_driver_details,
    load_drivers,
)
from resources.shift_reconciliation_sheet import (
    read_shift_reconciliation_records_for_dates,
    read_shift_reconciliation_records,
)
from resources.giriton_shifts_db import read_giriton_shift_records
from resources.foglalasok_db import read_foglalasok_records
from resources.peopleforce_documents import (
    create_peopleforce_complaint,
    decode_document_content,
    read_peopleforce_card_statuses,
    read_peopleforce_complaint_markers,
    read_peopleforce_complaints,
    read_peopleforce_document_markers,
    read_peopleforce_documents,
    upload_peopleforce_document,
    upsert_peopleforce_card_status,
)

EXPRESS_MAX_FEE = 6516
NORMAL_CITY_MAX_FEE = 13000
DAILY_CACHE_SECONDS = 24 * 60 * 60
LIVE_CACHE_SECONDS = 60
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_PEOPLEFORCE_UPLOAD_BYTES = 10 * 1024 * 1024


def format_number(value, decimals=1):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "0"


def format_percent(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def format_minutes(value):
    try:
        return f"{float(value):.1f} perc"
    except (TypeError, ValueError):
        return "0.0 perc"


def format_currency(value):
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        amount = 0

    return f"{amount:,} Ft".replace(",", " ")


def clean_display_text(value, fallback=""):
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass

    text = str(value or "").strip()

    if not text or text.lower() in ["nan", "none", "null"]:
        return fallback

    return text


def get_courier_display_name(row, user):
    return (
        clean_display_text(row.get("name"))
        or clean_display_text(row.get("courier_name"))
        or clean_display_text(user.get("username"))
        or "Kifli futár"
    )


def get_courier_display_warehouse(row):
    return (
        clean_display_text(row.get("warehouse"))
        or clean_display_text(row.get("warehouse_name"))
        or "Kifli pálya"
    )


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_courier_statistics(start_date, end_date, user):
    snapshot_month = None

    if end_date:
        snapshot_month = end_date.strftime("%Y-%m")
    elif start_date:
        snapshot_month = start_date.strftime("%Y-%m")

    if snapshot_month:
        try:
            db_snapshot_df = read_courier_card_stats(
                snapshot_month
            )

            if not db_snapshot_df.empty:
                if user and user.get("role") == "user":
                    courier_id = normalize_id(user.get("courierId"))
                    db_snapshot_df = db_snapshot_df[
                        db_snapshot_df["courier_id"].apply(normalize_id)
                        == courier_id
                    ].copy()

                details = {
                    "orders": pd.DataFrame(),
                    "customers": pd.DataFrame(),
                    "attendance_routes": pd.DataFrame(),
                    "giriton_login": pd.DataFrame(),
                    "db_snapshot": True,
                }

                return db_snapshot_df, details
        except Exception:
            pass

    try:
        db_summary_df, db_details = build_db_statistics(
            start_date=start_date,
            end_date=end_date,
            user=user,
        )

        if not db_summary_df.empty:
            return db_summary_df, db_details
    except Exception:
        pass

    if snapshot_month:
        snapshot_df = read_snapshot(snapshot_month)

        if not snapshot_df.empty:
            if user and user.get("role") == "user":
                courier_id = normalize_id(user.get("courierId"))
                snapshot_df = snapshot_df[
                    snapshot_df["courier_id"].apply(normalize_id) == courier_id
                ].copy()

            details = {
                "orders": pd.DataFrame(),
                "customers": pd.DataFrame(),
                "attendance_routes": pd.DataFrame(),
                "giriton_login": pd.DataFrame(),
                "snapshot": True,
            }

            return snapshot_df, details

    return build_statistics(
        start_date=start_date,
        end_date=end_date,
        user=user,
    )


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_courier_card_statistics(snapshot_month, user):
    db_snapshot_df = read_courier_card_stats(
        snapshot_month
    )

    if db_snapshot_df.empty:
        return db_snapshot_df, {
            "orders": pd.DataFrame(),
            "customers": pd.DataFrame(),
            "attendance_routes": pd.DataFrame(),
            "giriton_login": pd.DataFrame(),
            "db_snapshot": True,
        }

    if user and user.get("role") == "user":
        courier_id = normalize_id(user.get("courierId"))
        db_snapshot_df = db_snapshot_df[
            db_snapshot_df["courier_id"].apply(normalize_id)
            == courier_id
        ].copy()

    return db_snapshot_df, {
        "orders": pd.DataFrame(),
        "customers": pd.DataFrame(),
        "attendance_routes": pd.DataFrame(),
        "giriton_login": pd.DataFrame(),
        "db_snapshot": True,
    }


def empty_courier_details():
    return {
        "orders": pd.DataFrame(),
        "customers": pd.DataFrame(),
        "attendance_routes": pd.DataFrame(),
        "giriton_login": pd.DataFrame(),
    }


def normalize_courier_base_row(row, snapshot_month=""):
    clean_row = {
        "courier_id": normalize_id(row.get("courier_id")),
        "name": clean_display_text(row.get("name")),
        "warehouse": clean_display_text(row.get("warehouse")),
        "email": clean_display_text(row.get("email")),
        "phone": clean_display_text(row.get("phone")),
        "snapshot_month": snapshot_month,
    }

    if not clean_row["name"]:
        clean_row["name"] = clean_row["courier_id"] or "Ismeretlen futar"

    for column in COURIER_CARD_NUMERIC_COLUMNS:
        clean_row.setdefault(column, 0)

    return clean_row


def build_courier_base_dataframe(records, snapshot_month=""):
    rows = [
        normalize_courier_base_row(record, snapshot_month=snapshot_month)
        for record in records
    ]
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = df[df["courier_id"].apply(normalize_id) != ""].copy()

    if df.empty:
        return df

    for column in COURIER_CARD_NUMERIC_COLUMNS:
        if column not in df.columns:
            df[column] = 0

    return (
        df.sort_values(["name", "courier_id"])
        .drop_duplicates("courier_id", keep="first")
        .reset_index(drop=True)
    )


def build_courier_directory_from_master(snapshot_month):
    master_df = read_courier_master()

    if master_df.empty:
        return pd.DataFrame()

    records = []
    for _, row in master_df.iterrows():
        records.append({
            "courier_id": row.get("courier_id"),
            "name": row.get("courier_name"),
            "warehouse": row.get("warehouse_name"),
            "email": row.get("email"),
            "phone": row.get("phone_number"),
        })

    return build_courier_base_dataframe(
        records,
        snapshot_month=snapshot_month,
    )


def build_courier_directory_from_live_drivers(snapshot_month):
    try:
        drivers_data = load_drivers()
    except Exception:
        return pd.DataFrame()

    records = []
    for driver in drivers_data.get("drivers", []):
        personal_info = driver.get("personal_info", {}) or {}
        records.append({
            "courier_id": driver.get("driver_id"),
            "name": personal_info.get("name"),
            "warehouse": personal_info.get("warehouse_name"),
            "email": personal_info.get("contact_email"),
            "phone": personal_info.get("contact_number"),
        })

    return build_courier_base_dataframe(
        records,
        snapshot_month=snapshot_month,
    )


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_directory(snapshot_month):
    directory_df = build_courier_directory_from_master(snapshot_month)

    if not directory_df.empty:
        return directory_df

    return build_courier_directory_from_live_drivers(snapshot_month)


def add_user_fallback_courier(directory_df, user, snapshot_month):
    courier_id = normalize_id(user.get("courierId"))

    if not courier_id:
        return directory_df

    if (
        not directory_df.empty
        and courier_id
        in set(directory_df["courier_id"].apply(normalize_id).tolist())
    ):
        return directory_df

    fallback_df = build_courier_base_dataframe(
        [
            {
                "courier_id": courier_id,
                "name": user.get("username") or courier_id,
                "warehouse": user.get("warehouse") or "",
                "email": user.get("email") or "",
                "phone": user.get("phone") or "",
            }
        ],
        snapshot_month=snapshot_month,
    )

    if directory_df.empty:
        return fallback_df

    return pd.concat(
        [directory_df, fallback_df],
        ignore_index=True,
    ).drop_duplicates("courier_id", keep="first")


def merge_courier_directory_with_stats(directory_df, stats_df, snapshot_month):
    if directory_df.empty:
        return stats_df

    stats_df = stats_df.copy() if stats_df is not None else pd.DataFrame()
    directory_df = directory_df.copy()

    if not stats_df.empty and "courier_id" in stats_df.columns:
        stats_df["courier_id"] = stats_df["courier_id"].apply(normalize_id)
        stats_df = stats_df.drop_duplicates("courier_id", keep="first")
        merged = directory_df.merge(
            stats_df,
            on="courier_id",
            how="left",
            suffixes=("", "_stats"),
        )

        for column in [
            "name",
            "warehouse",
            "email",
            "phone",
            "snapshot_month",
            *COURIER_CARD_NUMERIC_COLUMNS,
        ]:
            stats_column = f"{column}_stats"
            if stats_column in merged.columns:
                merged[column] = merged[stats_column].replace(
                    "",
                    pd.NA,
                ).combine_first(
                    merged[column]
                )
                merged = merged.drop(columns=[stats_column])
    else:
        merged = directory_df

    for column in COURIER_CARD_NUMERIC_COLUMNS:
        if column not in merged.columns:
            merged[column] = 0

        merged[column] = pd.to_numeric(
            merged[column],
            errors="coerce",
        ).fillna(0)

    if "snapshot_month" not in merged.columns:
        merged["snapshot_month"] = snapshot_month

    merged["snapshot_month"] = merged["snapshot_month"].fillna(
        snapshot_month
    )

    return (
        merged.sort_values(["name", "courier_id"])
        .drop_duplicates("courier_id", keep="first")
        .reset_index(drop=True)
    )


def render_styles():
    st.markdown(
        """
<style>
.stApp {
    background: #020617;
}
.block-container {
    color: #e5e7eb;
}
.courier-inner-nav-title {
    color: #bef264;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: .08em;
    margin: 0 0 8px;
    text-transform: uppercase;
}
div[data-testid="stSegmentedControl"] {
    background: linear-gradient(135deg, #6cab2f 0%, #8bd346 52%, #f5fbea 100%);
    border: 1px solid rgba(22, 101, 52, 0.16);
    border-radius: 18px;
    box-shadow: 0 14px 30px rgba(36, 74, 20, 0.12);
    margin-bottom: 18px;
    padding: 8px;
    width: 100%;
}
div[data-testid="stSegmentedControl"] > div {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
}
div[data-testid="stSegmentedControl"] label {
    justify-content: center;
    min-height: 42px;
    width: 100%;
}
.courier-placeholder-card {
    background: #ffffff;
    border: 1px solid #dbeafe;
    border-radius: 16px;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
    color: #0f172a;
    margin-top: 12px;
    padding: 24px;
}
.courier-placeholder-card h2 {
    font-size: 24px;
    margin: 0 0 8px;
}
.courier-placeholder-card p {
    color: #64748b;
    margin: 0;
}
.peopleforce-grid {
    display: grid;
    gap: 14px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 14px;
}
.peopleforce-card {
    background: linear-gradient(135deg, #ffffff 0%, #f7fee7 100%);
    border: 1px solid #bbf7d0;
    border-radius: 16px;
    box-shadow: 0 12px 26px rgba(15, 23, 42, 0.06);
    color: #0f172a;
    min-height: 150px;
    margin-bottom: 8px;
    padding: 18px;
    transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease;
}
a.peopleforce-card {
    color: #0f172a !important;
    display: block;
    text-decoration: none !important;
}
.peopleforce-card:hover {
    border-color: #6cab2f;
    box-shadow: 0 14px 30px rgba(36, 74, 20, 0.14);
    transform: translateY(-2px);
}
.peopleforce-card-link {
    color: #166534;
    display: block;
    font-size: 12px;
    font-weight: 900;
    margin-top: 14px;
}
.peopleforce-card-head {
    align-items: flex-start;
    display: flex;
    gap: 10px;
    justify-content: space-between;
}
.peopleforce-status {
    align-items: center;
    border-radius: 999px;
    display: inline-flex;
    font-size: 11px;
    font-weight: 900;
    gap: 6px;
    padding: 6px 9px;
    white-space: nowrap;
}
.peopleforce-status-open {
    background: #fee2e2;
    color: #991b1b;
}
.peopleforce-status-done {
    background: #dcfce7;
    color: #166534;
}
.peopleforce-lamp {
    border-radius: 999px;
    display: inline-block;
    height: 10px;
    width: 10px;
}
.peopleforce-lamp-open {
    background: #ef4444;
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.18);
}
.peopleforce-lamp-done {
    background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.18);
}
.peopleforce-status-panel {
    background: #f8fafc;
    border: 1px solid #dbeafe;
    border-radius: 14px;
    margin: 12px 0;
    padding: 14px;
}
.peopleforce-badge {
    align-items: center;
    background: #6cab2f;
    border-radius: 12px;
    color: #ffffff;
    display: inline-flex;
    font-size: 13px;
    font-weight: 900;
    height: 34px;
    justify-content: center;
    margin-bottom: 14px;
    width: 42px;
}
.peopleforce-card h3 {
    font-size: 18px;
    margin: 0 0 8px;
}
.peopleforce-card p {
    color: #64748b;
    font-size: 13px;
    line-height: 1.4;
    margin: 0;
}
.courier-hero {
    background: linear-gradient(135deg, #6cab2f 0%, #8bd346 45%, #f5fbea 100%);
    border-radius: 18px;
    color: #10240d;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(0, 1.8fr) minmax(220px, 0.9fr);
    margin-bottom: 18px;
    overflow: hidden;
    padding: 26px;
    position: relative;
}
.courier-hero h1 {
    font-size: 34px;
    line-height: 1.1;
    margin: 0 0 8px;
}
.courier-hero p {
    font-size: 16px;
    margin: 0;
    max-width: 720px;
}
.courier-plate {
    align-self: center;
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(16, 36, 13, 0.14);
    border-radius: 14px;
    box-shadow: 0 14px 30px rgba(36, 74, 20, 0.14);
    padding: 18px;
}
.courier-plate-label {
    color: #45603b;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
}
.courier-plate-value {
    color: #10240d;
    font-size: 30px;
    font-weight: 900;
    line-height: 1.2;
}
.stat-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: 12px 0 18px;
}
.stat-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
    padding: 16px;
}
.stat-label {
    color: #64748b;
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
}
.stat-value {
    color: #0f172a;
    font-size: 28px;
    font-weight: 900;
    line-height: 1.25;
    margin-top: 6px;
}
.stat-note {
    color: #64748b;
    font-size: 12px;
    margin-top: 5px;
}
.fun-note {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 14px;
    color: #7c2d12;
    font-weight: 700;
    margin: 8px 0 18px;
    padding: 14px 16px;
}
.today-shift-card {
    background: linear-gradient(135deg, #ecfccb 0%, #ffffff 65%);
    border: 1px solid #bbf7d0;
    border-radius: 16px;
    color: #0f172a;
    margin: 8px 0 18px;
    padding: 18px;
}
.shift-day-selector {
    align-items: center;
    background: #ffffff;
    border: 1px solid #d9f99d;
    border-radius: 16px;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.05);
    display: flex;
    justify-content: space-between;
    margin: 0 0 10px;
    padding: 12px 16px;
}
.shift-day-label {
    color: #166534;
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .04em;
    text-transform: uppercase;
}
.shift-day-date {
    color: #0f172a;
    font-size: 20px;
    font-weight: 900;
    line-height: 1.25;
}
.today-shift-title {
    color: #166534;
    font-size: 18px;
    font-weight: 900;
    margin-bottom: 10px;
}
.today-shift-row {
    align-items: center;
    border-top: 1px solid rgba(34, 197, 94, 0.18);
    color: #0f172a;
    display: grid;
    gap: 10px;
    grid-template-columns: 1fr 1fr 1fr 1fr;
    padding: 10px 0;
}
.today-shift-row strong,
.today-shift-row div {
    color: #0f172a;
}
.today-pill {
    border-radius: 999px;
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    padding: 6px 10px;
}
.today-ok {
    background: #dcfce7;
    color: #166534;
}
.today-missing {
    background: #fee2e2;
    color: #991b1b;
}
.route-road-card {
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
    margin: 10px 0 18px;
    padding: 18px;
}
.route-road-head {
    align-items: center;
    display: flex;
    gap: 12px;
    justify-content: space-between;
    margin-bottom: 18px;
}
.route-brand {
    align-items: center;
    display: flex;
    gap: 10px;
    font-weight: 900;
}
.route-brand-logo {
    align-items: center;
    background: #6cab2f;
    border-radius: 14px;
    color: #ffffff;
    display: inline-flex;
    font-size: 22px;
    height: 44px;
    justify-content: center;
    width: 44px;
}
.route-road-title {
    color: #0f172a;
    font-size: 18px;
    font-weight: 900;
}
.route-inline-meta {
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
    border-radius: 999px;
    color: #166534;
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    margin-left: 8px;
    padding: 4px 9px;
    vertical-align: middle;
}
.route-road-subtitle {
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
}
.route-road-track {
    align-items: center;
    display: grid;
    gap: 0;
    grid-template-columns: repeat(var(--stop-count), minmax(64px, 1fr)) 82px;
    min-height: 118px;
    overflow-x: auto;
    padding: 10px 0 4px;
    position: relative;
}
.route-road-track:before {
    background: linear-gradient(90deg, #cbd5e1 0%, #94a3b8 100%);
    border-radius: 999px;
    content: "";
    height: 8px;
    left: 32px;
    position: absolute;
    right: 44px;
    top: 48px;
}
.route-stop {
    min-width: 74px;
    position: relative;
    text-align: center;
    z-index: 1;
}
.route-stop-dot {
    align-items: center;
    border: 4px solid #ffffff;
    border-radius: 999px;
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
    color: #ffffff;
    display: inline-flex;
    font-size: 13px;
    font-weight: 900;
    height: 40px;
    justify-content: center;
    width: 40px;
}
.route-stop-current .route-stop-dot {
    background: #16a34a;
}
.route-stop-waiting .route-stop-dot {
    background: #facc15;
    color: #713f12;
}
.route-stop-label {
    color: #334155;
    font-size: 11px;
    font-weight: 800;
    line-height: 1.25;
    margin-top: 8px;
}
.route-depot {
    position: relative;
    text-align: center;
    z-index: 1;
}
.route-depot-icon {
    align-items: center;
    background: #ffffff;
    border: 4px solid #ffffff;
    border-radius: 16px;
    box-shadow: 0 8px 18px rgba(245, 158, 11, 0.20);
    color: #92400e;
    display: inline-flex;
    height: 56px;
    justify-content: center;
    overflow: hidden;
    width: 56px;
}
.route-depot-icon img {
    display: block;
    height: 46px;
    object-fit: contain;
    width: 46px;
}
.bag-alert-preview {
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
    border-radius: 14px;
    display: grid;
    gap: 12px;
    grid-template-columns: 1.2fr .8fr;
    margin-top: 14px;
    padding: 14px;
}
.bag-alert-title {
    color: #166534;
    font-size: 15px;
    font-weight: 900;
}
.bag-alert-copy {
    color: #334155;
    font-size: 13px;
    line-height: 1.45;
    margin-top: 4px;
}
.route-window-note {
    color: #166534;
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    margin-bottom: 3px;
}
.bag-alert-button {
    align-self: center;
    background: #16a34a;
    border-radius: 12px;
    color: #ffffff;
    font-weight: 900;
    padding: 12px 14px;
    text-align: center;
}
.route-nav-button {
    align-self: center;
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    color: #0f172a !important;
    display: inline-block;
    font-weight: 900;
    padding: 11px 14px;
    text-align: center;
    text-decoration: none !important;
}
.route-nav-button:hover {
    background: #e2e8f0;
}
.route-empty-note {
    text-align: center;
}
.route-help-button {
    background: #16a34a;
    border-radius: 12px;
    color: #ffffff;
    display: inline-block;
    font-weight: 900;
    margin-top: 10px;
    padding: 12px 18px;
}
.route-stop-home .route-stop-dot {
    background: #ffffff;
    color: #166534;
}
.route-stop-alert .route-stop-dot {
    background: #f97316;
    color: #ffffff;
}
.kifli-journey-card {
    background: linear-gradient(180deg, #0f172a 0%, #020617 100%);
    border: 1px solid rgba(190, 242, 100, 0.22);
    border-radius: 22px;
    box-shadow: 0 20px 48px rgba(0, 0, 0, 0.38);
    color: #e5e7eb;
    margin: 10px 0 18px;
    overflow: hidden;
    padding: 22px;
}
.kifli-journey-head {
    align-items: flex-start;
    display: flex;
    gap: 16px;
    justify-content: space-between;
    margin-bottom: 18px;
}
.kifli-journey-title {
    color: #fefce8;
    font-size: 24px;
    font-weight: 950;
    letter-spacing: -.01em;
}
.kifli-journey-subtitle {
    color: #a7f3d0;
    font-size: 13px;
    font-weight: 800;
    margin-top: 4px;
}
.kifli-route-meta {
    background: rgba(250, 204, 21, 0.12);
    border: 1px solid rgba(250, 204, 21, 0.32);
    border-radius: 999px;
    color: #fef3c7;
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    margin: 4px 0 0 8px;
    padding: 5px 10px;
}
.kifli-route-list {
    margin: 28px 0 18px;
    padding: 0 0 0 8px;
    position: relative;
}
.kifli-route-list:before {
    background:
        radial-gradient(circle at 50% 0, rgba(250, 204, 21, .95) 0 4px, transparent 5px),
        radial-gradient(circle at 50% 18px, rgba(132, 204, 22, .72) 0 4px, transparent 5px);
    background-size: 18px 36px;
    border-radius: 999px;
    content: "";
    left: 36px;
    position: absolute;
    top: 12px;
    bottom: 42px;
    width: 10px;
}
.kifli-route-stop {
    align-items: center;
    display: grid;
    gap: 18px;
    grid-template-columns: 82px minmax(0, 1fr);
    margin: 0 0 18px;
    position: relative;
}
.kifli-route-stop:nth-child(even) {
    transform: translateX(28px);
}
.kifli-route-stop:nth-child(odd) {
    transform: translateX(-4px);
}
.kifli-stop-marker {
    align-items: center;
    background: #111827;
    border: 4px solid #020617;
    border-radius: 999px;
    box-shadow: 0 10px 24px rgba(0, 0, 0, .35);
    color: #fef3c7;
    display: inline-flex;
    font-size: 13px;
    font-weight: 950;
    height: 54px;
    justify-content: center;
    position: relative;
    width: 54px;
    z-index: 1;
}
.kifli-stop-card {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 16px;
    padding: 14px 16px;
}
.kifli-route-stop-current .kifli-stop-card {
    background: linear-gradient(135deg, rgba(250, 204, 21, .18), rgba(255, 255, 255, .09));
    border-color: rgba(250, 204, 21, .55);
    box-shadow: 0 18px 34px rgba(250, 204, 21, .10);
}
.kifli-pawn-ok {
    background: #facc15;
    color: #713f12;
}
.kifli-pawn-late {
    background: #ef4444;
    color: #ffffff;
}
.kifli-stop-done .kifli-stop-marker {
    background: #22c55e;
    color: #052e16;
}
.kifli-stop-title {
    color: #f8fafc;
    font-size: 15px;
    font-weight: 950;
}
.kifli-stop-note {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 700;
    margin-top: 5px;
}
.kifli-current-actions {
    display: grid;
    gap: 10px;
    grid-template-columns: 1fr 1fr;
    margin-top: 14px;
}
.kifli-current-actions .stButton > button {
    background: #facc15;
    border: 0;
    color: #713f12;
    font-weight: 950;
}
.kifli-depot-finish {
    align-items: center;
    display: grid;
    gap: 18px;
    grid-template-columns: 82px minmax(0, 1fr);
    margin-top: 20px;
}
.kifli-depot-card {
    background: rgba(34, 197, 94, 0.10);
    border: 1px solid rgba(34, 197, 94, 0.30);
    border-radius: 16px;
    color: #dcfce7;
    padding: 14px 16px;
}
@media (max-width: 900px) {
    .courier-hero {
        grid-template-columns: 1fr;
    }
    .stat-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .bag-alert-preview {
        grid-template-columns: 1fr;
    }
    .peopleforce-grid {
        grid-template-columns: 1fr;
    }
    .kifli-current-actions {
        grid-template-columns: 1fr;
    }
    .kifli-route-stop:nth-child(even),
    .kifli-route-stop:nth-child(odd) {
        transform: none;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_courier_profile_content(row, user):
    name = get_courier_display_name(row, user)
    courier_id = str(row.get("courier_id") or user.get("courierId") or "-")
    warehouse = get_courier_display_warehouse(row)
    vehicle_temperature = clean_display_text(row.get("vehicle_temperature"), "Nincs adat")
    license_plate = clean_display_text(row.get("license_plate"), "-")
    username = clean_display_text(user.get("username"), "-")
    role = clean_display_text(user.get("role"), "-")
    email = clean_display_text(row.get("email") or user.get("email"), "-")
    phone = clean_display_text(row.get("phone") or row.get("contact_number"), "-")

    st.write(f"**Név:** {name}")
    st.write(f"**Futár ID:** #{courier_id}")
    st.write(f"**Raktár:** {warehouse}")
    st.write(f"**Aktuális autó:** {license_plate}")
    st.write(f"**Hűtő hőmérséklet:** {vehicle_temperature}")
    st.write(f"**E-mail:** {email}")
    st.write(f"**Telefonszám:** {phone}")
    st.write(f"**Felhasználó:** {username}")
    st.write(f"**Jogosultság:** {role}")

    if st.button("Bejelentés", key=f"courier_profile_report_{courier_id}"):
        st.success("Bejelentés rögzítve előnézetként. Ide kötjük majd a következő folyamatot.")


def render_courier_top_menu():
    options = ["PeopleForce", "Kiflis utam", "Statisztika"]
    current = st.session_state.get("courier_dashboard_tab", "PeopleForce")

    if current not in options:
        current = "PeopleForce"

    st.markdown(
        '<div class="courier-inner-nav-title">Kifli futár menü</div>',
        unsafe_allow_html=True,
    )

    if hasattr(st, "segmented_control"):
        try:
            selected = st.segmented_control(
                "Kifli futár menü",
                options,
                default=current,
                key="courier_dashboard_tab",
                label_visibility="collapsed",
            )
            return selected or current
        except TypeError:
            pass

    columns = st.columns(3)

    for index, option in enumerate(options):
        with columns[index]:
            if st.button(
                option,
                key=f"courier_dashboard_tab_button_{option}",
                type="primary" if option == current else "secondary",
                use_container_width=True,
            ):
                st.session_state["courier_dashboard_tab"] = option
                return option

    return current


def format_upload_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"

    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"

    return f"{size_bytes / (1024 * 1024):.1f} MB"


def normalize_filename_token(value):
    text = clean_display_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def invoice_file_signature_ok(file_name, content):
    extension = Path(file_name or "").suffix.lower().lstrip(".")

    if extension == "pdf":
        return content.startswith(b"%PDF"), "PDF"

    if extension in ["jpg", "jpeg"]:
        return content.startswith(b"\xff\xd8"), "JPG"

    if extension == "png":
        return content.startswith(b"\x89PNG\r\n\x1a\n"), "PNG"

    return False, extension.upper() or "ismeretlen"


def build_invoice_checks(
    uploaded_file,
    invoice_month=None,
    invoice_number="",
    gross_amount=0,
    courier_id="",
    courier_name="",
    require_invoice_fields=False,
):
    checks = []

    def add(status, title, detail):
        checks.append({
            "status": status,
            "title": title,
            "detail": detail,
        })

    if not uploaded_file:
        add("error", "Fájl", "Nincs feltöltött számla.")
        return checks

    file_name = clean_display_text(uploaded_file.name, "ismeretlen_fajl")
    content = uploaded_file.getvalue()
    extension = Path(file_name).suffix.lower().lstrip(".")
    allowed_extensions = ["pdf", "jpg", "jpeg", "png"]

    if content:
        add("ok", "Fájl olvasható", f"{file_name} ({format_upload_size(len(content))})")
    else:
        add("error", "Fájl olvasható", "A fájl üres vagy nem olvasható.")

    if extension in allowed_extensions:
        add("ok", "Fájltípus", f"Elfogadott formátum: {extension.upper()}.")
    else:
        add("error", "Fájltípus", "Csak PDF, JPG, JPEG vagy PNG tölthető fel.")

    if len(content) <= 10 * 1024 * 1024:
        add("ok", "Fájlméret", "10 MB alatt van.")
    else:
        add("error", "Fájlméret", "A fájl túl nagy. Javasolt maximum: 10 MB.")

    signature_ok, signature_label = invoice_file_signature_ok(file_name, content)

    if signature_ok:
        add("ok", "Fájlfejléc", f"A fájl ténylegesen {signature_label} formátumnak tűnik.")
    else:
        add(
            "warn" if extension in allowed_extensions else "error",
            "Fájlfejléc",
            "A fájl kiterjesztése és belső formátuma nem tűnik egyértelműnek.",
        )

    if require_invoice_fields:
        if clean_display_text(invoice_number):
            add("ok", "Számlaszám", "Kitöltve.")
        else:
            add("error", "Számlaszám", "A számlaszám kötelező a beküldéshez.")

        try:
            amount = float(gross_amount or 0)
        except (TypeError, ValueError):
            amount = 0

        if amount > 0:
            add("ok", "Bruttó összeg", f"{format_currency(amount)} megadva.")
        else:
            add("error", "Bruttó összeg", "A bruttó összeget 0 Ft fölé kell állítani.")

    if invoice_month:
        month_text = invoice_month.strftime("%Y-%m")
        compact_month = invoice_month.strftime("%Y%m")
        file_token = normalize_filename_token(file_name)

        if month_text.replace("-", "") in file_token or compact_month in file_token:
            add("ok", "Hónap a fájlnévben", f"A fájlnév tartalmazza a hónapot: {month_text}.")
        else:
            add(
                "warn",
                "Hónap a fájlnévben",
                f"Jó lenne, ha a fájlnévben szerepelne a hónap: {month_text}.",
            )

    invoice_token = normalize_filename_token(invoice_number)

    if invoice_token and invoice_token in normalize_filename_token(file_name):
        add("ok", "Számlaszám a fájlnévben", "A fájlnév tartalmazza a számlaszámot.")
    elif invoice_token:
        add(
            "warn",
            "Számlaszám a fájlnévben",
            "Nem gond, de később könnyebb keresni, ha a fájlnévben is szerepel.",
        )

    courier_token = normalize_filename_token(courier_id or courier_name)

    if courier_token and courier_token in normalize_filename_token(file_name):
        add("ok", "Futár azonosító a fájlnévben", "A fájlnévben látszik a futár azonosítója/neve.")
    elif courier_token:
        add(
            "warn",
            "Futár azonosító a fájlnévben",
            "Javasolt a fájlnévbe betenni a futár ID-t vagy nevet.",
        )

    return checks


def render_invoice_check_result(checks):
    errors = [check for check in checks if check["status"] == "error"]
    warnings = [check for check in checks if check["status"] == "warn"]
    passed = len([check for check in checks if check["status"] == "ok"])
    total = len(checks) or 1
    score = round((passed / total) * 100)

    if errors:
        st.error(f"Számla ellenőrzés: javítandó ({score}%).")
    elif warnings:
        st.warning(f"Számla ellenőrzés: beküldhető, de van pár finomítás ({score}%).")
    else:
        st.success(f"Számla ellenőrzés: rendben ({score}%).")

    for check in checks:
        icon = {
            "ok": "OK",
            "warn": "FIGYELEM",
            "error": "HIBA",
        }.get(check["status"], "INFO")
        st.write(f"**{icon} - {check['title']}:** {check['detail']}")


def render_invoice_submission_panel(row, user):
    name = get_courier_display_name(row, user)
    courier_id = normalize_id(row.get("courier_id") or user.get("courierId"))
    current_month = local_now().date().replace(day=1)

    st.subheader("Számlabeküldő rendszer")
    st.caption("Első körös saját űrlap: még nem küld adatot, csak előkészít és formai alapon ellenőriz.")

    with st.form("peopleforce_invoice_submission_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.text_input("Futár", value=f"{name} #{courier_id}", disabled=True)
            invoice_month = st.date_input(
                "Számla hónapja",
                value=current_month,
                key="peopleforce_invoice_month",
            )
            invoice_number = st.text_input(
                "Számlaszám",
                placeholder="pl. JIT-2026-07-001",
            )

        with col2:
            gross_amount = st.number_input(
                "Bruttó összeg",
                min_value=0,
                step=1000,
                value=0,
            )
            tig_reference = st.text_input(
                "TIG / elszámolás azonosító",
                placeholder="ha van",
            )
            st.text_area(
                "Megjegyzés",
                placeholder="Rövid megjegyzés, ha valami eltér a megszokottól.",
                height=88,
            )

        uploaded_invoice = st.file_uploader(
            "Számla feltöltése",
            type=["pdf", "png", "jpg", "jpeg"],
            key="peopleforce_invoice_upload",
        )
        submitted = st.form_submit_button("Számla ellenőrzése")

    if submitted:
        checks = build_invoice_checks(
            uploaded_invoice,
            invoice_month=invoice_month,
            invoice_number=invoice_number,
            gross_amount=gross_amount,
            courier_id=courier_id,
            courier_name=name,
            require_invoice_fields=True,
        )
        render_invoice_check_result(checks)

        if not any(check["status"] == "error" for check in checks):
            st.info(
                "Ez most még csak előnézet. A következő lépésben ide tudjuk kötni a DB mentést, e-mailt vagy jóváhagyási folyamatot."
            )


def render_invoice_quick_check_panel(row, user):
    name = get_courier_display_name(row, user)
    courier_id = normalize_id(row.get("courier_id") or user.get("courierId"))

    st.subheader("Számla ellenőrzés")
    st.caption("Gyors formai ellenőrzés már meglévő számlára. Tartalmi/PDF szövegolvasást később kötünk rá.")

    uploaded_file = st.file_uploader(
        "Ellenőrizendő számla",
        type=["pdf", "png", "jpg", "jpeg"],
        key="peopleforce_invoice_quick_check_upload",
    )

    if st.button("Feltöltött számla ellenőrzése", use_container_width=True):
        checks = build_invoice_checks(
            uploaded_file,
            courier_id=courier_id,
            courier_name=name,
        )
        render_invoice_check_result(checks)


def add_months(month_start, offset):
    month_index = month_start.month - 1 + offset
    year = month_start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def build_peopleforce_month_options():
    current_month = local_now().date().replace(day=1)
    return [
        add_months(current_month, -offset)
        for offset in range(0, 13)
    ]


def format_peopleforce_month(month_start):
    month_names = [
        "január",
        "február",
        "március",
        "április",
        "május",
        "június",
        "július",
        "augusztus",
        "szeptember",
        "október",
        "november",
        "december",
    ]
    return f"{month_start.year}. {month_names[month_start.month - 1]}"


def get_peopleforce_month(action_key):
    months = build_peopleforce_month_options()
    return st.selectbox(
        "Hónap",
        months,
        format_func=format_peopleforce_month,
        key=f"peopleforce_month_{action_key}",
    )


def get_peopleforce_document_config(action_key):
    configs = {
        "tig": {
            "document_type": "tig",
            "title": "TIG havi nézet",
            "empty": "Ehhez a hónaphoz még nincs feltöltött TIG.",
            "upload_label": "TIG feltöltése",
            "complaint": True,
        },
        "settlement": {
            "document_type": "settlement",
            "title": "Elszámolás havi nézet",
            "empty": "Ehhez a hónaphoz még nincs feltöltött elszámolás.",
            "upload_label": "Elszámolás feltöltése",
            "complaint": True,
        },
        "my_invoices": {
            "document_type": "invoice",
            "title": "Számláim havi nézet",
            "empty": "Ehhez a hónaphoz még nincs feltöltött számla.",
            "upload_label": "Számla feltöltése",
            "complaint": False,
        },
    }
    return configs.get(action_key, configs["my_invoices"])


def document_type_to_peopleforce_action(document_type):
    return {
        "tig": "tig",
        "settlement": "settlement",
        "invoice": "my_invoices",
    }.get(clean_display_text(document_type).lower(), "")


def load_peopleforce_card_states(courier_id, selected_month):
    states = {}

    if not courier_id:
        return states

    try:
        documents = read_peopleforce_document_markers(
            courier_id,
            selected_month,
        )
    except Exception:
        documents = pd.DataFrame()

    for _, document in documents.iterrows():
        action_key = document_type_to_peopleforce_action(
            document.get("document_type")
        )

        if not action_key:
            continue

        state = states.setdefault(
            action_key,
            {
                "status": "open",
                "activity_count": 0,
            },
        )
        state["activity_count"] += 1

    try:
        complaints = read_peopleforce_complaint_markers(
            courier_id,
            selected_month,
        )
    except Exception:
        complaints = pd.DataFrame()

    for _, complaint in complaints.iterrows():
        action_key = document_type_to_peopleforce_action(
            complaint.get("document_type")
        )

        if not action_key:
            continue

        state = states.setdefault(
            action_key,
            {
                "status": "open",
                "activity_count": 0,
            },
        )
        state["activity_count"] += 1

    try:
        statuses = read_peopleforce_card_statuses(
            courier_id,
            selected_month,
        )
    except Exception:
        statuses = pd.DataFrame()

    for _, status_row in statuses.iterrows():
        action_key = clean_display_text(status_row.get("action_key"))

        if not action_key:
            continue

        state = states.setdefault(
            action_key,
            {
                "status": "open",
                "activity_count": 0,
            },
        )
        state["status"] = (
            "done"
            if clean_display_text(status_row.get("status")).lower() == "done"
            else "open"
        )
        state["status_note"] = clean_display_text(status_row.get("status_note"))
        state["updated_by"] = clean_display_text(status_row.get("updated_by"))
        state["updated_at"] = clean_display_text(status_row.get("updated_at"))

    return states


def render_peopleforce_card_status_badge(state):
    if not state:
        return ""

    status = clean_display_text(state.get("status"), "open").lower()
    status_key = "done" if status == "done" else "open"
    label = "Kész" if status_key == "done" else "Teendő"

    return (
        f'<span class="peopleforce-status peopleforce-status-{status_key}">'
        f'<span class="peopleforce-lamp peopleforce-lamp-{status_key}"></span>'
        f"{label}"
        f"</span>"
    )


def render_peopleforce_status_panel(
    *,
    action_key,
    courier_id,
    courier_name,
    selected_month,
    user,
    state,
):
    if not state:
        st.caption("Ehhez a hónaphoz még nincs külön jelzés.")
        return

    status = clean_display_text(state.get("status"), "open").lower()
    status_key = "done" if status == "done" else "open"
    label = "Zöld - elvégezve" if status_key == "done" else "Piros - teendő van"
    updated_by = clean_display_text(state.get("updated_by"), "-")
    updated_at = clean_display_text(state.get("updated_at"), "")

    st.markdown(
        f"""
<div class="peopleforce-status-panel">
  <span class="peopleforce-status peopleforce-status-{status_key}">
    <span class="peopleforce-lamp peopleforce-lamp-{status_key}"></span>
    {escape(label)}
  </span>
  <p style="margin: 10px 0 0; color: #64748b;">Utolsó állítás: {escape(updated_by)} {escape(updated_at)}</p>
</div>
""",
        unsafe_allow_html=True,
    )

    if user.get("role") != "admin":
        return

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "Elvégezve - zöldre állítom",
            disabled=status_key == "done",
            use_container_width=True,
            key=f"peopleforce_done_{action_key}_{courier_id}_{selected_month}",
        ):
            upsert_peopleforce_card_status(
                courier_id=courier_id,
                courier_name=courier_name,
                action_key=action_key,
                document_month=selected_month,
                status="done",
                status_note="Admin lezárta.",
                updated_by=user.get("username"),
            )
            st.success("Zöldre állítva.")
            st.rerun()

    with col2:
        if st.button(
            "Visszanyitás - piros",
            disabled=status_key == "open",
            use_container_width=True,
            key=f"peopleforce_open_{action_key}_{courier_id}_{selected_month}",
        ):
            upsert_peopleforce_card_status(
                courier_id=courier_id,
                courier_name=courier_name,
                action_key=action_key,
                document_month=selected_month,
                status="open",
                status_note="Admin visszanyitotta.",
                updated_by=user.get("username"),
            )
            st.success("Pirosra állítva.")
            st.rerun()


def render_peopleforce_document_list(documents):
    if documents.empty:
        return

    for _, document in documents.iterrows():
        file_name = clean_display_text(document.get("file_name"), "dokumentum")
        title = clean_display_text(document.get("title"), file_name)
        note = clean_display_text(document.get("note"))
        uploaded_at = clean_display_text(document.get("uploaded_at"))
        uploaded_by = clean_display_text(document.get("uploaded_by"), "-")
        file_size = document.get("file_size") or 0

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**{title}**")
                st.caption(
                    f"{file_name} | feltöltötte: {uploaded_by} | {uploaded_at}"
                )

                if note:
                    st.write(note)

            with col2:
                try:
                    data = decode_document_content(
                        document.get("file_content_base64")
                    )
                except Exception:
                    data = b""

                if data:
                    st.download_button(
                        "Letöltés",
                        data=data,
                        file_name=file_name,
                        mime=clean_display_text(
                            document.get("mime_type"),
                            "application/octet-stream",
                        ),
                        use_container_width=True,
                        key=f"download_peopleforce_{document.get('id')}",
                    )
                else:
                    st.caption(f"Méret: {file_size} bájt")


def render_peopleforce_admin_upload(
    *,
    action_key,
    config,
    courier_id,
    courier_name,
    selected_month,
    user,
):
    if user.get("role") != "admin":
        return

    with st.expander(f"Admin feltöltés - {config['upload_label']}", expanded=False):
        with st.form(f"peopleforce_upload_{action_key}_{courier_id}_{selected_month}"):
            title = st.text_input(
                "Megnevezés",
                value=f"{config['upload_label']} - {format_peopleforce_month(selected_month)}",
            )
            note = st.text_area(
                "Megjegyzés",
                placeholder="Opcionális belső megjegyzés a futárnak.",
                height=90,
            )
            uploaded_file = st.file_uploader(
                "Fájl",
                type=["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "csv"],
                key=f"peopleforce_file_{action_key}_{courier_id}_{selected_month}",
            )
            submitted = st.form_submit_button("Feltöltés")

        if not submitted:
            return

        if uploaded_file is None:
            st.error("Válassz ki egy fájlt a feltöltéshez.")
            return

        if uploaded_file.size > MAX_PEOPLEFORCE_UPLOAD_BYTES:
            st.error("A fájl túl nagy. Első körben maximum 10 MB-ot engedünk.")
            return

        try:
            upload_peopleforce_document(
                courier_id=courier_id,
                courier_name=courier_name,
                document_type=config["document_type"],
                document_month=selected_month,
                title=title,
                note=note,
                uploaded_file=uploaded_file,
                uploaded_by=user.get("username"),
            )
        except Exception as exc:
            st.error(
                "A feltöltés nem sikerült. Ellenőrizd, hogy a peopleforce_documents tábla létrejött-e Supabase-ben."
            )
            st.caption(str(exc))
            return

        try:
            upsert_peopleforce_card_status(
                courier_id=courier_id,
                courier_name=courier_name,
                action_key=action_key,
                document_month=selected_month,
                status="open",
                status_note="Új dokumentum érkezett.",
                updated_by=user.get("username"),
            )
        except Exception as exc:
            st.warning(
                "A dokumentum feltöltődött, de a piros/zöld státusz mentése nem sikerült."
            )
            st.caption(str(exc))

        st.success("Feltöltve.")
        st.rerun()


def render_peopleforce_complaint_box(
    *,
    action_key,
    config,
    courier_id,
    courier_name,
    selected_month,
    user,
):
    if not config.get("complaint"):
        return

    st.divider()
    st.subheader("Reklamáció")

    try:
        complaints = read_peopleforce_complaints(
            courier_id,
            selected_month,
            config["document_type"],
        )
    except Exception:
        complaints = pd.DataFrame()

    if not complaints.empty:
        st.caption("Korábbi reklamációk ebben a hónapban")
        for _, complaint in complaints.head(5).iterrows():
            st.write(
                f"**{clean_display_text(complaint.get('status'), 'new')}** - "
                f"{clean_display_text(complaint.get('message'))}"
            )

    with st.form(f"peopleforce_complaint_{action_key}_{courier_id}_{selected_month}"):
        message = st.text_area(
            "Mi a gond?",
            placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni.",
            height=100,
        )
        submitted = st.form_submit_button("Reklamáció küldése")

    if not submitted:
        return

    if not clean_display_text(message):
        st.error("Írj be egy rövid reklamációs szöveget.")
        return

    try:
        create_peopleforce_complaint(
            courier_id=courier_id,
            courier_name=courier_name,
            document_type=config["document_type"],
            document_month=selected_month,
            message=message,
            created_by=user.get("username"),
        )
    except Exception as exc:
        st.error(
            "A reklamáció mentése nem sikerült. Ellenőrizd, hogy a peopleforce_complaints tábla létrejött-e Supabase-ben."
        )
        st.caption(str(exc))
        return

    try:
        upsert_peopleforce_card_status(
            courier_id=courier_id,
            courier_name=courier_name,
            action_key=action_key,
            document_month=selected_month,
            status="open",
            status_note="Új reklamáció érkezett.",
            updated_by=user.get("username"),
        )
    except Exception as exc:
        st.warning(
            "A reklamáció rögzült, de a piros/zöld státusz mentése nem sikerült."
        )
        st.caption(str(exc))

    st.success("Reklamáció rögzítve.")
    st.rerun()


def render_peopleforce_monthly_documents(action_key, row, user, selected_month=None):
    config = get_peopleforce_document_config(action_key)
    courier_id = normalize_id(row.get("courier_id") or user.get("courierId"))
    courier_name = get_courier_display_name(row, user)
    selected_month = selected_month or get_peopleforce_month(action_key)

    st.subheader(config["title"])
    st.caption(
        f"{courier_name} #{courier_id} | {format_peopleforce_month(selected_month)}"
    )

    try:
        documents = read_peopleforce_documents(
            courier_id,
            selected_month,
            config["document_type"],
        )
    except Exception as exc:
        documents = pd.DataFrame()
        st.warning(
            "Még nincs kész a PeopleForce dokumentumtár tábla, vagy nem elérhető a Supabase."
        )
        st.caption(
            "Futtasd a docs/supabase_peopleforce_documents.sql fájlt a Supabase SQL Editorban."
        )
        st.caption(str(exc))

    if documents.empty:
        st.info(config["empty"])
    else:
        render_peopleforce_document_list(documents)

    card_states = load_peopleforce_card_states(
        courier_id,
        selected_month,
    )
    render_peopleforce_status_panel(
        action_key=action_key,
        courier_id=courier_id,
        courier_name=courier_name,
        selected_month=selected_month,
        user=user,
        state=card_states.get(action_key),
    )

    render_peopleforce_admin_upload(
        action_key=action_key,
        config=config,
        courier_id=courier_id,
        courier_name=courier_name,
        selected_month=selected_month,
        user=user,
    )
    render_peopleforce_complaint_box(
        action_key=action_key,
        config=config,
        courier_id=courier_id,
        courier_name=courier_name,
        selected_month=selected_month,
        user=user,
    )


def get_peopleforce_cards():
    return [
        {
            "key": "report",
            "code": "BJ",
            "title": "Bejelentés",
            "description": "Gyors belső jelzés vagy kérés előkészítése.",
        },
        {
            "key": "muszakpro",
            "code": "MP",
            "title": "MűszakPro",
            "description": "Műszakhoz kapcsolódó PeopleForce és MűszakPro ügyek.",
        },
        {
            "key": "task",
            "code": "TF",
            "title": "Task felvétele",
            "description": "Új feladat vagy teendő rögzítésének helye.",
        },
        {
            "key": "tig",
            "code": "TG",
            "title": "TIG",
            "description": "Teljesítésigazolással kapcsolatos ügyek és státuszok.",
        },
        {
            "key": "settlement",
            "code": "EL",
            "title": "Elszámolás",
            "description": "Elszámolási információk, kérdések és egyeztetések.",
        },
        {
            "key": "my_invoices",
            "code": "SZ",
            "title": "Számláim",
            "description": "Saját számlák és későbbi feltöltési folyamatok.",
        },
        {
            "key": "invoice_check",
            "code": "SE",
            "title": "Számla ellenőrzés",
            "description": "Feltöltött számla gyors formai ellenőrzése.",
        },
        {
            "key": "invoice_submit",
            "code": "SB",
            "title": "Számlabeküldő rendszer",
            "description": "Saját előkészítő felület és külső Google űrlap.",
            "url": "https://docs.google.com/forms/d/e/1FAIpQLSc9MQZXm21F9ZYjiKcY-lgmYB9_pHPHIteo9bR6laRMWoBTLg/viewform",
        },
        {
            "key": "phone_numbers",
            "code": "FT",
            "title": "Fontos telefonszámok",
            "description": "Koordinátor, tréning és sürgős kapcsolatok.",
        },
        {
            "key": "rules",
            "code": "SZB",
            "title": "Szabályzat",
            "description": "Futár szabályok, alapfolyamatok és belső tudnivalók.",
        },
        {
            "key": "personal_data",
            "code": "SA",
            "title": "Személyes adatok",
            "description": "Saját adatok és későbbi módosítási folyamatok.",
        },
    ]


def get_peopleforce_card(action_key):
    return next(
        (
            card
            for card in get_peopleforce_cards()
            if card["key"] == action_key
        ),
        {},
    )


def get_peopleforce_selected_action():
    try:
        value = st.query_params.get("peopleforce", "")
    except Exception:
        return ""

    if isinstance(value, list):
        value = value[0] if value else ""

    return clean_display_text(value)


def build_peopleforce_href(action_key):
    try:
        params = dict(st.query_params)
    except Exception:
        params = {}

    params["peopleforce"] = action_key
    query = urlencode(params, doseq=True)
    return f"?{query}#peopleforce"


def render_peopleforce_placeholder_content(card):
    st.subheader(card.get("title", "PeopleForce"))
    st.info(
        "Ez a PeopleForce modul elő van készítve. Ide kötjük majd a konkrét folyamatot, DB mentést, e-mailt vagy jóváhagyást."
    )


def render_peopleforce_action_content(action_key, row, user, selected_month=None):
    card = get_peopleforce_card(action_key)

    if action_key in ["tig", "settlement", "my_invoices"]:
        render_peopleforce_monthly_documents(
            action_key,
            row,
            user,
            selected_month=selected_month,
        )
        return

    if action_key == "invoice_submit":
        render_invoice_submission_panel(row, user)

        url = card.get("url")
        if url:
            st.markdown(
                f'<a class="route-nav-button" href="{escape(url)}" target="_blank" rel="noopener noreferrer">Google űrlap megnyitása</a>',
                unsafe_allow_html=True,
            )
        return

    if action_key == "invoice_check":
        render_invoice_quick_check_panel(row, user)
        return

    render_peopleforce_placeholder_content(card)


if hasattr(st, "dialog"):
    @st.dialog("PeopleForce")
    def render_peopleforce_action_dialog(action_key, row, user, selected_month=None):
        render_peopleforce_action_content(
            action_key,
            row,
            user,
            selected_month=selected_month,
        )
else:
    def render_peopleforce_action_dialog(action_key, row, user, selected_month=None):
        with st.expander("PeopleForce", expanded=True):
            render_peopleforce_action_content(
                action_key,
                row,
                user,
                selected_month=selected_month,
            )


def render_peopleforce_card_grid(cards, card_states):
    for start in range(0, len(cards), 3):
        columns = st.columns(3)

        for offset, card in enumerate(cards[start:start + 3]):
            with columns[offset]:
                href = escape(build_peopleforce_href(card["key"]), quote=True)
                status_badge = render_peopleforce_card_status_badge(
                    card_states.get(card["key"])
                )
                st.markdown(
                    f"""
<a class="peopleforce-card" href="{href}">
  <div class="peopleforce-card-head">
    <div class="peopleforce-badge">{escape(card["code"])}</div>
    {status_badge}
  </div>
  <h3>{escape(card["title"])}</h3>
  <p>{escape(card["description"])}</p>
  <span class="peopleforce-card-link">Megnyitás</span>
</a>
""",
                    unsafe_allow_html=True,
                )


def render_peopleforce_placeholder(row=None, user=None):
    user = user or {}
    safe_row = row if row is not None else {}
    cards = get_peopleforce_cards()
    courier_id = normalize_id(safe_row.get("courier_id") or user.get("courierId"))
    selected_month = get_peopleforce_month("cards")
    card_states = load_peopleforce_card_states(
        courier_id,
        selected_month,
    )

    st.markdown(
        """
<div class="courier-placeholder-card">
  <h2>PeopleForce</h2>
  <p>Ez a rész elő van készítve. Innen indulnak majd a futáros belső folyamatok.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<span id="peopleforce"></span>', unsafe_allow_html=True)
    render_peopleforce_card_grid(cards, card_states)

    selected_action = get_peopleforce_selected_action()
    if get_peopleforce_card(selected_action):
        render_peopleforce_action_dialog(
            selected_action,
            safe_row,
            user,
            selected_month=selected_month,
        )


if hasattr(st, "dialog"):
    @st.dialog("Futár személyes oldala")
    def render_courier_profile_dialog(row, user):
        render_courier_profile_content(row, user)
else:
    def render_courier_profile_dialog(row, user):
        with st.expander("Futár személyes oldala", expanded=True):
            render_courier_profile_content(row, user)


def render_hero(row, user):
    raw_name = get_courier_display_name(row, user)
    name = escape(raw_name)
    courier_id = escape(str(row.get("courier_id") or user.get("courierId") or "-"))
    warehouse = escape(get_courier_display_warehouse(row))
    vehicle_temperature = escape(
        clean_display_text(row.get("vehicle_temperature"), "Nincs adat")
    )
    vehicle_plate = escape(clean_display_text(row.get("license_plate")))
    vehicle_note = f"Hűtő: {vehicle_temperature}°C" if vehicle_temperature != "Nincs adat" else "Hűtő: nincs adat"

    if vehicle_plate:
        vehicle_note = f"{vehicle_note} | Autó: {vehicle_plate}"

    st.markdown(
        f"""
<div class="courier-hero">
  <div>
    <div class="courier-plate-label">Kifli futár cockpit</div>
    <h1>Szia, {name}!</h1>
    <p>Itt látod a mai műszakodat, az aktuális túrádat, az autódat és a fontos gyors jelzéseket.</p>
  </div>
  <div class="courier-plate">
    <div class="courier-plate-label">Futár azonosító</div>
    <div class="courier-plate-value">#{courier_id}</div>
    <div class="stat-note">Raktár: {warehouse}</div>
    <div class="stat-note">{vehicle_note}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def stat_card(label, value, note=""):
    return f"""
<div class="stat-card">
  <div class="stat-label">{label}</div>
  <div class="stat-value">{value}</div>
  <div class="stat-note">{note}</div>
</div>
"""


@st.cache_data(show_spinner=False)
def get_kifli_destination_logo():
    path = PROJECT_ROOT / "assets" / "kifli-destination.png"

    if not path.exists():
        return "K"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="Kifli">'


def normalize_name(value):
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def status_pill(value):
    value = str(value or "").strip()
    css_class = "today-ok" if value == "OK" else "today-missing"
    label = "OK" if value == "OK" else "Hiányzik"

    return f'<span class="today-pill {css_class}">{label}</span>'


def get_driver_temperature(driver):
    vehicle = driver.get("vehicle", {}) or {}
    temperature = vehicle.get("temperature")

    if temperature in [None, ""]:
        return ""

    try:
        return str(int(float(temperature)))
    except (TypeError, ValueError):
        return str(temperature)


def get_driver_license_plate(driver):
    vehicle = driver.get("vehicle", {}) or {}
    return str(vehicle.get("license_plate") or "").strip()


def attach_live_vehicle_info(row, driver):
    row = row.copy()
    row["vehicle_temperature"] = get_driver_temperature(driver)
    row["license_plate"] = get_driver_license_plate(driver)
    return row


def build_fast_shift_records(work_date_text):
    try:
        giriton_records = {
            record["serial"]: record
            for record in read_giriton_shift_records(
                work_date_text
            )
            if record.get("serial")
        }
    except Exception:
        giriton_records = {}

    try:
        foglalas_records = {
            record["serial"]: record
            for record in read_foglalasok_records(
                work_date_text
            )
            if record.get("serial")
        }
    except Exception:
        foglalas_records = {}

    records = []

    for serial in sorted(set(giriton_records) | set(foglalas_records)):
        giriton_record = giriton_records.get(serial, {})
        foglalas_record = foglalas_records.get(serial, {})
        source = giriton_record or foglalas_record
        records.append({
            "work_date": source.get("work_date", work_date_text),
            "name": source.get("name", ""),
            "email": source.get("email", ""),
            "warehouse": source.get("warehouse", ""),
            "start": source.get("start", ""),
            "end": giriton_record.get("end", ""),
            "giriton": "OK" if giriton_record else "-",
            "muszakpro": "OK" if foglalas_record else "-",
            "missing": ", ".join(
                value
                for value, exists in [
                    ("Giriton", bool(giriton_record)),
                    ("MuszakPro", bool(foglalas_record)),
                ]
                if not exists
            ),
            "giriton_check": "GIRITON_OK" if giriton_record else "",
            "muszakpro_code": foglalas_record.get("code", ""),
            "updated_at": "",
            "match_key": serial,
            "courier_id": source.get("courier_id", ""),
        })

    return records


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_today_shift_records(work_date_text):
    records = build_fast_shift_records(
        work_date_text
    )

    if records:
        return records

    try:
        return read_shift_reconciliation_records(work_date_text)
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=DAILY_CACHE_SECONDS)
def load_shift_records_for_dates(work_date_texts):
    records = []

    for work_date_text in work_date_texts:
        records.extend(
            build_fast_shift_records(work_date_text)
        )

    if records:
        return records

    try:
        return read_shift_reconciliation_records_for_dates(
            list(work_date_texts)
        )
    except Exception:
        return []


def filter_shift_rows(records, row, user):
    courier_name = normalize_name(row.get("name") or user.get("username"))
    courier_id = normalize_id(row.get("courier_id") or user.get("courierId"))
    shifts = []

    for record in records:
        record_courier_id = normalize_id(
            record.get("courier_id")
        )

        if courier_id and record_courier_id:
            if record_courier_id != courier_id:
                continue
        elif normalize_name(record.get("name")) != courier_name:
            continue

        shifts.append(record)

    return sorted(
        shifts,
        key=lambda item: str(item.get("start", "")),
    )


def get_today_shift_rows(row, user, today):
    return get_shift_rows_for_date(row, user, today)


def get_shift_rows_for_date(row, user, work_date):
    work_date_text = work_date.isoformat()
    records = load_today_shift_records(
        work_date_text
    )

    return filter_shift_rows(records, row, user)


def get_next_sheet_shift_rows(row, user, start_date, days=14):
    work_dates = [
        start_date + timedelta(days=offset)
        for offset in range(1, days + 1)
    ]
    records = load_shift_records_for_dates(
        tuple(work_date.isoformat() for work_date in work_dates)
    )
    records_by_date = {}

    for record in records:
        records_by_date.setdefault(
            record.get("work_date", ""),
            [],
        ).append(record)

    for offset in range(1, days + 1):
        work_date = start_date + timedelta(days=offset)
        shifts = filter_shift_rows(
            records_by_date.get(work_date.isoformat(), []),
            row,
            user,
        )

        if shifts:
            return work_date, shifts

    return None, []


def refresh_shift_reconciliation_for_courier_card(today):
    refresh_counter = st.session_state.get(
        "manual_refresh_counter",
        0,
    )
    last_refresh_counter = st.session_state.get(
        "courier_card_shift_refresh_counter",
        -1,
    )

    if refresh_counter <= 0 or refresh_counter == last_refresh_counter:
        return

    with st.spinner("Műszak ellenőrzés frissítése..."):
        load_today_shift_records.clear()
        load_shift_records_for_dates.clear()

    st.session_state["courier_card_shift_refresh_counter"] = refresh_counter


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def parse_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return parsed.astimezone(LOCAL_TIMEZONE)


def format_time(value):
    parsed = parse_datetime(value) if isinstance(value, str) else value

    if not parsed:
        return ""

    return parsed.strftime("%H:%M")


def format_time_window(start, end):
    start_text = format_time(start)
    end_text = format_time(end)

    if start_text and end_text:
        return f"{start_text} - {end_text}"

    return start_text or end_text or ""


def format_minutes_compact(minutes):
    minutes = int(round(minutes))
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    hours = minutes // 60
    remaining = minutes % 60

    if hours and remaining:
        return f"{sign}{hours} óra {remaining} perc"

    if hours:
        return f"{sign}{hours} óra"

    return f"{sign}{remaining} perc"


def format_return_countdown(planned_return):
    return_at = parse_datetime(planned_return)

    if not return_at:
        return ""

    minutes_left = (return_at - local_now()).total_seconds() / 60

    if minutes_left >= 0:
        return f"Még {format_minutes_compact(minutes_left)} a raktárig"

    return f"{format_minutes_compact(abs(minutes_left))} késés a tervezett visszaérkezéshez képest"


@st.cache_data(show_spinner=False, ttl=LIVE_CACHE_SECONDS)
def load_live_courier_sources():
    return load_attendance(), load_drivers()


@st.cache_data(show_spinner=False, ttl=LIVE_CACHE_SECONDS)
def load_live_driver_detail(driver_id):
    if not driver_id:
        return {}

    return load_driver_details(driver_id)


def find_attendance_courier(attendance_data, courier_id):
    courier_id = normalize_id(courier_id)

    for courier in attendance_data.get("couriers", []):
        if normalize_id(courier.get("courierId")) == courier_id:
            return courier

    return {}


def find_driver(drivers_data, courier_id):
    courier_id = normalize_id(courier_id)

    for driver in drivers_data.get("drivers", []):
        if normalize_id(driver.get("driver_id")) == courier_id:
            return driver

    return {}


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def first_nested_value(data, paths, default=""):
    for path in paths:
        value = nested_get(data, path, "")

        if value not in ["", None]:
            return value

    return default


def get_driver_route_id(driver):
    return first_nested_value(
        driver,
        [
            ["route", "id"],
            ["route", "route_id"],
            ["route", "routeId"],
            ["route_id"],
            ["routeId"],
            ["status", "route_id"],
            ["status", "routeId"],
        ],
    )


def get_driver_assigned_at(driver):
    return first_nested_value(
        driver,
        [
            ["status", "assignedAt"],
            ["status", "assigned_at"],
            ["route", "assignedAt"],
            ["route", "assigned_at"],
            ["route", "route_assigned_at"],
            ["route_assigned_at"],
            ["status", "loading_finished_at"],
        ],
    )


def get_live_driver_state(driver):
    return str(
        nested_get(
            driver,
            ["status", "current_state"],
            "",
        )
    )


def get_current_shift(attendance_courier):
    shifts = get_shift_items(attendance_courier)

    if not shifts:
        return {}

    now = local_now()

    for shift in shifts:
        end_at = shift.get("end_at")
        if end_at and end_at >= now - timedelta(minutes=15):
            return shift

    return {}


def get_shift_items(attendance_courier):
    shifts = []

    for shift in attendance_courier.get("shifts", []):
        start_at = parse_datetime(shift.get("shiftStart"))
        end_at = parse_datetime(shift.get("shiftEnd"))

        if not start_at:
            continue

        shifts.append(
            {
                "raw": shift,
                "start_at": start_at,
                "end_at": end_at,
            }
        )

    return sorted(shifts, key=lambda item: item["start_at"])


def get_next_shift(attendance_courier):
    now = local_now()

    for shift in get_shift_items(attendance_courier):
        end_at = shift.get("end_at")
        if end_at and end_at >= now - timedelta(minutes=15):
            return shift

    return {}


def get_future_shift(attendance_courier):
    now = local_now()

    for shift in get_shift_items(attendance_courier):
        start_at = shift.get("start_at")
        if start_at and start_at > now:
            return shift

    return {}


def get_best_route(driver, driver_detail):
    routes = driver_detail.get("routes", [])

    if not routes:
        return {}

    driver_route_id = normalize_id(get_driver_route_id(driver))
    if driver_route_id:
        for route in routes:
            if normalize_id(route.get("id") or route.get("routeId")) == driver_route_id:
                return route

    assigned_at = get_driver_assigned_at(driver)
    if assigned_at:
        for route in routes:
            if route.get("assignedAt") == assigned_at:
                return route

    open_routes = [
        route
        for route in routes
        if not route.get("realReturn")
    ]

    candidates = open_routes or routes

    return sorted(
        candidates,
        key=lambda route: parse_datetime(route.get("assignedAt")) or datetime.min.replace(tzinfo=LOCAL_TIMEZONE),
    )[-1]


def selected_shift_date(today):
    key = "courier_dashboard_shift_day_offset"
    st.session_state.setdefault(key, 0)

    left, middle, right = st.columns([1, 5, 1])

    with left:
        if st.button("‹", key="shift_day_prev", use_container_width=True):
            st.session_state[key] = max(0, st.session_state[key] - 1)

    with right:
        if st.button("›", key="shift_day_next", use_container_width=True):
            st.session_state[key] = min(2, st.session_state[key] + 1)

    offset = st.session_state[key]
    selected_date = today + timedelta(days=offset)
    labels = {
        0: "Mai műszak",
        1: "Holnapi műszak",
        2: "Holnaputáni műszak",
    }

    with middle:
        st.markdown(
            f"""
<div class="shift-day-selector">
  <div>
    <div class="shift-day-label">{labels.get(offset, "Műszak")}</div>
    <div class="shift-day-date">{selected_date:%Y.%m.%d}</div>
  </div>
  <div class="stat-note">Lapozz a nyilakkal: ma, holnap, holnapután</div>
</div>
""",
            unsafe_allow_html=True,
        )

    return selected_date, labels.get(offset, "Műszak")


def render_today_shifts(row, user, work_date=None, day_label="Mai műszak"):
    today = local_now().date()
    work_date = work_date or today
    shifts = get_today_shift_rows(
        row,
        user,
        work_date,
    )

    if shifts:
        rows_html = []

        for shift in shifts:
            rows_html.append(
                f"""
<div class="today-shift-row">
  <div><strong>{escape(str(shift.get("start", "")))}</strong> - {escape(str(shift.get("end", "")))}</div>
  <div>{escape(str(shift.get("warehouse", "")))}</div>
  <div>Giriton: {status_pill(shift.get("giriton"))}</div>
  <div>MűszakPro: {status_pill(shift.get("muszakpro"))}</div>
</div>
"""
            )

        body = "".join(rows_html)
        title = "Ma dolgozol" if work_date == today else f"{day_label}: dolgozol"
        note = "A műszakod a feltöltött Giriton és MűszakPro adatok alapján."
    else:
        body = """
<div class="today-shift-row">
  <div><strong>Nincs műszak ezen a napon</strong></div>
  <div>-</div>
  <div>Giriton: <span class="today-pill today-missing">Nincs adat</span></div>
  <div>MűszakPro: <span class="today-pill today-missing">Nincs adat</span></div>
</div>
"""
        title = "Ma nem látok műszakot" if work_date == today else f"{day_label}: nincs műszak"
        note = "Ha mégis dolgozol, akkor valószínűleg a robot frissítése vagy a feltöltés hiányzik."

    st.markdown(
        f"""
<div class="today-shift-card">
  <div class="today-shift-title">{title}</div>
  <div class="stat-note">{note}</div>
  {body}
</div>
""",
        unsafe_allow_html=True,
    )


def get_route_road_stops(row, details):
    customers = details.get("customers", pd.DataFrame())
    courier_id = normalize_id(row.get("courier_id"))

    if customers.empty or not courier_id or "courierId" not in customers.columns:
        return []

    customers = customers.copy()
    customers = customers[
        customers["courierId"].apply(normalize_id) == courier_id
    ]

    if customers.empty:
        return []

    if "date" in customers.columns:
        customers["date_dt"] = pd.to_datetime(
            customers["date"],
            errors="coerce",
        ).dt.date
        today = date.today()
        today_rows = customers[customers["date_dt"] == today]
        if not today_rows.empty:
            customers = today_rows
        else:
            return []

    if "routeId" in customers.columns:
        route_ids = customers["routeId"].dropna().astype(str)
        if not route_ids.empty:
            latest_route_id = route_ids.iloc[-1]
            customers = customers[
                customers["routeId"].astype(str) == latest_route_id
            ]

    if "position" in customers.columns:
        customers["position_sort"] = pd.to_numeric(
            customers["position"],
            errors="coerce",
        ).fillna(9999)
        customers = customers.sort_values("position_sort")

    stops = []
    current_index = None

    for index, (_, customer) in enumerate(customers.head(8).iterrows()):
        real_arrival = str(customer.get("realArrivalTime", "") or "").strip()
        if current_index is None and not real_arrival:
            current_index = index

        address = str(customer.get("address", "") or "").strip()
        position = str(customer.get("position", index + 1) or index + 1)
        stops.append(
            {
                "position": position,
                "address": address or f"Cim {position}",
                "order_id": customer.get("orderId") or customer.get("id") or "",
                "deliver_since": customer.get("deliverSince") or "",
                "deliver_till": customer.get("deliverTill") or "",
                "route_id": customer.get("routeId") or "",
            }
        )

    if stops and current_index is None:
        current_index = len(stops) - 1

    for index, stop in enumerate(stops):
        stop["current"] = index == current_index

    return stops


def render_shift_state_road(title, subtitle, dot_label, dot_text, note, show_help=False):
    kifli_logo = get_kifli_destination_logo()
    help_html = (
        '<div class="route-help-button">Elakadtam, segítség kell</div>'
        if show_help
        else ""
    )

    st.markdown(
        f"""
<div class="route-road-card">
  <div class="route-road-head">
    <div class="route-brand">
      <div class="route-brand-logo">K</div>
      <div>
        <div class="route-road-title">{escape(title)}</div>
        <div class="route-road-subtitle">{escape(subtitle)}</div>
      </div>
    </div>
    <div class="route-road-subtitle">A Kifli készen áll</div>
  </div>
  <div class="route-road-track" style="--stop-count: 2;">
    <div class="route-stop route-stop-home">
      <div class="route-stop-dot">H</div>
      <div class="route-stop-label">Otthon</div>
    </div>
    <div class="route-stop route-stop-waiting">
      <div class="route-stop-dot">{escape(dot_label)}</div>
      <div class="route-stop-label">{escape(dot_text)}</div>
    </div>
    <div class="route-depot">
      <div class="route-depot-icon">{kifli_logo}</div>
      <div class="route-stop-label">Kifli</div>
    </div>
  </div>
  <div class="fun-note route-empty-note">{escape(note)}{help_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_no_shift_road():
    render_shift_state_road(
        "Műszakra várunk",
        "Ma még nem látok műszakot a neveden.",
        "?",
        "Pihenő mód",
        "Ma még nincs műszakod. A futárcipő pihen, a kávé pedig jogosan lassú.",
    )


def render_before_shift_road(minutes_to_start):
    minutes_to_start = max(minutes_to_start, 0)

    if minutes_to_start > 40:
        render_shift_state_road(
            "Lassan kezdődik a műszakod",
            f"Még körülbelül {minutes_to_start} perc van a kezdésig.",
            "40+",
            "Készülődés",
            "Még van idő összerakni magad, de a műszak már integet a távolból.",
        )
        return

    render_shift_state_road(
        "Ideje Giritonba bejelentkezni",
        f"Még körülbelül {minutes_to_start} perc van a kezdésig.",
        "!",
        "Depó felé",
        "Jelentkezz be Giritonba. Ha valami nem áll össze, kérj segítséget.",
        show_help=True,
    )


def render_checked_in_waiting_road(next_shift=None):
    subtitle = "Amint route kerül a nevedre, frissítés után megjelenik az útvonal."
    note = "Bent vagy a rendszerben. Most már csak a route-nak kell megérkeznie."

    if next_shift:
        start_text = next_shift["start_at"].strftime("%H:%M")
        end_text = (
            next_shift["end_at"].strftime("%H:%M")
            if next_shift.get("end_at")
            else ""
        )
        subtitle = f"Következő műszak: {start_text} - {end_text}."
        note = "Visszaértél, és van még műszakod. Várjuk a következő túrát."

    render_shift_state_road(
        "Bejelentkezve, túrára vársz",
        subtitle,
        "OK",
        "Túrára vár",
        note,
    )


def render_day_done_road():
    render_shift_state_road(
        "Mára kész vagy",
        "Nem látok több mai műszakot a neveden.",
        "✓",
        "Nap lezárva",
        "Ha nincs új műszak, jöhet a pihenés. A futárcipő ma már letette a voksát a kanapé mellett.",
    )


def render_returned_to_depot_road():
    render_shift_state_road(
        "Visszaértél a depóba",
        "A route lezárult, jöhet a következő kör vagy egy kis levegő.",
        "✓",
        "Kör kész",
        "Szép munka. Ha új route kerül rád, frissítés után itt jelenik meg.",
    )


def get_route_checkpoint_stops(route):
    checkpoints = route.get("checkpoints", [])

    if not checkpoints:
        return []

    stops = []
    current_index = None

    for index, checkpoint in enumerate(checkpoints[:8]):
        left_stop = (
            checkpoint.get("realDepartureTime")
            or checkpoint.get("realArrivalTime")
        )

        if current_index is None and not left_stop:
            current_index = index

        position = str(checkpoint.get("position", index + 1) or index + 1)
        address = str(checkpoint.get("address", "") or "").strip()
        stops.append(
            {
                "position": position,
                "address": address or f"Cím {position}",
                "order_id": checkpoint.get("orderId") or checkpoint.get("id") or "",
                "deliver_since": checkpoint.get("deliverSince") or "",
                "deliver_till": checkpoint.get("deliverTill") or "",
                "route_id": checkpoint.get("routeId") or "",
            }
        )

    if stops and current_index is None:
        current_index = len(stops) - 1

    for index, stop in enumerate(stops):
        stop["current"] = index == current_index

    return stops


def get_current_route_stop(route):
    stops = get_route_checkpoint_stops(route)

    if not stops:
        return {}

    return next(
        (stop for stop in stops if stop.get("current")),
        stops[-1],
    )


def get_kiflis_journey_stops(route):
    checkpoints = route.get("checkpoints", []) or []

    if not checkpoints:
        return []

    sorted_checkpoints = sorted(
        checkpoints,
        key=lambda checkpoint: (
            int(checkpoint.get("position") or 999999),
            parse_datetime(checkpoint.get("plannedArrivalTime"))
            or parse_datetime(checkpoint.get("estimatedArrivalTime"))
            or parse_datetime(checkpoint.get("deliverSince"))
            or datetime.max.replace(tzinfo=LOCAL_TIMEZONE),
        ),
    )
    stops = []

    for index, checkpoint in enumerate(sorted_checkpoints):
        position = str(checkpoint.get("position", index + 1) or index + 1)
        stops.append(
            {
                "position": position,
                "address": str(checkpoint.get("address", "") or "").strip()
                or f"Cím {position}",
                "order_id": checkpoint.get("orderId") or checkpoint.get("id") or "",
                "deliver_since": checkpoint.get("deliverSince") or "",
                "deliver_till": checkpoint.get("deliverTill") or "",
                "planned_arrival": checkpoint.get("plannedArrivalTime") or "",
                "estimated_arrival": checkpoint.get("estimatedArrivalTime") or "",
                "real_arrival": checkpoint.get("realArrivalTime") or "",
                "real_departure": checkpoint.get("realDepartureTime") or "",
                "route_id": checkpoint.get("routeId") or "",
            }
        )

    return stops


def get_initial_journey_index(stops):
    if not stops:
        return 0

    for index, stop in enumerate(stops):
        if not (
            clean_display_text(stop.get("real_departure"))
            or clean_display_text(stop.get("real_arrival"))
        ):
            return index

    return len(stops)


def find_route_by_id(driver_detail, route_id):
    route_id = normalize_id(route_id)

    if not route_id:
        return {}

    for route in driver_detail.get("routes", []) or []:
        if normalize_id(route.get("id") or route.get("routeId")) == route_id:
            return route

    return {}


def load_kiflis_journey_route(row):
    courier_id = normalize_id(row.get("courier_id"))

    if not courier_id:
        return {}, {}, []

    notification = read_latest_discord_route(courier_id)
    route_id = normalize_id(notification.get("route_id"))

    if not route_id:
        return notification, {}, []

    cache_key = f"kiflis_journey_cache_{courier_id}"
    cached = st.session_state.get(cache_key, {})

    if cached.get("route_id") == route_id:
        return (
            cached.get("notification", {}),
            cached.get("route", {}),
            cached.get("stops", []),
        )

    driver_detail = load_live_driver_detail(courier_id)
    route = find_route_by_id(driver_detail, route_id)
    stops = get_kiflis_journey_stops(route)
    st.session_state[cache_key] = {
        "route_id": route_id,
        "notification": notification,
        "route": route,
        "stops": stops,
    }
    st.session_state.pop(
        f"kiflis_journey_index_{courier_id}_{route_id}",
        None,
    )

    return notification, route, stops


def is_journey_stop_late(stop):
    planned_at = (
        parse_datetime(stop.get("planned_arrival"))
        or parse_datetime(stop.get("estimated_arrival"))
    )

    if not planned_at:
        return False

    return local_now() > planned_at


def render_empty_kiflis_journey(message, note=""):
    kifli_logo = get_kifli_destination_logo()
    st.markdown(
        f"""
<div class="kifli-journey-card">
  <div class="kifli-journey-head">
    <div>
      <div class="kifli-journey-title">Kiflis utam</div>
      <div class="kifli-journey-subtitle">{escape(message)}</div>
    </div>
    <div class="route-depot-icon">{kifli_logo}</div>
  </div>
  <div class="fun-note route-empty-note">{escape(note or "A következő útvonal akkor jelenik meg, amikor a Discord cron route-ot logolt neked.")}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_kiflis_journey(row, user):
    app_settings = load_app_settings()
    courier_id = normalize_id(row.get("courier_id") or user.get("courierId"))
    notification, route, stops = load_kiflis_journey_route(row)
    route_id = normalize_id(notification.get("route_id") or route.get("id") or route.get("routeId"))

    if not route_id:
        render_empty_kiflis_journey(
            "Most nincs betöltött route.",
            "Ha kapsz új túrát, a Discord cron logolja, és utána itt megjelenik a Kiflis utad.",
        )
        return

    if not route or not stops:
        render_empty_kiflis_journey(
            f"Route #{route_id} már látszik, de a címlista még nem töltődött be.",
            "Frissítés után újra megpróbálom a driver-detail adatokból felhúzni a címeket.",
        )
        return

    progress_key = f"kiflis_journey_index_{courier_id}_{route_id}"

    if progress_key not in st.session_state:
        st.session_state[progress_key] = get_initial_journey_index(stops)

    current_index = min(
        max(int(st.session_state.get(progress_key, 0)), 0),
        len(stops),
    )
    st.session_state[progress_key] = current_index
    current_stop = stops[current_index] if current_index < len(stops) else {}
    current_order_id = normalize_id(current_stop.get("order_id")) or "-"
    late = bool(current_stop and is_journey_stop_late(current_stop))
    pawn_class = "kifli-pawn-late" if late else "kifli-pawn-ok"
    status_text = "Késésben vagy a tervezett érkezéshez képest." if late else "Haladsz, még nincs késés a tervezett érkezéshez képest."
    return_countdown = format_return_countdown(
        route.get("realReturn")
        or route.get("plannedReturn")
        or notification.get("planned_return")
    )
    kifli_logo = get_kifli_destination_logo()
    stop_items = []

    for index, stop in enumerate(stops):
        is_current = index == current_index
        is_done = index < current_index
        classes = ["kifli-route-stop"]

        if is_current:
            classes.append("kifli-route-stop-current")

        if is_done:
            classes.append("kifli-stop-done")

        marker_class = f"kifli-stop-marker {pawn_class}" if is_current else "kifli-stop-marker"
        marker_text = "K" if is_current else escape(str(stop.get("position") or index + 1))
        address = escape(clean_display_text(stop.get("address"), "-"))
        order_id = normalize_id(stop.get("order_id")) or "-"
        time_window = format_time_window(
            stop.get("deliver_since"),
            stop.get("deliver_till"),
        )
        planned_arrival = format_time(
            stop.get("planned_arrival")
            or stop.get("estimated_arrival")
        )
        detail_parts = []

        if order_id != "-":
            detail_parts.append(f"Rendelés #{escape(order_id)}")

        if time_window:
            detail_parts.append(f"Időablak: {escape(time_window)}")

        if planned_arrival:
            detail_parts.append(f"Tervezett érkezés: {escape(planned_arrival)}")

        stop_items.append(
            f"""
<div class="{' '.join(classes)}">
  <div class="{marker_class}">{marker_text}</div>
  <div class="kifli-stop-card">
    <div class="kifli-stop-title">{address}</div>
    <div class="kifli-stop-note">{' | '.join(detail_parts) or 'Nincs részletes időadat.'}</div>
  </div>
</div>
"""
        )

    route_meta = (
        f'<span class="kifli-route-meta">Route #{escape(route_id)}</span>'
        f'<span class="kifli-route-meta">Aktuális rendelés #{escape(current_order_id)}</span>'
    )

    st.markdown(
        f"""
<div class="kifli-journey-card">
  <div class="kifli-journey-head">
    <div>
      <div class="kifli-journey-title">Kiflis utam {route_meta}</div>
      <div class="kifli-journey-subtitle">{escape(status_text)}</div>
    </div>
    <div class="route-road-subtitle">{escape(return_countdown or "A Kifli készen áll")}</div>
  </div>
  <div class="kifli-route-list">
    {''.join(stop_items)}
  </div>
  <div class="kifli-depot-finish">
    <div class="route-depot-icon">{kifli_logo}</div>
    <div class="kifli-depot-card"><strong>Kifli depó</strong><br>A kör vége itt vár rád.</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    if current_stop:
        current_address_raw = clean_display_text(current_stop.get("address"))
        waze_url = (
            "https://waze.com/ul?"
            f"q={quote_plus(current_address_raw)}"
            "&navigate=yes"
        )
        left, right = st.columns(2)

        with left:
            if st.button(
                "Elhagyom a címet",
                key=f"kiflis_leave_stop_{courier_id}_{route_id}_{current_index}",
                use_container_width=True,
            ):
                st.session_state[progress_key] = min(
                    current_index + 1,
                    len(stops),
                )
                st.rerun()

        with right:
            if not app_settings.get("waze_button_hidden", False):
                st.markdown(
                    f'<a class="route-nav-button" href="{escape(waze_url, quote=True)}" target="_blank" rel="noopener noreferrer">Irány a cím</a>',
                    unsafe_allow_html=True,
                )
    else:
        st.success("Minden cím elhagyva. Irány vissza a Kiflihez.")


def render_route_assignment_popup_content(row, route, current_stop):
    user = st.session_state.get("user", {})
    name = get_courier_display_name(row, user)
    courier_id = normalize_id(row.get("courier_id")) or "-"
    route_id = normalize_id(route.get("id") or route.get("routeId")) or "-"
    order_id = normalize_id(current_stop.get("order_id")) or "-"
    address = clean_display_text(current_stop.get("address"), "-")
    time_window = format_time_window(
        current_stop.get("deliver_since"),
        current_stop.get("deliver_till"),
    )
    planned_departure = format_time(route.get("plannedDeparture")) or "-"
    planned_return = format_time(route.get("realReturn") or route.get("plannedReturn")) or "-"

    st.write(f"**Futár:** {name} #{courier_id}")
    st.write(f"**Route ID:** {route_id}")
    st.write(f"**Aktuális rendelés:** {order_id}")
    st.write(f"**Aktuális cím:** {address}")

    if time_window:
        st.write(f"**Ügyfél időablak:** {time_window}")

    st.write(f"**Tervezett indulás:** {planned_departure}")
    st.write(f"**Tervezett visszaérkezés:** {planned_return}")
    st.info("Új túra került rád. A részletek a Kiflis kártyán is frissültek.")


if hasattr(st, "dialog"):
    @st.dialog("Új túra érkezett")
    def render_route_assignment_popup(row, route, current_stop):
        render_route_assignment_popup_content(row, route, current_stop)
else:
    def render_route_assignment_popup(row, route, current_stop):
        with st.expander("Új túra érkezett", expanded=True):
            render_route_assignment_popup_content(row, route, current_stop)


def maybe_render_route_assignment_popup(row, route, current_stop):
    if not route or not current_stop:
        return

    courier_id = normalize_id(row.get("courier_id"))
    route_id = normalize_id(
        route.get("id")
        or route.get("routeId")
        or current_stop.get("route_id")
    )

    if not courier_id or not route_id:
        return

    state_key = f"courier_route_popup_seen_{courier_id}_{route_id}"

    if st.session_state.get(state_key):
        return

    st.session_state[state_key] = True
    render_route_assignment_popup(row, route, current_stop)


def render_route_road(row, details, show_route_popup=False):
    app_settings = load_app_settings()
    courier_id = normalize_id(row.get("courier_id"))
    attendance_data, drivers_data = load_live_courier_sources()
    attendance_courier = find_attendance_courier(
        attendance_data,
        courier_id,
    )
    driver = find_driver(
        drivers_data,
        courier_id,
    )
    is_active = driver.get("active")

    if is_active is False:
        future_shift = get_future_shift(attendance_courier)

        if future_shift:
            minutes_to_start = int(
                (future_shift["start_at"] - local_now()).total_seconds() // 60
            )
            render_before_shift_road(minutes_to_start)
        else:
            render_day_done_road()

        return

    current_shift = get_current_shift(attendance_courier)

    if not current_shift:
        if get_shift_items(attendance_courier):
            render_day_done_road()
        else:
            render_no_shift_road()
        return

    shift = current_shift["raw"]
    start_at = current_shift["start_at"]
    minutes_to_start = int(
        (start_at - local_now()).total_seconds() // 60
    )
    checked_in = bool(shift.get("availableForShiftSince"))
    driver_detail = load_live_driver_detail(courier_id)
    open_route = get_best_route(driver, driver_detail)
    live_state = get_live_driver_state(driver)
    live_route_active = live_state == "Delivering"
    route_without_return = bool(open_route and not open_route.get("realReturn"))
    route_is_open = bool(
        open_route
        and (
            live_route_active
            or route_without_return
        )
    )

    if route_is_open and app_settings.get("route_card_hidden", False):
        hidden_route_id = normalize_id(open_route.get("id") or open_route.get("routeId"))

        try:
            notify_route_assigned_once(
                courier_id,
                get_courier_display_name(row, st.session_state.get("user", {})),
                hidden_route_id,
                planned_departure=format_time(open_route.get("plannedDeparture")),
                planned_return=format_time(
                    open_route.get("realReturn") or open_route.get("plannedReturn")
                ),
            )
        except Exception:
            pass

        render_shift_state_road(
            "Útvonal elrejtve",
            "A route aktív, de az útvonal megjelenítése most ki van kapcsolva.",
            "OK",
            "Rejtve",
            "A részletek a Beállítások oldalon kapcsolhatók vissza.",
        )
        return

    if route_is_open:
        current_route_stop = get_current_route_stop(open_route)
        stops = [current_route_stop] if current_route_stop else []
    else:
        stops = []

    if not route_is_open and open_route and open_route.get("realReturn"):
        next_shift = get_next_shift(attendance_courier)
        if next_shift:
            render_checked_in_waiting_road(next_shift)
        else:
            render_day_done_road()
        return

    if not stops and route_is_open:
        stops = get_route_road_stops(row, details)

    if not stops:
        if checked_in:
            render_checked_in_waiting_road()
        else:
            render_before_shift_road(minutes_to_start)
        return

    current_stop = stops[0]
    current_address_raw = str(current_stop.get("address", "") or "").strip()
    current_address = escape(current_address_raw)
    current_position_raw = str(current_stop.get("position", "") or "")
    current_position = escape(current_position_raw)
    current_order_id = normalize_id(current_stop.get("order_id")) or "-"
    current_route_id = normalize_id(
        open_route.get("id")
        or open_route.get("routeId")
        or current_stop.get("route_id")
    )
    time_window = format_time_window(
        current_stop.get("deliver_since"),
        current_stop.get("deliver_till"),
    )
    time_window_html = (
        f'<span class="route-window-note">Időablak: {escape(time_window)}</span><br>'
        if time_window
        else ""
    )
    route_return_at = open_route.get("realReturn") or open_route.get("plannedReturn")
    return_countdown = format_return_countdown(route_return_at)
    route_title_meta = (
        f'<span class="route-inline-meta">Rendelés #{escape(current_order_id)}</span>'
        if current_order_id != "-"
        else ""
    )
    route_subtitle = "Zöld jel = aktuális cím"

    if current_route_id:
        route_subtitle = f"{route_subtitle} | Route {current_route_id}"

    try:
        notify_route_assigned_once(
            courier_id,
            get_courier_display_name(row, st.session_state.get("user", {})),
            current_route_id,
            current_order_id if current_order_id != "-" else "",
            current_address_raw,
            planned_departure=format_time(open_route.get("plannedDeparture")),
            planned_return=format_time(route_return_at),
        )
    except Exception:
        pass

    if show_route_popup:
        maybe_render_route_assignment_popup(row, open_route, current_stop)

    short_address = (
        current_address[:42] + "..."
        if len(current_address) > 42
        else current_address
    )
    waze_url = (
        "https://waze.com/ul?"
        f"q={quote_plus(current_address_raw)}"
        "&navigate=yes"
    )
    waze_button_html = (
        ""
        if app_settings.get("waze_button_hidden", False)
        else f'<a class="route-nav-button" href="{waze_url}" target="_blank" rel="noopener noreferrer">Irány a cím</a>'
    )
    kifli_logo = get_kifli_destination_logo()

    st.markdown(
        f"""
<div class="route-road-card">
  <div class="route-road-head">
    <div class="route-brand">
      <div class="route-brand-logo">K</div>
      <div>
        <div class="route-road-title">Mai útvonal {route_title_meta}</div>
        <div class="route-road-subtitle">{escape(route_subtitle)}</div>
      </div>
    </div>
    <div class="route-road-subtitle">{escape(return_countdown or "A Kifli készen áll")}</div>
  </div>
  <div class="route-road-track" style="--stop-count: 1;">
    <div class="route-stop route-stop-current">
      <div class="route-stop-dot">{current_position}</div>
      <div class="route-stop-label">{short_address}</div>
    </div>
    <div class="route-depot">
      <div class="route-depot-icon">{kifli_logo}</div>
      <div class="route-stop-label">Kifli</div>
    </div>
  </div>
  <div class="bag-alert-preview">
    <div>
      <div class="bag-alert-title">Táska hiány bejelentés - design előnézet</div>
      <div class="bag-alert-copy">{time_window_html}Aktuális cím: <strong>{current_address}</strong><br>Később innen indulhat majd a sablon e-mail és a kép csatolása az előre megadott címre.</div>
    </div>
    {waze_button_html}
    <div class="bag-alert-button">Táska hiány jelzése</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def calculate_route_mix(details, row, start_date=None, end_date=None):
    if row.get("estimated_max_revenue") not in [None, ""]:
        normal_routes = int(float(row.get("normal_routes", 0) or 0))
        express_routes = int(float(row.get("express_routes", 0) or 0))
        max_revenue = float(row.get("estimated_max_revenue", 0) or 0)
        avg_revenue = float(row.get("avg_revenue_per_route", 0) or 0)

        return {
            "express_routes": express_routes,
            "normal_routes": normal_routes,
            "max_revenue": max_revenue,
            "avg_revenue_per_route": avg_revenue,
        }

    earnings = read_sheet_dataframe("DSP_Earning_Estimate")
    courier_id = normalize_id(row.get("courier_id"))

    if not earnings.empty and courier_id and "courierId" in earnings.columns:
        earnings = earnings.copy()
        earnings = earnings[
            earnings["courierId"].apply(normalize_id) == courier_id
        ]

        if "date" in earnings.columns:
            earnings["date_dt"] = pd.to_datetime(
                earnings["date"],
                errors="coerce",
            ).dt.date

            if start_date:
                earnings = earnings[
                    earnings["date_dt"] >= start_date
                ]
            if end_date:
                earnings = earnings[
                    earnings["date_dt"] <= end_date
                ]

        for column in [
            "normal_routes",
            "express_routes",
            "estimated_max_revenue",
            "total_routes",
        ]:
            if column not in earnings.columns:
                earnings[column] = 0
            earnings[column] = pd.to_numeric(
                earnings[column],
                errors="coerce",
            ).fillna(0)

        total_routes = int(earnings["total_routes"].sum())
        max_revenue = float(earnings["estimated_max_revenue"].sum())

        if total_routes:
            return {
                "express_routes": int(earnings["express_routes"].sum()),
                "normal_routes": int(earnings["normal_routes"].sum()),
                "max_revenue": max_revenue,
                "avg_revenue_per_route": max_revenue / total_routes,
            }

    customers = details.get("customers", pd.DataFrame())

    if customers.empty or "routeId" not in customers.columns:
        express_routes = int(row.get("express_address_count", 0) > 0)
        total_routes = int(row.get("routes", 0))
        normal_routes = max(total_routes - express_routes, 0)
    else:
        if "courierId" in customers.columns and courier_id:
            customers = customers[
                customers["courierId"].apply(normalize_id) == courier_id
            ]

        route_groups = customers.groupby("routeId").agg(
            express_addresses=("express_address_count", "sum"),
        )
        express_routes = int(
            (route_groups["express_addresses"] > 0).sum()
        )
        total_routes = int(
            route_groups.shape[0]
        )
        normal_routes = max(
            total_routes - express_routes,
            0,
        )

    max_revenue = (
        express_routes * EXPRESS_MAX_FEE
        + normal_routes * NORMAL_CITY_MAX_FEE
    )
    avg_revenue_per_route = (
        max_revenue / (express_routes + normal_routes)
        if express_routes + normal_routes
        else 0
    )

    return {
        "express_routes": express_routes,
        "normal_routes": normal_routes,
        "max_revenue": max_revenue,
        "avg_revenue_per_route": avg_revenue_per_route,
    }


def calculate_month_revenue(row, start_date, end_date):
    snapshot_month = str(row.get("snapshot_month", "") or "")

    if snapshot_month:
        selected_month = start_date.strftime("%Y-%m")

        if selected_month == snapshot_month:
            return float(row.get("estimated_max_revenue", 0) or 0)

        previous_month_end = date.fromisoformat(
            f"{snapshot_month}-01"
        ) - timedelta(days=1)

        if selected_month == previous_month_end.strftime("%Y-%m"):
            return float(row.get("previous_month_revenue", 0) or 0)

    earnings = read_sheet_dataframe("DSP_Earning_Estimate")
    courier_id = normalize_id(row.get("courier_id"))

    if earnings.empty or not courier_id or "courierId" not in earnings.columns:
        return 0

    earnings = earnings.copy()
    earnings = earnings[
        earnings["courierId"].apply(normalize_id) == courier_id
    ]

    if earnings.empty or "date" not in earnings.columns:
        return 0

    earnings["date_dt"] = pd.to_datetime(
        earnings["date"],
        errors="coerce",
    ).dt.date
    earnings = earnings[
        (earnings["date_dt"] >= start_date)
        & (earnings["date_dt"] <= end_date)
    ]

    if earnings.empty or "estimated_max_revenue" not in earnings.columns:
        return 0

    return float(
        pd.to_numeric(
            earnings["estimated_max_revenue"],
            errors="coerce",
        ).fillna(0).sum()
    )


def month_bounds(reference_date):
    current_start = reference_date.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    return current_start, previous_start, previous_end


def selected_month_bounds(month_text, today):
    year_text, month_text = str(month_text).split("-")
    year = int(year_text)
    month = int(month_text)
    month_start = date(year, month, 1)
    month_end = date(
        year,
        month,
        monthrange(year, month)[1],
    )

    if month_start.year == today.year and month_start.month == today.month:
        month_end = today

    previous_end = month_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    return month_start, month_end, previous_start, previous_end


def render_stat_cards(row, details, start_date=None, end_date=None):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))
    today = date.today()
    selected_month_start = start_date or today.replace(day=1)
    selected_month_end = end_date or today
    previous_month_end = selected_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    selected_month_revenue = calculate_month_revenue(
        row,
        selected_month_start,
        selected_month_end,
    )
    previous_month_revenue = calculate_month_revenue(
        row,
        previous_month_start,
        previous_month_end,
    )
    route_mix = calculate_route_mix(
        details,
        row,
        start_date,
        end_date,
    )

    cards = [
        stat_card("Max bevétel lehetőség", format_currency(route_mix["max_revenue"]), "Képed alapján: expressz + city sáv / kör."),
        stat_card("Átlag / kör", format_currency(route_mix["avg_revenue_per_route"]), "Becsült kereseti lehetőség körönként."),
        stat_card("Normál körök", route_mix["normal_routes"], "City sávval becsülve."),
        stat_card("Expressz körök", route_mix["express_routes"], "Expressz sávval becsülve."),
        stat_card("Kivitt címek", delivered, "Ennyi csomag talált gazdára."),
        stat_card("Körök", routes, "Teljesített route-ok."),
        stat_card("Dolgozott napok", worked_days, "Aktív napok a szűrésben."),
        stat_card("Átlag cím / kör", format_number(row.get("avg_orders_per_route")), "Minél stabilabb, annál szebb."),
        stat_card("Időablak pontos", max(total_addresses - int(row.get("late_address_count", 0)) - int(row.get("early_address_count", 0)), 0), "Nem korai, nem késő."),
        stat_card("Átlag várakozás", format_minutes(row.get("avg_wait_minutes")), "Sorban állás, de számokban."),
    ]

    st.markdown(
        f"<div class=\"stat-grid\">{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def build_type_chart(row):
    return pd.DataFrame(
        [
            {
                "Tipus": "Normal",
                "Cimek": int(row.get("normal_address_count", 0)),
            },
            {
                "Tipus": "Expressz",
                "Cimek": int(row.get("express_address_count", 0)),
            },
        ]
    )


def build_timing_chart(row):
    total = int(row.get("total_address_count", 0))
    early = int(row.get("early_address_count", 0))
    late = int(row.get("late_address_count", 0))
    on_time = max(total - early - late, 0)

    return pd.DataFrame(
        [
            {"Statusz": "Idoben", "Cimek": on_time},
            {"Statusz": "Korai", "Cimek": early},
            {"Statusz": "Keso", "Cimek": late},
        ]
    )


def render_charts(row):
    type_df = build_type_chart(row)
    timing_df = build_timing_chart(row)

    left, right = st.columns(2)

    with left:
        st.subheader("Normál vs expressz")
        chart = (
            alt.Chart(type_df)
            .mark_arc(innerRadius=55)
            .encode(
                theta=alt.Theta("Cimek:Q"),
                color=alt.Color(
                    "Tipus:N",
                    scale=alt.Scale(range=["#6cab2f", "#f97316"]),
                ),
                tooltip=["Tipus", "Cimek"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("Időablak fegyelem")
        chart = (
            alt.Chart(timing_df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("Statusz:N", sort=None),
                y=alt.Y("Cimek:Q"),
                color=alt.Color(
                    "Statusz:N",
                    scale=alt.Scale(range=["#22c55e", "#38bdf8", "#ef4444"]),
                    legend=None,
                ),
                tooltip=["Statusz", "Cimek"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)


def render_stat_cards(row, details, start_date=None, end_date=None):
    delivered = int(row.get("delivered_orders", 0))
    routes = int(row.get("routes", 0))
    worked_days = int(row.get("worked_days", 0))
    total_addresses = int(row.get("total_address_count", 0))
    today = date.today()
    selected_month_start = start_date or today.replace(day=1)
    selected_month_end = end_date or today
    previous_month_end = selected_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    selected_month_revenue = calculate_month_revenue(
        row,
        selected_month_start,
        selected_month_end,
    )
    previous_month_revenue = calculate_month_revenue(
        row,
        previous_month_start,
        previous_month_end,
    )
    route_mix = calculate_route_mix(
        details,
        row,
        start_date,
        end_date,
    )
    on_time_addresses = max(
        total_addresses
        - int(row.get("late_address_count", 0))
        - int(row.get("early_address_count", 0)),
        0,
    )

    cards = [
        stat_card("Valasztott havi max", format_currency(selected_month_revenue), f"{selected_month_start:%Y-%m-%d} - {selected_month_end:%Y-%m-%d}"),
        stat_card("Elozo havi max", format_currency(previous_month_revenue), f"{previous_month_start:%Y-%m-%d} - {previous_month_end:%Y-%m-%d}"),
        stat_card("Atlag / kor", format_number(row.get("avg_orders_per_route")), "Osszes kivitt cim / teljesitett kor."),
        stat_card("Normal korok", route_mix["normal_routes"], "City savval becsulve."),
        stat_card("Expressz korok", route_mix["express_routes"], "Expressz savval becsulve."),
        stat_card("Kivitt cimek", delivered, "Ennyi csomag talalt gazdara."),
        stat_card("Korok", routes, "Teljesitett route-ok."),
        stat_card("Dolgozott napok", worked_days, "Aktiv napok a szuresben."),
        stat_card("Idoablak pontos", on_time_addresses, "Nem korai, nem keso."),
        stat_card("Atlag varakozas", format_minutes(row.get("avg_wait_minutes")), "Sorban allas, de szamokban."),
    ]

    st.markdown(
        f"<div class=\"stat-grid\">{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def render_extra_metrics(row):
    st.subheader("Hasznos apróságok")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Átlag túra hossz", format_minutes(row.get("avg_route_minutes")))
    col2.metric("Valós bepakolás", format_minutes(row.get("avg_real_loading_minutes")))
    col3.metric("Késő normál cím", f"{int(row.get('normal_late_address_count', 0))} ({format_percent(row.get('normal_late_address_rate'))})")
    col4.metric("Késő expressz cím", f"{int(row.get('express_late_address_count', 0))} ({format_percent(row.get('express_late_address_rate'))})")

    text = (
        "A bevételbecslés tájékoztató jellegű: a képen szereplő kiemelt expressz és city sávokkal számol, "
        "a tényleges elszámolást nem helyettesíti."
    )

    st.markdown(
        f"<div class=\"fun-note\">{text}</div>",
        unsafe_allow_html=True,
    )


def render_courier_statistics_view(current_row, user, today):
    default_month = today.strftime("%Y-%m")
    selected_month = st.text_input(
        "Hónap",
        value=default_month,
        help="Formátum: ÉÉÉÉ-HH, például: 2026-07.",
        key="courier_dashboard_stats_month",
    )

    try:
        selected_start, selected_end, _, _ = selected_month_bounds(
            selected_month,
            today,
        )
    except Exception:
        st.error("A hónapot ÉÉÉÉ-HH formátumban add meg, például: 2026-07.")
        return

    snapshot_month_text = selected_start.strftime("%Y-%m")
    app_settings = load_app_settings()
    snapshot_enabled = app_settings.get(
        "courier_card_snapshot_enabled",
        False,
    )
    summary_df = pd.DataFrame()
    details = empty_courier_details()
    load_error = None

    with st.spinner("Statisztika betöltése..."):
        if snapshot_enabled:
            try:
                summary_df, details = load_courier_card_statistics(
                    snapshot_month=snapshot_month_text,
                    user=user,
                )
            except Exception as exc:
                load_error = str(exc)

        if summary_df.empty:
            try:
                summary_df, details = build_db_statistics(
                    start_date=selected_start,
                    end_date=selected_end,
                    user=user,
                )
            except Exception as exc:
                load_error = str(exc)

    if summary_df.empty:
        if load_error:
            st.warning(f"Statisztika betöltési hiba: {load_error}")
        else:
            st.info("Ehhez a hónaphoz még nincs statisztikai adat.")
        return

    courier_id = normalize_id(current_row.get("courier_id"))
    match = summary_df[
        summary_df["courier_id"].apply(normalize_id) == courier_id
    ].copy()

    if match.empty:
        st.info("Ehhez a futárhoz nincs statisztika a kiválasztott hónapban.")
        return

    stats_row = match.iloc[0]
    st.subheader(f"Statisztika: {selected_start:%Y-%m}")
    render_stat_cards(
        stats_row,
        details,
        selected_start,
        selected_end,
    )
    render_extra_metrics(stats_row)


def unique_courier_count(summary_df):
    if summary_df is None or summary_df.empty or "courier_id" not in summary_df.columns:
        return 0

    return (
        summary_df["courier_id"]
        .apply(normalize_id)
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )


def select_visible_courier(summary_df, user):
    if summary_df.empty:
        return None

    if user.get("role") == "user":
        courier_id = normalize_id(user.get("courierId"))
        match = summary_df[
            summary_df["courier_id"].apply(normalize_id) == courier_id
        ]
        return match.iloc[0] if not match.empty else None

    options = summary_df.copy()
    options["_courier_id"] = options["courier_id"].apply(normalize_id)
    options = options[options["_courier_id"] != ""].copy()

    if options.empty:
        return None

    if "name" not in options.columns:
        options["name"] = options["_courier_id"]

    options = (
        options.sort_values(["name", "_courier_id"])
        .drop_duplicates("_courier_id", keep="first")
        .copy()
    )
    name_by_id = dict(zip(options["_courier_id"], options["name"]))
    selected_id = st.selectbox(
        "Futár kiválasztása",
        options["_courier_id"].tolist(),
        format_func=lambda courier_id: name_by_id.get(courier_id, courier_id),
    )
    match = options[options["_courier_id"] == selected_id]
    return match.iloc[0] if not match.empty else None


def _show_courier_dashboard_page_legacy_unused():
    render_styles()

    user = st.session_state["user"]
    today = date.today()
    default_month = today.strftime("%Y-%m")

    start_date, end_date = st.columns(2)
    selected_start = start_date.date_input(
        "Időszak kezdete",
        value=default_start,
    )
    selected_end = end_date.date_input(
        "Időszak vége",
        value=today,
    )

    with st.spinner("Saját Kifli-kártya összerakása..."):
        summary_df, details = load_courier_statistics(
            start_date=selected_start,
            end_date=selected_end,
            user=user,
        )

    if summary_df.empty:
        st.warning("Még nincs elég adat ehhez a futár-kártyához.")
        return

    row = select_visible_courier(summary_df, user)

    if row is None:
        st.warning("Ehhez a belépéshez nem találtam futár statisztikát.")
        return

    render_hero(row, user)
    render_today_shifts(row, user)
    render_route_road(row, details)
    render_stat_cards(
        row,
        details,
        selected_start,
        selected_end,
    )
    render_extra_metrics(row)


def show_courier_dashboard_page():
    render_styles()

    user = st.session_state["user"]
    today = local_now().date()
    selected_view = render_courier_top_menu()

    snapshot_month_text = today.strftime("%Y-%m")
    directory_df = load_courier_directory(snapshot_month_text)
    directory_df = add_user_fallback_courier(
        directory_df,
        user,
        snapshot_month_text,
    )
    selector_df = directory_df

    if selector_df.empty:
        st.warning("Meg nincs futar torzs adat a Kifli kartyahoz.")
        return

    if user.get("role") != "user":
        st.caption(
            f"Futarlista forras: futar torzs | {unique_courier_count(selector_df)} futar"
        )

    current_row = select_visible_courier(selector_df, user)

    if current_row is None:
        st.warning("Ehhez a belepeshez nem talaltam futart.")
        return

    try:
        _attendance_data, drivers_data = load_live_courier_sources()
        current_driver = find_driver(
            drivers_data,
            normalize_id(current_row.get("courier_id")),
        )
        current_row = attach_live_vehicle_info(
            current_row,
            current_driver,
        )
    except Exception:
        pass

    if selected_view == "PeopleForce":
        render_hero(current_row, user)
        shift_date, shift_day_label = selected_shift_date(today)
        render_today_shifts(
            current_row,
            user,
            shift_date,
            shift_day_label,
        )
        render_peopleforce_placeholder(current_row, user)
        return

    if selected_view == "Statisztika":
        render_courier_statistics_view(
            current_row,
            user,
            today,
        )
        return

    render_kiflis_journey(
        current_row,
        user,
    )
