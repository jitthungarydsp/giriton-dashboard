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
    "bill_jitt_invoice_final_routes_with_courier_id",
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
    "courier_master_target_reserve",
    "courier_master_target_reserved",
    "courier_master_target_reservd",
    "courier_target_reserve",
]

TARGET_RESERVE_RATE = 0.10
TARGET_RESERVE_MAX_HUF = 50000
INSURANCE_DEDUCTION_HUF = 10000

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

COURIER_BONUS_AMOUNT_OVERRIDES = {
    750: 500,
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


def parse_huf_amount(value):
    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value or "").strip()
    if not text:
        return 0.0

    text = (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("Ft", "")
        .replace("HUF", "")
        .replace("\u00a0", "")
        .replace(" ", "")
        .strip()
    )

    if not text or text.upper() in {"#VALUE!", "#N/A", "NAN", "NONE", "NULL"}:
        return 0.0

    if "," not in text and text.count(".") == 1:
        before, after = text.split(".")
        if len(after) == 3 and before.replace("-", "").isdigit() and after.isdigit():
            text = before + after

    text = text.replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def parse_bool_flag(value):
    if isinstance(value, bool):
        return value

    if pd.isna(value):
        return False

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value or "").strip().casefold()
    if not text:
        return False

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.replace("\u00a0", "").replace(" ", "")
    if text in {"true", "t", "yes", "y", "igen", "i", "1", "x", "active", "aktiv"}:
        return True
    if text in {"false", "f", "no", "n", "nem", "0", "inactive", "inaktiv", "none", "null"}:
        return False

    try:
        return float(text.replace(",", ".")) != 0
    except (TypeError, ValueError):
        return False


def normalize_courier_id_text(value):
    text = normalize_text(value)
    text = text.replace("\u00a0", "").replace(" ", "")
    text = text.replace(",", ".")
    if text.endswith(".0"):
        text = text[:-2]
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


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

    # A futárnevekben szereplő számozás az azonosító része is lehet
    # (például: "PAPP 777 Niki"), ezért a numerikus tokeneket megtartjuk.
    return " ".join(sorted(tokens))


def normalize_person_name_key(value):
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value).casefold(),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    tokens = re.findall(r"[a-z]+", text)
    return " ".join(sorted(tokens))


def normalize_column_key(value):
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold(),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", "", text)


def extract_usernumber_from_row(row):
    row_data = row.get("row_data") if hasattr(row, "get") else None
    if isinstance(row_data, str):
        try:
            row_data = json.loads(row_data)
        except json.JSONDecodeError:
            row_data = {}
    if isinstance(row_data, dict):
        for key, value in row_data.items():
            if normalize_column_key(key) in {"usernumber", "userno", "userid", "courierid"}:
                courier_id = normalize_courier_id_text(value)
                if courier_id:
                    return courier_id

    row_values = row.get("row_values") if hasattr(row, "get") else None
    if isinstance(row_values, str):
        try:
            row_values = json.loads(row_values)
        except json.JSONDecodeError:
            row_values = []
    if isinstance(row_values, (list, tuple)) and len(row_values) > 2:
        return normalize_courier_id_text(row_values[2])

    return ""


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


def read_target_reserve_for_courier_ids(courier_ids):
    normalized_ids = sorted(
        {
            normalize_courier_id_text(courier_id)
            for courier_id in courier_ids
            if normalize_courier_id_text(courier_id)
        }
    )
    if not normalized_ids:
        return pd.DataFrame()

    chunks = []
    for index in range(0, len(normalized_ids), 100):
        chunk_ids = normalized_ids[index:index + 100]
        filter_value = ",".join(chunk_ids)
        _table_name, chunk = read_optional_first_existing_table(
            TARGET_RESERVE_TABLES,
            "*",
            [
                f"USERNUMBER=in.({filter_value})",
            ],
            limit=max(len(chunk_ids) + 10, 100),
        )
        if chunk is not None and not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame()

    return pd.concat(chunks, ignore_index=True)


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
    final_base_columns = [
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
    final_select_candidates = [
        (
            ["bill_jitt_invoice_final_routes_with_courier_id"],
            final_base_columns + ["courierID"],
        ),
        (
            ["bill_jitt_invoice_final_routes", "jitt_invoice_final_routes"],
            final_base_columns + ["courier_id"],
        ),
        (
            ["bill_jitt_invoice_final_routes", "jitt_invoice_final_routes"],
            final_base_columns,
        ),
    ]
    last_final_error = None
    final_table = None
    final_df = pd.DataFrame()
    for table_names, final_columns in final_select_candidates:
        try:
            final_table, final_df = read_first_existing_table(
                table_names,
                ",".join(final_columns),
                date_filters,
                limit=50000,
            )
            break
        except Exception as exc:
            last_final_error = exc
    else:
        if last_final_error:
            raise last_final_error

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
        "driver_match_key",
        "driver_name",
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
    required_columns = ["driver_name", "work_date"]
    if route_id_column:
        required_columns.append(route_id_column)

    routes = final_df[required_columns].copy()
    routes["driver_name"] = routes["driver_name"].map(normalize_text)
    routes["driver_match_key"] = routes["driver_name"].map(normalize_person_key)
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
        ["driver_match_key", "driver_name", "work_date"]
    ].drop_duplicates()
    routes = routes.drop_duplicates(
        subset=["driver_match_key", "work_date", "_route_key"]
    )
    routes["weekday"] = routes["work_date"].dt.weekday

    grouped = (
        routes.groupby(["driver_match_key"], dropna=False)
        .agg(
            driver_name=("driver_name", "first"),
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
        worked_dates.groupby(["driver_match_key"], dropna=False)["work_date"]
        .nunique()
        .reset_index(name="worked_days")
    )
    grouped = grouped.merge(
        worked_days,
        on="driver_match_key",
        how="left",
    )

    return grouped[columns]


def build_manual_item_summary(manual_df):
    if manual_df is None or manual_df.empty:
        return pd.DataFrame()

    manual_df = manual_df.copy()
    manual_df["driver_name"] = manual_df["driver_name"].map(normalize_text)
    manual_df["driver_match_key"] = manual_df["driver_name"].map(normalize_person_key)
    manual_df = add_numeric_columns(
        manual_df,
        ["amount_huf"],
    )
    pivot = (
        manual_df.pivot_table(
            index=["driver_match_key"],
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
    columns = ["driver_match_key", output_column]
    if routes_df is None or routes_df.empty:
        return pd.DataFrame(columns=columns)
    routes = routes_df.copy()
    routes["driver_match_key"] = routes.get("driver_name", pd.Series("", index=routes.index)).map(normalize_person_key)
    route_type = routes.get("route_type", pd.Series("", index=routes.index)).astype(str).str.upper()
    routes = routes[route_type.str.contains("NORMAL", na=False)].copy()
    if routes.empty:
        return pd.DataFrame(columns=columns)
    if "route_unique_id" in routes.columns:
        counts = routes.groupby("driver_match_key")["route_unique_id"].nunique()
    else:
        counts = routes.groupby("driver_match_key").size()
    return counts.reset_index(name=output_column)


def build_loyalty_bonus_summary(current_routes_df, previous_routes_df, profiles_df, bookings_df, acceptance_df, period_start):
    current = _normal_route_counts(current_routes_df, "loyalty_current_normal_routes")
    if current.empty:
        return current
    previous = _normal_route_counts(previous_routes_df, "loyalty_previous_normal_routes")
    result = current.merge(previous, on="driver_match_key", how="left")
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
    final_df = enrich_invoice_routes(final_df, day_rates_df)
    final_df["driver_name"] = final_df["driver_name"].map(normalize_text)
    final_df["worksheet_name"] = final_df["worksheet_name"].map(normalize_text)
    final_df["driver_match_key"] = final_df["driver_name"].map(normalize_person_key)
    if "courier_id" not in final_df.columns:
        final_df["courier_id"] = ""
    final_df["courier_id"] = final_df["courier_id"].fillna("").map(normalize_courier_id_text)
    if "courierID" in final_df.columns:
        final_df["courier_id"] = final_df["courier_id"].where(
            final_df["courier_id"] != "",
            final_df["courierID"].fillna("").map(normalize_courier_id_text),
        )
    if raw_route_df is not None and not raw_route_df.empty:
        raw_ids = raw_route_df.copy()
        raw_ids["courier_id_from_usernumber"] = raw_ids.apply(
            extract_usernumber_from_row,
            axis=1,
        )
        raw_id_columns = [
            column
            for column in ["worksheet_name", "row_number", "courier_id_from_usernumber"]
            if column in raw_ids.columns
        ]
        if set(["worksheet_name", "row_number", "courier_id_from_usernumber"]).issubset(raw_id_columns):
            raw_ids = raw_ids[raw_id_columns].copy()
            raw_ids["worksheet_name"] = raw_ids["worksheet_name"].map(normalize_text)
            raw_ids = raw_ids[raw_ids["courier_id_from_usernumber"] != ""].drop_duplicates(
                subset=["worksheet_name", "row_number"],
            )
            final_df = final_df.merge(
                raw_ids,
                on=["worksheet_name", "row_number"],
                how="left",
            )
            usernumber_id = final_df["courier_id_from_usernumber"].fillna("").map(
                normalize_courier_id_text
            )
            final_df["courier_id"] = final_df["courier_id"].where(
                usernumber_id == "",
                usernumber_id,
            )
            final_df = final_df.drop(columns=["courier_id_from_usernumber"])

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

    worksheet_summary = (
        final_df.groupby("driver_match_key", dropna=False)["worksheet_name"]
        .apply(
            lambda values: " + ".join(
                sorted(
                    {
                        normalize_text(value)
                        for value in values
                        if normalize_text(value)
                    }
                )
            )
        )
        .reset_index()
    )
    driver_name_summary = (
        final_df.groupby("driver_match_key", dropna=False)["driver_name"]
        .apply(lambda values: max([normalize_text(value) for value in values if normalize_text(value)] or [""], key=len))
        .reset_index()
    )
    grouped = (
        final_df.groupby("driver_match_key", dropna=False)[numeric_columns]
        .sum()
        .reset_index()
        .merge(driver_name_summary, on="driver_match_key", how="left")
        .merge(worksheet_summary, on="driver_match_key", how="left")
    )
    if "courier_id" in final_df.columns:
        route_ids = final_df[["driver_match_key", "courier_id"]].copy()
        route_ids["courier_id"] = (
            route_ids["courier_id"]
            .fillna("")
            .map(normalize_courier_id_text)
        )
        route_ids = (
            route_ids[route_ids["courier_id"] != ""]
            .drop_duplicates()
            .groupby("driver_match_key", dropna=False)["courier_id"]
            .first()
            .reset_index()
        )
        grouped = grouped.merge(
            route_ids,
            on="driver_match_key",
            how="left",
        )
    if "target_reserve_active" in final_df.columns:
        route_target = final_df[[
            column
            for column in [
                "driver_match_key",
                "target_reserve_active",
                "target_reserve_ct_z_ft",
            ]
            if column in final_df.columns
        ]].copy()
        route_target["target_reserve_active_from_routes"] = route_target[
            "target_reserve_active"
        ].map(parse_bool_flag)
        if "target_reserve_ct_z_ft" in route_target.columns:
            route_target["target_reserve_ct_z_ft_from_routes"] = route_target[
                "target_reserve_ct_z_ft"
            ].map(parse_huf_amount)
        else:
            route_target["target_reserve_ct_z_ft_from_routes"] = 0
        route_target = (
            route_target.groupby("driver_match_key", dropna=False)
            .agg(
                target_reserve_active_from_routes=(
                    "target_reserve_active_from_routes",
                    "max",
                ),
                target_reserve_ct_z_ft_from_routes=(
                    "target_reserve_ct_z_ft_from_routes",
                    "max",
                ),
            )
            .reset_index()
        )
        grouped = grouped.merge(
            route_target,
            on="driver_match_key",
            how="left",
        )
    if "courier_id" not in grouped.columns:
        grouped["courier_id"] = ""
    grouped["courier_id"] = (
        grouped["courier_id"]
        .fillna("")
        .map(normalize_courier_id_text)
    )
    tip_source = final_df[["driver_match_key", "route_unique_id", "tip_huf"]].copy()
    tip_source["_tip_route_key"] = tip_source["route_unique_id"].map(normalize_text)
    empty_tip_route = tip_source["_tip_route_key"] == ""
    tip_source.loc[empty_tip_route, "_tip_route_key"] = (
        "__row_" + tip_source.index[empty_tip_route].astype(str)
    )
    deduped_tip = (
        tip_source.groupby(["driver_match_key", "_tip_route_key"], dropna=False)["tip_huf"]
        .max()
        .groupby("driver_match_key", dropna=False)
        .sum()
        .reset_index(name="_deduped_tip_huf")
    )
    grouped = grouped.merge(deduped_tip, on="driver_match_key", how="left")
    grouped["tip_huf"] = grouped["_deduped_tip_huf"].fillna(grouped["tip_huf"])
    grouped = grouped.drop(columns=["_deduped_tip_huf"])
    route_counts = (
        final_df.groupby("driver_match_key", dropna=False)["route_unique_id"]
        .nunique()
        .reset_index(name="route_count")
    )
    grouped = grouped.merge(
        route_counts,
        on="driver_match_key",
        how="left",
    )
    day_type_summary = (
        final_df.groupby(["driver_match_key", "calculated_day_type"], dropna=False)
        .agg(
            day_type_routes=("route_unique_id", "nunique"),
            day_type_base_huf=("fixed_rate_huf", "sum"),
        )
        .reset_index()
    )
    day_type_pivot = pd.DataFrame()
    if not day_type_summary.empty:
        route_pivot = day_type_summary.pivot_table(
            index="driver_match_key",
            columns="calculated_day_type",
            values="day_type_routes",
            aggfunc="sum",
            fill_value=0,
        )
        base_pivot = day_type_summary.pivot_table(
            index="driver_match_key",
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
            on="driver_match_key",
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
        on="driver_match_key",
        how="left",
        suffixes=("", "_weekday"),
    )
    if "driver_name_weekday" in grouped.columns:
        grouped = grouped.drop(columns=["driver_name_weekday"])
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
            "driver_match_key", "loyalty_current_normal_routes",
            "loyalty_previous_normal_routes", "loyalty_rate_huf", "loyalty_bonus_huf",
            "loyalty_eligible", "loyalty_status",
        ]
        grouped = grouped.merge(
            loyalty[loyalty_columns],
            on="driver_match_key",
            how="left",
        )

    if bonus_df is not None and not bonus_df.empty:
        bonus_df = bonus_df.copy()
        bonus_df["driver_name"] = bonus_df["driver_name"].map(normalize_text)
        bonus_df["driver_match_key"] = bonus_df["driver_name"].map(normalize_person_key)
        if "courier_id" in bonus_df.columns:
            bonus_df["courier_id"] = bonus_df["courier_id"].map(normalize_text)
        bonus_df = add_numeric_columns(
            bonus_df,
            ["bonus_huf"],
        )
        bonus_grouped = (
            bonus_df.groupby("driver_match_key", dropna=False)["bonus_huf"]
            .sum()
            .reset_index(name="compliance_extra_huf")
        )
        grouped = grouped.merge(
            bonus_grouped,
            on="driver_match_key",
            how="left",
        )
        if "courier_id" in bonus_df.columns:
            bonus_ids = (
                bonus_df[["driver_match_key", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .groupby("driver_match_key", dropna=False)["courier_id"]
                .first()
                .reset_index(name="_bonus_courier_id")
            )
            grouped = grouped.merge(
                bonus_ids,
                on="driver_match_key",
                how="left",
            )
            if "courier_id" not in grouped.columns:
                grouped["courier_id"] = ""
            grouped["courier_id"] = (
                grouped["courier_id"]
                .fillna("")
                .map(normalize_courier_id_text)
            )
            grouped["courier_id"] = grouped["courier_id"].where(
                grouped["courier_id"] != "",
                grouped["_bonus_courier_id"]
                .fillna("")
                .map(normalize_courier_id_text),
            )
            grouped = grouped.drop(columns=["_bonus_courier_id"])
    else:
        grouped["compliance_extra_huf"] = 0

    if penalty_df is not None and not penalty_df.empty:
        penalty_df = penalty_df.copy()
        penalty_df["driver_name"] = penalty_df["driver_name"].map(normalize_text)
        penalty_df["driver_match_key"] = penalty_df["driver_name"].map(normalize_person_key)
        if "courier_id" in penalty_df.columns:
            penalty_df["courier_id"] = penalty_df["courier_id"].map(normalize_text)
        penalty_df = add_numeric_columns(
            penalty_df,
            ["amount_huf"],
        )
        penalty_grouped = (
            penalty_df.groupby("driver_match_key", dropna=False)["amount_huf"]
            .sum()
            .reset_index(name="adjustment_huf")
        )
        grouped = grouped.merge(
            penalty_grouped,
            on="driver_match_key",
            how="left",
        )
        if "courier_id" not in grouped.columns and "courier_id" in penalty_df.columns:
            penalty_ids = (
                penalty_df[["driver_name", "courier_id"]]
                .dropna()
                .drop_duplicates()
                .assign(driver_match_key=lambda frame: frame["driver_name"].map(normalize_person_key))
                .groupby("driver_match_key", dropna=False)["courier_id"]
                .first()
                .reset_index()
            )
            grouped = grouped.merge(
                penalty_ids,
                on="driver_match_key",
                how="left",
            )
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
            "driver_name",
            pd.Series("", index=source.index),
        ).map(normalize_text)
        source["driver_match_key"] = source["driver_name"].map(normalize_person_key)

        for source_column in value_map:
            if source_column not in source.columns:
                source[source_column] = 0
            source[source_column] = pd.to_numeric(
                source[source_column],
                errors="coerce",
            ).fillna(0)

        # These sources are courier-level monthly conditions. If a courier appears
        # once under BUD1 and once under BUD2 with the same values, count it once.
        source = source.drop_duplicates(
            subset=["driver_match_key", *list(value_map)],
        )

        aggregated = (
            source.groupby("driver_match_key", dropna=False)[list(value_map)]
            .sum()
            .reset_index()
            .rename(columns=value_map)
        )
        grouped = grouped.merge(
            aggregated,
            on="driver_match_key",
            how="left",
        )

        if "courier_id" in source.columns:
            ids = (
                source[["driver_match_key", "courier_id"]]
                .copy()
            )

            ids["courier_id"] = (
                ids["courier_id"]
                .fillna("")
                .map(normalize_text)
            )

            ids = (
                ids[ids["courier_id"] != ""]
                .drop_duplicates()
                .groupby(
                    "driver_match_key",
                    dropna=False,
                )["courier_id"]
                .first()
                .reset_index(name="_source_courier_id")
            )

            grouped = grouped.merge(
                ids,
                on="driver_match_key",
                how="left",
            )

            if "courier_id" not in grouped.columns:
                grouped["courier_id"] = ""

            grouped["courier_id"] = (
                grouped["courier_id"]
                .fillna("")
                .map(normalize_text)
            )

            grouped["courier_id"] = grouped["courier_id"].where(
                grouped["courier_id"] != "",
                grouped["_source_courier_id"]
                .fillna("")
                .map(normalize_text),
            )

            grouped = grouped.drop(
                columns=["_source_courier_id"],
            )

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
            on="driver_match_key",
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

    for column in ["loyalty_current_normal_routes", "loyalty_previous_normal_routes", "loyalty_rate_huf", "loyalty_bonus_huf"]:
        if column not in grouped.columns:
            grouped[column] = 0
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0)
    if "loyalty_status" not in grouped.columns:
        grouped["loyalty_status"] = "Nincs normál kör"

    grouped["compliance_extra_huf"] = grouped["compliance_extra_huf"].fillna(0)
    grouped["compliance_bonus_huf"] = (
        grouped["compliance_bonus_huf"] + grouped["compliance_extra_huf"]
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
    grouped["manual_payable_huf"] = (
        grouped["fuel_huf"]
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

    # A hívó régebbi verziója nem feltétlenül adja át külön a táblát,
    # ezért ilyenkor itt is megpróbáljuk beolvasni.
    if target_reserve_df is None or target_reserve_df.empty:
        target_reserve_df = pd.DataFrame()
        if "courier_id" in grouped.columns:
            target_reserve_df = read_target_reserve_for_courier_ids(
                grouped["courier_id"].dropna().tolist()
            )
        if target_reserve_df is None or target_reserve_df.empty:
            _reserve_table, target_reserve_df = read_optional_first_existing_table(
                TARGET_RESERVE_TABLES,
                "*",
                limit=10000,
            )

    reserve_courier_ct_zft = {}
    reserve_courier_active = {}
    if target_reserve_df is not None and not target_reserve_df.empty:
        reserve_source = target_reserve_df.copy()

        id_columns = [
            "USERNUMBER", "usernumber", "user_number", "courier_id",
            "driver_id", "employee_id", "peopleforce_id",
            "courier_uuid", "user_id", "id",
        ]
        ct_column = None
        ct_column_keys = {
            "ctzft",
            "ctz",
            "currentbalancehuf",
            "openingbalancehuf",
            "balancehuf",
            "targetreservehuf",
            "targetreservebalancehuf",
        }
        for column in reserve_source.columns:
            column_key = normalize_column_key(column)
            if column_key in ct_column_keys:
                ct_column = column
                break
        if ct_column is None:
            reserve_source["_ct_zft_huf"] = 0
        else:
            reserve_source["_ct_zft_huf"] = reserve_source[ct_column].map(
                parse_huf_amount
            )

        active_column = None
        active_column_keys = {
            "insuranceactive",
            "insurance",
            "biztositasactive",
            "biztositasaktiv",
            "biztositas",
            "targetreserveactive",
            "celtartalekactive",
            "celtartalekaktiv",
        }
        for column in reserve_source.columns:
            column_key = normalize_column_key(column)
            if column_key in active_column_keys:
                active_column = column
                break
        if active_column is None:
            reserve_source["_insurance_active"] = False
        else:
            reserve_source["_insurance_active"] = reserve_source[active_column].map(
                parse_bool_flag
            )

        for id_column in id_columns:
            if id_column in reserve_source.columns:
                for _, reserve_row in reserve_source.iterrows():
                    courier_id = normalize_courier_id_text(reserve_row.get(id_column))
                    if courier_id:
                        reserve_courier_ct_zft[courier_id] = reserve_row.get("_ct_zft_huf", 0)
                        reserve_courier_active[courier_id] = bool(
                            reserve_row.get("_insurance_active", False)
                        )

        # The DB insurance_active flag is the single source of truth:
        # True => target reserve + insurance deduction, False => no deduction.

    def target_reserve_ct_zft(row):
        route_ct = row.get("target_reserve_ct_z_ft_from_routes")
        if pd.notna(route_ct) and parse_huf_amount(route_ct) != 0:
            return parse_huf_amount(route_ct)
        courier_id = normalize_courier_id_text(row.get("courier_id"))
        if courier_id in reserve_courier_ct_zft:
            return reserve_courier_ct_zft[courier_id]
        return pd.NA

    def target_reserve_active(row):
        route_active = row.get("target_reserve_active_from_routes")
        if pd.notna(route_active):
            return parse_bool_flag(route_active)
        courier_id = normalize_courier_id_text(row.get("courier_id"))
        if courier_id in reserve_courier_active:
            return reserve_courier_active[courier_id]
        return False

    grouped["target_reserve_ct_zft_huf"] = grouped.apply(
        target_reserve_ct_zft,
        axis=1,
    )
    grouped["target_reserve_active"] = grouped.apply(
        target_reserve_active,
        axis=1,
    ).map(parse_bool_flag)
    grouped["has_target_reserve"] = grouped["target_reserve_active"]
    grouped["target_reserve_ct_zft_huf"] = grouped["target_reserve_ct_zft_huf"].map(
        parse_huf_amount
    )

    # A céltartalék nem fix 50 000 Ft: a levonás a levonások előtti
    # fizetendő összeg 10%-a, de legfeljebb 50 000 Ft.
    eligible_base = grouped["payable_before_reserve_huf"].clip(lower=0)
    grouped["target_reserve_deduction_huf"] = 0.0
    reserve_mask = grouped["target_reserve_active"]
    grouped.loc[reserve_mask, "target_reserve_deduction_huf"] = (
        eligible_base.loc[reserve_mask]
        .map(lambda amount: min(amount * TARGET_RESERVE_RATE, TARGET_RESERVE_MAX_HUF))
        .round(0)
    )

    grouped["insurance_deduction_huf"] = 0.0
    insurance_mask = grouped["target_reserve_active"]
    grouped.loc[insurance_mask, "insurance_deduction_huf"] = INSURANCE_DEDUCTION_HUF

    grouped["payable_total_huf"] = (
        grouped["payable_before_reserve_huf"]
        - grouped["target_reserve_deduction_huf"]
        - grouped["insurance_deduction_huf"]
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
        "compliance_bonus_huf",
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
        "target_reserve_ct_zft_huf",
        "target_reserve_deduction_huf",
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
            "bonus_total_huf": "Bonusz osszesen",
            "tip_huf": "Tip",
            "route_total_huf": "Route osszesen",
            "extra_bonus_huf": "Egyeb bonusz",
            "adjustment_huf": "Levonas / plusz",
            "cash_missing_huf": "Be nem fizetett KP",
            "manual_total_huf": "Manualis tetelek",
            "manual_payable_huf": "Manualis fizetendo hatas",
            "payable_before_reserve_huf": "Levonasok elotti fizetendo",
            "target_reserve_active": "Celtartalek/biztositas aktiv",
            "target_reserve_ct_zft_huf": "CT_ZFT",
            "target_reserve_deduction_huf": "Céltartalék levonás",
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
        driver_key = normalize_person_key(driver_name)
        route_driver_names = (
            route_df["driver_name"].astype(str).map(normalize_person_key)
            if "driver_name" in route_df.columns
            else pd.Series("", index=route_df.index)
        )
        route_sheet_names = (
            route_df["worksheet_name"].astype(str)
            if "worksheet_name" in route_df.columns
            else pd.Series("", index=route_df.index)
        )
        route_mask = route_driver_names == driver_key
        if sheet_name and " + " not in sheet_name:
            route_mask = route_mask & (route_sheet_names == sheet_name)
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
        payable_before_reserve = money(driver_row.get("payable_before_reserve_huf"))
        target_reserve_deduction = money(driver_row.get("target_reserve_deduction_huf"))
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

        story.append(Paragraph("ALAPADATOK ÉS LEVONÁSOK", section_style))
        base = Table(
            [
                ["Alap címpénz (Ft/db)", format_huf(base_per_order), "Levonások előtti fizetendő", format_huf(payable_before_reserve)],
                ["Kiflis bónuszok Ft/cím", f"+{format_huf(bonus_per_order)}", "Céltartalék levonás", format_huf(-target_reserve_deduction)],
                ["Összes címpénz", format_huf(base_per_order + bonus_per_order), "Biztosítás (10 000 Ft)", format_huf(-insurance_deduction)],
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
            ["Manuális bevételek", format_huf(fuel_manual + other_income + instructor_fee)],
        ]
        expenses = [
            ["Maluszok / levonások", format_huf(abs(adjustment)) if adjustment < 0 else "0 Ft"],
            ["Havi málusz + leadott kör", format_huf(abs(monthly_malus) + abs(monthly_returned_route))],
            ["ATM egyenleg", format_huf(abs(atm_balance))],
            ["Károkozás", format_huf(abs(damage))],
            ["Be nem fiz. KP", format_huf(abs(cash_missing))],
            ["Egyéb levonás", format_huf(abs(other_deduction))],
            ["Céltartalék levonás", format_huf(target_reserve_deduction)],
            ["Biztosítás (10 000 Ft)", format_huf(insurance_deduction)],
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
                    + target_reserve_deduction
                    + insurance_deduction
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
