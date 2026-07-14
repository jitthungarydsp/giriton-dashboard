from datetime import date, datetime
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


FINAL_TABLES = [
    "bill_jitt_invoice_final_routes",
    "jitt_invoice_final_routes",
]
SUMMARY_TABLES = [
    "bill_jitt_invoice_summary",
    "jitt_invoice_summary_rows",
]
BONUS_TABLES = [
    "bill_jitt_invoice_bonus_routes",
    "jitt_invoice_bonus_routes",
]
PENALTY_TABLES = [
    "bill_jitt_invoice_penalties",
    "jitt_invoice_penalties",
]
MANUAL_ITEM_TABLES = [
    "bill_jitt_invoice_manual_items",
    "jitt_invoice_manual_items",
]
DAY_RATE_TABLES = [
    "dsp_day_rates",
]

BASE_RATE_MATRIX = [
    {"service_type": "EXPRESSZ", "day_type": "Kiemelt nap", "amount_huf": 3350},
    {"service_type": "City", "day_type": "Kiemelt nap", "amount_huf": 6500},
    {"service_type": "Régió", "day_type": "Kiemelt nap", "amount_huf": 9000},
    {"service_type": "EXPRESSZ", "day_type": "Nem kiemelt nap", "amount_huf": 2650},
    {"service_type": "City", "day_type": "Nem kiemelt nap", "amount_huf": 4500},
    {"service_type": "Régió", "day_type": "Nem kiemelt nap", "amount_huf": 6300},
]

COURIER_BONUS_AMOUNT_OVERRIDES = {
    750: 500,
}

MANUAL_ITEM_TYPES = {
    "target_reserve_open_huf": "Nyitó céltartalék",
    "target_reserve_topup_huf": "Céltartalék feltöltés",
    "target_reserve_close_huf": "Céltartalék záró egyenleg",
    "fuel_huf": "Üzemanyag",
    "damage_huf": "Károkozás",
    "cash_missing_huf": "Be nem fizetett KP",
    "other_income_huf": "Egyéb bevétel",
    "other_deduction_huf": "Egyéb levonás",
}


def money(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def format_huf(value):
    return f"{money(value):,.0f} Ft".replace(",", " ")


def normalize_text(value):
    return str(value or "").strip()


def normalize_service_type(value):
    text = normalize_text(value).lower()

    if "exp" in text:
        return "EXPRESSZ"
    if "reg" in text or "rĂ©g" in text or "rég" in text:
        return "Regio"

    return "City"


def normalize_day_rate_key(value):
    text = normalize_text(value).lower()

    if "kiemelt" in text and "nem" not in text:
        return "KIEMELT"
    if text in ["kiemelt", "highlighted"]:
        return "KIEMELT"

    return "SIMA"


def classify_day_type(work_date):
    parsed = pd.to_datetime(
        work_date,
        errors="coerce",
    )

    if pd.isna(parsed):
        return "SIMA"

    # Kiemelt nap: hetfo, pentek, szombat, vasarnap.
    # Unnepnapot kulon naptarral kesobb tudunk finomitani.
    return "KIEMELT" if int(parsed.weekday()) in [0, 4, 5, 6] else "SIMA"


def courier_bonus_amount(value):
    raw = money(value)
    rounded = int(round(raw))
    return float(COURIER_BONUS_AMOUNT_OVERRIDES.get(rounded, raw))


def build_day_rate_lookup(day_rates_df=None):
    lookup = {}

    if day_rates_df is not None and not day_rates_df.empty:
        rates = day_rates_df.copy()
        for column in ["service_type", "day_type", "loyalty_bonus", "amount"]:
            if column not in rates.columns:
                rates[column] = None

        for _index, row in rates.iterrows():
            if bool(row.get("loyalty_bonus")):
                continue

            service_type = normalize_service_type(row.get("service_type"))
            day_type = normalize_day_rate_key(row.get("day_type"))
            amount = money(row.get("amount"))

            if amount:
                lookup[(service_type, day_type)] = amount

    if lookup:
        return lookup

    fallback = {}
    for row in BASE_RATE_MATRIX:
        service_type = normalize_service_type(row.get("service_type"))
        day_type = normalize_day_rate_key(row.get("day_type"))
        fallback[(service_type, day_type)] = money(row.get("amount_huf"))

    return fallback


def enrich_invoice_routes(final_df, day_rates_df=None):
    if final_df.empty:
        return final_df.copy()

    enriched = final_df.copy()
    rate_lookup = build_day_rate_lookup(day_rates_df)
    enriched["calculated_service_type"] = enriched.get(
        "route_type",
        pd.Series("", index=enriched.index),
    ).map(normalize_service_type)
    enriched["calculated_day_type"] = enriched.get(
        "work_date",
        pd.Series("", index=enriched.index),
    ).map(classify_day_type)
    enriched["calculated_base_huf"] = enriched.apply(
        lambda row: rate_lookup.get(
            (
                row.get("calculated_service_type"),
                row.get("calculated_day_type"),
            ),
            0,
        ),
        axis=1,
    )

    return enriched


def format_date_filter(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]

    return normalize_text(value)


def month_bounds(month_value):
    if isinstance(month_value, date):
        first = month_value.replace(day=1)
    else:
        first = datetime.strptime(str(month_value)[:7], "%Y-%m").date()

    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1)
    else:
        next_month = first.replace(month=first.month + 1)

    return first, next_month - pd.Timedelta(days=1)


def get_headers():
    _supabase_url, service_role_key = get_supabase_config()
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def read_first_existing_table(table_names, select, extra_filters=None, limit=10000):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    filters = [f"select={select}", f"limit={int(limit)}"]

    if extra_filters:
        filters.extend(extra_filters)

    headers = get_headers()
    last_error = None

    for table_name in table_names:
        endpoint = f"{supabase_url}/rest/v1/{table_name}?{'&'.join(filters)}"
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=60,
        )

        if response.status_code in [404, 406]:
            last_error = response.text
            continue

        raise_for_supabase_error(response)
        rows = response.json()
        return table_name, pd.DataFrame(rows)

    raise RuntimeError(
        f"Egyik invoice tabla sem olvashato: {', '.join(table_names)}. {last_error or ''}"
    )


def read_optional_first_existing_table(table_names, select, extra_filters=None, limit=10000):
    try:
        return read_first_existing_table(
            table_names,
            select,
            extra_filters,
            limit,
        )
    except Exception:
        return None, pd.DataFrame()


def post_supabase_row(table_names, row):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    headers = get_headers()
    headers.update(
        {
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
    )
    last_error = None

    for table_name in table_names:
        endpoint = f"{supabase_url}/rest/v1/{table_name}"
        response = requests.post(
            endpoint,
            headers=headers,
            json=row,
            timeout=60,
        )

        if response.status_code in [404, 406]:
            last_error = response.text
            continue

        raise_for_supabase_error(response)
        return table_name

    raise RuntimeError(
        f"Egyik manualis invoice tabla sem irhato: {', '.join(table_names)}. {last_error or ''}"
    )


@st.cache_data(show_spinner=False, ttl=300)
def read_invoice_data(start_date, end_date):
    start_text = format_date_filter(start_date)
    end_text = format_date_filter(end_date)
    date_filters = [
        f"work_date=gte.{start_text}",
        f"work_date=lte.{end_text}",
        "order=driver_name.asc,work_date.asc",
    ]
    final_table, final_df = read_first_existing_table(
        FINAL_TABLES,
        ",".join(
            [
                "worksheet_name",
                "location",
                "driver_name",
                "route_unique_id",
                "route_type",
                "dsp",
                "work_date",
                "orders",
                "routes",
                "license_plate",
                "fixed_rate_huf",
                "fuel_bonus_huf",
                "car_fridge_bonus_huf",
                "branding_huf",
                "delay_bonus_huf",
                "compliance_bonus_huf",
                "fill_rate_bonus_huf",
                "bonus_total_huf",
                "tip_huf",
                "route_total_without_tip_huf",
                "route_total_huf",
                "comment",
            ]
        ),
        date_filters,
        limit=50000,
    )

    _summary_table, summary_df = read_first_existing_table(
        SUMMARY_TABLES,
        "worksheet_name,row_number,metric_name,total_value,normal_value,region_value,express_value,total_raw,normal_raw,region_raw,express_raw",
        ["order=worksheet_name.asc,row_number.asc"],
        limit=1000,
    )
    _bonus_table, bonus_df = read_first_existing_table(
        BONUS_TABLES,
        "worksheet_name,courier_id,driver_name,routes,bonus_huf",
        ["order=driver_name.asc"],
        limit=10000,
    )
    _penalty_table, penalty_df = read_first_existing_table(
        PENALTY_TABLES,
        "worksheet_name,penalty_type,penalty_date,courier_id,driver_name,note,amount_huf,extra_note",
        [
            f"penalty_date=gte.{start_text}",
            f"penalty_date=lte.{end_text}",
            "order=driver_name.asc,penalty_date.asc",
        ],
        limit=10000,
    )
    _manual_table, manual_df = read_optional_first_existing_table(
        MANUAL_ITEM_TABLES,
        "id,item_date,worksheet_name,driver_name,item_type,item_label,amount_huf,note,created_by,created_at",
        [
            f"item_date=gte.{start_text}",
            f"item_date=lte.{end_text}",
            "order=driver_name.asc,item_date.asc,created_at.asc",
        ],
        limit=10000,
    )
    _day_rate_table, day_rates_df = read_optional_first_existing_table(
        DAY_RATE_TABLES,
        "valid_from,valid_to,service_type,day_type,loyalty_bonus,amount",
        [
            "order=service_type.asc,day_type.asc,loyalty_bonus.asc",
        ],
        limit=1000,
    )

    return {
        "final_table": final_table,
        "final": final_df,
        "summary": summary_df,
        "bonus": bonus_df,
        "penalties": penalty_df,
        "manual": manual_df,
        "day_rates": day_rates_df,
    }


def create_manual_invoice_item(
    item_date,
    worksheet_name,
    driver_name,
    item_type,
    amount_huf,
    note="",
    created_by="",
):
    item_type = normalize_text(item_type)
    if item_type not in MANUAL_ITEM_TYPES:
        raise ValueError("Ismeretlen manualis tetel tipus.")

    row = {
        "item_date": format_date_filter(item_date),
        "worksheet_name": normalize_text(worksheet_name),
        "driver_name": normalize_text(driver_name),
        "item_type": item_type,
        "item_label": MANUAL_ITEM_TYPES[item_type],
        "amount_huf": money(amount_huf),
        "note": normalize_text(note),
        "created_by": normalize_text(created_by),
    }
    return post_supabase_row(MANUAL_ITEM_TABLES, row)


def add_numeric_columns(df, columns):
    for column in columns:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    return df


def build_weekday_counts(final_df):
    columns = [
        "driver_name",
        "worksheet_name",
        "hetfo",
        "kedd",
        "szerda",
        "csutortok",
        "pentek",
        "szombat",
        "vasarnap",
        "worked_days",
    ]

    if final_df.empty or "work_date" not in final_df.columns:
        return pd.DataFrame(columns=columns)

    route_id_column = "route_unique_id" if "route_unique_id" in final_df.columns else None
    required_columns = ["driver_name", "worksheet_name", "work_date"]
    if route_id_column:
        required_columns.append(route_id_column)

    routes = final_df[required_columns].copy()
    routes["driver_name"] = routes["driver_name"].map(normalize_text)
    routes["worksheet_name"] = routes["worksheet_name"].map(normalize_text)
    routes["work_date"] = pd.to_datetime(
        routes["work_date"],
        errors="coerce",
    )
    routes = routes.dropna(subset=["work_date"])
    if route_id_column:
        routes[route_id_column] = routes[route_id_column].map(normalize_text)
        routes["_route_key"] = routes[route_id_column]
        empty_route = routes["_route_key"] == ""
        routes.loc[empty_route, "_route_key"] = routes.index[empty_route].astype(str)
    else:
        routes["_route_key"] = routes.index.astype(str)

    worked_dates = routes[
        ["driver_name", "worksheet_name", "work_date"]
    ].drop_duplicates()
    routes = routes.drop_duplicates(
        subset=["driver_name", "worksheet_name", "work_date", "_route_key"]
    )
    routes["weekday"] = routes["work_date"].dt.weekday

    grouped = (
        routes.groupby(["driver_name", "worksheet_name"], dropna=False)
        .agg(
            hetfo=("weekday", lambda value: int((value == 0).sum())),
            kedd=("weekday", lambda value: int((value == 1).sum())),
            szerda=("weekday", lambda value: int((value == 2).sum())),
            csutortok=("weekday", lambda value: int((value == 3).sum())),
            pentek=("weekday", lambda value: int((value == 4).sum())),
            szombat=("weekday", lambda value: int((value == 5).sum())),
            vasarnap=("weekday", lambda value: int((value == 6).sum())),
        )
        .reset_index()
    )
    worked_days = (
        worked_dates.groupby(["driver_name", "worksheet_name"], dropna=False)["work_date"]
        .nunique()
        .reset_index(name="worked_days")
    )
    grouped = grouped.merge(
        worked_days,
        on=["driver_name", "worksheet_name"],
        how="left",
    )

    return grouped[columns]


def build_manual_item_summary(manual_df):
    if manual_df is None or manual_df.empty:
        return pd.DataFrame()

    manual_df = manual_df.copy()
    manual_df["driver_name"] = manual_df["driver_name"].map(normalize_text)
    manual_df["worksheet_name"] = manual_df["worksheet_name"].map(normalize_text)
    manual_df = add_numeric_columns(
        manual_df,
        ["amount_huf"],
    )
    pivot = (
        manual_df.pivot_table(
            index=["driver_name", "worksheet_name"],
            columns="item_type",
            values="amount_huf",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    pivot.columns.name = None
    return pivot


def build_driver_invoice_summary(
    final_df,
    bonus_df=None,
    penalty_df=None,
    manual_df=None,
    day_rates_df=None,
):
    if final_df.empty:
        return pd.DataFrame()

    final_df = enrich_invoice_routes(final_df, day_rates_df)
    final_df["driver_name"] = final_df["driver_name"].map(normalize_text)
    final_df["worksheet_name"] = final_df["worksheet_name"].map(normalize_text)

    numeric_columns = [
        "orders",
        "routes",
        "fixed_rate_huf",
        "fuel_bonus_huf",
        "car_fridge_bonus_huf",
        "branding_huf",
        "delay_bonus_huf",
        "compliance_bonus_huf",
        "fill_rate_bonus_huf",
        "bonus_total_huf",
        "tip_huf",
        "route_total_without_tip_huf",
        "route_total_huf",
        "calculated_base_huf",
    ]
    final_df = add_numeric_columns(final_df, numeric_columns)
    final_df["source_fixed_rate_huf"] = final_df["fixed_rate_huf"]
    final_df["source_delay_bonus_huf"] = final_df["delay_bonus_huf"]
    final_df["source_compliance_bonus_huf"] = final_df["compliance_bonus_huf"]
    final_df["fixed_rate_huf"] = final_df["calculated_base_huf"]
    final_df["delay_bonus_huf"] = final_df["delay_bonus_huf"].map(courier_bonus_amount)
    final_df["compliance_bonus_huf"] = final_df["compliance_bonus_huf"].map(courier_bonus_amount)
    final_df["bonus_total_huf"] = (
        final_df["fuel_bonus_huf"]
        + final_df["car_fridge_bonus_huf"]
        + final_df["branding_huf"]
        + final_df["delay_bonus_huf"]
        + final_df["compliance_bonus_huf"]
        + final_df["fill_rate_bonus_huf"]
    )
    final_df["route_total_without_tip_huf"] = (
        final_df["fixed_rate_huf"]
        + final_df["bonus_total_huf"]
    )
    final_df["route_total_huf"] = (
        final_df["route_total_without_tip_huf"]
        + final_df["tip_huf"]
    )

    grouped = (
        final_df.groupby(["driver_name", "worksheet_name"], dropna=False)[numeric_columns]
        .sum()
        .reset_index()
    )
    route_counts = (
        final_df.groupby(["driver_name", "worksheet_name"], dropna=False)["route_unique_id"]
        .nunique()
        .reset_index(name="route_count")
    )
    grouped = grouped.merge(
        route_counts,
        on=["driver_name", "worksheet_name"],
        how="left",
    )
    day_type_summary = (
        final_df.groupby(["driver_name", "worksheet_name", "calculated_day_type"], dropna=False)
        .agg(
            day_type_routes=("route_unique_id", "nunique"),
            day_type_base_huf=("fixed_rate_huf", "sum"),
        )
        .reset_index()
    )
    day_type_pivot = pd.DataFrame()
    if not day_type_summary.empty:
        route_pivot = day_type_summary.pivot_table(
            index=["driver_name", "worksheet_name"],
            columns="calculated_day_type",
            values="day_type_routes",
            aggfunc="sum",
            fill_value=0,
        )
        base_pivot = day_type_summary.pivot_table(
            index=["driver_name", "worksheet_name"],
            columns="calculated_day_type",
            values="day_type_base_huf",
            aggfunc="sum",
            fill_value=0,
        )
        day_type_pivot = pd.DataFrame(index=route_pivot.index)
        day_type_pivot["kiemelt_routes"] = route_pivot.get("KIEMELT", 0)
        day_type_pivot["sima_routes"] = route_pivot.get("SIMA", 0)
        day_type_pivot["kiemelt_base_huf"] = base_pivot.get("KIEMELT", 0)
        day_type_pivot["sima_base_huf"] = base_pivot.get("SIMA", 0)
        day_type_pivot = day_type_pivot.reset_index()
    if not day_type_pivot.empty:
        grouped = grouped.merge(
            day_type_pivot,
            on=["driver_name", "worksheet_name"],
            how="left",
        )
    else:
        grouped["kiemelt_routes"] = 0
        grouped["sima_routes"] = 0
        grouped["kiemelt_base_huf"] = 0
        grouped["sima_base_huf"] = 0
    weekday_counts = build_weekday_counts(final_df)
    grouped = grouped.merge(
        weekday_counts,
        on=["driver_name", "worksheet_name"],
        how="left",
    )

    if bonus_df is not None and not bonus_df.empty:
        bonus_df = bonus_df.copy()
        bonus_df["driver_name"] = bonus_df["driver_name"].map(normalize_text)
        if "courier_id" in bonus_df.columns:
            bonus_df["courier_id"] = bonus_df["courier_id"].map(normalize_text)
        bonus_df = add_numeric_columns(
            bonus_df,
            ["bonus_huf"],
        )
        bonus_grouped = (
            bonus_df.groupby("driver_name", dropna=False)["bonus_huf"]
            .sum()
            .reset_index(name="extra_bonus_huf")
        )
        grouped = grouped.merge(
            bonus_grouped,
            on="driver_name",
            how="left",
        )
        if "courier_id" in bonus_df.columns:
            bonus_ids = (
                bonus_df[["driver_name", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .groupby("driver_name", dropna=False)["courier_id"]
                .first()
                .reset_index()
            )
            grouped = grouped.merge(
                bonus_ids,
                on="driver_name",
                how="left",
            )
    else:
        grouped["extra_bonus_huf"] = 0

    if penalty_df is not None and not penalty_df.empty:
        penalty_df = penalty_df.copy()
        penalty_df["driver_name"] = penalty_df["driver_name"].map(normalize_text)
        if "courier_id" in penalty_df.columns:
            penalty_df["courier_id"] = penalty_df["courier_id"].map(normalize_text)
        penalty_df = add_numeric_columns(
            penalty_df,
            ["amount_huf"],
        )
        penalty_grouped = (
            penalty_df.groupby("driver_name", dropna=False)["amount_huf"]
            .sum()
            .reset_index(name="adjustment_huf")
        )
        grouped = grouped.merge(
            penalty_grouped,
            on="driver_name",
            how="left",
        )
        if "courier_id" not in grouped.columns and "courier_id" in penalty_df.columns:
            penalty_ids = (
                penalty_df[["driver_name", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .groupby("driver_name", dropna=False)["courier_id"]
                .first()
                .reset_index()
            )
            grouped = grouped.merge(
                penalty_ids,
                on="driver_name",
                how="left",
            )
    else:
        grouped["adjustment_huf"] = 0

    if "courier_id" not in grouped.columns:
        grouped["courier_id"] = ""
    grouped["courier_id"] = grouped["courier_id"].fillna("").map(normalize_text)

    manual_summary = build_manual_item_summary(manual_df)
    if not manual_summary.empty:
        grouped = grouped.merge(
            manual_summary,
            on=["driver_name", "worksheet_name"],
            how="left",
        )

    for column in [
        "worked_days",
        "hetfo",
        "kedd",
        "szerda",
        "csutortok",
        "pentek",
        "szombat",
        "vasarnap",
        "kiemelt_routes",
        "sima_routes",
    ]:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = grouped[column].fillna(0).astype(int)

    for column in ["kiemelt_base_huf", "sima_base_huf"]:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(
            grouped[column],
            errors="coerce",
        ).fillna(0)

    for column in MANUAL_ITEM_TYPES:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(
            grouped[column],
            errors="coerce",
        ).fillna(0)

    grouped["extra_bonus_huf"] = grouped["extra_bonus_huf"].fillna(0)
    grouped["adjustment_huf"] = grouped["adjustment_huf"].fillna(0)
    grouped["manual_total_huf"] = grouped[list(MANUAL_ITEM_TYPES.keys())].sum(axis=1)
    grouped["manual_payable_huf"] = (
        grouped["target_reserve_topup_huf"]
        + grouped["fuel_huf"]
        + grouped["damage_huf"]
        + grouped["cash_missing_huf"]
        + grouped["other_income_huf"]
        + grouped["other_deduction_huf"]
    )
    grouped["payable_total_huf"] = (
        grouped["route_total_huf"]
        + grouped["extra_bonus_huf"]
        + grouped["adjustment_huf"]
        + grouped["manual_payable_huf"]
    )

    return grouped.sort_values(
        ["driver_name", "worksheet_name"],
        kind="stable",
    )


def build_display_summary(summary_df):
    if summary_df.empty:
        return pd.DataFrame()

    columns = [
        "worksheet_name",
        "metric_name",
        "total_raw",
        "normal_raw",
        "region_raw",
        "express_raw",
    ]
    columns = [column for column in columns if column in summary_df.columns]
    return summary_df[columns].rename(
        columns={
            "worksheet_name": "Raktar ful",
            "metric_name": "Mutato",
            "total_raw": "Osszesen",
            "normal_raw": "City",
            "region_raw": "Regio",
            "express_raw": "Expressz",
        }
    )


def build_display_routes(final_df):
    if final_df.empty:
        return pd.DataFrame()

    columns = [
        "work_date",
        "worksheet_name",
        "driver_name",
        "route_unique_id",
        "route_type",
        "orders",
        "routes",
        "fixed_rate_huf",
        "delay_bonus_huf",
        "compliance_bonus_huf",
        "fill_rate_bonus_huf",
        "tip_huf",
        "route_total_huf",
        "comment",
    ]
    visible = final_df[[column for column in columns if column in final_df.columns]].copy()

    money_columns = [
        "fixed_rate_huf",
        "delay_bonus_huf",
        "compliance_bonus_huf",
        "fill_rate_bonus_huf",
        "tip_huf",
        "route_total_huf",
    ]
    for column in money_columns:
        if column in visible.columns:
            visible[column] = visible[column].map(format_huf)

    return visible.rename(
        columns={
            "work_date": "Datum",
            "worksheet_name": "Raktar ful",
            "driver_name": "Futar",
            "route_unique_id": "Route ID",
            "route_type": "Tipus",
            "orders": "Rendeles",
            "routes": "Kor",
            "fixed_rate_huf": "Alapdij",
            "delay_bonus_huf": "Kesedelmi dij",
            "compliance_bonus_huf": "Turamegfeleles",
            "fill_rate_bonus_huf": "Toltesi dij",
            "tip_huf": "Tip",
            "route_total_huf": "Osszesen",
            "comment": "Megjegyzes",
        }
    )


def build_display_driver_summary(summary_df):
    if summary_df.empty:
        return pd.DataFrame()

    visible = summary_df.copy()
    for column in [
        "fixed_rate_huf",
        "fuel_bonus_huf",
        "car_fridge_bonus_huf",
        "branding_huf",
        "delay_bonus_huf",
        "compliance_bonus_huf",
        "fill_rate_bonus_huf",
        "bonus_total_huf",
        "tip_huf",
        "route_total_huf",
        "extra_bonus_huf",
        "adjustment_huf",
        "kiemelt_base_huf",
        "sima_base_huf",
        "manual_total_huf",
        "cash_missing_huf",
        "manual_payable_huf",
        "payable_total_huf",
    ]:
        if column in visible.columns:
            visible[column] = visible[column].map(format_huf)

    return visible.rename(
        columns={
            "courier_id": "Futar ID",
            "driver_name": "Futar",
            "worksheet_name": "Raktar ful",
            "orders": "Rendeles",
            "routes": "Kor",
            "worked_days": "Dolgozott nap",
            "hetfo": "Hetfo kor",
            "kedd": "Kedd kor",
            "szerda": "Szerda kor",
            "csutortok": "Csutortok kor",
            "pentek": "Pentek kor",
            "szombat": "Szombat kor",
            "vasarnap": "Vasarnap kor",
            "kiemelt_routes": "Kiemelt kor",
            "sima_routes": "Sima kor",
            "kiemelt_base_huf": "Kiemelt alapdij",
            "sima_base_huf": "Sima alapdij",
            "route_count": "Route db",
            "fixed_rate_huf": "Alapdij",
            "delay_bonus_huf": "Kesedelmi dij",
            "compliance_bonus_huf": "Turamegfeleles",
            "fill_rate_bonus_huf": "Toltesi dij",
            "bonus_total_huf": "Bonusz osszesen",
            "tip_huf": "Tip",
            "route_total_huf": "Route osszesen",
            "extra_bonus_huf": "Egyeb bonusz",
            "adjustment_huf": "Levonas / plusz",
            "cash_missing_huf": "Be nem fizetett KP",
            "manual_total_huf": "Manualis tetelek",
            "manual_payable_huf": "Manualis fizetendo hatas",
            "payable_total_huf": "Fizetendo osszesen",
        }
    )


def build_display_manual_items(manual_df):
    if manual_df is None or manual_df.empty:
        return pd.DataFrame()

    visible = manual_df.copy()
    if "amount_huf" in visible.columns:
        visible["amount_huf"] = visible["amount_huf"].map(format_huf)

    columns = [
        "item_date",
        "worksheet_name",
        "driver_name",
        "item_label",
        "amount_huf",
        "note",
        "created_by",
    ]
    columns = [column for column in columns if column in visible.columns]
    return visible[columns].rename(
        columns={
            "item_date": "Datum",
            "worksheet_name": "Raktar ful",
            "driver_name": "Futar",
            "item_label": "Tetel",
            "amount_huf": "Osszeg",
            "note": "Megjegyzes",
            "created_by": "Rogzitette",
        }
    )


def build_base_rate_matrix_df():
    return pd.DataFrame(BASE_RATE_MATRIX)


def build_display_base_rate_matrix():
    df = build_base_rate_matrix_df()
    if df.empty:
        return df

    pivot = (
        df.pivot_table(
            index="day_type",
            columns="service_type",
            values="amount_huf",
            aggfunc="first",
        )
        .reset_index()
    )
    for column in [column for column in pivot.columns if column != "day_type"]:
        pivot[column] = pivot[column].map(format_huf)

    return pivot.rename(columns={"day_type": "Nap tipus"})


def build_invoice_pdf_bytes(driver_summary_df, route_df, title):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "A PDF generalashoz hianyzik a reportlab csomag."
        ) from exc

    font_name, bold_font_name = register_pdf_fonts(
        pdfmetrics,
        TTFont,
    )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.15 * cm,
        rightMargin=1.15 * cm,
        topMargin=0.9 * cm,
        bottomMargin=0.9 * cm,
    )
    styles = getSampleStyleSheet()

    for style in styles.byName.values():
        style.fontName = font_name

    styles["Title"].fontName = bold_font_name
    styles["Heading2"].fontName = bold_font_name
    styles["Heading3"].fontName = bold_font_name

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER
    title_style.textColor = colors.HexColor("#1f7a1f")

    center_style = styles["Normal"].clone("invoice_center")
    center_style.alignment = TA_CENTER
    section_style = styles["Heading2"].clone("invoice_section")
    section_style.textColor = colors.HexColor("#245c24")

    story = []
    summary_df = driver_summary_df.copy()
    route_df = route_df.copy()

    for index, driver_row in summary_df.reset_index(drop=True).iterrows():
        driver_name = normalize_text(driver_row.get("driver_name")) or "Ismeretlen futar"
        sheet_name = normalize_text(driver_row.get("worksheet_name"))
        route_driver_names = (
            route_df["driver_name"].astype(str)
            if "driver_name" in route_df.columns
            else pd.Series("", index=route_df.index)
        )
        route_sheet_names = (
            route_df["worksheet_name"].astype(str)
            if "worksheet_name" in route_df.columns
            else pd.Series("", index=route_df.index)
        )
        driver_routes = route_df[
            (route_driver_names == driver_name)
            & (route_sheet_names == sheet_name)
        ].copy()

        orders = int(money(driver_row.get("orders")))
        routes = int(money(driver_row.get("route_count") or driver_row.get("routes")))
        payable_total = money(driver_row.get("payable_total_huf"))
        fixed_total = money(driver_row.get("fixed_rate_huf"))
        highlighted_routes = int(money(driver_row.get("kiemelt_routes")))
        regular_routes = int(money(driver_row.get("sima_routes")))
        highlighted_base = money(driver_row.get("kiemelt_base_huf"))
        regular_base = money(driver_row.get("sima_base_huf"))
        delay_bonus = money(driver_row.get("delay_bonus_huf"))
        compliance_bonus = money(driver_row.get("compliance_bonus_huf"))
        fill_rate_bonus = money(driver_row.get("fill_rate_bonus_huf"))
        fuel_bonus = money(driver_row.get("fuel_bonus_huf"))
        fridge_bonus = money(driver_row.get("car_fridge_bonus_huf"))
        branding = money(driver_row.get("branding_huf"))
        tip = money(driver_row.get("tip_huf"))
        extra_bonus = money(driver_row.get("extra_bonus_huf"))
        adjustment = money(driver_row.get("adjustment_huf"))
        manual_total = money(driver_row.get("manual_total_huf"))
        target_open = money(driver_row.get("target_reserve_open_huf"))
        target_topup = money(driver_row.get("target_reserve_topup_huf"))
        target_close = money(driver_row.get("target_reserve_close_huf"))
        fuel_manual = money(driver_row.get("fuel_huf"))
        damage = money(driver_row.get("damage_huf"))
        cash_missing = money(driver_row.get("cash_missing_huf"))
        other_income = money(driver_row.get("other_income_huf"))
        other_deduction = money(driver_row.get("other_deduction_huf"))
        bonus_total = (
            delay_bonus
            + compliance_bonus
            + fill_rate_bonus
            + fuel_bonus
            + fridge_bonus
            + branding
            + extra_bonus
        )
        average_per_order = payable_total / orders if orders else 0
        bonus_per_order = bonus_total / orders if orders else 0
        base_per_order = fixed_total / orders if orders else 0

        if index:
            story.append(PageBreak())

        story.append(Paragraph(f"{driver_name} elszámoló", title_style))
        story.append(Paragraph(f"Időszak: {title} | Raktár fül: {sheet_name}", center_style))
        story.append(Spacer(1, 0.22 * cm))

        hero = Table(
            [
                [
                    Paragraph("<b>TELJESÍTMÉNY INDEX</b>", center_style),
                    Paragraph("<b>FT / KISZÁLLÍTOTT CÍM</b>", center_style),
                ],
                [
                    Paragraph(
                        "Minden egyes kiszállított címed átlagosan ennyit ért ebben az időszakban:",
                        center_style,
                    ),
                    Paragraph(
                        f"<font size='18'><b>{format_huf(average_per_order)}</b></font>",
                        center_style,
                    ),
                ],
                [
                    Paragraph(f"{format_huf(payable_total)} / {orders} cím", center_style),
                    Paragraph(
                        "Tartalmazza az alapdíjat, bónuszokat, pótlékokat, borravalót és az elszámolási tételeket.",
                        center_style,
                    ),
                ],
            ],
            colWidths=[9.2 * cm, 8.0 * cm],
        )
        hero.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f7d8")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#75b843")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bddda5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(hero)
        story.append(Spacer(1, 0.28 * cm))

        story.append(Paragraph("ALAPADATOK ÉS CÉLTARTALÉK", section_style))
        base = Table(
            [
                ["Alap címpénz (Ft/db)", format_huf(base_per_order), "Nyitó céltartalék", format_huf(target_open)],
                ["Kiflis bónuszok Ft/cím", f"+{format_huf(bonus_per_order)}", "Célt. feltöltés (+)", format_huf(target_topup)],
                ["Összes címpénz", format_huf(base_per_order + bonus_per_order), "Célt. záró egyenleg", format_huf(target_close)],
            ],
            colWidths=[5.4 * cm, 3.1 * cm, 5.4 * cm, 3.1 * cm],
        )
        apply_statement_table_style(base, font_name, bold_font_name, TableStyle, colors)
        story.append(base)
        story.append(Spacer(1, 0.28 * cm))

        story.append(Paragraph("KIEMELT / SIMA TÚRÁK ALAPDÍJA", section_style))
        route_base_table = Table(
            [
                ["Nap típus", "Túra db", "Alapösszeg"],
                ["Kiemelt nap", highlighted_routes, format_huf(highlighted_base)],
                ["Nem kiemelt nap", regular_routes, format_huf(regular_base)],
                ["Összesen", highlighted_routes + regular_routes, format_huf(highlighted_base + regular_base)],
            ],
            colWidths=[7.0 * cm, 4.0 * cm, 6.0 * cm],
        )
        apply_statement_table_style(route_base_table, font_name, bold_font_name, TableStyle, colors)
        route_base_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#d9ead3")),
                    ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#fff2cc")),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eeeeee")),
                    ("FONTNAME", (0, -1), (-1, -1), bold_font_name),
                ]
            )
        )
        story.append(route_base_table)
        story.append(Spacer(1, 0.28 * cm))

        story.append(Paragraph("ALAPDÍJ MÁTRIX", section_style))
        rate_rows = [["Nap típusa", "EXPRESSZ", "City", "Régió"]]
        base_rate_df = build_display_base_rate_matrix()
        for _row_index, rate_row in base_rate_df.iterrows():
            rate_rows.append(
                [
                    rate_row.get("Nap tipus", ""),
                    rate_row.get("EXPRESSZ", ""),
                    rate_row.get("City", ""),
                    rate_row.get("Régió", ""),
                ]
            )
        rate_table = Table(
            rate_rows,
            colWidths=[5.2 * cm, 3.9 * cm, 3.9 * cm, 3.9 * cm],
        )
        apply_statement_table_style(rate_table, font_name, bold_font_name, TableStyle, colors)
        rate_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#d9ead3")),
                    ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#fff2cc")),
                ]
            )
        )
        story.append(rate_table)
        story.append(Spacer(1, 0.28 * cm))

        story.append(Paragraph("BÓNUSZOK ÉS TELJESÍTMÉNY", section_style))
        bonus_table = Table(
            [
                ["Kiszállított címek", orders, "Körök", routes],
                ["Just in Time / késés", format_huf(delay_bonus), "Túramegfelelés", format_huf(compliance_bonus)],
                ["Töltési / fill-rate bónusz", format_huf(fill_rate_bonus), "Üzemanyag / hűtő / branding", format_huf(fuel_bonus + fridge_bonus + branding + fuel_manual)],
                ["Egyéb bónusz", format_huf(extra_bonus + other_income), "Borravaló", format_huf(tip)],
            ],
            colWidths=[5.4 * cm, 3.1 * cm, 5.4 * cm, 3.1 * cm],
        )
        apply_statement_table_style(bonus_table, font_name, bold_font_name, TableStyle, colors)
        story.append(bonus_table)
        story.append(Spacer(1, 0.28 * cm))

        revenues = [
            ["Szállítási díj", format_huf(fixed_total)],
            ["DSP bónuszok", format_huf(bonus_total)],
            ["Borravaló", format_huf(tip)],
            ["Manuális bevételek", format_huf(target_topup + fuel_manual + other_income)],
        ]
        expenses = [
            ["Maluszok / levonások", format_huf(abs(adjustment)) if adjustment < 0 else "0 Ft"],
            ["Károkozás", format_huf(abs(damage))],
            ["Be nem fiz. KP", format_huf(abs(cash_missing))],
            ["Egyéb levonás", format_huf(abs(other_deduction))],
        ]
        settlement_rows = [["Bevételek", "Ft", "Kiadások", "Ft"]]
        for left, right in zip(revenues, expenses):
            settlement_rows.append([left[0], left[1], right[0], right[1]])
        settlement_rows.append(
            [
                "BEVÉTELEK ÖSSZESEN",
                format_huf(fixed_total + bonus_total + tip + target_topup + fuel_manual + other_income),
                "KIADÁSOK ÖSSZESEN",
                format_huf((abs(adjustment) if adjustment < 0 else 0) + abs(damage) + abs(cash_missing) + abs(other_deduction)),
            ]
        )
        settlement = Table(
            settlement_rows,
            colWidths=[5.2 * cm, 3.2 * cm, 5.2 * cm, 3.2 * cm],
        )
        apply_statement_table_style(settlement, font_name, bold_font_name, TableStyle, colors)
        settlement.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#d9ead3")),
                    ("BACKGROUND", (2, 0), (3, 0), colors.HexColor("#f4cccc")),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eeeeee")),
                    ("FONTNAME", (0, -1), (-1, -1), bold_font_name),
                ]
            )
        )
        story.append(settlement)
        story.append(Spacer(1, 0.28 * cm))

        final_table = Table(
            [["PÉNZÜGYILEG RENDEZENDŐ EGYENLEG", format_huf(payable_total)]],
            colWidths=[11 * cm, 6 * cm],
        )
        final_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#222222")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), bold_font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 13),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("BOX", (0, 0), (-1, -1), 1, colors.black),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(final_table)

        manual_rows = [
            ["Nyitó céltartalék", format_huf(target_open)],
            ["Céltartalék feltöltés", format_huf(target_topup)],
            ["Céltartalék záró egyenleg", format_huf(target_close)],
            ["Üzemanyag / egyéb bevétel", format_huf(fuel_manual + other_income)],
            ["Károkozás / KP / egyéb levonás", format_huf(abs(damage) + abs(cash_missing) + abs(other_deduction))],
            ["Manuális tételek összesen", format_huf(manual_total)],
        ]
        if any(money(row[1].replace(" Ft", "").replace(" ", "")) for row in manual_rows):
            story.append(Spacer(1, 0.28 * cm))
            story.append(Paragraph("MANUÁLISAN FELVETT TÉTELEK", section_style))
            manual_table = Table(
                [["Tétel", "Összeg"]] + manual_rows,
                colWidths=[11 * cm, 6 * cm],
            )
            apply_statement_table_style(manual_table, font_name, bold_font_name, TableStyle, colors)
            story.append(manual_table)

        story.append(Spacer(1, 0.18 * cm))
        story.append(
            Paragraph(
                "Számlázásra NEM JOGOSÍT! Változtatás jogát fenntartjuk.",
                center_style,
            )
        )

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def register_pdf_fonts(pdfmetrics, TTFont):
    font_candidates = [
        ("ArialUnicode", "ArialUnicodeBold", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("DejaVuSans", "DejaVuSansBold", "C:/Windows/Fonts/DejaVuSans.ttf", "C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
    ]

    for regular_name, bold_name, regular_path, bold_path in font_candidates:
        try:
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            return regular_name, bold_name
        except Exception:
            continue

    return "Helvetica", "Helvetica-Bold"


def apply_statement_table_style(table, font_name, bold_font_name, TableStyle, colors):
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b7b7b7")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f6f0")),
                ("FONTNAME", (0, 0), (-1, 0), bold_font_name),
                ("FONTNAME", (0, 1), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
