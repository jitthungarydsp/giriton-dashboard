from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from scripts import build_dsp_route_stories as route_story_builder

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")

ROUTE_STORY_TABLE = "mart_dsp_route_stories"
PERFORMANCE_TABLE = "stg_jitt_invoice_performance_couriers"
DRIVER_DETAIL_TABLES = [
    "raw_dsp_driver_detail",
    "dsp_driver_detail_raw",
]

ROUTE_STORY_COLUMNS = [
    "work_date",
    "courier_id",
    "courier_name",
    "warehouse_name",
    "route_id",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "queue_started_at",
    "courier_registered_at",
    "assigned_at",
    "loading_time",
    "planned_departure",
    "real_departure",
    "planned_return",
    "real_return",
    "queue_entry_delta_minutes",
    "queue_wait_minutes",
    "planned_loading_minutes",
    "real_loading_minutes",
    "planned_route_minutes",
    "real_route_minutes",
    "assigned_to_return_minutes",
    "total_route_minutes",
    "gps_distance_km",
    "checkpoint_straight_km",
    "booking_shift_count",
    "next_booking_shift_text",
    "next_booking_shift_start",
    "next_shift_delay_minutes",
    "address_count",
    "planned_early_count",
    "planned_late_count",
    "time_window_early_count",
    "time_window_late_count",
    "assignment_mode",
    "story_text",
    "updated_at",
]

PERFORMANCE_COLUMNS = [
    "warehouse_id",
    "warehouse_code",
    "date_from",
    "date_to",
    "courier_id",
    "courier_name",
    "shifts",
    "orders",
    "delayed",
    "delay_percent",
    "late_percent",
    "no_show_percent",
    "compliance_bad_percent",
    "compliance_score_percent",
    "delay_level",
    "compliance_level",
    "raw_table",
    "raw_fetched_at",
    "calculated_at",
]

DRIVER_DETAIL_COLUMNS = [
    "work_date",
    "driver_id",
    "response_json",
    "fetched_at",
]


def is_missing_table_response(response):
    if response.status_code not in (400, 404):
        return False

    text = response.text.lower()

    return (
        "could not find the table" in text
        or "does not exist" in text
        or "undefined_table" in text
        or "pgrst205" in text
    )


def missing_column_name(response):
    if response.status_code != 400:
        return ""

    try:
        payload = response.json()
    except ValueError:
        return ""

    if payload.get("code") != "PGRST204":
        return ""

    message = str(payload.get("message") or "")
    marker = "Could not find the '"

    if marker not in message:
        return ""

    return message.split(marker, 1)[1].split("'", 1)[0]


def get_headers(service_role_key):
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }


def format_date_filter(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value or "").strip()


def read_table(
    table_name,
    columns,
    filters=None,
    order="",
    limit=10000,
    page_size=500,
):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    active_columns = list(columns)
    filters = filters or {}
    rows = []

    while True:
        params = {
            "select": ",".join(active_columns),
        }
        params.update(filters)

        if order:
            params["order"] = order

        endpoint = f"{supabase_url}/rest/v1/{table_name}"
        rows.clear()

        while len(rows) < int(limit):
            range_start = len(rows)
            range_end = min(
                range_start + int(page_size) - 1,
                int(limit) - 1,
            )
            headers = get_headers(service_role_key)
            headers.update(
                {
                    "Range-Unit": "items",
                    "Range": f"{range_start}-{range_end}",
                }
            )

            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=60,
            )

            if is_missing_table_response(response):
                return pd.DataFrame()

            missing_column = missing_column_name(response)

            if missing_column:
                active_columns = [
                    column for column in active_columns if column != missing_column
                ]
                break

            raise_for_supabase_error(response)
            chunk = response.json()

            if not chunk:
                break

            rows.extend(chunk)

            if len(chunk) < (range_end - range_start + 1):
                break
        else:
            break

        if missing_column:
            continue

        break

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=300)
def read_route_stories(start_date, end_date, courier_id="", warehouse=""):
    # PostgREST does not allow duplicate keys in a dict, so range filters are
    # encoded with the query string style supported by requests params list below.
    filters_list = [
        ("work_date", f"gte.{format_date_filter(start_date)}"),
        ("work_date", f"lte.{format_date_filter(end_date)}"),
    ]

    clean_courier_id = str(courier_id or "").strip()

    if clean_courier_id:
        filters_list.append(("courier_id", f"eq.{clean_courier_id}"))

    return read_table_with_filter_list(
        table_name=ROUTE_STORY_TABLE,
        columns=ROUTE_STORY_COLUMNS,
        filters_list=filters_list,
        order="work_date.asc,courier_name.asc,assigned_at.asc",
        limit=20000,
        page_size=500,
    )


@st.cache_data(show_spinner=False, ttl=300)
def rebuild_route_stories_from_sources(start_date, end_date):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    parsed_start = route_story_builder.parse_date(format_date_filter(start_date))
    parsed_end = route_story_builder.parse_date(format_date_filter(end_date))
    summary_table, summary_rows, arrivals_table, arrivals = (
        route_story_builder.load_sources(
            supabase_url=supabase_url.rstrip("/"),
            service_role_key=service_role_key,
            start_date=parsed_start,
            end_date=parsed_end,
            force_raw=False,
        )
    )
    _distance_table, distance_rows = route_story_builder.load_optional_table(
        supabase_url=supabase_url.rstrip("/"),
        service_role_key=service_role_key,
        candidates=route_story_builder.DISTANCE_TABLE_CANDIDATES,
        columns=route_story_builder.DISTANCE_COLUMNS,
        start_date=parsed_start,
        end_date=parsed_end,
        order="work_date.asc,driver_id.asc,route_id.asc",
        chunk_by_day=True,
        page_size=500,
    )
    _booking_table, booking_rows = route_story_builder.load_optional_table(
        supabase_url=supabase_url.rstrip("/"),
        service_role_key=service_role_key,
        candidates=route_story_builder.BOOKING_TABLE_CANDIDATES,
        columns=route_story_builder.BOOKING_COLUMNS,
        start_date=parsed_start,
        end_date=parsed_end,
        order="work_date.asc,courier_id.asc,shift_text.asc",
        chunk_by_day=True,
        page_size=500,
    )
    rows = route_story_builder.build_output_rows(
        summary_rows=summary_rows,
        arrival_stats=route_story_builder.build_arrival_stats(arrivals),
        distance_lookup=route_story_builder.build_distance_lookup(distance_rows),
        booking_lookup=route_story_builder.build_booking_lookup(booking_rows),
        source_summary_table=summary_table,
        source_arrivals_table=arrivals_table,
    )

    return pd.DataFrame(rows)


def read_table_with_filter_list(
    table_name,
    columns,
    filters_list,
    order="",
    limit=10000,
    page_size=500,
):
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    active_columns = list(columns)

    while True:
        rows = []
        params = [("select", ",".join(active_columns))]
        params.extend(filters_list)

        if order:
            params.append(("order", order))

        endpoint = f"{supabase_url}/rest/v1/{table_name}"

        while len(rows) < int(limit):
            range_start = len(rows)
            range_end = min(
                range_start + int(page_size) - 1,
                int(limit) - 1,
            )
            headers = get_headers(service_role_key)
            headers.update(
                {
                    "Range-Unit": "items",
                    "Range": f"{range_start}-{range_end}",
                }
            )
            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=60,
            )

            if is_missing_table_response(response):
                return pd.DataFrame()

            missing_column = missing_column_name(response)

            if missing_column:
                active_columns = [
                    column for column in active_columns if column != missing_column
                ]
                break

            raise_for_supabase_error(response)
            chunk = response.json()

            if not chunk:
                return pd.DataFrame(rows)

            rows.extend(chunk)

            if len(chunk) < (range_end - range_start + 1):
                return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=300)
def read_performance_rows(start_date, end_date, courier_id="", warehouse=""):
    filters_list = [
        ("date_from", f"lte.{format_date_filter(end_date)}"),
        ("date_to", f"gte.{format_date_filter(start_date)}"),
    ]
    clean_courier_id = str(courier_id or "").strip()

    if clean_courier_id:
        filters_list.append(("courier_id", f"eq.{clean_courier_id}"))

    warehouse_map = {
        "BUD1": "1",
        "BUD2": "2",
    }
    warehouse_id = warehouse_map.get(str(warehouse or "").strip().upper())

    if warehouse_id:
        filters_list.append(("warehouse_id", f"eq.{warehouse_id}"))

    return read_table_with_filter_list(
        table_name=PERFORMANCE_TABLE,
        columns=PERFORMANCE_COLUMNS,
        filters_list=filters_list,
        order="date_from.asc,warehouse_id.asc,courier_id.asc",
        limit=10000,
        page_size=500,
    )


def parse_datetime(value):
    if value in (None, ""):
        return pd.NaT

    parsed = pd.to_datetime(
        value,
        errors="coerce",
        utc=True,
    )

    if pd.isna(parsed):
        return pd.NaT

    return parsed.tz_convert(BUDAPEST_TZ).tz_localize(None)


def minutes_between(start_value, end_value):
    start = parse_datetime(start_value)
    end = parse_datetime(end_value)

    if pd.isna(start) or pd.isna(end):
        return None

    return int(round((end - start).total_seconds() / 60))


def checkpoint_status(real_arrival, window_start, window_end):
    real = parse_datetime(real_arrival)
    start = parse_datetime(window_start)
    end = parse_datetime(window_end)

    if pd.isna(real):
        return "Nincs valos erkezes", None

    if not pd.isna(start) and real < start:
        return "Korai idokapuhoz", int(round((real - start).total_seconds() / 60))

    if not pd.isna(end) and real > end:
        return "Keso idokapuhoz", int(round((real - end).total_seconds() / 60))

    if not pd.isna(start) and not pd.isna(end):
        return "Idoben idokapuhoz", 0

    return "Nincs idokapu", None


def parse_driver_detail_order_rows(raw_rows, route_ids):
    wanted_route_ids = {str(route_id) for route_id in route_ids if str(route_id).strip()}
    order_rows = []

    for raw in raw_rows:
        response_json = raw.get("response_json") or {}
        work_date = raw.get("work_date")
        driver_id = raw.get("driver_id") or response_json.get("courier-id")
        courier_name = response_json.get("courierName") or response_json.get("name")
        warehouse_name = response_json.get("warehouseName")

        for route in response_json.get("routes", []) or []:
            route_id = route.get("id") or route.get("routeId")

            if wanted_route_ids and str(route_id) not in wanted_route_ids:
                continue

            for checkpoint in route.get("checkpoints", []) or []:
                status, window_delta = checkpoint_status(
                    checkpoint.get("realArrivalTime"),
                    checkpoint.get("deliverSince"),
                    checkpoint.get("deliverTill"),
                )
                planned_delta = minutes_between(
                    checkpoint.get("plannedArrivalTime"),
                    checkpoint.get("realArrivalTime"),
                )

                order_rows.append(
                    {
                        "work_date": work_date,
                        "courier_id": str(driver_id or ""),
                        "courier_name": courier_name,
                        "warehouse_name": warehouse_name,
                        "route_id": str(route_id or ""),
                        "order_id": str(checkpoint.get("orderId") or ""),
                        "checkpoint_id": str(checkpoint.get("id") or ""),
                        "position": checkpoint.get("position"),
                        "address": checkpoint.get("address") or "",
                        "deliver_since": parse_datetime(
                            checkpoint.get("deliverSince")
                        ),
                        "deliver_till": parse_datetime(
                            checkpoint.get("deliverTill")
                        ),
                        "planned_arrival": parse_datetime(
                            checkpoint.get("plannedArrivalTime")
                        ),
                        "estimated_arrival": parse_datetime(
                            checkpoint.get("estimatedArrivalTime")
                        ),
                        "real_arrival": parse_datetime(
                            checkpoint.get("realArrivalTime")
                        ),
                        "planned_delta_minutes": planned_delta,
                        "time_window_delta_minutes": window_delta,
                        "time_window_status": status,
                    }
                )

    if not order_rows:
        return pd.DataFrame()

    result = pd.DataFrame(order_rows)
    result["position_sort"] = pd.to_numeric(
        result["position"],
        errors="coerce",
    ).fillna(9999)

    return result.sort_values(
        ["work_date", "route_id", "position_sort", "order_id"],
        ascending=True,
    )


@st.cache_data(show_spinner=False, ttl=300)
def read_order_details_for_routes(start_date, end_date, courier_id, route_ids):
    route_ids = [str(route_id) for route_id in route_ids if str(route_id).strip()]

    if not route_ids:
        return pd.DataFrame()

    clean_courier_id = str(courier_id or "").strip()
    filters_list = [
        ("work_date", f"gte.{format_date_filter(start_date)}"),
        ("work_date", f"lte.{format_date_filter(end_date)}"),
    ]

    if clean_courier_id:
        filters_list.append(("driver_id", f"eq.{clean_courier_id}"))

    for table_name in DRIVER_DETAIL_TABLES:
        raw_rows = read_table_with_filter_list(
            table_name=table_name,
            columns=DRIVER_DETAIL_COLUMNS,
            filters_list=filters_list,
            order="work_date.asc,driver_id.asc",
            limit=20000,
            page_size=100,
        )

        if raw_rows.empty:
            continue

        return parse_driver_detail_order_rows(
            raw_rows.to_dict("records"),
            route_ids,
        )

    return pd.DataFrame()


def summarize_performance(performance_df):
    if performance_df.empty:
        return {}

    df = performance_df.copy()

    for column in [
        "shifts",
        "orders",
        "delayed",
        "delay_percent",
        "late_percent",
        "no_show_percent",
        "compliance_bad_percent",
        "compliance_score_percent",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    shifts = int(df.get("shifts", pd.Series(dtype=float)).fillna(0).sum())
    orders = int(df.get("orders", pd.Series(dtype=float)).fillna(0).sum())
    delayed = int(df.get("delayed", pd.Series(dtype=float)).fillna(0).sum())
    delay_percent = (delayed / orders * 100) if orders else 0

    def weighted_percent(column, weight_column):
        if column not in df.columns or weight_column not in df.columns:
            return 0

        valid = df[[column, weight_column]].dropna()

        if valid.empty or valid[weight_column].sum() == 0:
            return 0

        return (
            valid[column].mul(valid[weight_column]).sum()
            / valid[weight_column].sum()
        )

    late_percent = weighted_percent("late_percent", "shifts")
    no_show_percent = weighted_percent("no_show_percent", "shifts")
    compliance_bad_percent = (0.7 * no_show_percent) + (0.3 * late_percent)
    compliance_score_percent = 100 - compliance_bad_percent

    return {
        "shifts": shifts,
        "orders": orders,
        "delayed": delayed,
        "delay_percent": delay_percent,
        "late_percent": late_percent,
        "no_show_percent": no_show_percent,
        "compliance_bad_percent": compliance_bad_percent,
        "compliance_score_percent": compliance_score_percent,
    }


def summarize_story_rows(stories_df, official_shifts=0):
    if stories_df.empty:
        return {}

    df = stories_df.copy()

    for column in [
        "address_count",
        "planned_late_count",
        "time_window_late_count",
        "queue_entry_delta_minutes",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    orders = int(df.get("address_count", pd.Series(dtype=float)).sum())
    delayed = int(df.get("time_window_late_count", pd.Series(dtype=float)).sum())
    late_shift_count = int(
        (df.get("queue_entry_delta_minutes", pd.Series(dtype=float)) > 0).sum()
    )
    shift_base = int(official_shifts or 0)

    if not shift_base:
        if "shift_id" in df.columns:
            shift_base = int(df["shift_id"].replace("", pd.NA).dropna().nunique())

        if not shift_base:
            shift_base = int(len(df))

    return {
        "orders": orders,
        "delayed": delayed,
        "delay_percent": (delayed / orders * 100) if orders else 0,
        "late_shift_count": late_shift_count,
        "shift_base": shift_base,
        "late_percent": (late_shift_count / shift_base * 100) if shift_base else 0,
        "time_window_late_count": int(
            df.get("time_window_late_count", pd.Series(dtype=float)).sum()
        ),
    }


def format_dt(value):
    parsed = parse_datetime(value)

    if pd.isna(parsed):
        return "-"

    return parsed.strftime("%Y-%m-%d %H:%M")


def format_minutes(value):
    if value in (None, "") or pd.isna(value):
        return "-"

    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError):
        return "-"

    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    hours = minutes // 60
    remainder = minutes % 60

    if hours and remainder:
        return f"{sign}{hours} ora {remainder} perc"

    if hours:
        return f"{sign}{hours} ora"

    return f"{sign}{remainder} perc"


def format_percent(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def route_status_label(row):
    queue_delta = pd.to_numeric(
        pd.Series([row.get("queue_entry_delta_minutes")]),
        errors="coerce",
    ).iloc[0]
    time_window_late = pd.to_numeric(
        pd.Series([row.get("time_window_late_count")]),
        errors="coerce",
    ).fillna(0).iloc[0]

    if pd.notna(queue_delta) and queue_delta > 0:
        return "Sorba allas kesett", "bad"

    if time_window_late > 0:
        return "Idokapu keses volt", "warn"

    return "Rendben", "ok"


def order_status_class(row):
    planned_delta = row.get("planned_delta_minutes")
    window_status = str(row.get("time_window_status") or "")

    try:
        planned_delta = float(planned_delta)
    except (TypeError, ValueError):
        planned_delta = 0

    if "Keso" in window_status or planned_delta > 0:
        return "late"

    if "Korai" in window_status or planned_delta < 0:
        return "early"

    return "ok"


def render_route_path_html(route_orders):
    if route_orders.empty:
        return ""

    items = []

    for _, row in route_orders.iterrows():
        status_class = order_status_class(row)
        position = escape(str(row.get("position") or "?"))
        order_id = escape(str(row.get("order_id") or "-"))
        address = escape(str(row.get("address") or "-"))
        window_text = (
            f"{format_dt(row.get('deliver_since'))} - "
            f"{format_dt(row.get('deliver_till'))}"
        )
        planned_text = format_dt(row.get("planned_arrival"))
        real_text = format_dt(row.get("real_arrival"))
        delta_text = format_minutes(row.get("planned_delta_minutes"))
        status_text = escape(str(row.get("time_window_status") or "-"))

        items.append(
            f"""
            <div class="perf-stop perf-stop-{status_class}">
                <div class="perf-stop-dot">{position}</div>
                <div class="perf-stop-card">
                    <div class="perf-stop-title">Order #{order_id}</div>
                    <div class="perf-stop-address">{address}</div>
                    <div class="perf-stop-meta">Időablak: {escape(window_text)}</div>
                    <div class="perf-stop-meta">Tervezett: {escape(planned_text)} | Valós: {escape(real_text)} | Eltérés: {escape(delta_text)}</div>
                    <div class="perf-stop-status">{status_text}</div>
                </div>
            </div>
            """
        )

    return f"""
    <div class="perf-route-path">
        {''.join(items)}
    </div>
    """
