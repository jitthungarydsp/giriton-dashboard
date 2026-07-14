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
        routes = int(money(driver_row.get("routes")))
        payable_total = money(driver_row.get("payable_total_huf"))
        fixed_total = money(driver_row.get("fixed_rate_huf"))
        delay_bonus = money(driver_row.get("delay_bonus_huf"))
        compliance_bonus = money(driver_row.get("compliance_bonus_huf"))
        fill_rate_bonus = money(driver_row.get("fill_rate_bonus_huf"))
        fuel_bonus = money(driver_row.get("fuel_bonus_huf"))
        fridge_bonus = money(driver_row.get("car_fridge_bonus_huf"))
        branding = money(driver_row.get("branding_huf"))
        tip = money(driver_row.get("tip_huf"))
        extra_bonus = money(driver_row.get("extra_bonus_huf"))
        adjustment = money(driver_row.get("adjustment_huf"))
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
                ["Alap címpénz (Ft/db)", format_huf(base_per_order), "Nyitó céltartalék", "0 Ft"],
                ["Kiflis bónuszok Ft/cím", f"+{format_huf(bonus_per_order)}", "Célt. feltöltés (+)", "0 Ft"],
                ["Összes címpénz", format_huf(base_per_order + bonus_per_order), "Célt. záró egyenleg", "0 Ft"],
            ],
            colWidths=[5.4 * cm, 3.1 * cm, 5.4 * cm, 3.1 * cm],
        )
        apply_statement_table_style(base, font_name, bold_font_name, TableStyle, colors)
        story.append(base)
        story.append(Spacer(1, 0.28 * cm))

        story.append(Paragraph("BÓNUSZOK ÉS TELJESÍTMÉNY", section_style))
        bonus_table = Table(
            [
                ["Kiszállított címek", orders, "Körök", routes],
                ["Just in Time / késés", format_huf(delay_bonus), "Túramegfelelés", format_huf(compliance_bonus)],
                ["Töltési / fill-rate bónusz", format_huf(fill_rate_bonus), "Üzemanyag / hűtő / branding", format_huf(fuel_bonus + fridge_bonus + branding)],
                ["Egyéb bónusz", format_huf(extra_bonus), "Borravaló", format_huf(tip)],
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
            ["Egyéb / Mátrix", format_huf(max(extra_bonus, 0))],
        ]
        expenses = [
            ["Maluszok / levonások", format_huf(abs(adjustment)) if adjustment < 0 else "0 Ft"],
            ["Károkozás", "0 Ft"],
            ["Be nem fiz. KP", "0 Ft"],
            ["Egyéb plusz", format_huf(adjustment) if adjustment > 0 else "0 Ft"],
        ]
        settlement_rows = [["Bevételek", "Ft", "Kiadások", "Ft"]]
        for left, right in zip(revenues, expenses):
            settlement_rows.append([left[0], left[1], right[0], right[1]])
        settlement_rows.append(
            [
                "BEVÉTELEK ÖSSZESEN",
                format_huf(fixed_total + bonus_total + tip + max(extra_bonus, 0)),
                "KIADÁSOK ÖSSZESEN",
                format_huf(abs(adjustment)) if adjustment < 0 else "0 Ft",
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

        if not driver_routes.empty:
            story.append(Spacer(1, 0.28 * cm))
            story.append(Paragraph("Route részletek", section_style))
            route_display = build_display_routes(driver_routes)
            route_columns = [
                "Datum",
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
            route_rows = [route_columns] + route_display[route_columns].astype(str).head(18).values.tolist()
            route_table = Table(route_rows, repeatRows=1)
            route_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("FONTNAME", (0, 0), (-1, 0), bold_font_name),
                        ("FONTNAME", (0, 1), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(route_table)

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
