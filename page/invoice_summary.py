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
from resources.email_sender import send_login_credentials
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
from resources.users import load_users, reset_password_and_send

from resources.peopleforce_documents import (
    decode_document_content,
    delete_peopleforce_document,
    read_peopleforce_complaints,
    read_peopleforce_complaints_for_month,
    read_peopleforce_documents_for_courier,
    read_peopleforce_document_content,
    read_peopleforce_card_statuses_for_month,
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


def normalize_courier_id(value):
    """A Courier ID egységes szöveges alakja: pl. 7644.0 -> 7644."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""

    try:
        numeric = float(text.replace(",", "."))
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass

    return text


def resolve_courier_identity(selected_row, selected_driver):
    courier_id = normalize_courier_id(selected_row.get("courier_id", ""))
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
    courier_id = normalize_courier_id(match.get("courier_id", ""))
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
def read_sent_invoice_driver_names(document_month, document_type="settlement"):
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
            "document_type": f"eq.{document_type}",
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


def build_invoice_feedback_context():
    master_by_name = {}
    master_by_id = {}
    try:
        master_df = read_courier_master()
    except Exception:
        master_df = pd.DataFrame()

    if not master_df.empty:
        for _, master_row in master_df.iterrows():
            row = master_row.to_dict()
            name = str(
                row.get("courier_name")
                or row.get("name")
                or row.get("driver_name")
                or ""
            ).strip()
            courier_id = normalize_courier_id(row.get("courier_id") or row.get("driver_id"))
            if name:
                master_by_name.setdefault(normalize_name(name), row)
            if courier_id:
                master_by_id.setdefault(courier_id, row)

    users_by_name = {}
    users_by_id = {}
    try:
        users_data = load_users()
    except Exception:
        users_data = {"users": []}

    for user_row in users_data.get("users", []):
        name = str(user_row.get("username") or user_row.get("name") or "").strip()
        courier_id = normalize_courier_id(user_row.get("courierId") or user_row.get("courier_id"))
        if name:
            users_by_name.setdefault(normalize_name(name), user_row)
        if courier_id:
            users_by_id.setdefault(courier_id, user_row)

    return master_by_name, master_by_id, users_by_name, users_by_id


def first_invoice_contact_value(row, *keys):
    for key in keys:
        value = row.get(key, "") if isinstance(row, dict) else ""
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def user_has_logged_in(user_row):
    if not isinstance(user_row, dict):
        return False
    for key in ["lastLoginAt", "last_login_at", "lastLogin", "last_login"]:
        if str(user_row.get(key) or "").strip():
            return True
    return bool(str(user_row.get("token") or "").strip())


def render_invoice_delivery_status(route_driver_names, document_month):
    """
    Admin visszajelzo: hol tart a futar az elszamolasi folyamatban.
    Piros sor: segitseget ker / nyitott reklamacio.
    Zold sor: elfogadta / lezart allapotban van.
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
    month_start = month_start_from_date(document_month)
    master_by_name, master_by_id, users_by_name, users_by_id = build_invoice_feedback_context()

    try:
        sent_lookup = read_sent_invoice_driver_names(month_start, "settlement")
    except Exception as exc:
        st.warning(
            f"A futar visszajelzo dokumentumallapota nem toltheto be: {exc}"
        )
        return

    try:
        status_df = read_peopleforce_card_statuses_for_month(
            month_start,
            action_key="settlement",
        )
    except Exception as exc:
        st.warning(f"A futar visszajelzo statuszai nem tolthet?k be: {exc}")
        status_df = pd.DataFrame()

    try:
        complaints_df = read_peopleforce_complaints_for_month(
            month_start,
            document_type="settlement",
        )
    except Exception as exc:
        st.warning(f"A reklamacios adatok nem tolthet?k be: {exc}")
        complaints_df = pd.DataFrame()

    def row_name_key(row):
        return normalize_name(row.get("courier_name", ""))

    def row_id_key(row):
        courier_id = str(row.get("courier_id") or "").strip()
        return courier_id if courier_id and courier_id.lower() != "nan" else ""

    status_by_name = {}
    status_by_id = {}
    if not status_df.empty:
        for _, status_row in status_df.iterrows():
            name_key = row_name_key(status_row)
            id_key = row_id_key(status_row)
            if name_key and name_key not in status_by_name:
                status_by_name[name_key] = status_row
            if id_key and id_key not in status_by_id:
                status_by_id[id_key] = status_row

    open_complaints_by_name = {}
    open_complaints_by_id = {}
    if not complaints_df.empty:
        status_series = complaints_df.get("status", pd.Series(dtype=str))
        open_complaints = complaints_df[
            status_series.astype(str).str.strip().str.lower().ne("resolved")
        ].copy()
        for _, complaint_row in open_complaints.iterrows():
            name_key = row_name_key(complaint_row)
            id_key = row_id_key(complaint_row)
            if name_key:
                open_complaints_by_name.setdefault(name_key, []).append(complaint_row)
            if id_key:
                open_complaints_by_id.setdefault(id_key, []).append(complaint_row)

    for details in sent_lookup.values():
        name = str(details.get("courier_name") or "").strip()
        if name:
            route_name_lookup.setdefault(normalize_name(name), name)
    if not status_df.empty:
        for _, status_row in status_df.iterrows():
            name = str(status_row.get("courier_name") or "").strip()
            if name:
                route_name_lookup.setdefault(normalize_name(name), name)
    if not complaints_df.empty:
        for _, complaint_row in complaints_df.iterrows():
            name = str(complaint_row.get("courier_name") or "").strip()
            if name:
                route_name_lookup.setdefault(normalize_name(name), name)

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

    total_count = len(route_name_lookup)
    sent_count = len(sent_names)
    missing_count = len(missing_names)
    completion = (sent_count / total_count * 100) if total_count else 0

    feedback_rows = []
    for name_key, name in sorted(route_name_lookup.items(), key=lambda item: item[1].casefold()):
        sent_details = sent_lookup.get(name_key, {})
        courier_id = normalize_courier_id(sent_details.get("courier_id"))
        master_row = master_by_id.get(courier_id) if courier_id else None
        if master_row is None:
            master_row = master_by_name.get(name_key, {})
        if not courier_id and master_row:
            courier_id = normalize_courier_id(master_row.get("courier_id") or master_row.get("driver_id"))

        user_row = users_by_id.get(courier_id) if courier_id else None
        if user_row is None:
            user_row = users_by_name.get(name_key, {})

        contact_email = first_invoice_contact_value(
            master_row,
            "billing_email",
            "invoice_email",
            "email",
            "contact_email",
        ) or first_invoice_contact_value(user_row, "email", "contact_email")
        username = first_invoice_contact_value(user_row, "username", "name")
        has_logged_in = user_has_logged_in(user_row)

        status_row = status_by_id.get(courier_id) if courier_id else None
        if status_row is None:
            status_row = status_by_name.get(name_key)
        if status_row is not None and not courier_id:
            courier_id = row_id_key(status_row)

        complaint_rows = open_complaints_by_id.get(courier_id, []) if courier_id else []
        if not complaint_rows:
            complaint_rows = open_complaints_by_name.get(name_key, [])

        status_value = ""
        status_note = ""
        updated_at = ""
        if status_row is not None:
            status_value = str(status_row.get("status") or "").strip().lower()
            status_note = str(status_row.get("status_note") or "").strip()
            updated_at = str(status_row.get("updated_at") or "").strip()

        uploaded_at = str(sent_details.get("uploaded_at") or "").strip()
        has_uploaded_document = bool(uploaded_at)

        if complaint_rows:
            row_state = "help"
            lamp = "Piros"
            step = "Segitseget ker"
            courier_feedback = "Nyitott reklamacio"
            note = str(complaint_rows[0].get("message") or status_note or "").strip()
        elif status_value == "done":
            row_state = "done"
            lamp = "Zold"
            if "utal" in status_note.lower():
                step = "Sikeres elutalas"
            else:
                step = "Elfogadva"
            courier_feedback = "Rendben"
            note = status_note
        elif has_uploaded_document or status_value == "open":
            row_state = "waiting"
            lamp = "Sarga"
            step = "Futarnal"
            courier_feedback = "Visszajelzesre var"
            note = status_note or "Elszamolas feltoltve."
        else:
            row_state = "missing"
            lamp = "Szurke"
            step = "Meg nincs kikuldve"
            courier_feedback = "-"
            note = ""

        feedback_rows.append(
            {
                "Lampa": lamp,
                "Futar": name,
                "Courier ID": courier_id or "-",
                "Hol tart": step,
                "Futar visszajelzes": courier_feedback,
                "Feltoltve": uploaded_at or "-",
                "Utolso frissites": updated_at or uploaded_at or "-",
                "E-mail": contact_email or "-",
                "Belepett": "Igen" if has_logged_in else "Nem",
                "Megjegyzes": note or "-",
                "_state": row_state,
                "_email": contact_email,
                "_username": username,
                "_has_logged_in": has_logged_in,
            }
        )

    feedback_df = pd.DataFrame(feedback_rows)
    state_series = feedback_df.get("_state", pd.Series(dtype=str))
    done_count = int((state_series == "done").sum()) if not feedback_df.empty else 0
    help_count = int((state_series == "help").sum()) if not feedback_df.empty else 0
    waiting_count = int((state_series == "waiting").sum()) if not feedback_df.empty else 0

    st.subheader("Futar visszajelzo")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Futar osszesen", total_count)
    metric2.metric("Kikuldve", sent_count)
    metric3.metric("Segitseget ker", help_count)
    metric4.metric("Elfogadva / zold", done_count)

    sub1, sub2 = st.columns(2)
    sub1.metric("Visszajelzesre var", waiting_count)
    sub2.metric("Meg nincs kikuldve", missing_count)

    if total_count:
        st.progress(min(max(completion / 100, 0), 1))

    def style_feedback_rows(row):
        state = row.get("_state")
        if state == "help":
            return ["background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"] * len(row)
        if state == "done":
            return ["background-color: #dcfce7; color: #14532d; font-weight: 700;"] * len(row)
        if state == "waiting":
            return ["background-color: #fef9c3; color: #713f12;"] * len(row)
        return ["background-color: #f8fafc; color: #475569;"] * len(row)

    if not feedback_df.empty:
        display_feedback_df = feedback_df.drop(
            columns=["_state", "_email", "_username", "_has_logged_in"],
            errors="ignore",
        )

        def style_display_feedback_rows(row):
            state = feedback_df.loc[row.name, "_state"]
            if state == "help":
                return ["background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"] * len(row)
            if state == "done":
                return ["background-color: #dcfce7; color: #14532d; font-weight: 700;"] * len(row)
            if state == "waiting":
                return ["background-color: #fef9c3; color: #713f12;"] * len(row)
            return ["background-color: #f8fafc; color: #475569;"] * len(row)

        st.dataframe(
            display_feedback_df.style.apply(style_display_feedback_rows, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    if missing_names:
        st.warning(
            f"{missing_count} futarnak meg nincs elszamolas dokumentuma "
            f"a(z) {month_start:%Y-%m} honapra."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Meg nincs elszamolas kikuldve": missing_names,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success(
            "Minden, az elszamolasi route adatokban szereplo futarnak "
            "ki lett kuldve az elszamolasa."
        )

    if not feedback_df.empty:
        resend_candidates = feedback_df[
            feedback_df["_state"].isin(["missing", "waiting"])
            & feedback_df["_username"].astype(str).str.strip().ne("")
            & feedback_df["_email"].astype(str).str.contains("@", na=False)
            & (~feedback_df["_has_logged_in"].astype(bool))
        ].copy()
        with st.expander("Belepesi adatok ujrakuldese azoknak, akik meg nem leptek be", expanded=False):
            if resend_candidates.empty:
                st.info("Nincs olyan futar, akinek van e-mail cime, felhasznaloja, es meg nem lepett be.")
            else:
                st.caption("Uj jelszot generalunk, es elkuldjuk a felhasznalonevet, jelszot, valamint hogy elkeszult az elszamolasa.")
                st.dataframe(
                    resend_candidates[["Futar", "Courier ID", "E-mail", "Hol tart"]],
                    use_container_width=True,
                    hide_index=True,
                )
                confirm_resend = st.checkbox(
                    f"Meger?sitem {len(resend_candidates)} futar belepesi adatainak ujrakuldeset.",
                    key=f"invoice_resend_login_confirm_{month_start.isoformat()}",
                )
                if st.button(
                    "Belepesi e-mail ujrakuldese",
                    disabled=not confirm_resend,
                    use_container_width=True,
                    key=f"invoice_resend_login_button_{month_start.isoformat()}",
                ):
                    sent_rows = []
                    for _, candidate in resend_candidates.iterrows():
                        try:
                            reset_password_and_send(
                                str(candidate["_username"]).strip(),
                                str(candidate["_email"]).strip(),
                                send_login_credentials,
                            )
                            sent_rows.append({"Futar": candidate["Futar"], "Allapot": "Elkuldve", "Hiba": ""})
                        except Exception as exc:
                            sent_rows.append({"Futar": candidate["Futar"], "Allapot": "Hiba", "Hiba": str(exc)})
                    st.dataframe(pd.DataFrame(sent_rows), use_container_width=True, hide_index=True)

    with st.expander("Kikuldott elszamolasok listaja", expanded=False):
        if sent_names:
            sent_rows = []
            for name in sent_names:
                details = sent_lookup.get(normalize_name(name), {})
                sent_rows.append(
                    {
                        "Futar": name,
                        "Courier ID": details.get("courier_id"),
                        "Feltoltve": details.get("uploaded_at"),
                    }
                )

            st.dataframe(
                pd.DataFrame(sent_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Ehhez a honaphoz meg nincs kikuldott elszamolas.")

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
        if selected_driver == "Mind":
            st.divider()
            st.subheader("Tömeges elszámolás-feltöltés raktár szerint")
            st.caption(
                "Válassz egy raktárt. A rendszer csak az adott raktár futárainak "
                "készít külön PDF-et, majd feltölti azokat a profiljukba."
            )

            bulk_source_rows = driver_summary.reset_index(drop=True)
            warehouse_options = sorted(
                {
                    str(value).strip()
                    for value in bulk_source_rows.get(
                        "worksheet_name",
                        pd.Series(dtype=str),
                    ).dropna()
                    if str(value).strip()
                }
            )

            if not warehouse_options:
                st.info("A jelenlegi időszakban nincs tömegesen generálható raktár.")
                bulk_rows = bulk_source_rows.iloc[0:0].copy()
                bulk_sheet = ""
            else:
                default_bulk_sheet = (
                    selected_sheet
                    if selected_sheet in warehouse_options
                    else warehouse_options[0]
                )
                bulk_sheet = st.selectbox(
                    "Tömeges generálás raktára",
                    warehouse_options,
                    index=warehouse_options.index(default_bulk_sheet),
                    key=(
                        f"invoice_bulk_warehouse_{start_date.isoformat()}_"
                        f"{end_date.isoformat()}"
                    ),
                )
                bulk_rows = bulk_source_rows[
                    bulk_source_rows["worksheet_name"].astype(str).str.strip()
                    == str(bulk_sheet).strip()
                ].reset_index(drop=True)

            bulk_upload_count = len(bulk_rows)
            st.info(
                f"Kiválasztott raktár: {bulk_sheet or '-'} | "
                f"Generálandó elszámolások: {bulk_upload_count}"
            )

            skip_existing = st.checkbox(
                "A már feltöltött elszámolások kihagyása",
                value=True,
                key=(
                    f"invoice_bulk_skip_existing_{start_date.isoformat()}_"
                    f"{end_date.isoformat()}_{bulk_sheet}"
                ),
            )
            bulk_confirm = st.checkbox(
                (
                    f"Megerősítem a(z) {bulk_sheet or '-'} raktár "
                    f"{bulk_upload_count} futár elszámolásának feltöltését."
                ),
                key=(
                    f"invoice_bulk_upload_confirm_{start_date.isoformat()}_"
                    f"{end_date.isoformat()}_{bulk_sheet}"
                ),
            )

            if st.button(
                f"{bulk_sheet or 'Kiválasztott raktár'} elszámolásainak feltöltése",
                type="primary",
                use_container_width=True,
                disabled=(not bulk_confirm or bulk_rows.empty),
                key=(
                    f"invoice_bulk_upload_{start_date.isoformat()}_"
                    f"{end_date.isoformat()}_{bulk_sheet}"
                ),
            ):
                document_month = month_start_from_date(start_date)
                uploaded_count = 0
                skipped_count = 0
                failed_rows = []
                progress = st.progress(0)
                status_box = st.empty()

                existing_lookup = {}
                if skip_existing:
                    try:
                        existing_lookup = read_sent_invoice_driver_names(document_month)
                    except Exception as exc:
                        st.warning(
                            "A már feltöltött dokumentumok ellenőrzése nem sikerült; "
                            f"a feldolgozás folytatódik: {exc}"
                        )

                total_bulk_rows = len(bulk_rows)
                for row_index, bulk_row in bulk_rows.iterrows():
                    bulk_driver_name = str(
                        bulk_row.get("driver_name") or ""
                    ).strip()
                    bulk_courier_id, bulk_courier_name = resolve_courier_identity(
                        bulk_row,
                        bulk_driver_name,
                    )
                    bulk_courier_id = normalize_courier_id(bulk_courier_id)

                    status_box.write(
                        f"Feldolgozás: {bulk_driver_name or 'Ismeretlen futár'} "
                        f"({row_index + 1}/{total_bulk_rows})"
                    )

                    if not bulk_courier_id:
                        skipped_count += 1
                        failed_rows.append(
                            {
                                "Futár": bulk_driver_name,
                                "Állapot": "Kihagyva",
                                "Hiba": "Nincs courier ID.",
                            }
                        )
                        progress.progress((row_index + 1) / total_bulk_rows)
                        continue

                    if (
                        skip_existing
                        and normalize_name(bulk_courier_name) in existing_lookup
                    ):
                        skipped_count += 1
                        failed_rows.append(
                            {
                                "Futár": bulk_driver_name,
                                "Állapot": "Kihagyva",
                                "Hiba": "Erre a hónapra már van feltöltött elszámolás.",
                            }
                        )
                        progress.progress((row_index + 1) / total_bulk_rows)
                        continue

                    try:
                        single_summary = bulk_rows.iloc[[row_index]].copy()
                        warehouse_routes = filter_by_worksheet(
                            all_filtered_final_df,
                            bulk_sheet,
                        )
                        single_routes = filter_by_driver(
                            warehouse_routes,
                            bulk_driver_name,
                        )

                        single_pdf_bytes = build_invoice_pdf_bytes(
                            single_summary,
                            single_routes,
                            (
                                f"JITT elszamolas {start_date.isoformat()} - "
                                f"{end_date.isoformat()}"
                            ),
                        )
                        single_file_name = (
                            f"jitt_elszamolas_{bulk_courier_id}_"
                            f"{slugify_filename(bulk_courier_name)}_"
                            f"{start_date.isoformat()}_{end_date.isoformat()}.pdf"
                        )

                        upload_peopleforce_document_bytes(
                            courier_id=bulk_courier_id,
                            courier_name=bulk_courier_name,
                            document_type="settlement",
                            document_month=document_month,
                            title=(
                                f"Elszamolas - {start_date.isoformat()} - "
                                f"{end_date.isoformat()}"
                            ),
                            note="Admin által tömegesen feltöltött elszámolás.",
                            file_name=single_file_name,
                            mime_type="application/pdf",
                            file_bytes=single_pdf_bytes,
                            uploaded_by=str(
                                st.session_state.get("username", "admin")
                            ),
                        )
                        upsert_peopleforce_card_status(
                            courier_id=bulk_courier_id,
                            courier_name=bulk_courier_name,
                            action_key="settlement",
                            document_month=document_month,
                            status="open",
                            status_note=(
                                "Elszámolás tömegesen feltöltve, "
                                "futár visszajelzésére vár."
                            ),
                            updated_by=str(
                                st.session_state.get("username", "admin")
                            ),
                        )
                        uploaded_count += 1
                    except Exception as exc:
                        failed_rows.append(
                            {
                                "Futár": bulk_driver_name,
                                "Állapot": "Hiba",
                                "Hiba": str(exc),
                            }
                        )

                    progress.progress((row_index + 1) / total_bulk_rows)

                status_box.empty()
                st.cache_data.clear()
                error_count = sum(
                    row["Állapot"] == "Hiba" for row in failed_rows
                )
                st.success(
                    f"Tömeges feltöltés kész. Feltöltve: {uploaded_count}, "
                    f"kihagyva: {skipped_count}, hibás: {error_count}."
                )
                if failed_rows:
                    st.dataframe(
                        pd.DataFrame(failed_rows),
                        use_container_width=True,
                        hide_index=True,
                    )


            with st.expander("Tomeges TIG generalas es feltoltes", expanded=False):
                st.caption("A jelenlegi szuresben szereplo futaroknak keszit TIG-et, majd feltolti a Kiflis kartyara.")
                tig_source_rows = driver_summary.reset_index(drop=True)
                tig_skip_existing = st.checkbox(
                    "A mar feltoltott TIG-ek kihagyasa",
                    value=True,
                    key=f"tig_bulk_skip_existing_{start_date.isoformat()}_{end_date.isoformat()}",
                )
                tig_confirm = st.checkbox(
                    f"Meger?sitem {len(tig_source_rows)} TIG tomeges generalasat.",
                    key=f"tig_bulk_confirm_{start_date.isoformat()}_{end_date.isoformat()}",
                )
                if st.button(
                    "TIG-ek tomeges generalasa es feltoltese",
                    disabled=(not tig_confirm or tig_source_rows.empty),
                    use_container_width=True,
                    key=f"tig_bulk_upload_{start_date.isoformat()}_{end_date.isoformat()}",
                ):
                    document_month = month_start_from_date(start_date)
                    existing_tig_lookup = {}
                    if tig_skip_existing:
                        try:
                            existing_tig_lookup = read_sent_invoice_driver_names(document_month, "tig")
                        except Exception as exc:
                            st.warning(f"A mar feltoltott TIG-ek ellenorzese nem sikerult, folytatom: {exc}")

                    try:
                        tig_master_df = read_courier_master()
                    except Exception:
                        tig_master_df = pd.DataFrame()
                    tig_master_by_id = {}
                    if not tig_master_df.empty and "courier_id" in tig_master_df.columns:
                        for _, master_item in tig_master_df.iterrows():
                            master_id = normalize_courier_id(master_item.get("courier_id"))
                            if master_id:
                                tig_master_by_id[master_id] = master_item.to_dict()

                    uploaded_count = 0
                    skipped_count = 0
                    result_rows = []
                    progress = st.progress(0)
                    total_tig_rows = len(tig_source_rows)
                    for row_index, tig_row in tig_source_rows.iterrows():
                        driver_name = str(tig_row.get("driver_name") or "").strip()
                        tig_courier_id, tig_courier_name = resolve_courier_identity(tig_row, driver_name)
                        tig_courier_id = normalize_courier_id(tig_courier_id)
                        if not tig_courier_id:
                            skipped_count += 1
                            result_rows.append({"Futar": driver_name, "Allapot": "Kihagyva", "Hiba": "Nincs courier ID."})
                            progress.progress((row_index + 1) / total_tig_rows)
                            continue
                        if tig_skip_existing and normalize_name(tig_courier_name) in existing_tig_lookup:
                            skipped_count += 1
                            result_rows.append({"Futar": tig_courier_name, "Allapot": "Kihagyva", "Hiba": "Erre a honapra mar van TIG."})
                            progress.progress((row_index + 1) / total_tig_rows)
                            continue

                        master_row = tig_master_by_id.get(tig_courier_id, {})
                        seller_name = first_invoice_contact_value(master_row, "company_name") or tig_courier_name
                        seller_address = first_invoice_contact_value(master_row, "company_address", "courier_address", "address", "billing_address", "invoice_address")
                        tax_number = first_invoice_contact_value(master_row, "tax_number", "tax_id", "vat_number", "adoszam")
                        if not seller_address or not tax_number:
                            skipped_count += 1
                            result_rows.append({"Futar": tig_courier_name, "Allapot": "Kihagyva", "Hiba": "Hianyzik a vallalkozas cime vagy adoszama."})
                            progress.progress((row_index + 1) / total_tig_rows)
                            continue

                        try:
                            transfer_amount = int(round(float(tig_row.get("payable_total_huf", 0) or 0)))
                            tig_pdf_bytes = build_tig_pdf_bytes(
                                courier_name=seller_name,
                                courier_address=seller_address,
                                courier_tax_number=tax_number,
                                courier_id=tig_courier_id,
                                document_month=document_month,
                                transfer_amount_huf=transfer_amount,
                                cash_amount_huf=0,
                            )
                            tig_file_name = f"jitt_tig_{tig_courier_id}_{slugify_filename(tig_courier_name)}_{document_month.strftime('%Y-%m')}.pdf"
                            upload_peopleforce_document_bytes(
                                courier_id=tig_courier_id,
                                courier_name=tig_courier_name,
                                document_type="tig",
                                document_month=document_month,
                                title=f"TIG - {document_month.strftime('%Y-%m')}",
                                note="Admin altal tomegesen generalt teljesitesi igazolas.",
                                file_name=tig_file_name,
                                mime_type="application/pdf",
                                file_bytes=tig_pdf_bytes,
                                uploaded_by=str(st.session_state.get("username", "admin")),
                            )
                            upsert_peopleforce_card_status(
                                courier_id=tig_courier_id,
                                courier_name=tig_courier_name,
                                action_key="tig",
                                document_month=document_month,
                                status="open",
                                status_note="TIG tomegesen feltoltve, futar elfogadasara var.",
                                updated_by=str(st.session_state.get("username", "admin")),
                            )
                            uploaded_count += 1
                            result_rows.append({"Futar": tig_courier_name, "Allapot": "Feltoltve", "Hiba": ""})
                        except Exception as exc:
                            result_rows.append({"Futar": tig_courier_name, "Allapot": "Hiba", "Hiba": str(exc)})
                        progress.progress((row_index + 1) / total_tig_rows)

                    st.cache_data.clear()
                    st.success(f"TIG tomeges feltoltes kesz. Feltoltve: {uploaded_count}, kihagyva: {skipped_count}.")
                    st.dataframe(pd.DataFrame(result_rows), use_container_width=True, hide_index=True)

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