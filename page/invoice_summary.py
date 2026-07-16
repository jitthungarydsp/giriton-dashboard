from datetime import date
from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd
import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st

from resources.courier_master_db import read_courier_master
from resources.invoice_summary import (
    MANUAL_ITEM_TYPES,
    build_display_base_rate_matrix,
    build_display_driver_summary,
    build_display_manual_items,
    build_display_routes,
    build_display_summary,
    build_driver_invoice_summary,
    build_invoice_pdf_bytes,
    create_manual_invoice_item,
    format_huf,
    read_invoice_data,
)
from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)

from resources.peopleforce_documents import (
    decode_document_content,
    delete_peopleforce_document,
    read_peopleforce_complaints,
    read_peopleforce_documents_for_courier,
    read_peopleforce_document_content,
    respond_to_peopleforce_complaint,
    update_peopleforce_document,
    update_peopleforce_complaint_status,
    upload_peopleforce_document_bytes,
    upsert_peopleforce_card_status,
)


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
    safe = []
    for char in text:
        if char.isalnum():
            safe.append(char)
        elif char in [" ", "-", "_", "."]:
            safe.append("_")
    return "".join(safe).strip("_") or "osszes"


def _register_tig_font():
    """Magyar ékezeteket támogató betűtípus regisztrálása, ha elérhető."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    try:
        for regular_path in font_candidates:
            if Path(regular_path).exists():
                pdfmetrics.registerFont(TTFont("TIGFont", regular_path))
                break
        else:
            return "Helvetica", "Helvetica-Bold"

        for bold_path in bold_candidates:
            if Path(bold_path).exists():
                pdfmetrics.registerFont(TTFont("TIGFont-Bold", bold_path))
                return "TIGFont", "TIGFont-Bold"
        return "TIGFont", "TIGFont"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def _huf(value):
    try:
        amount = int(round(float(value or 0)))
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,}".replace(",", " ") + " Ft"


def build_tig_pdf_bytes(
    *,
    courier_name: str,
    courier_address: str,
    courier_tax_number: str,
    courier_id: str,
    document_month: date,
    transfer_amount_huf: float,
    cash_amount_huf: float = 0,
) -> bytes:
    """Teljesítési igazolás PDF előállítása a kiválasztott futárnak."""
    regular_font, bold_font = _register_tig_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"TIG {document_month:%Y-%m} - {courier_name}",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "TIGNormal", parent=styles["Normal"], fontName=regular_font,
        fontSize=9.5, leading=12, textColor=colors.HexColor("#222222")
    )
    small = ParagraphStyle(
        "TIGSmall", parent=normal, fontSize=8, leading=10
    )
    title_style = ParagraphStyle(
        "TIGTitle", parent=normal, fontName=bold_font, fontSize=21,
        leading=24, alignment=TA_LEFT, spaceAfter=8
    )
    heading = ParagraphStyle(
        "TIGHeading", parent=normal, fontName=bold_font, fontSize=10,
        textColor=colors.HexColor("#666666")
    )
    center = ParagraphStyle("TIGCenter", parent=normal, alignment=TA_CENTER)
    right = ParagraphStyle("TIGRight", parent=normal, alignment=TA_RIGHT)
    bold = ParagraphStyle("TIGBold", parent=normal, fontName=bold_font)
    red_bold = ParagraphStyle(
        "TIGRedBold", parent=right, fontName=bold_font,
        textColor=colors.HexColor("#d60000"), fontSize=12
    )

    period_label = f"{document_month.year}. {document_month.strftime('%B')}"
    hu_months = {
        1: "január", 2: "február", 3: "március", 4: "április",
        5: "május", 6: "június", 7: "július", 8: "augusztus",
        9: "szeptember", 10: "október", 11: "november", 12: "december",
    }
    period_label = f"{document_month.year}. {hu_months[document_month.month]}"
    transfer_amount_huf = int(round(float(transfer_amount_huf or 0)))
    cash_amount_huf = int(round(float(cash_amount_huf or 0)))

    story = [
        Paragraph("TELJESÍTÉSI IGAZOLÁS", title_style),
        Spacer(1, 3 * mm),
    ]

    party_data = [
        [
            Paragraph("SZOLGÁLTATÓ (ELADÓ):", heading),
            Paragraph("MEGBÍZÓ (VEVŐ):", heading),
        ],
        [
            Paragraph(
                f"<b>{courier_name}</b><br/>{courier_address or '—'}<br/>"
                f"Adószám: <b>{courier_tax_number or '—'}</b>", normal
            ),
            Paragraph(
                "<b>Just in Time Transport Hungary Kft.</b><br/>"
                "1201 Budapest, Atléta utca 44<br/>"
                "Adószám: <b>32649460-2-43</b>", normal
            ),
        ],
    ]
    party_table = Table(party_data, colWidths=[82 * mm, 82 * mm])
    party_table.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 1), 0.7, colors.HexColor("#cccccc")),
        ("BOX", (1, 0), (1, 1), 0.7, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([party_table, Spacer(1, 5 * mm)])

    timing = Table([
        [Paragraph("Számlázott időszak", bold), Paragraph("Teljesítés napja", bold), Paragraph("Fizetési határidő", bold), Paragraph("Fizetés módja", bold)],
        [Paragraph(period_label, center), Paragraph("Kiállítás napja + 8 nap", center), Paragraph("Kiállítás napja + 8 nap", center), Paragraph("Átutalás", center)],
    ], colWidths=[40 * mm, 48 * mm, 48 * mm, 30 * mm])
    timing.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([timing, Spacer(1, 5 * mm)])

    amount_table = Table([
        [Paragraph("Tétel megnevezése", bold), Paragraph("Nettó (Ft)", bold), Paragraph("ÁFA (Ft)", bold), Paragraph("Bruttó (Ft)", bold)],
        [Paragraph("Szállítási díj (494107)", normal), Paragraph(_huf(transfer_amount_huf), right), Paragraph("AAM", center), Paragraph(_huf(transfer_amount_huf), right)],
        [Paragraph("VÉGÖSSZEG:", bold), "", "", Paragraph(_huf(transfer_amount_huf), red_bold)],
    ], colWidths=[76 * mm, 32 * mm, 28 * mm, 32 * mm])
    amount_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, 1), 0.7, colors.HexColor("#444444")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("SPAN", (0, 2), (2, 2)),
        ("ALIGN", (0, 2), (2, 2), "RIGHT"),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f9f9f9")),
        ("BOX", (0, 2), (-1, 2), 0.7, colors.HexColor("#444444")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.extend([amount_table, Spacer(1, 4 * mm)])

    id_table = Table([[Paragraph("Megjegyzésbe kötelező az azonosító:", bold), Paragraph(str(courier_id), red_bold)]], colWidths=[116 * mm, 52 * mm])
    id_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#777777")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.7, colors.HexColor("#777777")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([id_table, Spacer(1, 5 * mm)])

    story.append(Paragraph(
        "<b>⚠ SZÁMLÁZÁSI SZABÁLYOK:</b><br/>"
        "• A teljesítési és fizetési határidőt is a kiállítás napja + 8 napra állítsd.<br/>"
        "• Hibás számla (stornó/javítás) esetén nettó 5 000 Ft adminisztrációs költséget érvényesítünk.",
        normal,
    ))

    if cash_amount_huf:
        story.extend([Spacer(1, 5 * mm), Paragraph("KÉSZPÉNZES SZÁMLA (csak ha a levonás miatt szükséges)", heading)])
        cash_table = Table([
            [Paragraph("Megnevezés", bold), Paragraph("Nettó", bold), Paragraph("ÁFA", bold), Paragraph("Bruttó", bold), Paragraph("Mód", bold)],
            [Paragraph("Szállítási díj (494107)", normal), Paragraph(_huf(cash_amount_huf), right), Paragraph("TA (0%)", center), Paragraph(_huf(cash_amount_huf), right), Paragraph("KP", bold)],
        ], colWidths=[68 * mm, 29 * mm, 25 * mm, 29 * mm, 17 * mm])
        cash_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(cash_table)

    story.extend([
        Spacer(1, 8 * mm),
        Paragraph(
            "Gépi úton készült igazolás, aláírás nélkül is hiteles.<br/>"
            "<b>Just in Time Transport Hungary Kft.</b><br/>"
            "Észrevétel és kifogások: elszamolas@jitt.hu",
            ParagraphStyle("TIGFooter", parent=small, alignment=TA_CENTER, textColor=colors.HexColor("#777777")),
        ),
    ])

    doc.build(story)
    return buffer.getvalue()


def normalize_person_key(value):
    """
    Futárnév-egyeztető kulcs.

    Például:
    - Papp Nikolett
    - Papp 7486 Nikolett

    ugyanahhoz a futárhoz fog tartozni.
    """
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").strip().casefold(),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    tokens = re.findall(r"[a-z0-9]+", text)

    # A névben szereplő Courier ID figyelmen kívül hagyása.
    tokens = [
        token
        for token in tokens
        if not (
            token.isdigit()
            and 3 <= len(token) <= 6
        )
    ]

    return " ".join(sorted(tokens))


def normalize_name(value):
    return normalize_person_key(value)


def resolve_courier_identity(selected_row, selected_driver):
    courier_id = str(selected_row.get("courier_id", "") or "").strip()
    courier_name = str(
        selected_row.get("driver_name", selected_driver) or selected_driver
    ).strip()

    if courier_id:
        return courier_id, courier_name

    try:
        master = read_courier_master()
    except Exception:
        master = pd.DataFrame()

    if master.empty or "courier_name" not in master.columns:
        return courier_id, courier_name

    target_name = normalize_name(courier_name)
    matches = master[
        master["courier_name"].astype(str).map(normalize_name) == target_name
    ].copy()

    if matches.empty:
        return courier_id, courier_name

    match = matches.iloc[0]
    courier_id = str(match.get("courier_id", "") or "").strip()
    courier_name = str(match.get("courier_name", courier_name) or courier_name).strip()
    return courier_id, courier_name


def normalize_worksheet_key(value):
    text = str(value or "").strip().upper()
    text = text.replace("-", "_").replace(" ", "_")

    if "BUD1" in text:
        return "BUD1_JIT"

    if "BUD2" in text:
        return "BUD2_JIT"

    return text


def filter_by_worksheet(df, selected_sheet):
    if (
        df is None
        or df.empty
        or selected_sheet == "Mind"
    ):
        return df

    if "worksheet_name" not in df.columns:
        return df.iloc[0:0].copy()

    selected_key = normalize_worksheet_key(selected_sheet)

    return df[
        df["worksheet_name"]
        .astype(str)
        .map(normalize_worksheet_key)
        == selected_key
    ].copy()

def filter_by_driver(df, selected_driver):
    if (
        df is None
        or df.empty
        or selected_driver == "Mind"
    ):
        return df

    if "driver_name" not in df.columns:
        return df.iloc[0:0].copy()

    selected_key = normalize_person_key(selected_driver)

    return df[
        df["driver_name"]
        .astype(str)
        .map(normalize_person_key)
        == selected_key
    ].copy()


def month_start_from_date(value):
    return value.replace(day=1)


def render_admin_document_manager(courier_id, courier_name):
    with st.expander("A futárnak feltöltött dokumentumok kezelése", expanded=False):
        try:
            documents = read_peopleforce_documents_for_courier(courier_id)
        except Exception as exc:
            st.error(f"A dokumentumlista nem tölthető be: {exc}")
            return
        if documents.empty:
            st.info("Ehhez a futárhoz még nincs feltöltött dokumentum.")
            return
        type_labels = {
            "settlement": "Elszámolás", "tig": "TIG", "invoice": "Számla",
            "complaint_response": "Reklamációs válasz",
        }
        st.caption(f"{len(documents)} feltöltött dokumentum – {courier_name}")
        overview = documents.copy()
        overview["Típus"] = overview["document_type"].map(
            lambda value: type_labels.get(str(value), str(value))
        )
        overview["Hónap"] = overview["document_month"].astype(str).str[:7]
        st.dataframe(
            overview[["Hónap", "Típus", "title", "file_name", "uploaded_at"]].rename(
                columns={"title": "Megnevezés", "file_name": "Fájl", "uploaded_at": "Feltöltve"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        rows_by_id = {
            str(row.get("id")): row for _, row in documents.iterrows()
        }
        selected_id = st.selectbox(
            "Kezelendő dokumentum",
            list(rows_by_id),
            format_func=lambda value: (
                f"{str(rows_by_id[value].get('document_month', ''))[:7]} | "
                f"{type_labels.get(str(rows_by_id[value].get('document_type', '')), str(rows_by_id[value].get('document_type', '')))} | "
                f"{rows_by_id[value].get('title') or rows_by_id[value].get('file_name')}"
            ),
        )
        document = rows_by_id[selected_id]
        file_name = str(document.get("file_name") or "dokumentum")
        title = str(document.get("title") or file_name)
        note = str(document.get("note") or "")
        try:
            content = read_peopleforce_document_content(selected_id)
            file_bytes = decode_document_content(content.get("file_content_base64"))
        except Exception:
            file_bytes = b""
        if file_bytes:
            st.download_button(
                "Kiválasztott dokumentum letöltése",
                data=file_bytes,
                file_name=file_name,
                mime=str(document.get("mime_type") or "application/octet-stream"),
            )
        with st.form(f"admin_document_edit_{selected_id}"):
            edited_title = st.text_input("Megnevezés", value=title)
            edited_note = st.text_area("Megjegyzés", value=note, height=70)
            if st.form_submit_button("Adatok mentése"):
                update_peopleforce_document(selected_id, title=edited_title, note=edited_note)
                st.success("A dokumentum adatai frissültek.")
                st.rerun()
        confirm_delete = st.checkbox(
            "Törlés megerősítése",
            key=f"admin_document_delete_confirm_{selected_id}",
        )
        if st.button("Dokumentum törlése", disabled=not confirm_delete):
            delete_peopleforce_document(selected_id)
            st.success("A dokumentum törölve.")
            st.rerun()



def _invoice_status_headers(service_role_key):
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


@st.cache_data(show_spinner=False, ttl=120)
def read_sent_invoice_driver_names(document_month):
    """
    A peopleforce_documents táblából kiolvassa azoknak a futároknak a nevét,
    akiknek az adott hónapra már invoice típusú dokumentum lett feltöltve.
    """
    supabase_url, service_role_key = get_supabase_config()

    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beállítás."
        )

    month_value = month_start_from_date(document_month).isoformat()
    response = requests.get(
        f"{supabase_url.rstrip('/')}/rest/v1/peopleforce_documents",
        headers=_invoice_status_headers(service_role_key),
        params={
            "select": "courier_name,courier_id,document_month,document_type,uploaded_at",
            "document_type": "eq.invoice",
            "document_month": f"eq.{month_value}",
            "order": "courier_name.asc,uploaded_at.desc",
            "limit": "10000",
        },
        timeout=60,
    )

    raise_for_supabase_error(response)
    rows = response.json() or []

    result = {}
    for row in rows:
        name = str(row.get("courier_name") or "").strip()
        if not name:
            continue

        key = normalize_name(name)
        if key not in result:
            result[key] = {
                "courier_name": name,
                "courier_id": row.get("courier_id"),
                "uploaded_at": row.get("uploaded_at"),
            }

    return result


def render_invoice_delivery_status(route_driver_names, document_month):
    """
    Megmutatja, hány egyedi futár szerepel az elszámolási route adatokban,
    hányuknak lett számla kiküldve, és kik hiányoznak még.
    """
    clean_names = sorted(
        {
            str(name or "").strip()
            for name in route_driver_names
            if str(name or "").strip()
        },
        key=lambda value: value.casefold(),
    )

    route_name_lookup = {
        normalize_name(name): name
        for name in clean_names
    }

    try:
        sent_lookup = read_sent_invoice_driver_names(document_month)
    except Exception as exc:
        st.warning(
            f"A számlakiküldési állapot nem tölthető be: {exc}"
        )
        return

    sent_names = sorted(
        [
            route_name_lookup[key]
            for key in route_name_lookup
            if key in sent_lookup
        ],
        key=lambda value: value.casefold(),
    )

    missing_names = sorted(
        [
            route_name_lookup[key]
            for key in route_name_lookup
            if key not in sent_lookup
        ],
        key=lambda value: value.casefold(),
    )

    total_count = len(clean_names)
    sent_count = len(sent_names)
    missing_count = len(missing_names)
    completion = (sent_count / total_count * 100) if total_count else 0

    st.subheader("Számlakiküldési visszajelző")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Route adatokban szereplő futárok", total_count)
    metric2.metric("Számla kiküldve", sent_count)
    metric3.metric("Még nincs kiküldve", missing_count)
    metric4.metric("Készültség", f"{completion:.0f}%")

    if total_count:
        st.progress(min(max(completion / 100, 0), 1))

    if missing_names:
        st.warning(
            f"{missing_count} futárnak még nincs invoice dokumentuma "
            f"a(z) {month_start_from_date(document_month):%Y-%m} hónapra."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Még nincs számla kiküldve": missing_names,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success(
            "Minden, az elszámolási route adatokban szereplő futárnak "
            "ki lett küldve a számlája."
        )

    with st.expander("Kiküldött számlák listája", expanded=False):
        if sent_names:
            sent_rows = []
            for name in sent_names:
                details = sent_lookup.get(normalize_name(name), {})
                sent_rows.append(
                    {
                        "Futár": name,
                        "Courier ID": details.get("courier_id"),
                        "Feltöltve": details.get("uploaded_at"),
                    }
                )

            st.dataframe(
                pd.DataFrame(sent_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Ehhez a hónaphoz még nincs kiküldött számla.")



def show_invoice_summary_page():
    st.title("Elszamolas")
    st.caption(
        "Forras: JITT invoice workbook. A BUD1_JIT es BUD2_JIT fulek 23. sortol indulnak, "
        "ezekbol keszul a futar szintu osszesito."
    )

    today = date.today()
    default_start = today.replace(day=1)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.5])
    start_date = col1.date_input(
        "Kezdo datum",
        value=default_start,
        key="invoice_start_date",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today,
        key="invoice_end_date",
    )
    selected_sheet = col3.selectbox(
        "Raktar ful",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="invoice_sheet_filter",
    )

    try:
        data = read_invoice_data(
            start_date,
            end_date,
        )

        final_df_debug = data.get("final", pd.DataFrame())

        st.warning(
            f"""
    DEBUG

    Route sorok: {len(final_df_debug)}

    Egyedi futárok: {final_df_debug['driver_name'].nunique() if not final_df_debug.empty else 0}

    Munkalapok: {sorted(final_df_debug['worksheet_name'].dropna().unique().tolist()) if 'worksheet_name' in final_df_debug.columns else []}

    Dátumok: {final_df_debug['work_date'].min() if 'work_date' in final_df_debug.columns and not final_df_debug.empty else '-'} → {final_df_debug['work_date'].max() if 'work_date' in final_df_debug.columns and not final_df_debug.empty else '-'}
    """
        )

    except Exception as exc:
        st.error(
            f"Elszamolas DB olvasasi hiba: {exc}"
        )
        return

    final_df = data["final"]
    summary_df = data["summary"]
    bonus_df = data["bonus"]
    penalty_df = data["penalties"]
    manual_df = data["manual"]
    atm_balance_df = data.get("atm_balance", pd.DataFrame())
    customer_rating_df = data.get("customer_rating", pd.DataFrame())
    monthly_adjustment_df = data.get("monthly_adjustments", pd.DataFrame())
    day_rates_df = data.get("day_rates", pd.DataFrame())
    raw_route_df = data.get("routes", pd.DataFrame())

    final_df = filter_by_worksheet(
        final_df,
        selected_sheet,
    )

    all_filtered_final_df = final_df.copy()

    # A futárlista alapja kizárólag a route-adat.
    # A külső forrásokból csak a teljesebb megjelenítési nevet vesszük át.
    driver_names_by_key = {}

    if (
        all_filtered_final_df is not None
        and not all_filtered_final_df.empty
        and "driver_name" in all_filtered_final_df.columns
    ):
        for value in (
            all_filtered_final_df["driver_name"]
            .dropna()
            .astype(str)
        ):
            name = value.strip()
            key = normalize_person_key(name)

            if name and key:
                driver_names_by_key[key] = name


    def enrich_driver_names(frame):
        if (
            frame is None
            or frame.empty
            or "driver_name" not in frame.columns
        ):
            return

        for value in (
            frame["driver_name"]
            .dropna()
            .astype(str)
        ):
            name = value.strip()
            key = normalize_person_key(name)

            if not name or key not in driver_names_by_key:
                continue

            current_name = driver_names_by_key[key]

            if len(name) > len(current_name):
                driver_names_by_key[key] = name


    enrich_driver_names(bonus_df)
    enrich_driver_names(penalty_df)
    enrich_driver_names(manual_df)
    enrich_driver_names(atm_balance_df)
    enrich_driver_names(customer_rating_df)
    enrich_driver_names(monthly_adjustment_df)

    drivers = sorted(
        driver_names_by_key.values(),
        key=normalize_person_key,
    )

    render_invoice_delivery_status(
        drivers,
        start_date,
    )

    selected_driver = col4.selectbox(
        "Futar",
        ["Mind"] + drivers,
        key="invoice_driver_filter",
    )

    final_df = filter_by_driver(
        final_df,
        selected_driver,
    )
    bonus_df = filter_by_driver(
        bonus_df,
        selected_driver,
    )
    penalty_df = filter_by_driver(
        penalty_df,
        selected_driver,
    )
    manual_df = filter_by_driver(
        manual_df,
        selected_driver,
    )
    atm_balance_df = filter_by_driver(
        atm_balance_df,
        selected_driver,
    )
    customer_rating_df = filter_by_driver(
        customer_rating_df,
        selected_driver,
    )
    monthly_adjustment_df = filter_by_driver(
        monthly_adjustment_df,
        selected_driver,
    )

    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df=bonus_df,
        penalty_df=penalty_df,
        manual_df=manual_df,
        day_rates_df=day_rates_df,
        raw_route_df=raw_route_df,
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=atm_balance_df,
        customer_rating_df=customer_rating_df,
        monthly_adjustment_df=monthly_adjustment_df,
        period_start=start_date,
    )

    if driver_summary.empty:
        st.warning(
            "Nincs elszamolasi route adat erre a szuresre."
        )
        return

    total_orders = int(pd.to_numeric(driver_summary["orders"], errors="coerce").fillna(0).sum())
    total_routes_source = (
        "route_count" if "route_count" in driver_summary.columns else "routes"
    )
    total_routes = int(
        pd.to_numeric(
            driver_summary[total_routes_source],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )
    total_delay = pd.to_numeric(driver_summary["delay_bonus_huf"], errors="coerce").fillna(0).sum()
    total_compliance = pd.to_numeric(driver_summary["compliance_bonus_huf"], errors="coerce").fillna(0).sum()
    total_adjustment = pd.to_numeric(driver_summary["adjustment_huf"], errors="coerce").fillna(0).sum()
    total_manual = pd.to_numeric(driver_summary.get("manual_payable_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_loyalty = pd.to_numeric(driver_summary.get("loyalty_bonus_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_instructor = pd.to_numeric(driver_summary.get("instructor_fee_huf", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_customer_rating = pd.to_numeric(
        driver_summary.get("customer_rating_bonus_huf", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()
    total_monthly_effect = pd.to_numeric(
        driver_summary.get("monthly_adjustment_effect_huf", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()
    total_atm_effect = pd.to_numeric(
        driver_summary.get("atm_effect_huf", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()
    total_payable = pd.to_numeric(driver_summary["payable_total_huf"], errors="coerce").fillna(0).sum()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Rendelés", total_orders)
    m2.metric("Kör", total_routes)
    m3.metric("Késedelmi díj", format_huf(total_delay))
    m4.metric("Túramegfelelés", format_huf(total_compliance))
    m5.metric("Ügyfélértékelési bónusz", format_huf(total_customer_rating))
    m6.metric("Fizetendő", format_huf(total_payable))

    m7, m8, m9, m10, m11, m12 = st.columns(6)
    m7.metric("Levonás / plusz", format_huf(total_adjustment))
    m8.metric("Havi bónusz/málusz hatás", format_huf(total_monthly_effect))
    m9.metric("ATM hatás", format_huf(total_atm_effect))
    m10.metric("Lojalitás", format_huf(total_loyalty))
    m11.metric("Oktatói díj", format_huf(total_instructor))
    m12.metric("Manuális", format_huf(total_manual - total_loyalty - total_instructor))

    st.subheader("Futar osszesito")
    display_summary = build_display_driver_summary(driver_summary)
    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True,
    )
    if data.get("loyalty_error"):
        st.warning(
            "A lojalitási Google-törzsadat jelenleg nem olvasható. "
            "A Google service-account kulcsot frissíteni kell; ez a Túramegfelelés számítását nem érinti."
        )
    with st.expander("Lojalitási bónusz ellenőrzése", expanded=False):
        loyalty_columns = [
            "driver_name", "loyalty_previous_normal_routes", "loyalty_current_normal_routes",
            "loyalty_rate_huf", "loyalty_bonus_huf", "loyalty_status",
        ]
        st.dataframe(
            driver_summary[[column for column in loyalty_columns if column in driver_summary.columns]],
            use_container_width=True,
            hide_index=True,
        )

    if selected_driver != "Mind" and not driver_summary.empty:
        selected_row = driver_summary.iloc[0]
        courier_id, courier_name = resolve_courier_identity(selected_row, selected_driver)
        if courier_id:
            try:
                complaints = read_peopleforce_complaints(
                    courier_id,
                    month_start_from_date(start_date),
                    "settlement",
                )
            except Exception:
                complaints = pd.DataFrame()
            open_complaints = complaints[
                complaints.get("status", pd.Series(dtype=str)).astype(str).str.lower() != "resolved"
            ] if not complaints.empty else complaints
            if not open_complaints.empty:
                st.error("A futár reklamációt küldött ehhez az elszámoláshoz. Az elszámolás visszanyitva.")
                for _, complaint in open_complaints.iterrows():
                    with st.container(border=True):
                        st.write(complaint.get("message", ""))
                        st.caption(f"Beküldte: {complaint.get('created_by', courier_name)} | {complaint.get('created_at', '')}")
                        complaint_id = complaint.get("id")
                        with st.form(f"reply_invoice_complaint_{complaint_id}"):
                            response_message = st.text_area(
                                "Válasz a futárnak",
                                placeholder="Írd le, mit javítottál vagy miért helyes az elszámolás.",
                                height=100,
                            )
                            send_response = st.form_submit_button(
                                "Válasz küldése és reklamáció lezárása"
                            )
                        if send_response:
                            if not str(response_message or "").strip():
                                st.warning("Írj választ a futárnak.")
                            else:
                                respond_to_peopleforce_complaint(
                                    complaint_id,
                                    response_message,
                                    str(st.session_state.get("username", "admin")),
                                    courier_id=courier_id,
                                    courier_name=courier_name,
                                    document_type="settlement",
                                    document_month=month_start_from_date(start_date),
                                )
                                st.success("A választ elküldtük a futárnak, a reklamáció lezárva.")
                                st.rerun()
                        if st.button(
                            "Lezárás válasz nélkül",
                            key=f"resolve_invoice_complaint_{complaint_id}",
                        ):
                            update_peopleforce_complaint_status(complaint_id, "resolved")
                            st.success("A reklamáció lezárva.")
                            st.rerun()
            render_admin_document_manager(courier_id, courier_name)

    pdf_title = (
        f"JITT elszamolas {start_date.isoformat()} - {end_date.isoformat()}"
    )
    try:
        filename_driver = "osszes"
        if selected_driver != "Mind" and not driver_summary.empty:
            selected_row = driver_summary.iloc[0]
            courier_id, _courier_name = resolve_courier_identity(
                selected_row,
                selected_driver,
            )
            driver_slug = slugify_filename(selected_driver)
            filename_driver = (
                f"{courier_id}_{driver_slug}" if courier_id else driver_slug
            )
        pdf_bytes = build_invoice_pdf_bytes(
            driver_summary,
            final_df,
            pdf_title,
        )
        st.download_button(
            "PDF generalasa",
            data=pdf_bytes,
            file_name=f"jitt_elszamolas_{filename_driver}_{start_date.isoformat()}_{end_date.isoformat()}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        if selected_driver != "Mind":
            selected_row = driver_summary.iloc[0]
            courier_id, courier_name = resolve_courier_identity(
                selected_row,
                selected_driver,
            )

            if st.button(
                "Elszámolás feltöltése a futár profiljába",
                use_container_width=True,
                key="invoice_send_to_courier_card",
            ):
                if not courier_id:
                    st.warning(
                        "Ehhez a futárhoz nincs courier ID, így nem tudom a profiljába küldeni."
                    )
                else:
                    document_month = month_start_from_date(start_date)
                    file_name = (
                        f"jitt_elszamolas_{courier_id}_{slugify_filename(courier_name)}_"
                        f"{start_date.isoformat()}_{end_date.isoformat()}.pdf"
                    )
                    upload_peopleforce_document_bytes(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        document_type="settlement",
                        document_month=document_month,
                        title=f"Elszamolas - {start_date.isoformat()} - {end_date.isoformat()}",
                        note="Admin által profilba feltöltött elszámolás.",
                        file_name=file_name,
                        mime_type="application/pdf",
                        file_bytes=pdf_bytes,
                        uploaded_by=str(st.session_state.get("username", "admin")),
                    )
                    upsert_peopleforce_card_status(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        action_key="settlement",
                        document_month=document_month,
                        status="open",
                        status_note="Elszámolás feltöltve, futár visszajelzésére vár.",
                        updated_by=str(st.session_state.get("username", "admin")),
                    )
                    st.cache_data.clear()
                    st.success("Az elszámolás bekerült a futár profiljába.")
                    st.rerun()

            st.divider()
            st.subheader("TIG generálása")
            st.caption(
                "Az admin itt állítja elő a teljesítési igazolást, majd közvetlenül a futár profiljába töltheti."
            )

            master_row = {}
            try:
                master_df = read_courier_master()
                if not master_df.empty and "courier_id" in master_df.columns:
                    matches = master_df[
                        master_df["courier_id"].astype(str).str.strip() == str(courier_id).strip()
                    ]
                    if not matches.empty:
                        master_row = matches.iloc[0].to_dict()
            except Exception:
                master_row = {}

            def first_value(*names, default=""):
                for name in names:
                    value = master_row.get(name, selected_row.get(name, ""))
                    if value is not None and str(value).strip():
                        return str(value).strip()
                return default

            default_company_name = first_value(
                "company_name",
                default=courier_name,
            )

            default_address = first_value(
                "company_address",
                "courier_address",
                "address",
                "billing_address",
                "invoice_address",
            )

            default_tax_number = first_value(
                "tax_number",
                "tax_id",
                "vat_number",
                "adoszam",
            )

            default_bank_account = first_value(
                "bank_account_number",
            )

            default_billing_email = first_value(
                "billing_email",
                "email",
            )
            try:
                default_transfer_amount = int(
                    round(float(selected_row.get("payable_total_huf", 0) or 0))
                )
            except (TypeError, ValueError):
                default_transfer_amount = 0
            

            with st.form(f"tig_generator_{courier_id}_{start_date.isoformat()}"):
                tig_col1, tig_col2 = st.columns(2)
                tig_seller_name = tig_col1.text_input(
                    "Szolgáltató / vállalkozás neve",
                    value=default_company_name,
                )
                tig_tax_number = tig_col2.text_input(
                    "Adószám",
                    value=default_tax_number,
                )
                tig_address = st.text_input(
                    "Vállalkozás székhelye",
                    value=default_address,
                )
                details_col1, details_col2 = st.columns(2)
                details_col1.text_input(
                    "Bankszámlaszám",
                    value=default_bank_account,
                    disabled=True,
                )
                details_col2.text_input(
                    "Számlázási e-mail",
                    value=default_billing_email,
                    disabled=True,
                )
                amount_col1, amount_col2 = st.columns(2)
                tig_transfer_amount = amount_col1.number_input(
                    "Átutalásos számla összege (Ft)",
                    min_value=0,
                    value=max(default_transfer_amount, 0),
                    step=100,
                )
                tig_cash_amount = amount_col2.number_input(
                    "Készpénzes számla összege (Ft, ha szükséges)",
                    min_value=0,
                    value=0,
                    step=100,
                )
                generate_tig = st.form_submit_button(
                    "TIG előállítása",
                    use_container_width=True,
                )

            tig_state_key = f"generated_tig_{courier_id}_{start_date.isoformat()}"
            if generate_tig:
                if not courier_id:
                    st.warning("Ehhez a futárhoz nincs courier ID.")
                elif not str(tig_seller_name).strip():
                    st.warning("Add meg a szolgáltató nevét.")
                elif not str(tig_tax_number).strip():
                    st.warning("Add meg az adószámot.")
                elif not str(tig_address).strip():
                    st.warning("Add meg a szolgáltató címét.")
                else:
                    document_month = month_start_from_date(start_date)
                    generated_tig_bytes = build_tig_pdf_bytes(
                        courier_name=str(tig_seller_name).strip(),
                        courier_address=str(tig_address).strip(),
                        courier_tax_number=str(tig_tax_number).strip(),
                        courier_id=courier_id,
                        document_month=document_month,
                        transfer_amount_huf=tig_transfer_amount,
                        cash_amount_huf=tig_cash_amount,
                    )
                    st.session_state[tig_state_key] = {
                        "bytes": generated_tig_bytes,
                        "seller_name": str(tig_seller_name).strip(),
                        "month": document_month,
                    }
                    st.success(
                        "A TIG elkészült. Ellenőrizd a PDF-et, majd nyomd meg a TIG feltöltése gombot."
                    )

            generated_tig = st.session_state.get(tig_state_key)
            if generated_tig:
                document_month = generated_tig["month"]
                tig_file_name = (
                    f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_"
                    f"{document_month.strftime('%Y-%m')}.pdf"
                )
                st.download_button(
                    "TIG letöltése ellenőrzéshez",
                    data=generated_tig["bytes"],
                    file_name=tig_file_name,
                    mime="application/pdf",
                    use_container_width=True,
                )
                if st.button(
                    "TIG feltöltése a futár profiljába",
                    use_container_width=True,
                    key=f"tig_send_to_courier_card_{courier_id}_{start_date.isoformat()}",
                ):
                    upload_peopleforce_document_bytes(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        document_type="tig",
                        document_month=document_month,
                        title=f"TIG - {document_month.strftime('%Y-%m')}",
                        note="Admin által generált teljesítési igazolás.",
                        file_name=tig_file_name,
                        mime_type="application/pdf",
                        file_bytes=generated_tig["bytes"],
                        uploaded_by=str(st.session_state.get("username", "admin")),
                    )
                    upsert_peopleforce_card_status(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        action_key="tig",
                        document_month=document_month,
                        status="open",
                        status_note="TIG elkészült, futár elfogadására vár.",
                        updated_by=str(st.session_state.get("username", "admin")),
                    )
                    st.session_state.pop(tig_state_key, None)
                    st.cache_data.clear()
                    st.success("A generált TIG bekerült a futár profiljába.")
                    st.rerun()

        else:
            st.caption(
                "Elszámolás vagy TIG feltöltéséhez válassz ki egy konkrét futárt."
            )
    except Exception as exc:
        st.info(
            f"PDF generalas nem elerheto: {exc}"
        )

    with st.expander("Manualis elszamolasi tetelek", expanded=False):
        st.caption(
            "Ide kerulnek azok az osszegek, amelyek meg nincsenek a DB-ben automatikus forrasbol: "
            "celtartalek, uzemanyag, karokozas, KP vagy egyeb plusz/levonas."
        )
        form_col1, form_col2, form_col3 = st.columns([1, 1, 1])
        manual_date = form_col1.date_input(
            "Tetel datuma",
            value=end_date,
            key="invoice_manual_date",
        )
        manual_sheet = form_col2.selectbox(
            "Raktar ful",
            ["BUD1_JIT", "BUD2_JIT"],
            key="invoice_manual_sheet",
        )
        manual_driver_options = drivers or sorted(
            value
            for value in final_df.get("driver_name", pd.Series(dtype=str)).dropna().astype(str).unique()
            if value.strip()
        )
        manual_driver = form_col3.selectbox(
            "Futar",
            manual_driver_options,
            key="invoice_manual_driver",
        )
        form_col4, form_col5 = st.columns([1, 1])
        manual_type = form_col4.selectbox(
            "Tetel tipusa",
            list(MANUAL_ITEM_TYPES.keys()),
            format_func=lambda value: MANUAL_ITEM_TYPES[value],
            key="invoice_manual_type",
        )
        manual_amount = form_col5.number_input(
            "Osszeg Ft",
            value=0,
            step=500,
            key="invoice_manual_amount",
        )
        manual_note = st.text_input(
            "Megjegyzes",
            key="invoice_manual_note",
        )
        if st.button("Manualis tetel mentese", use_container_width=True):
            if not manual_driver:
                st.warning("Valassz futart a manualis tetelhez.")
            else:
                try:
                    table_name = create_manual_invoice_item(
                        manual_date,
                        manual_sheet,
                        manual_driver,
                        manual_type,
                        manual_amount,
                        manual_note,
                        created_by=str(st.session_state.get("username", "admin")),
                    )
                    st.cache_data.clear()
                    st.success(f"Manualis tetel mentve: {table_name}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Manualis tetel mentese sikertelen: {exc}")

        st.dataframe(
            build_display_manual_items(manual_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Alapdij matrix"):
        st.dataframe(
            build_display_base_rate_matrix(),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Felso osszesito tabla"):
        st.dataframe(
            build_display_summary(summary_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Route reszletek - nyers ellenorzes"):
        st.caption("A PDF-be ezt mar nem generaljuk, csak oldali ellenorzesre marad.")
        st.dataframe(
            build_display_routes(final_df),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Bonusz es penalty forras"):
        c1, c2 = st.columns(2)
        c1.write("Bonus routes")
        c1.dataframe(
            bonus_df,
            use_container_width=True,
            hide_index=True,
        )
        c2.write("Penalties")
        c2.dataframe(
            penalty_df,
            use_container_width=True,
            hide_index=True,
        )