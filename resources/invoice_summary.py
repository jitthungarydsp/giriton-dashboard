from datetime import date, datetime
from io import BytesIO

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


def money(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def format_huf(value):
    return f"{money(value):,.0f} Ft".replace(",", " ")


def normalize_text(value):
    return str(value or "").strip()


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

    return {
        "final_table": final_table,
        "final": final_df,
        "summary": summary_df,
        "bonus": bonus_df,
        "penalties": penalty_df,
    }


def add_numeric_columns(df, columns):
    for column in columns:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    return df


def build_driver_invoice_summary(final_df, bonus_df=None, penalty_df=None):
    if final_df.empty:
        return pd.DataFrame()

    final_df = final_df.copy()
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
    ]
    final_df = add_numeric_columns(final_df, numeric_columns)

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

    if bonus_df is not None and not bonus_df.empty:
        bonus_df = bonus_df.copy()
        bonus_df["driver_name"] = bonus_df["driver_name"].map(normalize_text)
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
    else:
        grouped["extra_bonus_huf"] = 0

    if penalty_df is not None and not penalty_df.empty:
        penalty_df = penalty_df.copy()
        penalty_df["driver_name"] = penalty_df["driver_name"].map(normalize_text)
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
    else:
        grouped["adjustment_huf"] = 0

    grouped["extra_bonus_huf"] = grouped["extra_bonus_huf"].fillna(0)
    grouped["adjustment_huf"] = grouped["adjustment_huf"].fillna(0)
    grouped["payable_total_huf"] = (
        grouped["route_total_huf"]
        + grouped["extra_bonus_huf"]
        + grouped["adjustment_huf"]
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
        "payable_total_huf",
    ]:
        if column in visible.columns:
            visible[column] = visible[column].map(format_huf)

    return visible.rename(
        columns={
            "driver_name": "Futar",
            "worksheet_name": "Raktar ful",
            "orders": "Rendeles",
            "routes": "Kor",
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
            "payable_total_huf": "Fizetendo osszesen",
        }
    )


def build_invoice_pdf_bytes(driver_summary_df, route_df, title):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
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

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 0.3 * cm),
    ]

    summary_display = build_display_driver_summary(driver_summary_df)
    summary_columns = [
        "Futar",
        "Raktar ful",
        "Rendeles",
        "Kor",
        "Kesedelmi dij",
        "Turamegfeleles",
        "Levonas / plusz",
        "Fizetendo osszesen",
    ]
    summary_columns = [
        column for column in summary_columns if column in summary_display.columns
    ]
    summary_table = [summary_columns] + summary_display[summary_columns].astype(str).values.tolist()
    table = Table(summary_table, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9ead3")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([table, Spacer(1, 0.4 * cm)])

    route_display = build_display_routes(route_df)
    route_columns = [
        "Datum",
        "Futar",
        "Route ID",
        "Rendeles",
        "Alapdij",
        "Kesedelmi dij",
        "Turamegfeleles",
        "Osszesen",
    ]
    route_columns = [
        column for column in route_columns if column in route_display.columns
    ]
    if not route_display.empty:
        story.append(Paragraph("Route reszletek", styles["Heading2"]))
        route_table = [route_columns] + route_display[route_columns].astype(str).head(200).values.tolist()
        table = Table(route_table, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(table)

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()
