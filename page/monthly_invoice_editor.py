from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from resources.invoice_summary import (
    build_driver_invoice_summary,
    format_huf,
    read_invoice_data,
)
from resources.peopleforce_documents import (
    upload_peopleforce_document_bytes,
    upsert_peopleforce_card_status,
)


def previous_month_period(reference_date=None):
    reference_date = reference_date or date.today()
    current_month_start = reference_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return previous_month_start, previous_month_end


def normalize_courier_id(value):
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def to_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_tax_number(value):
    """Egységes, szóközmentes magyar adószám szöveg."""
    return str(value or "").strip().replace(" ", "")


def get_tax_number(summary_row):
    """Adószám kiolvasása több, a projektben előforduló mezőnévből."""
    candidate_keys = (
        "tax_number",
        "tax_id",
        "taxnumber",
        "adoszam",
        "adóazonosító",
        "adóazonosito",
        "vat_number",
        "vat_id",
    )
    for key in candidate_keys:
        value = normalize_tax_number(summary_row.get(key))
        if value:
            return value
    return ""


def is_vat_tax_number(value):
    """A magyar adószám középső, 2-es ÁFA-kódját ellenőrzi.

    Példa: 12345678-2-42 -> True.
    """
    tax_number = normalize_tax_number(value)
    match = re.fullmatch(r"\d{8}-([1-5])-\d{2}", tax_number)
    return bool(match and match.group(1) == "2")


def split_gross_vat(gross_amount, vat_rate=0.27):
    """Bruttó összegből egész forintra bontott nettó és ÁFA.

    Előjeles összegekkel is működik, így egy esetleges negatív korrekció
    nettó és ÁFA része is pontosan visszaadja az eredeti bruttó összeget.
    """
    gross = int(round(to_number(gross_amount)))
    if gross == 0:
        return 0, 0
    net = int(round(gross / (1 + vat_rate)))
    vat = gross - net
    return net, vat


def current_username():
    user = st.session_state.get("user", {})
    if isinstance(user, dict):
        return str(user.get("username") or user.get("name") or "admin")
    return str(st.session_state.get("username") or "admin")


def month_start(value):
    return value.replace(day=1)


def slugify_filename(value):
    text = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "dokumentum"


def filter_by_worksheet(df, selected_sheet):
    if df is None or df.empty or selected_sheet == "Mind":
        return df
    if "worksheet_name" not in df.columns:
        return df.iloc[0:0].copy()
    return df[
        df["worksheet_name"]
        .astype(str)
        .str.strip()
        .eq(str(selected_sheet).strip())
    ].copy()


def register_pdf_font():
    regular_candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    try:
        for path in regular_candidates:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont("JittEditorFont", path))
                break
        else:
            return "Helvetica", "Helvetica-Bold"

        for path in bold_candidates:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont("JittEditorFont-Bold", path))
                return "JittEditorFont", "JittEditorFont-Bold"
        return "JittEditorFont", "JittEditorFont"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def build_editor_pdf_bytes(
    *,
    title,
    subtitle,
    courier_id,
    courier_name,
    period_label,
    rows,
    total_huf,
):
    regular_font, bold_font = register_pdf_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "JittNormal",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=8.5,
        leading=10.5,
    )
    title_style = ParagraphStyle(
        "JittTitle",
        parent=normal,
        fontName=bold_font,
        fontSize=18,
        leading=22,
        spaceAfter=5,
    )
    bold = ParagraphStyle("JittBold", parent=normal, fontName=bold_font)
    right = ParagraphStyle("JittRight", parent=normal, alignment=TA_RIGHT)

    story = [
        Paragraph(title, title_style),
        Paragraph(subtitle, normal),
        Spacer(1, 4 * mm),
        Paragraph(f"Futár: <b>{courier_name}</b> | Courier ID: <b>{courier_id}</b>", normal),
        Paragraph(f"Időszak: <b>{period_label}</b>", normal),
        Spacer(1, 5 * mm),
    ]

    table_data = [
        [
            Paragraph("Tétel", bold),
            Paragraph("Szöveg", bold),
            Paragraph("Összeg", bold),
        ]
    ]
    for _, row in rows.iterrows():
        table_data.append(
            [
                Paragraph(str(row.get("Megnevezes") or ""), normal),
                Paragraph(str(row.get("Szoveg") or ""), normal),
                Paragraph(format_huf(row.get("Osszeg (Ft)")), right),
            ]
        )
    table_data.append(
        [
            Paragraph("VÉGÖSSZEG", bold),
            "",
            Paragraph(format_huf(total_huf), right),
        ]
    )

    table = Table(table_data, colWidths=[45 * mm, 100 * mm, 35 * mm])
    total_row = len(table_data) - 1
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -2), 0.4, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#233018")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, total_row), (-1, total_row), colors.HexColor("#eef9e8")),
                ("BOX", (0, total_row), (-1, total_row), 0.7, colors.HexColor("#6ab82f")),
                ("SPAN", (0, total_row), (1, total_row)),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def upload_editor_pdf_to_profile(
    *,
    courier_id,
    courier_name,
    document_type,
    action_key,
    document_month,
    title,
    note,
    file_name,
    pdf_bytes,
):
    upload_peopleforce_document_bytes(
        courier_id=courier_id,
        courier_name=courier_name,
        document_type=document_type,
        document_month=document_month,
        title=title,
        note=note,
        file_name=file_name,
        mime_type="application/pdf",
        file_bytes=pdf_bytes,
        uploaded_by=current_username(),
    )
    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key=action_key,
        document_month=document_month,
        status="open",
        status_note=f"{title} feltöltve, futár elfogadására vár.",
        updated_by=current_username(),
    )


def build_driver_label(row):
    courier_id = normalize_courier_id(row.get("courier_id"))
    name = str(row.get("driver_name") or "").strip() or "Nevtelen futar"
    warehouse = str(row.get("worksheet_name") or "").strip()
    prefix = f"#{courier_id} - " if courier_id else ""
    suffix = f" ({warehouse})" if warehouse else ""
    return f"{prefix}{name}{suffix}"


def line_row(code, label, note, amount, source, quantity=1, unit_price=None):
    amount = int(round(to_number(amount)))
    if unit_price is None:
        unit_price = amount if quantity else 0
    return {
        "Aktiv": True,
        "Kod": code,
        "Megnevezes": label,
        "Szoveg": note,
        "Mennyiseg": quantity,
        "Egysegar (Ft)": int(round(to_number(unit_price))),
        "Osszeg (Ft)": amount,
        "Forras": source,
        "Torles": False,
    }


def build_default_invoice_lines(summary_row):
    fixed_amount = to_number(summary_row.get("fixed_rate_huf"))
    highlighted_amount = to_number(summary_row.get("kiemelt_base_huf"))
    normal_amount = to_number(summary_row.get("sima_base_huf"))

    lines = [
        line_row(
            "base_total",
            "Alapdij osszesen",
            (
                f"Kiemelt kor: {int(to_number(summary_row.get('kiemelt_routes')))} db / "
                f"{format_huf(highlighted_amount)}; sima kor: "
                f"{int(to_number(summary_row.get('sima_routes')))} db / "
                f"{format_huf(normal_amount)}."
            ),
            fixed_amount,
            "Szamolt route dij",
        ),
        line_row(
            "delay_bonus",
            "Kesedelmi bonusz",
            "Szerzodeses kesedelmi mutato alapjan szamolt futari resz.",
            summary_row.get("delay_bonus_huf"),
            "Invoice bonusz tabla",
        ),
        line_row(
            "compliance_bonus",
            "Turamegfelelesi bonusz",
            "Szerzodeses turamegfelelesi mutato alapjan szamolt futari resz.",
            summary_row.get("compliance_bonus_huf"),
            "Invoice bonusz tabla",
        ),
        line_row(
            "customer_rating_bonus",
            "Ugyfelertekelesi bonusz",
            "Ugyfelertekeles alapjan szamolt havi bonusz.",
            summary_row.get("customer_rating_bonus_huf"),
            "Ugyfelertekeles",
        ),
        line_row(
            "monthly_adjustment",
            "Havi korrekcio",
            "Havi zarasbol erkezo bonusz, malusz, leadott vagy felvett kor hatasa.",
            summary_row.get("monthly_adjustment_effect_huf"),
            "Havi zaras",
        ),
        line_row(
            "atm_effect",
            "KP / ATM hatas",
            "KP egyenleg elszamolasi hatasa.",
            summary_row.get("atm_effect_huf"),
            "ATM / KP",
        ),
        line_row(
            "cash_missing",
            "Be nem fizetett KP",
            "Manualisan rogzitett KP hiany.",
            summary_row.get("cash_missing_huf"),
            "Manualis tetel",
        ),
        line_row(
            "damage",
            "Karokozas",
            "Manualisan rogzitett karokozas vagy levonas.",
            summary_row.get("damage_huf"),
            "Manualis tetel",
        ),
        line_row(
            "instructor_fee",
            "Oktatoi dij",
            "Manualisan rogzitett oktatoi dij.",
            summary_row.get("instructor_fee_huf"),
            "Manualis tetel",
        ),
        line_row(
            "loyalty_bonus",
            "Lojalitasi bonusz",
            "Lojalitas szabaly alapjan szamolt bonusz.",
            summary_row.get("loyalty_bonus_huf"),
            "Lojalitas",
        ),
        line_row(
            "other_income",
            "Egyeb bevetel",
            "Manualisan rogzitett plusz tetel.",
            summary_row.get("other_income_huf"),
            "Manualis tetel",
        ),
        line_row(
            "other_deduction",
            "Egyeb levonas",
            "Manualisan rogzitett levonas.",
            summary_row.get("other_deduction_huf"),
            "Manualis tetel",
        ),
        line_row(
            "tip",
            "Borravalo",
            "Futarnak atadando borravalo.",
            summary_row.get("tip_huf"),
            "Invoice",
        ),
        line_row(
            "target_reserve",
            "Celtartalek levonas",
            "Celtartalek szabaly szerinti levonas.",
            -abs(to_number(summary_row.get("target_reserve_deduction_huf"))),
            "Celtartalek",
        ),
        line_row(
            "insurance",
            "Biztositas",
            "Biztositas levonas.",
            -abs(to_number(summary_row.get("insurance_deduction_huf"))),
            "Celtartalek",
        ),
    ]

    non_zero_lines = [row for row in lines if int(row["Osszeg (Ft)"]) != 0]
    return pd.DataFrame(non_zero_lines or lines)


def build_default_tig_lines(summary_row):
    payable_total = int(round(to_number(summary_row.get("payable_total_huf"))))
    tip_amount = max(int(round(to_number(summary_row.get("tip_huf")))), 0)

    # A KP a TIG-en önálló tétel. Mivel a payable_total már tartalmazza,
    # előbb kivesszük a szolgáltatási részből, majd külön soron visszatesszük.
    cash_gross = abs(int(round(to_number(summary_row.get("atm_balance_huf")))))
    taxable_gross_total = payable_total - tip_amount
    delivery_gross = taxable_gross_total - cash_gross

    tax_number = get_tax_number(summary_row)
    vat_applicable = is_vat_tax_number(tax_number)

    rows = []
    if vat_applicable:
        delivery_net, delivery_vat = split_gross_vat(delivery_gross, vat_rate=0.27)
        cash_net, cash_vat = split_gross_vat(cash_gross, vat_rate=0.27)
        vat_amount = delivery_vat + cash_vat

        rows.extend(
            [
                {
                    **line_row(
                        "service_fee_net",
                        "Szállítási díj – nettó",
                        "A TIG fő szolgáltatási sora a KP és a borravaló nélkül; 27%-os ÁFA alapja.",
                        delivery_net,
                        "Elszámolás fizetendő összeg",
                    ),
                    "TIG-be szamit": True,
                },
                {
                    **line_row(
                        "cash_net",
                        "KP – nettó",
                        "A KP külön soron, a bruttó KP összeg 27%-os ÁFÁ-val visszanettósított értéke.",
                        cash_net,
                        "ATM / KP",
                    ),
                    "TIG-be szamit": True,
                },
                {
                    **line_row(
                        "vat_27",
                        "ÁFA 27%",
                        "A nettó szállítási díj és a nettósított KP együttes 27%-os ÁFÁ-ja.",
                        vat_amount,
                        "Adószám ÁFA-kód: 2",
                    ),
                    "TIG-be szamit": True,
                },
            ]
        )
    else:
        rows.extend(
            [
                {
                    **line_row(
                        "service_fee",
                        "Szállítási díj",
                        "A TIG fő szolgáltatási sora a KP és a borravaló nélkül.",
                        delivery_gross,
                        "Elszámolás fizetendő összeg",
                    ),
                    "TIG-be szamit": True,
                },
                {
                    **line_row(
                        "cash",
                        "KP",
                        "A KP külön TIG-soron szereplő összege.",
                        cash_gross,
                        "ATM / KP",
                    ),
                    "TIG-be szamit": True,
                },
            ]
        )

    rows.append(
        {
            **line_row(
                "tip",
                "Borravaló – adómentes",
                "A futár részére változatlan összegben továbbadott borravaló; az ÁFA alapjába nem számít bele.",
                tip_amount,
                "Elszámolás tip",
            ),
            "TIG-be szamit": True,
        }
    )

    non_zero_rows = [
        row
        for row in rows
        if int(row["Osszeg (Ft)"]) != 0
        or row["Kod"] in {"service_fee", "service_fee_net"}
    ]
    return pd.DataFrame(non_zero_rows or rows)


def normalize_editor_df(df):
    if df is None or df.empty:
        df = pd.DataFrame(
            columns=[
                "Aktiv",
                "Kod",
                "Megnevezes",
                "Szoveg",
                "Mennyiseg",
                "Egysegar (Ft)",
                "Osszeg (Ft)",
                "Forras",
                "Torles",
            ]
        )
    df = df.copy()
    for column, default in {
        "Aktiv": True,
        "Kod": "",
        "Megnevezes": "",
        "Szoveg": "",
        "Mennyiseg": 1,
        "Egysegar (Ft)": 0,
        "Osszeg (Ft)": 0,
        "Forras": "Manualis",
        "Torles": False,
    }.items():
        if column not in df.columns:
            df[column] = default
    df["Aktiv"] = df["Aktiv"].fillna(True).astype(bool)
    df["Torles"] = df["Torles"].fillna(False).astype(bool)
    for column in ["Mennyiseg", "Egysegar (Ft)", "Osszeg (Ft)"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df[
        [
            "Aktiv",
            "Kod",
            "Megnevezes",
            "Szoveg",
            "Mennyiseg",
            "Egysegar (Ft)",
            "Osszeg (Ft)",
            "Forras",
            "Torles",
        ]
    ]


def normalize_tig_editor_df(df):
    df = normalize_editor_df(df)
    if "TIG-be szamit" not in df.columns:
        df["TIG-be szamit"] = True
    df["TIG-be szamit"] = df["TIG-be szamit"].fillna(True).astype(bool)
    return df[
        [
            "Aktiv",
            "TIG-be szamit",
            "Kod",
            "Megnevezes",
            "Szoveg",
            "Mennyiseg",
            "Egysegar (Ft)",
            "Osszeg (Ft)",
            "Forras",
            "Torles",
        ]
    ]


def load_driver_summary_for_editor(start_date, end_date, selected_sheet):
    data = read_invoice_data(start_date, end_date)
    final_df = filter_by_worksheet(data.get("final", pd.DataFrame()), selected_sheet)
    if final_df is None or final_df.empty:
        return data, final_df, pd.DataFrame()

    driver_summary = build_driver_invoice_summary(
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
        period_start=start_date,
    )
    return data, final_df, driver_summary


def render_month_filters(prefix):
    default_start, default_end = previous_month_period()
    col1, col2, col3 = st.columns([1, 1, 1])
    start_date = col1.date_input(
        "Honap kezdete",
        value=default_start,
        key=f"{prefix}_start",
    )
    end_date = col2.date_input(
        "Honap vege",
        value=default_end,
        key=f"{prefix}_end",
    )
    selected_sheet = col3.selectbox(
        "Telephely",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key=f"{prefix}_sheet",
    )
    return start_date, end_date, selected_sheet


def render_driver_selector(driver_summary, key):
    driver_summary = driver_summary.reset_index(drop=True)
    options = list(driver_summary.index)
    labels = {
        index: build_driver_label(row)
        for index, row in driver_summary.iterrows()
    }
    selected_index = st.selectbox(
        "Futar",
        options,
        format_func=lambda index: labels.get(index, str(index)),
        key=key,
    )
    return driver_summary, selected_index, driver_summary.loc[selected_index]


def show_monthly_invoice_editor_page():
    st.title("Havi szamla")
    st.caption(
        "A PDF-ben szereplo elszamolasi tetelek szerkesztheto munkanezete. "
        "Itt egyelore kezzel tudsz sort hozzaadni, osszeget modositani vagy sort kivenni."
    )

    start_date, end_date, selected_sheet = render_month_filters(
        "monthly_invoice_editor"
    )

    try:
        _data, final_df, driver_summary = load_driver_summary_for_editor(
            start_date,
            end_date,
            selected_sheet,
        )
    except Exception as exc:
        st.error(f"Elszamolasi adatok betoltese sikertelen: {exc}")
        return

    if final_df is None or final_df.empty:
        st.warning("Nincs elszamolasi route adat erre a szuresre.")
        return

    if driver_summary.empty:
        st.warning("A futar szintu osszesito ures erre a szuresre.")
        return

    driver_summary, selected_index, summary_row = render_driver_selector(
        driver_summary,
        "monthly_invoice_editor_driver",
    )

    courier_id = normalize_courier_id(summary_row.get("courier_id"))
    state_key = (
        f"monthly_invoice_lines_"
        f"{start_date:%Y%m%d}_{end_date:%Y%m%d}_"
        f"{courier_id or selected_index}_"
        f"{summary_row.get('worksheet_name', '')}"
    )
    default_lines = normalize_editor_df(build_default_invoice_lines(summary_row))

    top_cols = st.columns([1, 1, 1, 1])
    top_cols[0].metric("Route", int(to_number(summary_row.get("route_count"))))
    top_cols[1].metric("Order", int(to_number(summary_row.get("orders"))))
    top_cols[2].metric("PDF szerinti osszeg", format_huf(summary_row.get("payable_total_huf")))
    top_cols[3].metric("Borravalo", format_huf(summary_row.get("tip_huf")))

    if state_key not in st.session_state:
        st.session_state[state_key] = default_lines

    action_cols = st.columns([1, 1, 4])
    if action_cols[0].button("Alaphelyzet", key=f"{state_key}_reset"):
        st.session_state[state_key] = default_lines
        st.rerun()
    if action_cols[1].button("Ures sor hozzaadasa", key=f"{state_key}_add"):
        current = normalize_editor_df(st.session_state[state_key])
        new_row = pd.DataFrame(
            [
                line_row(
                    "manual",
                    "Uj manualis tetel",
                    "Kezzel rogzitett sor.",
                    0,
                    "Manualis",
                )
            ]
        )
        st.session_state[state_key] = pd.concat(
            [current, new_row],
            ignore_index=True,
        )
        st.rerun()

    edited = st.data_editor(
        normalize_editor_df(st.session_state[state_key]),
        key=f"{state_key}_editor",
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Aktiv": st.column_config.CheckboxColumn("Aktiv"),
            "Kod": st.column_config.TextColumn("Kod"),
            "Megnevezes": st.column_config.TextColumn("Megnevezes"),
            "Szoveg": st.column_config.TextColumn("Szoveg", width="large"),
            "Mennyiseg": st.column_config.NumberColumn("Mennyiseg", step=1),
            "Egysegar (Ft)": st.column_config.NumberColumn("Egysegar (Ft)", step=100),
            "Osszeg (Ft)": st.column_config.NumberColumn("Osszeg (Ft)", step=100),
            "Forras": st.column_config.TextColumn("Forras"),
            "Torles": st.column_config.CheckboxColumn("Torles"),
        },
    )
    edited = normalize_editor_df(edited)
    st.session_state[state_key] = edited

    if st.button("Torlesre jelolt sorok kivetele", key=f"{state_key}_delete"):
        st.session_state[state_key] = edited[~edited["Torles"]].reset_index(drop=True)
        st.rerun()

    payable_rows = edited[(edited["Aktiv"]) & (~edited["Torles"])].copy()
    payable_total = int(round(payable_rows["Osszeg (Ft)"].sum())) if not payable_rows.empty else 0
    delta = payable_total - int(round(to_number(summary_row.get("payable_total_huf"))))

    st.divider()
    result_cols = st.columns([1, 1, 1])
    result_cols[0].metric("Szerkesztett vegosszeg", format_huf(payable_total))
    result_cols[1].metric("Aktiv sorok", len(payable_rows))
    result_cols[2].metric("Elteres a PDF alaphoz kepest", format_huf(delta))

    courier_name = str(summary_row.get("driver_name") or "").strip()
    period_label = f"{start_date} - {end_date}"
    pdf_bytes = build_editor_pdf_bytes(
        title="JITT havi elszámolás előnézet",
        subtitle="Szerkesztett elszámolási sorok az admin munkanézet alapján.",
        courier_id=courier_id,
        courier_name=courier_name,
        period_label=period_label,
        rows=payable_rows,
        total_huf=payable_total,
    )
    settlement_file_name = (
        f"jitt_elszamolas_elonezet_"
        f"{courier_id or 'futar'}_"
        f"{slugify_filename(courier_name)}_"
        f"{start_date:%Y_%m}.pdf"
    )

    export_df = payable_rows.copy()
    export_df.insert(0, "Courier ID", courier_id)
    export_df.insert(1, "Futar", summary_row.get("driver_name", ""))
    export_df.insert(2, "Honap kezdete", str(start_date))
    export_df.insert(3, "Honap vege", str(end_date))

    download_cols = st.columns([1, 1, 1])
    download_cols[0].download_button(
        "Elonezet PDF letoltese",
        data=pdf_bytes,
        file_name=settlement_file_name,
        mime="application/pdf",
    )
    download_cols[1].download_button(
        "Szerkesztett havi szamla CSV",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"havi_szamla_{courier_id or 'futar'}_{start_date:%Y_%m}.csv",
        mime="text/csv",
    )
    if download_cols[2].button(
        "Feltoltes a profilba",
        key=f"{state_key}_upload_profile",
        disabled=not bool(courier_id),
    ):
        try:
            upload_editor_pdf_to_profile(
                courier_id=courier_id,
                courier_name=courier_name,
                document_type="settlement",
                action_key="settlement",
                document_month=month_start(start_date),
                title=f"Elszámolás - {start_date:%Y-%m}",
                note="Havi számla szerkesztőből feltöltött előnézeti elszámolás.",
                file_name=settlement_file_name,
                pdf_bytes=pdf_bytes,
            )
            st.success("Az elszámolás felkerült a futár profiljába.")
        except Exception as exc:
            st.error(f"Profil feltoltes sikertelen: {exc}")

    st.info(
        "Ez a nezet most szerkeszto munkalap. A kovetkezo lepesben ugyanennek tudunk "
        "DB mentest es PDF generalast adni, ha a sorlogika igy rendben van."
    )


def show_monthly_tig_editor_page():
    st.title("Havi TIG")
    st.caption(
        "A TIG-ben szereplo osszegek es szoveges sorok szerkesztheto nezete. "
        "A 'TIG-be szamit' kapcsoloval dontheto el, hogy egy sor beleszamoljon-e a vegosszegbe."
    )

    start_date, end_date, selected_sheet = render_month_filters("monthly_tig_editor")

    try:
        _data, final_df, driver_summary = load_driver_summary_for_editor(
            start_date,
            end_date,
            selected_sheet,
        )
    except Exception as exc:
        st.error(f"TIG adatok betoltese sikertelen: {exc}")
        return

    if final_df is None or final_df.empty:
        st.warning("Nincs elszamolasi route adat erre a szuresre.")
        return
    if driver_summary.empty:
        st.warning("A futar szintu osszesito ures erre a szuresre.")
        return

    driver_summary, selected_index, summary_row = render_driver_selector(
        driver_summary,
        "monthly_tig_editor_driver",
    )
    courier_id = normalize_courier_id(summary_row.get("courier_id"))

    # Az összesítő nem minden esetben adja át az adószámot, ezért itt
    # közvetlenül is megadható. A TIG sorai ebből az értékből épülnek fel.
    detected_tax_number = get_tax_number(summary_row)
    tax_number = st.text_input(
        "Adószám",
        value=detected_tax_number,
        placeholder="12345678-2-42",
        key=(
            f"monthly_tig_tax_number_"
            f"{start_date:%Y%m%d}_{end_date:%Y%m%d}_"
            f"{courier_id or selected_index}"
        ),
        help="A középső 2-es ÁFA-kód esetén a szolgáltatási rész nettó és 27% ÁFA sorokra bomlik.",
    ).strip()

    summary_for_tig = summary_row.copy()
    summary_for_tig["tax_number"] = tax_number
    vat_applicable = is_vat_tax_number(tax_number)
    tax_state = re.sub(r"[^0-9]", "", tax_number) or "no_tax"

    # Verziózott state kulcs: a korábban session_state-ben maradt régi,
    # összevont TIG sorok nem írhatják felül az új külön bontást.
    state_key = (
        f"monthly_tig_lines_taxsplit_v4_"
        f"{start_date:%Y%m%d}_{end_date:%Y%m%d}_"
        f"{courier_id or selected_index}_"
        f"{summary_row.get('worksheet_name', '')}_"
        f"{tax_state}"
    )
    default_lines = normalize_tig_editor_df(build_default_tig_lines(summary_for_tig))

    payable_total = int(round(to_number(summary_row.get("payable_total_huf"))))
    tip_amount = max(int(round(to_number(summary_row.get("tip_huf")))), 0)
    cash_gross = abs(int(round(to_number(summary_row.get("atm_balance_huf")))))
    taxable_gross_total = payable_total - tip_amount
    delivery_gross = taxable_gross_total - cash_gross
    vat_status = "Áfás (27%)" if vat_applicable else "Nem áfás / AAM"

    if vat_applicable:
        delivery_display, _ = split_gross_vat(delivery_gross)
        cash_display, _ = split_gross_vat(cash_gross)
    else:
        delivery_display = delivery_gross
        cash_display = cash_gross

    top_cols = st.columns([1, 1, 1, 1])
    top_cols[0].metric("PDF/TIG alap", format_huf(payable_total))
    top_cols[1].metric(
        "Szállítási rész" + (" – nettó" if vat_applicable else ""),
        format_huf(delivery_display),
    )
    top_cols[2].metric("Borravaló – adómentes", format_huf(tip_amount))
    top_cols[3].metric(
        "KP" + (" – nettó" if vat_applicable else ""),
        format_huf(cash_display),
    )

    st.caption(
        f"Adószám: {tax_number or 'nincs az összesítőben'} · Adózási mód: {vat_status}. "
        "A KP külön TIG-sor. Áfás futárnál a KP is visszanettósítva jelenik meg, "
        "a hozzá tartozó ÁFA pedig az ÁFA 27% sorba kerül. A borravaló külön adómentes tétel."
    )
    if not tax_number:
        st.warning(
            "Nincs megadva adószám. Írd be fent az adószámot; középső 2-es kódnál "
            "a szolgáltatási díj automatikusan nettó és 27% ÁFA sorokra válik szét."
        )

    info_cols = st.columns(3)
    info_cols[0].text_input(
        "Szolgaltato / elado neve",
        value=str(summary_row.get("driver_name") or ""),
        key=f"{state_key}_seller_name",
    )
    info_cols[1].text_input(
        "Courier ID",
        value=courier_id,
        key=f"{state_key}_courier_id",
    )
    info_cols[2].text_input(
        "Elszamolasi idoszak",
        value=f"{start_date} - {end_date}",
        key=f"{state_key}_period",
    )

    if state_key not in st.session_state:
        st.session_state[state_key] = default_lines

    action_cols = st.columns([1, 1, 4])
    if action_cols[0].button("Alaphelyzet", key=f"{state_key}_reset"):
        st.session_state[state_key] = default_lines
        st.rerun()
    if action_cols[1].button("Ures TIG sor hozzaadasa", key=f"{state_key}_add"):
        current = normalize_tig_editor_df(st.session_state[state_key])
        new_row = pd.DataFrame(
            [
                {
                    **line_row(
                        "manual",
                        "Uj TIG tetel",
                        "Kezzel rogzitett TIG sor.",
                        0,
                        "Manualis",
                    ),
                    "TIG-be szamit": True,
                }
            ]
        )
        st.session_state[state_key] = pd.concat(
            [current, new_row],
            ignore_index=True,
        )
        st.rerun()

    edited = st.data_editor(
        normalize_tig_editor_df(st.session_state[state_key]),
        key=f"{state_key}_editor",
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Aktiv": st.column_config.CheckboxColumn("Aktiv"),
            "TIG-be szamit": st.column_config.CheckboxColumn("TIG-be szamit"),
            "Kod": st.column_config.TextColumn("Kod"),
            "Megnevezes": st.column_config.TextColumn("Megnevezes"),
            "Szoveg": st.column_config.TextColumn("Szoveg", width="large"),
            "Mennyiseg": st.column_config.NumberColumn("Mennyiseg", step=1),
            "Egysegar (Ft)": st.column_config.NumberColumn("Egysegar (Ft)", step=100),
            "Osszeg (Ft)": st.column_config.NumberColumn("Osszeg (Ft)", step=100),
            "Forras": st.column_config.TextColumn("Forras"),
            "Torles": st.column_config.CheckboxColumn("Torles"),
        },
    )
    edited = normalize_tig_editor_df(edited)
    st.session_state[state_key] = edited

    if st.button("Torlesre jelolt TIG sorok kivetele", key=f"{state_key}_delete"):
        st.session_state[state_key] = edited[~edited["Torles"]].reset_index(drop=True)
        st.rerun()

    tig_rows = edited[
        (edited["Aktiv"])
        & (~edited["Torles"])
        & (edited["TIG-be szamit"])
    ].copy()
    tig_total = int(round(tig_rows["Osszeg (Ft)"].sum())) if not tig_rows.empty else 0
    source_total = int(round(to_number(summary_row.get("payable_total_huf"))))
    delta = tig_total - source_total

    st.divider()
    result_cols = st.columns([1, 1, 1])
    result_cols[0].metric("Szerkesztett TIG vegosszeg", format_huf(tig_total))
    result_cols[1].metric("TIG-be szamito sorok", len(tig_rows))
    result_cols[2].metric("Elteres a TIG alaphoz kepest", format_huf(delta))

    courier_name = str(st.session_state.get(f"{state_key}_seller_name") or summary_row.get("driver_name") or "").strip()
    period_label = f"{start_date} - {end_date}"
    pdf_rows = edited[(edited["Aktiv"]) & (~edited["Torles"])].copy()
    pdf_bytes = build_editor_pdf_bytes(
        title="JITT TIG előnézet",
        subtitle="Szerkesztett teljesítési igazolás sorok az admin munkanézet alapján.",
        courier_id=courier_id,
        courier_name=courier_name,
        period_label=period_label,
        rows=pdf_rows,
        total_huf=tig_total,
    )
    tig_file_name = (
        f"jitt_tig_elonezet_"
        f"{courier_id or 'futar'}_"
        f"{slugify_filename(courier_name)}_"
        f"{start_date:%Y_%m}.pdf"
    )

    export_df = edited[(edited["Aktiv"]) & (~edited["Torles"])].copy()
    export_df.insert(0, "Courier ID", courier_id)
    export_df.insert(1, "Futar", summary_row.get("driver_name", ""))
    export_df.insert(2, "Honap kezdete", str(start_date))
    export_df.insert(3, "Honap vege", str(end_date))
    export_df.insert(4, "Adoszam", tax_number)
    export_df.insert(5, "Adozasi mod", vat_status)

    download_cols = st.columns([1, 1, 1])
    download_cols[0].download_button(
        "TIG elonezet PDF letoltese",
        data=pdf_bytes,
        file_name=tig_file_name,
        mime="application/pdf",
    )
    download_cols[1].download_button(
        "Szerkesztett TIG CSV",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"havi_tig_{courier_id or 'futar'}_{start_date:%Y_%m}.csv",
        mime="text/csv",
    )
    if download_cols[2].button(
        "TIG feltoltes a profilba",
        key=f"{state_key}_upload_profile",
        disabled=not bool(courier_id),
    ):
        try:
            upload_editor_pdf_to_profile(
                courier_id=courier_id,
                courier_name=courier_name,
                document_type="tig",
                action_key="tig",
                document_month=month_start(start_date),
                title=f"TIG - {start_date:%Y-%m}",
                note="Havi TIG szerkesztőből feltöltött előnézeti TIG.",
                file_name=tig_file_name,
                pdf_bytes=pdf_bytes,
            )
            st.success("A TIG felkerült a futár profiljába.")
        except Exception as exc:
            st.error(f"TIG profil feltoltes sikertelen: {exc}")

    st.info(
        "Ez most TIG munkalap. Ha a sorlogika rendben van, a kovetkezo korben "
        "osszekotjuk DB mentessel es TIG PDF generalassal."
    )