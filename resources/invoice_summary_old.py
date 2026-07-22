from datetime import date, datetime
from io import BytesIO
import json
import re
import unicodedata
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
ROUTE_TABLES = [
    "bill_jitt_invoice_routes",
    "jitt_invoice_route_rows",
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
ATM_BALANCE_TABLES = [
    "bill_jitt_invoice_atm_balance",
]
CUSTOMER_RATING_TABLES = [
    "bill_jitt_invoice_customer_rating_bonus",
]
MONTHLY_ADJUSTMENT_TABLES = [
    "bill_jitt_invoice_monthly_adjustments",
]
DAY_RATE_TABLES = [
    "dsp_day_rates",
]
TARGET_RESERVE_TABLES = [
    "courier_target_reserve",
]

TARGET_RESERVE_RATE = 0.10
TARGET_RESERVE_MAX_HUF = 50_000
INSURANCE_DEDUCTION_HUF = 10_000

# Pozitív ATM-egyenleg levonásként jelenik meg az elszámolásban.
# Ha üzletileg pluszként kell kezelni, állítsd 1-re.
ATM_BALANCE_SIGN = -1

BASE_RATE_MATRIX = [
    {"service_type": "EXPRESSZ", "day_type": "Kiemelt nap", "amount_huf": 3350},
    {"service_type": "City", "day_type": "Kiemelt nap", "amount_huf": 6500},
    {"service_type": "Régió", "day_type": "Kiemelt nap", "amount_huf": 9000},
    {"service_type": "EXPRESSZ", "day_type": "Nem kiemelt nap", "amount_huf": 2650},
    {"service_type": "City", "day_type": "Nem kiemelt nap", "amount_huf": 4500},
    {"service_type": "Régió", "day_type": "Nem kiemelt nap", "amount_huf": 6300},
]

# Vallalkozoi bonusz -> futarnak elszamolando bonusz.
# A kesedelmi es a turamegfelelesi dijra ugyanaz a tabla ervenyes.
COURIER_BONUS_AMOUNT_OVERRIDES = {
    0: 0,
    333: 250,
    666: 500,
    750: 500,
    1333: 1333,
    1500: 1000,
    3000: 3000,
}

MANUAL_ITEM_TYPES = {
    "instructor_fee_huf": "Oktatói Díj",
    "fuel_huf": "Üzemanyag",
    "damage_huf": "Károkozás",
    "cash_missing_huf": "Be nem fizetett KP",
    "other_income_huf": "Egyéb bevétel",
    "other_deduction_huf": "Egyéb levonás",
}

LOYALTY_ACCEPTANCE_ACTION = "loyalty_bonus_acceptance"
LOYALTY_EFFECTIVE_FROM = date(2026, 6, 1)


def money(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def format_huf(value):
    return f"{money(value):,.0f} Ft".replace(",", " ")


def normalize_text(value):
    return str(value or "").strip()


def normalize_person_key(value):
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value).casefold(),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    tokens = re.findall(r"[a-z0-9]+", text)

    tokens = [
        token
        for token in tokens
        if not (
            token.isdigit()
            and 3 <= len(token) <= 6
        )
    ]

    return " ".join(sorted(tokens))


def _first_non_empty(values):
    for value in values:
        normalized = normalize_text(value)
        if normalized:
            return normalized
    return ""


def _invoice_identity_series(frame):
    """Courier ID is authoritative; the normalized driver key is the fallback."""
    courier_ids = frame.get(
        "courier_id", pd.Series("", index=frame.index, dtype=str)
    ).fillna("").map(normalize_text)
    match_keys = frame.get(
        "driver_match_key", pd.Series("", index=frame.index, dtype=str)
    ).fillna("").map(normalize_text)
    return courier_ids.map(lambda value: f"id:{value}" if value else "").where(
        courier_ids.ne(""),
        match_keys.map(lambda value: f"driver:{value}"),
    )


def collapse_invoice_rows_by_courier(grouped):
    """Collapse warehouse rows before courier-level amounts and deductions are applied."""
    if grouped is None or grouped.empty:
        return pd.DataFrame()

    result = grouped.copy()
    if "courier_id" not in result.columns:
        result["courier_id"] = ""
    result["courier_id"] = result["courier_id"].fillna("").map(normalize_text)

    known_ids = (
        result[result["courier_id"] != ""]
        .groupby("driver_match_key", dropna=False)["courier_id"]
        .agg(_first_non_empty)
    )
    missing_id = result["courier_id"] == ""
    result.loc[missing_id, "courier_id"] = (
        result.loc[missing_id, "driver_match_key"].map(known_ids).fillna("")
    )
    result["_invoice_courier_key"] = _invoice_identity_series(result)

    # These sources were already aggregated per courier before being joined to
    # every warehouse row, so they must be retained once rather than summed.
    courier_level_columns = {
        "adjustment_huf",
        "atm_balance_huf",
        "customer_rating_count",
        "customer_average_rating",
        "customer_bonus_per_route_huf",
        "customer_completed_routes",
        "customer_rating_bonus_huf",
        "monthly_bonus_huf",
        "monthly_malus_huf",
        "monthly_returned_route_huf",
        "monthly_accepted_route_huf",
        "monthly_source_total_huf",
    }
    identity_columns = {
        "courier_id",
        "driver_name",
        "driver_match_key",
        "worksheet_name",
    }
    aggregation = {}
    for column in result.columns:
        if column == "_invoice_courier_key":
            continue
        if column in identity_columns or column in courier_level_columns:
            aggregation[column] = "first"
        elif pd.api.types.is_numeric_dtype(result[column]):
            aggregation[column] = "sum"
        else:
            aggregation[column] = "first"

    warehouses = (
        result.assign(
            worksheet_name=result["worksheet_name"].fillna("").map(normalize_text)
        )
        .groupby("_invoice_courier_key", sort=False, dropna=False)["worksheet_name"]
        .agg(lambda values: sorted({value for value in values if value}))
    )
    result = (
        result.groupby(
            "_invoice_courier_key", as_index=False, sort=False, dropna=False
        )
        .agg(aggregation)
    )
    result["warehouses"] = result["_invoice_courier_key"].map(
        warehouses.map(lambda values: ", ".join(values))
    )
    result["warehouse_count"] = result["_invoice_courier_key"].map(
        warehouses.map(len)
    ).fillna(0).astype(int)
    result["worksheet_name"] = result["warehouses"]
    return result.drop(columns=["_invoice_courier_key"], errors="ignore")


def build_invoice_regeneration_candidates(final_df, invoice_documents_df=None):
    """List couriers whose period contains routes from multiple warehouses."""
    columns = [
        "courier_id",
        "driver_name",
        "warehouse_count",
        "warehouses",
        "current_invoice_count",
        "needs_regeneration",
    ]
    if final_df is None or final_df.empty:
        return pd.DataFrame(columns=columns)

    routes = final_df.copy()
    routes["driver_name"] = routes.get(
        "driver_name", pd.Series("", index=routes.index)
    ).fillna("").map(normalize_text)
    routes["driver_match_key"] = routes["driver_name"].map(normalize_person_key)
    routes["worksheet_name"] = routes.get(
        "worksheet_name", pd.Series("", index=routes.index)
    ).fillna("").map(normalize_text)
    if "courier_id" not in routes.columns:
        routes["courier_id"] = ""
    routes["courier_id"] = routes["courier_id"].fillna("").map(normalize_text)

    known_route_ids = (
        routes[routes["courier_id"] != ""]
        .groupby("driver_match_key", dropna=False)["courier_id"]
        .agg(_first_non_empty)
    )
    missing_route_id = routes["courier_id"] == ""
    routes.loc[missing_route_id, "courier_id"] = (
        routes.loc[missing_route_id, "driver_match_key"]
        .map(known_route_ids)
        .fillna("")
    )

    documents = (
        invoice_documents_df.copy()
        if invoice_documents_df is not None
        else pd.DataFrame()
    )
    document_ids_by_name = {}
    if not documents.empty:
        documents["courier_id"] = documents.get(
            "courier_id", pd.Series("", index=documents.index)
        ).fillna("").map(normalize_text)
        documents["driver_match_key"] = documents.get(
            "courier_name", pd.Series("", index=documents.index)
        ).fillna("").map(normalize_person_key)
        document_ids_by_name = (
            documents[documents["courier_id"] != ""]
            .groupby("driver_match_key", dropna=False)["courier_id"]
            .agg(_first_non_empty)
            .to_dict()
        )

    missing_id = routes["courier_id"] == ""
    routes.loc[missing_id, "courier_id"] = (
        routes.loc[missing_id, "driver_match_key"]
        .map(document_ids_by_name)
        .fillna("")
    )
    routes["_invoice_courier_key"] = _invoice_identity_series(routes)

    invoice_counts = {}
    invoice_counts_by_name = {}
    if not documents.empty:
        documents["_invoice_courier_key"] = _invoice_identity_series(documents)
        invoice_counts = documents.groupby("_invoice_courier_key").size().to_dict()
        invoice_counts_by_name = documents.groupby("driver_match_key").size().to_dict()

    rows = []
    for identity, group in routes.groupby(
        "_invoice_courier_key", sort=False, dropna=False
    ):
        warehouses = sorted(
            {value for value in group["worksheet_name"] if normalize_text(value)}
        )
        if len(warehouses) <= 1:
            continue
        rows.append(
            {
                "courier_id": _first_non_empty(group["courier_id"]),
                "driver_name": _first_non_empty(group["driver_name"]),
                "warehouse_count": len(warehouses),
                "warehouses": ", ".join(warehouses),
                "current_invoice_count": int(
                    invoice_counts.get(identity, 0)
                    or invoice_counts_by_name.get(
                        _first_non_empty(group["driver_match_key"]), 0
                    )
                ),
                "needs_regeneration": True,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        "driver_name", kind="stable"
    ).reset_index(drop=True)


def normalize_bonus_worksheet(site):
    value = normalize_text(site).upper().replace("-", "_").replace(" ", "_")
    if "BUD1" in value:
        return "BUD1_JIT"
    if "BUD2" in value:
        return "BUD2_JIT"
    return value


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


def deduplicate_invoice_routes(final_df):
    """Keep one payable row for each real route.

    The imported workbook can contain the same route more than once (this was
    most visible for Express routes).  A route fee and its quality bonuses are
    route-level amounts, so summing duplicate rows would pay them twice.
    Rows without a route id are retained because they cannot be matched safely.
    """
    if final_df is None or final_df.empty or "route_unique_id" not in final_df.columns:
        return final_df.copy()

    routes = final_df.copy()
    route_id = routes["route_unique_id"].map(normalize_text)
    identified = routes[route_id.ne("")].copy()
    unidentified = routes[route_id.eq("")].copy()

    if identified.empty:
        return routes

    dedupe_columns = [
        column
        for column in ["worksheet_name", "driver_name", "route_unique_id"]
        if column in identified.columns
    ]
    identified = identified.drop_duplicates(subset=dedupe_columns, keep="first")
    return pd.concat([identified, unidentified], ignore_index=True)


def combine_compliance_bonus(route_amount, bonus_table_amount):
    """Combine the route and monthly bonus-table compliance amounts."""
    return money(route_amount) + money(bonus_table_amount)


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


def previous_month_bounds(value):
    first, _last = month_bounds(value)
    previous_last = first - pd.Timedelta(days=1)
    return previous_last.replace(day=1), previous_last


def get_headers():
    _supabase_url, service_role_key = get_supabase_config()
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def read_first_existing_table(
    table_names,
    select,
    extra_filters=None,
    limit=10000,
):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy "
            "SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    headers = get_headers()
    last_error = None

    # A Supabase alapértelmezett maximális válaszmérete
    # gyakran 1000 sor, ezért oldalanként kérjük le az adatokat.
    page_size = 1000

    for table_name in table_names:
        all_rows = []
        offset = 0
        table_failed = False

        while offset < int(limit):
            current_limit = min(
                page_size,
                int(limit) - offset,
            )

            filters = [
                f"select={select}",
                f"limit={current_limit}",
                f"offset={offset}",
            ]

            if extra_filters:
                filters.extend(extra_filters)

            endpoint = (
                f"{supabase_url.rstrip('/')}"
                f"/rest/v1/{table_name}"
                f"?{'&'.join(filters)}"
            )

            response = requests.get(
                endpoint,
                headers=headers,
                timeout=60,
            )

            if response.status_code in [404, 406]:
                last_error = response.text
                table_failed = True
                break

            if (
                response.status_code == 400
                and "PGRST205" in response.text
            ):
                last_error = response.text
                table_failed = True
                break

            raise_for_supabase_error(response)

            rows = response.json() or []
            all_rows.extend(rows)

            # Ha kevesebb érkezett, elfogyott a tábla.
            if len(rows) < current_limit:
                break

            offset += current_limit

        if table_failed:
            continue

        return table_name, pd.DataFrame(all_rows)

    raise RuntimeError(
        "Egyik invoice tabla sem olvashato: "
        f"{', '.join(table_names)}. "
        f"{last_error or ''}"
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


def read_optional_first_nonempty_table(table_names, select, extra_filters=None, limit=10000):
    """Prefer the first table that actually contains rows, not merely the first existing table."""
    first_existing_name = None
    first_existing_df = pd.DataFrame()
    for table_name in table_names:
        try:
            resolved_name, frame = read_first_existing_table(
                [table_name], select, extra_filters, limit
            )
        except Exception:
            continue
        if first_existing_name is None:
            first_existing_name, first_existing_df = resolved_name, frame
        if not frame.empty:
            return resolved_name, frame
    return first_existing_name, first_existing_df


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

        if response.status_code == 400 and "PGRST205" in response.text:
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
                "row_number",
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

    _route_table, raw_route_df = read_optional_first_nonempty_table(
        ROUTE_TABLES,
        "worksheet_name,row_number,driver_name,route_unique_id,work_date,compliance_bonus_huf,row_data,row_values",
        date_filters,
        limit=50000,
    )
    if raw_route_df.empty:
        _route_table, raw_route_df = read_optional_first_nonempty_table(
            ROUTE_TABLES,
            "worksheet_name,row_number,work_date,row_values",
            date_filters,
            limit=50000,
        )

    _summary_table, summary_df = read_first_existing_table(
        SUMMARY_TABLES,
        "worksheet_name,row_number,metric_name,total_value,normal_value,region_value,express_value,total_raw,normal_raw,region_raw,express_raw",
        ["order=worksheet_name.asc,row_number.asc"],
        limit=1000,
    )
    _bonus_table, bonus_df = read_optional_first_nonempty_table(
        BONUS_TABLES,
        "worksheet_name,site,courier_id,driver_name,routes,bonus_huf",
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
    _atm_table, atm_balance_df = read_optional_first_existing_table(
        ATM_BALANCE_TABLES,
        "billing_month,worksheet_name,courier_id,driver_name,balance_huf,dsp,warehouse_name,source_row_number",
        [
            f"billing_month=eq.{start_text[:7]}-01",
            "order=driver_name.asc",
        ],
        limit=10000,
    )
    _rating_table, customer_rating_df = read_optional_first_existing_table(
        CUSTOMER_RATING_TABLES,
        "billing_month,worksheet_name,courier_id,driver_name,rating_count,average_rating,bonus_per_route_huf,completed_routes,bonus_total_huf,source_row_number",
        [
            f"billing_month=eq.{start_text[:7]}-01",
            "order=driver_name.asc",
        ],
        limit=10000,
    )
    _monthly_adjustment_table, monthly_adjustment_df = read_optional_first_existing_table(
        MONTHLY_ADJUSTMENT_TABLES,
        "billing_month,worksheet_name,courier_id,driver_name,bonus_huf,malus_huf,returned_route_huf,accepted_route_huf,source_total_huf,source_row_number",
        [
            f"billing_month=eq.{start_text[:7]}-01",
            "order=driver_name.asc",
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

    _target_reserve_table, target_reserve_df = read_optional_first_existing_table(
        TARGET_RESERVE_TABLES,
        "*",
        limit=10000,
    )

    previous_start, previous_end = previous_month_bounds(start_date)
    _previous_table, previous_routes_df = read_optional_first_existing_table(
        FINAL_TABLES,
        "worksheet_name,driver_name,route_unique_id,route_type,work_date",
        [
            f"work_date=gte.{format_date_filter(previous_start)}",
            f"work_date=lte.{format_date_filter(previous_end)}",
            "order=driver_name.asc,work_date.asc",
        ],
        limit=50000,
    )
    try:
        from resources.foglalasok_db import read_foglalasok_raw
        bookings_df = read_foglalasok_raw(start_date, end_date, limit=50000)
    except Exception:
        bookings_df = pd.DataFrame()
    try:
        from resources.peopleforce_documents import read_peopleforce_card_statuses_for_month
        acceptance_df = read_peopleforce_card_statuses_for_month(
            LOYALTY_EFFECTIVE_FROM,
            LOYALTY_ACCEPTANCE_ACTION,
        )
    except Exception:
        acceptance_df = pd.DataFrame()
    loyalty_error = ""
    try:
        from resources.loyalty_bonus import read_loyalty_profiles
        loyalty_profiles_df = read_loyalty_profiles()
    except Exception as exc:
        loyalty_profiles_df = pd.DataFrame()
        loyalty_error = str(exc)

    return {
        "final_table": final_table,
        "final": final_df,
        "routes": raw_route_df,
        "summary": summary_df,
        "bonus": bonus_df,
        "penalties": penalty_df,
        "manual": manual_df,
        "atm_balance": atm_balance_df,
        "customer_rating": customer_rating_df,
        "monthly_adjustments": monthly_adjustment_df,
        "day_rates": day_rates_df,
        "target_reserve": target_reserve_df,
        "previous_routes": previous_routes_df,
        "bookings": bookings_df,
        "loyalty_acceptance": acceptance_df,
        "loyalty_profiles": loyalty_profiles_df,
        "loyalty_error": loyalty_error,
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


def raw_compliance_bonus(row_values):
    values = row_values
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except (TypeError, ValueError, json.JSONDecodeError):
            return 0
    if not isinstance(values, (list, tuple)) or len(values) <= 16:
        return 0
    return money(values[16])


def raw_compliance_from_record(row):
    direct = money(row.get("compliance_bonus_huf"))
    if direct:
        return direct
    row_data = row.get("row_data")
    if isinstance(row_data, str):
        try:
            row_data = json.loads(row_data)
        except (TypeError, ValueError, json.JSONDecodeError):
            row_data = {}
    if isinstance(row_data, dict):
        for key, value in row_data.items():
            normalized = normalize_text(key).lower().replace(" ", "_")
            if "compliance" in normalized and "bonus" in normalized:
                parsed = money(value)
                if parsed:
                    return parsed
    return raw_compliance_bonus(row.get("row_values"))


def restore_raw_compliance_bonus(final_df, raw_route_df):
    if final_df.empty or raw_route_df is None or raw_route_df.empty:
        return final_df
    required = {"worksheet_name", "row_number"}
    if not required.issubset(raw_route_df.columns) or "row_number" not in final_df.columns:
        return final_df
    raw = raw_route_df.copy()
    raw["raw_compliance_bonus_huf"] = raw.apply(raw_compliance_from_record, axis=1)
    raw = raw[["worksheet_name", "row_number", "raw_compliance_bonus_huf"]].drop_duplicates()
    restored = final_df.merge(raw, on=["worksheet_name", "row_number"], how="left")
    current = pd.to_numeric(restored.get("compliance_bonus_huf"), errors="coerce").fillna(0)
    fallback = pd.to_numeric(restored.get("raw_compliance_bonus_huf"), errors="coerce").fillna(0)
    restored["compliance_bonus_huf"] = current.where(current != 0, fallback)
    missing = restored["compliance_bonus_huf"].eq(0)
    if missing.any() and "route_unique_id" in final_df.columns and "route_unique_id" in raw_route_df.columns:
        route_fallback = raw_route_df.copy()
        route_fallback["raw_route_compliance_huf"] = route_fallback.apply(raw_compliance_from_record, axis=1)
        route_fallback = route_fallback[["worksheet_name", "route_unique_id", "raw_route_compliance_huf"]].drop_duplicates()
        restored = restored.merge(route_fallback, on=["worksheet_name", "route_unique_id"], how="left")
        route_values = pd.to_numeric(restored["raw_route_compliance_huf"], errors="coerce").fillna(0)
        restored["compliance_bonus_huf"] = restored["compliance_bonus_huf"].where(~missing, route_values)
        restored = restored.drop(columns=["raw_route_compliance_huf"])
    return restored.drop(columns=["raw_compliance_bonus_huf"])


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


def _normal_route_counts(routes_df, output_column):
    columns = ["driver_match_key", "worksheet_name", output_column]
    if routes_df is None or routes_df.empty:
        return pd.DataFrame(columns=columns)
    routes = routes_df.copy()
    routes["driver_match_key"] = routes.get("driver_name", pd.Series("", index=routes.index)).map(normalize_person_key)
    routes["worksheet_name"] = routes.get("worksheet_name", pd.Series("", index=routes.index)).map(normalize_text)
    route_type = routes.get("route_type", pd.Series("", index=routes.index)).astype(str).str.upper()
    routes = routes[route_type.str.contains("NORMAL", na=False)].copy()
    if routes.empty:
        return pd.DataFrame(columns=columns)
    if "route_unique_id" in routes.columns:
        counts = routes.groupby(["driver_match_key", "worksheet_name"])["route_unique_id"].nunique()
    else:
        counts = routes.groupby(["driver_match_key", "worksheet_name"]).size()
    return counts.reset_index(name=output_column)


def build_loyalty_bonus_summary(current_routes_df, previous_routes_df, profiles_df, bookings_df, acceptance_df, period_start):
    current = _normal_route_counts(current_routes_df, "loyalty_current_normal_routes")
    if current.empty:
        return current
    previous = _normal_route_counts(previous_routes_df, "loyalty_previous_normal_routes")
    result = current.merge(previous, on=["driver_match_key", "worksheet_name"], how="left")
    result["loyalty_previous_normal_routes"] = result["loyalty_previous_normal_routes"].fillna(0).astype(int)

    profiles = profiles_df.copy() if profiles_df is not None else pd.DataFrame()
    if not profiles.empty:
        profiles["driver_match_key"] = profiles["driver_name"].map(normalize_person_key)
        keep = ["driver_match_key", "start_date", "is_active", "is_notice_period", "employment_status"]
        result = result.merge(profiles[[c for c in keep if c in profiles.columns]], on="driver_match_key", how="left")
    for column, default in [("is_active", False), ("is_notice_period", False)]:
        if column not in result.columns:
            result[column] = default
        result[column] = result[column].fillna(default).astype(bool)
    if "start_date" not in result.columns:
        result["start_date"] = pd.NaT
    result["start_date"] = pd.to_datetime(result["start_date"], errors="coerce")

    accepted_names = set()
    if acceptance_df is not None and not acceptance_df.empty:
        accepted = acceptance_df.copy()
        status = accepted.get("status", pd.Series("", index=accepted.index)).astype(str).str.lower()
        accepted = accepted[status == "done"]
        accepted_names = set(accepted.get("courier_name", pd.Series(dtype=str)).map(normalize_person_key))
    booking_names = set()
    if bookings_df is not None and not bookings_df.empty:
        booking_names = set(bookings_df.get("courier_name", pd.Series(dtype=str)).map(normalize_person_key))

    period = pd.Timestamp(period_start).date().replace(day=1)
    def calculate(row):
        previous_count = int(row.get("loyalty_previous_normal_routes") or 0)
        rate = 1000 if previous_count >= 45 else 500 if previous_count >= 25 else 0
        start = row.get("start_date")
        service_months = -1 if pd.isna(start) else (period.year - start.year) * 12 + period.month - start.month
        checks = {
            "hatályos": period >= LOYALTY_EFFECTIVE_FROM,
            "7. hónap": service_months >= 6,
            "aktív jogviszony": bool(row.get("is_active")) and not bool(row.get("is_notice_period")),
            "előfoglalás": row["driver_match_key"] in booking_names,
            "elfogadás": row["driver_match_key"] in accepted_names,
            "előző havi 25 kör": rate > 0,
        }
        missing = [label for label, ok in checks.items() if not ok]
        eligible = not missing
        return pd.Series({
            "loyalty_rate_huf": rate,
            "loyalty_bonus_huf": int(row.get("loyalty_current_normal_routes") or 0) * rate if eligible else 0,
            "loyalty_eligible": eligible,
            "loyalty_status": "Jogosult" if eligible else "Hiányzik: " + ", ".join(missing),
        })
    return pd.concat([result, result.apply(calculate, axis=1)], axis=1)


def build_driver_invoice_summary(
    final_df,
    bonus_df=None,
    penalty_df=None,
    manual_df=None,
    day_rates_df=None,
    raw_route_df=None,
    previous_routes_df=None,
    loyalty_profiles_df=None,
    bookings_df=None,
    loyalty_acceptance_df=None,
    atm_balance_df=None,
    customer_rating_df=None,
    monthly_adjustment_df=None,
    target_reserve_df=None,
    period_start=None,
):
    if final_df.empty:
        return pd.DataFrame()

    final_df = restore_raw_compliance_bonus(final_df, raw_route_df)
    final_df = deduplicate_invoice_routes(final_df)
    final_df = enrich_invoice_routes(final_df, day_rates_df)
    final_df["driver_name"] = final_df["driver_name"].map(normalize_text)
    final_df["worksheet_name"] = final_df["worksheet_name"].map(normalize_text)
    final_df["driver_match_key"] = final_df["driver_name"].map(normalize_person_key)

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
    numeric_columns.append("source_delay_bonus_huf")
    final_df["fixed_rate_huf"] = final_df["calculated_base_huf"]
    final_df["delay_bonus_huf"] = final_df["delay_bonus_huf"].map(courier_bonus_amount)
    final_df["compliance_bonus_huf"] = final_df["compliance_bonus_huf"].map(courier_bonus_amount)
    final_df["bonus_total_huf"] = (
        + final_df["delay_bonus_huf"]
        + final_df["compliance_bonus_huf"]
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
        final_df.groupby(
            ["driver_name", "driver_match_key", "worksheet_name"],
            dropna=False,
        )[numeric_columns]
        .sum()
        .reset_index()
    )
    if "courier_id" in final_df.columns:
        route_courier_ids = final_df[
            ["driver_name", "worksheet_name", "courier_id"]
        ].copy()
        route_courier_ids["courier_id"] = (
            route_courier_ids["courier_id"].fillna("").map(normalize_text)
        )
        route_courier_ids = (
            route_courier_ids[route_courier_ids["courier_id"] != ""]
            .groupby(["driver_name", "worksheet_name"], dropna=False)["courier_id"]
            .agg(_first_non_empty)
            .reset_index()
        )
        grouped = grouped.merge(
            route_courier_ids,
            on=["driver_name", "worksheet_name"],
            how="left",
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

    service_type_summary = (
        final_df.groupby(
            ["driver_name", "worksheet_name", "calculated_service_type"],
            dropna=False,
        )["route_unique_id"]
        .nunique()
        .unstack(fill_value=0)
        .reset_index()
    )
    service_type_summary = service_type_summary.rename(
        columns={
            "EXPRESSZ": "express_routes",
            "City": "city_routes",
            "Regio": "region_routes",
        }
    )
    grouped = grouped.merge(
        service_type_summary,
        on=["driver_name", "worksheet_name"],
        how="left",
    )
    weekday_counts = build_weekday_counts(final_df)
    grouped = grouped.merge(
        weekday_counts,
        on=["driver_name", "worksheet_name"],
        how="left",
    )
    loyalty = build_loyalty_bonus_summary(
        final_df,
        previous_routes_df,
        loyalty_profiles_df,
        bookings_df,
        loyalty_acceptance_df,
        period_start or date.today().replace(day=1),
    )
    if not loyalty.empty:
        loyalty_columns = [
            "driver_match_key", "worksheet_name", "loyalty_current_normal_routes",
            "loyalty_previous_normal_routes", "loyalty_rate_huf", "loyalty_bonus_huf",
            "loyalty_eligible", "loyalty_status",
        ]
        grouped = grouped.merge(
            loyalty[loyalty_columns],
            on=["driver_match_key", "worksheet_name"],
            how="left",
        )

    if bonus_df is not None and not bonus_df.empty:
        bonus_df = bonus_df.copy()
        bonus_df["driver_name"] = bonus_df["driver_name"].map(normalize_text)
        bonus_df["driver_match_key"] = bonus_df["driver_name"].map(normalize_person_key)
        bonus_df["worksheet_name"] = bonus_df.get(
            "site",
            pd.Series("", index=bonus_df.index),
        ).map(normalize_bonus_worksheet)
        if "courier_id" in bonus_df.columns:
            bonus_df["courier_id"] = bonus_df["courier_id"].map(normalize_text)
        bonus_df = add_numeric_columns(
            bonus_df,
            ["bonus_huf"],
        )
        bonus_df = bonus_df.drop_duplicates(
            subset=[
                column
                for column in [
                    "driver_match_key",
                    "worksheet_name",
                    "courier_id",
                    "routes",
                    "bonus_huf",
                ]
                if column in bonus_df.columns
            ],
            keep="first",
        )
        bonus_grouped = (
            bonus_df.groupby(
                ["driver_match_key", "worksheet_name"],
                dropna=False,
            )["bonus_huf"]
            .sum()
            .reset_index(name="compliance_extra_huf")
        )
        grouped = grouped.merge(
            bonus_grouped,
            on=["driver_match_key", "worksheet_name"],
            how="left",
        )
        if "courier_id" in bonus_df.columns:
            bonus_ids = (
                bonus_df[["driver_match_key", "worksheet_name", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .groupby(
                    ["driver_match_key", "worksheet_name"],
                    dropna=False,
                )["courier_id"]
                .first()
                .reset_index(name="_bonus_courier_id")
            )
            grouped = grouped.merge(
                bonus_ids,
                on=["driver_match_key", "worksheet_name"],
                how="left",
            )
            if "courier_id" not in grouped.columns:
                grouped["courier_id"] = ""
            grouped["courier_id"] = grouped["courier_id"].fillna("").map(
                normalize_text
            )
            grouped["courier_id"] = grouped["courier_id"].where(
                grouped["courier_id"] != "",
                grouped["_bonus_courier_id"].fillna("").map(normalize_text),
            )
            grouped = grouped.drop(columns=["_bonus_courier_id"])
    else:
        grouped["compliance_extra_huf"] = 0

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
        if "courier_id" in penalty_df.columns:
            penalty_ids = (
                penalty_df[["driver_name", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .groupby("driver_name", dropna=False)["courier_id"]
                .first()
                .reset_index(name="_penalty_courier_id")
            )
            grouped = grouped.merge(
                penalty_ids,
                on="driver_name",
                how="left",
            )
            if "courier_id" not in grouped.columns:
                grouped["courier_id"] = ""
            grouped["courier_id"] = grouped["courier_id"].fillna("").map(
                normalize_text
            )
            grouped["courier_id"] = grouped["courier_id"].where(
                grouped["courier_id"] != "",
                grouped["_penalty_courier_id"].fillna("").map(normalize_text),
            )
            grouped = grouped.drop(columns=["_penalty_courier_id"])
    else:
        grouped["adjustment_huf"] = 0

    def merge_external_source(source_df, value_map):
        nonlocal grouped
        if source_df is None or source_df.empty:
            for output_column in value_map.values():
                if output_column not in grouped.columns:
                    grouped[output_column] = 0
            return

        source = source_df.copy()
        source["driver_name"] = source.get(
            "driver_name", pd.Series("", index=source.index)
        ).fillna("").map(normalize_text)
        source["driver_match_key"] = source["driver_name"].map(normalize_person_key)
        if "courier_id" not in source.columns:
            source["courier_id"] = ""
        source["courier_id"] = source["courier_id"].fillna("").map(normalize_text)

        ids = (
            source[source["courier_id"] != ""]
            .groupby("driver_match_key", dropna=False)["courier_id"]
            .agg(_first_non_empty)
        )
        if "courier_id" not in grouped.columns:
            grouped["courier_id"] = ""
        grouped["courier_id"] = grouped["courier_id"].fillna("").map(normalize_text)
        missing_grouped_id = grouped["courier_id"] == ""
        grouped.loc[missing_grouped_id, "courier_id"] = (
            grouped.loc[missing_grouped_id, "driver_match_key"].map(ids).fillna("")
        )
        grouped_ids = (
            grouped[grouped["courier_id"] != ""]
            .groupby("driver_match_key", dropna=False)["courier_id"]
            .agg(_first_non_empty)
        )
        missing_source_id = source["courier_id"] == ""
        source.loc[missing_source_id, "courier_id"] = (
            source.loc[missing_source_id, "driver_match_key"]
            .map(grouped_ids)
            .fillna("")
        )

        for source_column in value_map:
            if source_column not in source.columns:
                source[source_column] = 0
            source[source_column] = pd.to_numeric(
                source[source_column], errors="coerce"
            ).fillna(0)

        source["_external_courier_key"] = _invoice_identity_series(source)
        grouped["_external_courier_key"] = _invoice_identity_series(grouped)

        # Courier-level snapshots can occur once per imported warehouse. Keep
        # one value per courier so ATM, ratings and monthly corrections do not
        # multiply with the number of warehouses.
        aggregated = (
            source.groupby("_external_courier_key", dropna=False, sort=False)[
                list(value_map)
            ]
            .first()
            .reset_index()
            .rename(columns=value_map)
        )
        grouped = grouped.merge(
            aggregated, on="_external_courier_key", how="left"
        ).drop(columns=["_external_courier_key"])

    merge_external_source(
        atm_balance_df,
        {"balance_huf": "atm_balance_huf"},
    )
    merge_external_source(
        customer_rating_df,
        {
            "rating_count": "customer_rating_count",
            "average_rating": "customer_average_rating",
            "bonus_per_route_huf": "customer_bonus_per_route_huf",
            "completed_routes": "customer_completed_routes",
            "bonus_total_huf": "customer_rating_bonus_huf",
        },
    )
    merge_external_source(
        monthly_adjustment_df,
        {
            "bonus_huf": "monthly_bonus_huf",
            "malus_huf": "monthly_malus_huf",
            "returned_route_huf": "monthly_returned_route_huf",
            "accepted_route_huf": "monthly_accepted_route_huf",
            "source_total_huf": "monthly_source_total_huf",
        },
    )

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
        "express_routes",
        "city_routes",
        "region_routes",
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

    for column in ["loyalty_current_normal_routes", "loyalty_previous_normal_routes", "loyalty_rate_huf", "loyalty_bonus_huf"]:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0)
    if "loyalty_status" not in grouped.columns:
        grouped["loyalty_status"] = "Nincs normál kör"

    # From this point onward there must be exactly one row per courier. Route-,
    # warehouse- and manual-item values are summed; courier-level sources are
    # retained once. Reserve and insurance are calculated only after this step.
    grouped = collapse_invoice_rows_by_courier(grouped)

    grouped["compliance_extra_huf"] = grouped["compliance_extra_huf"].fillna(0)
    grouped["route_compliance_huf"] = grouped["compliance_bonus_huf"]
    grouped["bonus_table_compliance_huf"] = grouped["compliance_extra_huf"]
    grouped["compliance_bonus_huf"] = grouped.apply(
        lambda row: combine_compliance_bonus(
            row.get("route_compliance_huf"),
            row.get("bonus_table_compliance_huf"),
        ),
        axis=1,
    )
    grouped["compliance_source"] = grouped.apply(
        lambda row: (
            "Route sorok + bónusz tábla"
            if money(row.get("route_compliance_huf"))
            and money(row.get("bonus_table_compliance_huf"))
            else "Route sorok"
            if money(row.get("route_compliance_huf"))
            else "Bónusz tábla"
            if money(row.get("bonus_table_compliance_huf"))
            else "Nincs díj"
        ),
        axis=1,
    )
    grouped["bonus_total_huf"] = (
        grouped["delay_bonus_huf"]
        + grouped["compliance_bonus_huf"]
    )
    grouped["route_total_without_tip_huf"] = (
        grouped["fixed_rate_huf"] + grouped["bonus_total_huf"]
    )
    grouped["route_total_huf"] = (
        grouped["route_total_without_tip_huf"] + grouped["tip_huf"]
    )
    # Kept for display/PDF compatibility; bonus route rows are compliance bonuses.
    grouped["extra_bonus_huf"] = 0
    grouped["adjustment_huf"] = grouped["adjustment_huf"].fillna(0)
    grouped["manual_total_huf"] = grouped[list(MANUAL_ITEM_TYPES.keys())].sum(axis=1)
    manual_payable_columns = [
        "target_reserve_topup_huf",
        "fuel_huf",
        "damage_huf",
        "cash_missing_huf",
        "other_income_huf",
        "other_deduction_huf",
        "instructor_fee_huf",
        "loyalty_bonus_huf",
    ]
    for column in manual_payable_columns:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(
            grouped[column],
            errors="coerce",
        ).fillna(0)
    grouped["manual_payable_huf"] = (
        grouped["target_reserve_topup_huf"]
        + grouped["fuel_huf"]
        + grouped["damage_huf"]
        + grouped["cash_missing_huf"]
        + grouped["other_income_huf"]
        + grouped["other_deduction_huf"]
        + grouped["instructor_fee_huf"]
        + grouped["loyalty_bonus_huf"]
    )

    for column in [
        "atm_balance_huf",
        "customer_rating_count",
        "customer_average_rating",
        "customer_bonus_per_route_huf",
        "customer_completed_routes",
        "customer_rating_bonus_huf",
        "monthly_bonus_huf",
        "monthly_malus_huf",
        "monthly_returned_route_huf",
        "monthly_accepted_route_huf",
        "monthly_source_total_huf",
    ]:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(
            grouped[column],
            errors="coerce",
        ).fillna(0)

    grouped["atm_effect_huf"] = (
        grouped["atm_balance_huf"].abs() * ATM_BALANCE_SIGN
    )
    grouped["monthly_adjustment_effect_huf"] = (
        grouped["monthly_bonus_huf"]
        - grouped["monthly_malus_huf"].abs()
        - grouped["monthly_returned_route_huf"].abs()
        + grouped["monthly_accepted_route_huf"]
    )
    grouped["external_bonus_total_huf"] = (
        grouped["customer_rating_bonus_huf"]
        + grouped["monthly_bonus_huf"]
    )
    grouped["external_deduction_total_huf"] = (
        grouped["monthly_malus_huf"].abs()
        + grouped["monthly_returned_route_huf"].abs()
        + grouped["atm_balance_huf"].abs()
    )

    grouped["payable_before_reserve_huf"] = (
        grouped["route_total_huf"]
        + grouped["extra_bonus_huf"]
        + grouped["adjustment_huf"]
        + grouped["manual_payable_huf"]
        + grouped["customer_rating_bonus_huf"]
        + grouped["monthly_adjustment_effect_huf"]
        + grouped["atm_effect_huf"]
    )

def parse_ct_z_ft(value):
    """CT_Z_FT mező biztonságos számmá alakítása."""
    if value is None:
        return 0

    text = str(value).strip()
    if not text:
        return 0

    text = (
        text.replace("Ft", "")
            .replace("ft", "")
            .replace(" ", "")
            .replace(".", "")
            .replace(",", "")
    )

    try:
        return int(text)
    except ValueError:
        return 0


reserve_lookup = {}

if target_reserve_df is not None and not target_reserve_df.empty:
    reserve_source = target_reserve_df.copy()

    for _, r in reserve_source.iterrows():
        key = normalize_text(r.get("courier_ID"))
        if key:
            reserve_lookup[key] = {
                "insurance_active": bool(r.get("insurance_active")),
                "ct_z_ft": parse_ct_z_ft(r.get("CT_Z_FT")),
            }


def calculate_deductions(row):
    info = reserve_lookup.get(
        normalize_text(row.get("courier_id")),
        None,
    )

    insurance = 0
    reserve = 0

    if info and info["insurance_active"]:
        insurance = INSURANCE_DEDUCTION_HUF

        if info["ct_z_ft"] < 350_000:
            reserve = min(
                max(row["payable_before_reserve_huf"], 0)
                * TARGET_RESERVE_RATE,
                TARGET_RESERVE_MAX_HUF,
            )

    return pd.Series(
        {
            "insurance_deduction_huf": insurance,
            "reserve_deduction_huf": reserve,
        }
    )


grouped[
    ["insurance_deduction_huf", "reserve_deduction_huf"]
] = grouped.apply(calculate_deductions, axis=1)

grouped["payable_total_huf"] = (
    grouped["payable_before_reserve_huf"]
    - grouped["insurance_deduction_huf"]
    - grouped["reserve_deduction_huf"]
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
        "tip_huf",
        "route_total_huf",
        "comment",
    ]
    visible = final_df[[column for column in columns if column in final_df.columns]].copy()

    money_columns = [
        "fixed_rate_huf",
        "delay_bonus_huf",
        "compliance_bonus_huf",
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
        "source_delay_bonus_huf",
        "compliance_bonus_huf",
        "route_compliance_huf",
        "bonus_table_compliance_huf",
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
        "payable_before_reserve_huf",
        "reserve_deduction_huf",
        "insurance_deduction_huf",
        "payable_total_huf",
        "loyalty_bonus_huf",
        "instructor_fee_huf",
        "atm_balance_huf",
        "atm_effect_huf",
        "customer_bonus_per_route_huf",
        "customer_rating_bonus_huf",
        "monthly_bonus_huf",
        "monthly_malus_huf",
        "monthly_returned_route_huf",
        "monthly_accepted_route_huf",
        "monthly_source_total_huf",
        "monthly_adjustment_effect_huf",
        "external_bonus_total_huf",
        "external_deduction_total_huf",
    ]:
        if column in visible.columns:
            visible[column] = visible[column].map(format_huf)

    visible = visible.rename(
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
            "express_routes": "Express db",
            "city_routes": "City db",
            "region_routes": "Régió db",
            "fixed_rate_huf": "Alapdij",
            "delay_bonus_huf": "Kesedelmi dij",
            "source_delay_bonus_huf": "Késedelmi díj (vállalkozói forrás)",
            "compliance_bonus_huf": "Turamegfeleles",
            "route_compliance_huf": "Túramegfelelés (route)",
            "bonus_table_compliance_huf": "Túramegfelelés (bónusz tábla)",
            "compliance_source": "Túramegfelelés forrása",
            "bonus_total_huf": "Bonusz osszesen",
            "tip_huf": "Tip",
            "route_total_huf": "Route osszesen",
            "extra_bonus_huf": "Egyeb bonusz",
            "adjustment_huf": "Levonas / plusz",
            "cash_missing_huf": "Be nem fizetett KP",
            "manual_total_huf": "Manualis tetelek",
            "manual_payable_huf": "Manualis fizetendo hatas",
            "payable_before_reserve_huf": "Fizetendő levonások előtt",
            "reserve_deduction_huf": "Céltartalék levonás",
            "insurance_deduction_huf": "Biztosítás (10 000 Ft)",
            "payable_total_huf": "Fizetendo osszesen",
            "loyalty_bonus_huf": "Lojalitási bónusz",
            "instructor_fee_huf": "Oktatói Díj",
            "loyalty_previous_normal_routes": "Előző havi normál kör",
            "loyalty_current_normal_routes": "Aktuális normál kör",
            "loyalty_rate_huf": "Lojalitás Ft / kör",
            "loyalty_status": "Lojalitás ellenőrzés",
            "atm_balance_huf": "ATM egyenleg",
            "atm_effect_huf": "ATM hatás",
            "customer_rating_count": "Ügyfélértékelések",
            "customer_average_rating": "Átlagos értékelés",
            "customer_bonus_per_route_huf": "Értékelési bónusz / kör",
            "customer_completed_routes": "Értékelt teljesített kör",
            "customer_rating_bonus_huf": "Ügyfélértékelési bónusz",
            "monthly_bonus_huf": "Havi bónusz",
            "monthly_malus_huf": "Havi málusz",
            "monthly_returned_route_huf": "Leadott kör",
            "monthly_accepted_route_huf": "Felvett kör",
            "monthly_source_total_huf": "Havizárás forrás összesen",
            "monthly_adjustment_effect_huf": "Havizárás számított hatás",
            "external_bonus_total_huf": "Külső bónusz összesen",
            "external_deduction_total_huf": "Külső levonás összesen",
        }
    )

    summary_columns = [
        "Futar ID",
        "Futar",
        "Raktar ful",
        "Route db",
        "Express db",
        "City db",
        "Régió db",
        "Alapdij",
        "Késedelmi díj (vállalkozói forrás)",
        "Kesedelmi dij",
        "Túramegfelelés (route)",
        "Túramegfelelés (bónusz tábla)",
        "Turamegfeleles",
        "Túramegfelelés forrása",
        "Tip",
        "Fizetendo osszesen",
    ]
    return visible[[column for column in summary_columns if column in visible.columns]]


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
    
    # Financial aggregation has already happened in build_driver_invoice_summary().
    # This function only renders the rows it receives.

    for index, driver_row in summary_df.reset_index(drop=True).iterrows():
        driver_name = normalize_text(driver_row.get("driver_name")) or "Ismeretlen futar"
        driver_match_key = normalize_text(
            driver_row.get("driver_match_key")
        ) or normalize_person_key(driver_name)
        route_driver_keys = (
            route_df["driver_name"].map(normalize_person_key)
            if "driver_name" in route_df.columns
            else pd.Series("", index=route_df.index)
        )
        route_mask = route_driver_keys == driver_match_key
        courier_id = normalize_text(driver_row.get("courier_id"))
        if courier_id and "courier_id" in route_df.columns:
            route_courier_ids = route_df["courier_id"].fillna("").map(normalize_text)
            route_mask = route_mask | route_courier_ids.eq(courier_id)
        driver_routes = route_df[route_mask].copy()

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
        tip = money(driver_row.get("tip_huf"))
        extra_bonus = money(driver_row.get("extra_bonus_huf"))
        adjustment = money(driver_row.get("adjustment_huf"))
        manual_total = money(driver_row.get("manual_total_huf"))
        reserve_deduction = money(driver_row.get("reserve_deduction_huf"))
        insurance_deduction = money(driver_row.get("insurance_deduction_huf"))
        fuel_manual = money(driver_row.get("fuel_huf"))
        damage = money(driver_row.get("damage_huf"))
        cash_missing = money(driver_row.get("cash_missing_huf"))
        other_income = money(driver_row.get("other_income_huf"))
        other_deduction = money(driver_row.get("other_deduction_huf"))
        instructor_fee = money(driver_row.get("instructor_fee_huf"))
        loyalty_bonus = money(driver_row.get("loyalty_bonus_huf"))
        atm_balance = money(driver_row.get("atm_balance_huf"))
        atm_effect = money(driver_row.get("atm_effect_huf"))
        customer_rating_count = int(money(driver_row.get("customer_rating_count")))
        customer_average_rating = money(driver_row.get("customer_average_rating"))
        customer_bonus_per_route = money(driver_row.get("customer_bonus_per_route_huf"))
        customer_completed_routes = int(money(driver_row.get("customer_completed_routes")))
        customer_rating_bonus = money(driver_row.get("customer_rating_bonus_huf"))
        monthly_bonus = money(driver_row.get("monthly_bonus_huf"))
        monthly_malus = money(driver_row.get("monthly_malus_huf"))
        monthly_returned_route = money(driver_row.get("monthly_returned_route_huf"))
        monthly_accepted_route = money(driver_row.get("monthly_accepted_route_huf"))
        monthly_source_total = money(driver_row.get("monthly_source_total_huf"))
        monthly_effect = money(driver_row.get("monthly_adjustment_effect_huf"))
        bonus_total = (
            delay_bonus
            + compliance_bonus
            + extra_bonus
            + loyalty_bonus
            + customer_rating_bonus
            + monthly_bonus
        )
        average_per_order = payable_total / orders if orders else 0
        bonus_per_order = 0
        base_per_order = 0

        if index:
            story.append(PageBreak())

        story.append(Paragraph(f"{driver_name} elszámoló", title_style))
        story.append(
            Paragraph(
                f"Időszak: {title}",
                center_style,
            )
        )
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

        story.append(Paragraph("ALAPADATOK", section_style))
        base = Table(
            [
                ["Alap címpénz (Ft/db)", format_huf(base_per_order)],
                ["Kiflis bónuszok Ft/cím", f"+{format_huf(bonus_per_order)}"],
                ["Összes címpénz", format_huf(base_per_order + bonus_per_order)],
            ],
            colWidths=[11 * cm, 6 * cm],
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
                ["Egyéb plusz", format_huf(extra_bonus + other_income), "Be nem fiz. KP", format_huf(abs(cash_missing))],
                ["Lojalitási bónusz", format_huf(loyalty_bonus), "Oktatói Díj", format_huf(instructor_fee)],
            ],
            colWidths=[5.4 * cm, 3.1 * cm, 5.4 * cm, 3.1 * cm],
        )
        apply_statement_table_style(bonus_table, font_name, bold_font_name, TableStyle, colors)
        story.append(bonus_table)
        story.append(Spacer(1, 0.28 * cm))

        if any([
            customer_rating_count,
            customer_average_rating,
            customer_bonus_per_route,
            customer_completed_routes,
            customer_rating_bonus,
        ]):
            story.append(Paragraph("ÜGYFÉLÉRTÉKELÉSI BÓNUSZ", section_style))
            rating_table = Table(
                [
                    ["Értékelések száma", customer_rating_count],
                    ["Átlagos rating", f"{customer_average_rating:.3f}".replace(".", ",")],
                    ["Bónusz / kör", format_huf(customer_bonus_per_route)],
                    ["Teljesített körök", customer_completed_routes],
                    ["Összes ügyfélértékelési bónusz", format_huf(customer_rating_bonus)],
                ],
                colWidths=[11 * cm, 6 * cm],
            )
            apply_statement_table_style(
                rating_table, font_name, bold_font_name, TableStyle, colors
            )
            story.append(rating_table)
            story.append(Spacer(1, 0.28 * cm))

        if any([
            monthly_bonus,
            monthly_malus,
            monthly_returned_route,
            monthly_accepted_route,
            monthly_source_total,
        ]):
            story.append(Paragraph("HAVI BÓNUSZ / MÁLUSZ ÖSSZESÍTŐ", section_style))
            monthly_table = Table(
                [
                    ["Tétel", "Összeg"],
                    ["Bónusz", format_huf(monthly_bonus)],
                    ["Málusz", format_huf(-abs(monthly_malus))],
                    ["Kör leadott", format_huf(-abs(monthly_returned_route))],
                    ["Kör felvett", format_huf(monthly_accepted_route)],
                    ["Számított hatás", format_huf(monthly_effect)],
                    ["Forrás szerinti összesen", format_huf(monthly_source_total)],
                ],
                colWidths=[11 * cm, 6 * cm],
            )
            apply_statement_table_style(
                monthly_table, font_name, bold_font_name, TableStyle, colors
            )
            story.append(monthly_table)
            story.append(Spacer(1, 0.28 * cm))

        if atm_balance:
            story.append(Paragraph("ATM EGYENLEG", section_style))
            atm_table = Table(
                [
                    ["ATM balance", format_huf(atm_balance)],
                    ["Elszámolási hatás", format_huf(atm_effect)],
                ],
                colWidths=[11 * cm, 6 * cm],
            )
            apply_statement_table_style(
                atm_table, font_name, bold_font_name, TableStyle, colors
            )
            story.append(atm_table)
            story.append(Spacer(1, 0.28 * cm))

        revenues = [
            ["Szállítási díj", format_huf(fixed_total)],
            ["Bónuszok / pótlékok", format_huf(bonus_total)],
            ["Borravaló", format_huf(tip)],
            ["Ügyfélértékelési bónusz", format_huf(customer_rating_bonus)],
            ["Havi bónusz + felvett kör", format_huf(monthly_bonus + monthly_accepted_route)],
            ["Manuális bevételek", format_huf(fuel_manual + other_income + instructor_fee)],
        ]
        expenses = [
            ["Maluszok / levonások", format_huf(abs(adjustment)) if adjustment < 0 else "0 Ft"],
            ["Havi málusz + leadott kör", format_huf(abs(monthly_malus) + abs(monthly_returned_route))],
            ["ATM egyenleg", format_huf(abs(atm_balance))],
            ["Károkozás", format_huf(abs(damage))],
            ["Be nem fiz. KP", format_huf(abs(cash_missing))],
            ["Egyéb levonás", format_huf(abs(other_deduction))],
            ["Céltartalék levonás", format_huf(abs(reserve_deduction))],
            ["Biztosítás (10 000 Ft)", format_huf(abs(insurance_deduction))],
        ]
        while len(revenues) < len(expenses):
            revenues.append(["", ""])
        while len(expenses) < len(revenues):
            expenses.append(["", ""])

        settlement_rows = [["Bevételek", "Ft", "Kiadások", "Ft"]]
        for left, right in zip(revenues, expenses):
            settlement_rows.append([left[0], left[1], right[0], right[1]])
        settlement_rows.append(
            [
                "BEVÉTELEK ÖSSZESEN",
                format_huf(
                    fixed_total
                    + bonus_total
                    + tip
                    + monthly_accepted_route
                    + fuel_manual
                    + other_income
                    + instructor_fee
                ),
                "KIADÁSOK ÖSSZESEN",
                format_huf(
                    (abs(adjustment) if adjustment < 0 else 0)
                    + abs(monthly_malus)
                    + abs(monthly_returned_route)
                    + abs(atm_balance)
                    + abs(damage)
                    + abs(cash_missing)
                    + abs(other_deduction)
                    + abs(reserve_deduction)
                    + abs(insurance_deduction)
                ),
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
            ["Üzemanyag / egyéb bevétel", format_huf(fuel_manual + other_income)],
            ["Oktatói Díj", format_huf(instructor_fee)],
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
