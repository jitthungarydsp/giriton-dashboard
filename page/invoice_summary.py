from datetime import date, datetime, timedelta
import base64
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

from resources.courier_master_db import (
    apply_billing_staging_updates,
    build_billing_staging_update_preview,
    read_courier_master,
)
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
    read_target_reserve_for_courier_ids,
)
from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)

from resources.peopleforce_documents import (
    decode_document_content,
    delete_peopleforce_document,
    read_peopleforce_complaints,
    read_peopleforce_complaints_for_month,
    read_peopleforce_card_statuses_for_month,
    read_peopleforce_documents_for_month,
    read_peopleforce_documents_for_courier,
    read_peopleforce_document_content,
    respond_to_peopleforce_complaint,
    update_peopleforce_document,
    update_peopleforce_complaint_status,
    upload_peopleforce_document_bytes,
    upsert_peopleforce_card_status,
)
from resources.users import load_users as load_system_users


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


def prefixed_document_filename(prefix_kind, courier_id, courier_name, document_month, base_file_name):
    month_value = month_start_from_date(document_month)
    prefix = (
        f"{prefix_kind}_{datetime.now().strftime('%H%M%S')}_"
        f"{normalize_courier_id(courier_id)}_"
        f"{slugify_filename(courier_name)}_"
        f"{month_value.strftime('%m')}_{month_value.strftime('%d')}_"
    )
    return prefix + str(base_file_name or "").strip()


def reopen_peopleforce_acceptance_after_complaint(
    *,
    courier_id,
    courier_name,
    document_type,
    document_month,
    updated_by,
):
    action_key = {"settlement": "settlement", "tig": "tig"}.get(
        str(document_type or "").strip()
    )
    if not action_key:
        return
    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key=action_key,
        document_month=document_month,
        status="open",
        status_note="Reklamacio lezarva, futar elfogadasara var.",
        updated_by=updated_by,
    )


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
        story.extend([Spacer(1, 5 * mm), Paragraph("KÉSZPÉNZES SZÁMLA (Csak ha a levonás miatt szükséges!)", heading)])
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


def resolve_settlement_identity(selected_row, selected_driver):
    courier_id = normalize_courier_id(selected_row.get("courier_id", ""))
    courier_name = str(
        selected_row.get("driver_name", selected_driver) or selected_driver
    ).strip()
    return courier_id, courier_name


def build_courier_master_lookup(master_df):
    lookup = {}
    if master_df is None or master_df.empty or "courier_id" not in master_df.columns:
        return lookup

    for _, master_row in master_df.iterrows():
        master_data = master_row.to_dict()
        master_id = normalize_courier_id(master_data.get("courier_id", ""))
        if master_id:
            lookup[master_id] = master_data

    return lookup


def read_courier_master_row_by_id(courier_id):
    clean_id = normalize_courier_id(courier_id)
    if not clean_id:
        return {}

    try:
        master_df = read_courier_master()
    except Exception:
        return {}

    return build_courier_master_lookup(master_df).get(clean_id, {})


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


def previous_month_period(reference_date=None):
    reference_date = reference_date or date.today()
    current_month_start = reference_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return previous_month_start, previous_month_end


def render_admin_document_manager(courier_id, courier_name, key_prefix="admin_document_manager"):
    clean_key_prefix = f"{key_prefix}_{normalize_courier_id(courier_id)}"
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
            key=f"{clean_key_prefix}_selected_document",
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
                key=f"{clean_key_prefix}_download_{selected_id}",
            )
        with st.form(f"{clean_key_prefix}_edit_{selected_id}"):
            edited_title = st.text_input("Megnevezés", value=title)
            edited_note = st.text_area("Megjegyzés", value=note, height=70)
            if st.form_submit_button("Adatok mentése"):
                update_peopleforce_document(selected_id, title=edited_title, note=edited_note)
                st.success("A dokumentum adatai frissültek.")
                st.rerun()
        confirm_delete = st.checkbox(
            "Torles megerositese",
            key=f"{clean_key_prefix}_delete_confirm_{selected_id}",
        )
        if st.button(
            "Dokumentum torlese",
            disabled=not confirm_delete,
            key=f"{clean_key_prefix}_delete_{selected_id}",
        ):
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


def _latest_by_courier_and_type(documents):
    latest = {}
    if documents is None or documents.empty:
        return latest

    for _, row in documents.iterrows():
        courier_id = normalize_courier_id(row.get("courier_id", ""))
        document_type = str(row.get("document_type") or "").strip()
        if not courier_id or not document_type:
            continue
        key = (courier_id, document_type)
        if key not in latest:
            latest[key] = row.to_dict()

    return latest


def _latest_status_by_courier_and_action(statuses):
    latest = {}
    if statuses is None or statuses.empty:
        return latest

    for _, row in statuses.iterrows():
        courier_id = normalize_courier_id(row.get("courier_id", ""))
        action_key = str(row.get("action_key") or "").strip()
        if not courier_id or not action_key:
            continue
        key = (courier_id, action_key)
        if key not in latest:
            latest[key] = row.to_dict()

    return latest


def _complaints_by_courier(complaints):
    grouped = {}
    if complaints is None or complaints.empty:
        return grouped

    for _, row in complaints.iterrows():
        courier_id = normalize_courier_id(row.get("courier_id", ""))
        if not courier_id:
            continue
        grouped.setdefault(courier_id, []).append(row.to_dict())

    return grouped


def _is_done(status_row):
    return str((status_row or {}).get("status") or "").strip().lower() == "done"


def _current_username(default="admin"):
    user = st.session_state.get("user") or {}
    return str(
        user.get("username")
        or st.session_state.get("username")
        or default
    ).strip()


def _current_role(default="user"):
    user = st.session_state.get("user") or {}
    return str(user.get("role") or default).strip().lower()


def _feedback_assignee_options():
    current_role = _current_role()
    current_username = _current_username("")
    options = []
    try:
        users = load_system_users().get("users", [])
    except Exception:
        users = []

    allowed_roles = {"admin", "trainer"}
    for user in users:
        if not user.get("active", True):
            continue
        username = str(user.get("username") or "").strip()
        role = str(user.get("role") or "").strip().lower()
        if not username or role not in allowed_roles:
            continue
        if current_role == "trainer" and username != current_username:
            continue
        options.append(username)

    if current_role == "admin" and current_username and current_username not in options:
        options.append(current_username)
    if current_role == "trainer" and current_username and current_username not in options:
        options.append(current_username)

    return ["Nincs kijelölve"] + sorted(set(options), key=lambda value: value.casefold())


def _feedback_owner_from_status(status_row):
    return str((status_row or {}).get("status_note") or "").strip()


def _ignore_complaints_from_status(status_row):
    return _is_done(status_row)


def _settlement_feedback_priority(row):
    def first_value(candidates, default=""):
        for column in candidates:
            if column in row:
                return row.get(column)
        return default

    values = [
        str(first_value(["Elszámolás", "ElszĂˇmolĂˇs"]) or ""),
        str(row.get("TIG") or ""),
        str(first_value(["Számlafeltöltés", "SzĂˇmlafeltĂ¶ltĂ©s"]) or ""),
    ]
    open_complaints = int(
        first_value(["Nyitott reklamáció", "Nyitott reklamĂˇciĂł"], 0)
        or 0
    )
    ignore_complaints = str(first_value(["Reklamáció blokkolás", "Reklamacio blokkolas"]) or "") == "Nem blokkol"
    if ignore_complaints:
        open_complaints = 0
    if open_complaints > 0 or any("Reklam" in value for value in values):
        return 0
    if any("VĂˇr" in value or "ZĂˇrolva" in value for value in values):
        return 1
    return 2


def _settlement_feedback_row_style(row):
    priority = row.get("_priority")
    if priority == 0:
        return [
            "background-color: #fde2e2; color: #7f1d1d; font-weight: 600"
            for _ in row
        ]
    if priority == 1:
        return [
            "background-color: #fff1f2; color: #9f1239"
            for _ in row
        ]
    return ["" for _ in row]


def _first_existing_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None


def vat_status_from_tax_number(tax_number):
    text = str(tax_number or "").strip()
    if not text:
        return "Nincs adat"

    match = re.search(r"\b\d{8}[-\s]?([0-9])[-\s]?\d{2}\b", text)
    if not match:
        return "Nincs adat"

    vat_code = match.group(1)
    if vat_code == "1":
        return "Nem áfás"
    if vat_code in {"2", "3", "4", "5"}:
        return "Áfás"
    return "Nincs adat"


def _has_open_complaint(rows, document_type):
    for row in rows or []:
        if str(row.get("document_type") or "") != document_type:
            continue
        if str(row.get("status") or "").strip().lower() != "resolved":
            return True
    return False


def _courier_document_response_status(done, open_complaint, has_document):
    if done and open_complaint:
        return "Elfogadta + reklamalt"
    if done:
        return "Elfogadta"
    if open_complaint:
        return "Reklamalt"
    if has_document:
        return "Meg nem valaszolt"
    return "Nincs dokumentum"


def render_settlement_feedback_overview(
    driver_summary,
    document_month,
    selected_driver_filter="Mind",
):
    if driver_summary is None or driver_summary.empty:
        return

    document_month = month_start_from_date(document_month)

    try:
        documents = read_peopleforce_documents_for_month(document_month)
        statuses = read_peopleforce_card_statuses_for_month(document_month)
        complaints = read_peopleforce_complaints_for_month(document_month)
    except Exception as exc:
        st.warning(f"A havi elszámolási visszajelző nem tölthető be: {exc}")
        return

    latest_docs = _latest_by_courier_and_type(documents)
    latest_statuses = _latest_status_by_courier_and_action(statuses)
    complaint_lookup = _complaints_by_courier(complaints)
    master_by_id = {}
    master_by_name = {}
    try:
        master_df = read_courier_master()
        if master_df is not None and not master_df.empty:
            for _, master_row in master_df.iterrows():
                master_data = master_row.to_dict()
                master_id = normalize_courier_id(master_data.get("courier_id", ""))
                master_name = normalize_name(master_data.get("courier_name", ""))
                if master_id:
                    master_by_id[master_id] = master_data
                if master_name:
                    master_by_name[master_name] = master_data
    except Exception:
        master_by_id = {}
        master_by_name = {}

    courier_rows = []
    seen_couriers = set()
    for _, row in driver_summary.iterrows():
        fallback_name = str(row.get("driver_name") or "").strip()
        courier_id, courier_name = resolve_settlement_identity(row, fallback_name)
        if not courier_id:
            continue
        if courier_id in seen_couriers:
            continue
        seen_couriers.add(courier_id)

        courier_complaints = complaint_lookup.get(courier_id, [])
        courier_response_documents = [
            document
            for document in documents.to_dict("records")
            if str(document.get("courier_id") or "").strip() == str(courier_id)
            and str(document.get("document_type") or "").strip() == "complaint_response"
        ] if documents is not None and not documents.empty else []
        settlement_doc = latest_docs.get((courier_id, "settlement"))
        tig_doc = latest_docs.get((courier_id, "tig"))
        invoice_doc = latest_docs.get((courier_id, "invoice"))
        settlement_done = _is_done(latest_statuses.get((courier_id, "settlement")))
        tig_done = _is_done(latest_statuses.get((courier_id, "tig")))
        invoice_check_done = _is_done(latest_statuses.get((courier_id, "invoice_check")))
        invoice_submit_done = _is_done(latest_statuses.get((courier_id, "invoice_submit")))
        invoice_payment_done = _is_done(latest_statuses.get((courier_id, "invoice_payment")))
        feedback_owner = _feedback_owner_from_status(
            latest_statuses.get((courier_id, "feedback_owner"))
        )
        ignore_complaints_for_billing = _ignore_complaints_from_status(
            latest_statuses.get((courier_id, "ignore_complaints_for_billing"))
        )
        settlement_complaint = _has_open_complaint(courier_complaints, "settlement")
        tig_complaint = _has_open_complaint(courier_complaints, "tig")
        settlement_response_status = _courier_document_response_status(
            settlement_done,
            settlement_complaint,
            bool(settlement_doc),
        )
        tig_response_status = _courier_document_response_status(
            tig_done,
            tig_complaint,
            bool(tig_doc),
        )
        blocking_settlement_complaint = settlement_complaint and not ignore_complaints_for_billing
        blocking_tig_complaint = tig_complaint and not ignore_complaints_for_billing

        if blocking_settlement_complaint:
            settlement_status = "Reklamáció"
        elif settlement_done:
            settlement_status = "Elfogadva"
        elif settlement_doc:
            settlement_status = "Vár futárra"
        else:
            settlement_status = "Vár dokumentumra"

        if blocking_tig_complaint:
            tig_status = "Reklamáció"
        elif tig_done:
            tig_status = "Elfogadva"
        elif tig_doc and settlement_done:
            tig_status = "Vár futárra"
        elif tig_doc:
            tig_status = "TIG kész, elszámolásra vár"
        elif settlement_done:
            tig_status = "Vár TIG-re"
        else:
            tig_status = "Zárolva"

        if invoice_payment_done:
            invoice_status = "Kifizetve"
        elif invoice_submit_done or invoice_doc:
            invoice_status = "Feltöltve"
        elif invoice_check_done:
            invoice_status = "Ellenőrizve"
        elif tig_done:
            invoice_status = "Vár számlára"
        else:
            invoice_status = "Zárolva"

        open_complaint_count = sum(
            1
            for item in courier_complaints
            if str(item.get("status") or "").strip().lower() != "resolved"
        )
        master_row = master_by_id.get(courier_id) or master_by_name.get(
            normalize_name(courier_name)
        ) or {}
        vat_status = vat_status_from_tax_number(
            master_row.get("tax_number")
            or row.get("tax_number", "")
            or row.get("vat_number", "")
            or row.get("adoszam", "")
        )

        courier_rows.append(
            {
                "courier_id": courier_id,
                "courier_name": courier_name,
                "settlement_doc": settlement_doc,
                "tig_doc": tig_doc,
                "invoice_doc": invoice_doc,
                "complaints": courier_complaints,
                "response_documents": courier_response_documents,
                "feedback_owner": feedback_owner,
                "ignore_complaints_for_billing": ignore_complaints_for_billing,
                "display": {
                    "Futár": courier_name,
                    "courier_id": courier_id,
                    "ÁFA státusz": vat_status,
                    "Felelos": feedback_owner or "Nincs kijelolve",
                    "Reklamáció blokkolás": "Nem blokkol" if ignore_complaints_for_billing else "Blokkol",
                    "Elszámolás": settlement_status,
                    "Elszámolás visszajelzés": settlement_response_status,
                    "TIG": tig_status,
                    "TIG visszajelzés": tig_response_status,
                    "Számlafeltöltés": invoice_status,
                    "Kifizetés": "Lezárva" if invoice_payment_done else ("Vár adminra" if invoice_doc else "Nincs számla"),
                    "Számla": (invoice_doc or {}).get("file_name", ""),
                    "Nyitott reklamáció": open_complaint_count,
                },
            }
        )

    if not courier_rows:
        st.info("A havi visszajelzőhöz nem találtam futár azonosítókat.")
        return

    st.subheader("Elszámolási visszajelző")
    st.caption(
        "Havi admin nézet: elszámolás elfogadás, TIG elfogadás és számlafeltöltés állapota futáronként."
    )

    display_df = pd.DataFrame([row["display"] for row in courier_rows])
    display_df["_priority"] = display_df.apply(
        _settlement_feedback_priority,
        axis=1,
    )
    complaint_column = _first_existing_column(
        display_df,
        ["Nyitott reklamáció", "Nyitott reklamĂˇciĂł"],
    )
    courier_column = _first_existing_column(
        display_df,
        ["Futár", "FutĂˇr"],
    )
    sort_columns = ["_priority"]
    sort_ascending = [True]
    if complaint_column:
        sort_columns.append(complaint_column)
        sort_ascending.append(False)
    if courier_column:
        sort_columns.append(courier_column)
        sort_ascending.append(True)
    display_df = display_df.sort_values(
        sort_columns,
        ascending=sort_ascending,
        kind="stable",
    )
    metric1, metric2, metric3, metric4, metric5 = st.columns(5)
    metric1.metric("Futár", len(display_df))
    metric2.metric(
        "Elszámolás elfogadva",
        int(display_df["Elszámolás visszajelzés"].astype(str).str.contains("Elfogadta").sum()),
    )
    metric3.metric(
        "TIG elfogadva",
        int(display_df["TIG visszajelzés"].astype(str).str.contains("Elfogadta").sum()),
    )
    metric4.metric("Számla feltöltve", int(display_df["Számlafeltöltés"].isin(["Feltöltve", "Kifizetve"]).sum()))
    metric5.metric("Kifizetve / lezárva", int((display_df["Kifizetés"] == "Lezárva").sum()))

    st.dataframe(
        display_df.style.apply(
            _settlement_feedback_row_style,
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "_priority": None,
        },
    )

    rows_by_key = {
        f"{row['courier_id']}|{row['courier_name']}": row
        for row in courier_rows
    }
    selected_filter_key = normalize_person_key(selected_driver_filter)
    matched_key = ""
    if selected_driver_filter != "Mind" and selected_filter_key:
        for key, row in rows_by_key.items():
            if normalize_person_key(row["courier_name"]) == selected_filter_key:
                matched_key = key
                break

    if matched_key:
        selected_key = matched_key
        st.info(f"Kivalasztott futar adatlapja: {rows_by_key[selected_key]['courier_name']}")
    else:
        selected_key = st.selectbox(
            "Futar kezelese",
            list(rows_by_key),
            format_func=lambda key: rows_by_key[key]["courier_name"],
            key=f"settlement_feedback_driver_{document_month.isoformat()}",
        )
    selected = rows_by_key[selected_key]

    with st.container(border=True):
        st.markdown(f"**{selected['courier_name']} #{selected['courier_id']}**")
        if selected_driver_filter == "Mind":
            if st.button(
                "Egyedi elszamolas, szamla es TIG muveletek megnyitasa ennel a futarnal",
                key=f"open_invoice_tools_{selected['courier_id']}_{document_month.isoformat()}",
                use_container_width=True,
            ):
                st.session_state["invoice_driver_filter_pending"] = selected["courier_name"]
                st.rerun()
        assignee_options = _feedback_assignee_options()
        current_owner = selected.get("feedback_owner") or "Nincs kijelolve"
        if current_owner not in assignee_options:
            assignee_options.append(current_owner)
        current_owner_index = assignee_options.index(current_owner)
        owner_col, save_owner_col = st.columns([3, 1])
        selected_owner = owner_col.selectbox(
            "Elszamolasi felelos",
            assignee_options,
            index=current_owner_index,
            key=f"feedback_owner_{selected['courier_id']}_{document_month.isoformat()}",
            disabled=_current_role() not in {"admin", "trainer"},
        )
        if save_owner_col.button(
            "Felelos mentese",
            key=f"save_feedback_owner_{selected['courier_id']}_{document_month.isoformat()}",
            use_container_width=True,
            disabled=_current_role() not in {"admin", "trainer"},
        ):
            owner_value = "" if selected_owner == "Nincs kijelolve" else selected_owner
            upsert_peopleforce_card_status(
                courier_id=selected["courier_id"],
                courier_name=selected["courier_name"],
                action_key="feedback_owner",
                document_month=document_month,
                status="open",
                status_note=owner_value,
                updated_by=_current_username(),
            )
            st.success("A felelos mentve.")
            st.rerun()

        ignore_current = bool(selected.get("ignore_complaints_for_billing"))
        ignore_value = st.checkbox(
            "Számlázási folyamatnál a reklamáció ne blokkolja az elszámolás/TIG elfogadást",
            value=ignore_current,
            key=f"ignore_complaints_for_billing_{selected['courier_id']}_{document_month.isoformat()}",
            disabled=_current_role() not in {"admin", "trainer"},
        )
        if ignore_value != ignore_current:
            upsert_peopleforce_card_status(
                courier_id=selected["courier_id"],
                courier_name=selected["courier_name"],
                action_key="ignore_complaints_for_billing",
                document_month=document_month,
                status="done" if ignore_value else "open",
                status_note=(
                    "A nyitott reklamáció nem blokkolja a számlázási folyamatot."
                    if ignore_value
                    else "A nyitott reklamáció blokkolja az elfogadási folyamatot."
                ),
                updated_by=_current_username(),
            )
            st.success("A reklamáció blokkolási beállítás mentve.")
            st.rerun()
        doc_cols = st.columns(3)
        for col, label, doc_key in [
            (doc_cols[0], "Elszámolás", "settlement_doc"),
            (doc_cols[1], "TIG", "tig_doc"),
            (doc_cols[2], "Számla", "invoice_doc"),
        ]:
            document = selected.get(doc_key)
            if not document:
                col.info(f"Nincs {label.lower()} dokumentum.")
                continue
            try:
                content = read_peopleforce_document_content(document.get("id"))
                file_bytes = decode_document_content(content.get("file_content_base64"))
            except Exception:
                file_bytes = b""
            col.caption(document.get("file_name") or label)
            if file_bytes:
                col.download_button(
                    f"{label} megtekintése",
                    data=file_bytes,
                    file_name=str(document.get("file_name") or f"{label}.pdf"),
                    mime=str(document.get("mime_type") or "application/octet-stream"),
                    key=f"download_{doc_key}_{document.get('id')}",
                    use_container_width=True,
                )

        invoice_document = selected.get("invoice_doc")
        if invoice_document:
            try:
                invoice_content = read_peopleforce_document_content(invoice_document.get("id"))
                invoice_bytes = decode_document_content(invoice_content.get("file_content_base64"))
            except Exception:
                invoice_bytes = b""
            invoice_mime = str(invoice_document.get("mime_type") or "").lower()
            if invoice_bytes and "pdf" in invoice_mime:
                encoded_invoice = base64.b64encode(invoice_bytes).decode("ascii")
                st.markdown(
                    f'<iframe src="data:application/pdf;base64,{encoded_invoice}" '
                    'width="100%" height="720" style="border:1px solid #ddd;border-radius:8px;"></iframe>',
                    unsafe_allow_html=True,
                )
            elif invoice_bytes and invoice_mime.startswith("image/"):
                st.image(invoice_bytes, caption=str(invoice_document.get("file_name") or "Számla"))

        payment_done = str(selected.get("display", {}).get("Kifizetés") or "") == "Lezárva"
        with st.container(border=True):
            st.markdown("**Számla admin elfogadás / kifizetés**")
            if payment_done:
                st.success("A számla elfogadva, a kifizetés megtörtént. A hónap lezárva.")
            elif not selected.get("invoice_doc"):
                st.info("A kifizetés csak feltöltött számla után zárható le.")
            else:
                st.warning("A számla feltöltve, admin elfogadásra és kifizetésre vár.")
                payment_note = st.text_input(
                    "Kifizetés megjegyzés / tranzakció",
                    key=f"invoice_payment_note_{selected['courier_id']}_{document_month.isoformat()}",
                )
                if st.button(
                    "Számla elfogadva, kifizetés megtörtént - hónap lezárása",
                    key=f"mark_invoice_paid_{selected['courier_id']}_{document_month.isoformat()}",
                    use_container_width=True,
                    disabled=_current_role() not in {"admin", "trainer"},
                ):
                    close_note = payment_note or "Számla elfogadva, kifizetés megtörtént."
                    upsert_peopleforce_card_status(
                        courier_id=selected["courier_id"],
                        courier_name=selected["courier_name"],
                        action_key="invoice_payment",
                        document_month=document_month,
                        status="done",
                        status_note=close_note,
                        updated_by=_current_username(),
                    )
                    upsert_peopleforce_card_status(
                        courier_id=selected["courier_id"],
                        courier_name=selected["courier_name"],
                        action_key="my_invoices",
                        document_month=document_month,
                        status="done",
                        status_note=close_note,
                        updated_by=_current_username(),
                    )
                    st.success("A számla kifizetése rögzítve, a hónap lezárva.")
                    st.rerun()

        active_complaints = [
            item
            for item in selected.get("complaints", [])
            if str(item.get("status") or "").strip().lower() != "resolved"
        ]
        resolved_complaints = [
            item
            for item in selected.get("complaints", [])
            if str(item.get("status") or "").strip().lower() == "resolved"
        ]
        if not active_complaints:
            st.success("Nincs nyitott reklamáció ennél a futárnál.")
        else:
            st.warning(f"{len(active_complaints)} nyitott reklamáció vár válaszra.")
            type_labels = {"settlement": "Elszámolás", "tig": "TIG"}
            for complaint in active_complaints:
                complaint_id = complaint.get("id")
                document_type = str(complaint.get("document_type") or "")
                with st.form(f"feedback_complaint_reply_{complaint_id}"):
                    st.write(
                        f"{type_labels.get(document_type, document_type)} reklamáció: "
                        f"{complaint.get('message', '')}"
                    )
                    response_message = st.text_area(
                        "Válasz a futárnak",
                        placeholder="Írd le röviden a javítást vagy a döntést.",
                        height=90,
                        key=f"feedback_response_text_{complaint_id}",
                    )
                    send_response = st.form_submit_button("Válasz küldése és lezárás")
                if send_response:
                    if not str(response_message or "").strip():
                        st.warning("A válasz szövege kötelező.")
                    else:
                        respond_to_peopleforce_complaint(
                            complaint_id,
                            response_message,
                            str(st.session_state.get("username", "admin")),
                            courier_id=selected["courier_id"],
                            courier_name=selected["courier_name"],
                            document_type=document_type,
                            document_month=document_month,
                        )
                        reopen_peopleforce_acceptance_after_complaint(
                            courier_id=selected["courier_id"],
                            courier_name=selected["courier_name"],
                            document_type=document_type,
                            document_month=document_month,
                            updated_by=str(st.session_state.get("username", "admin")),
                        )
                        st.success("A választ elküldtük, a reklamáció lezárva.")
                        st.rerun()

        response_documents = selected.get("response_documents", [])
        if resolved_complaints or response_documents:
            with st.expander("Lezart reklamaciok es admin valaszok", expanded=False):
                type_labels = {"settlement": "Elszamolas", "tig": "TIG"}
                shown_response_document_ids = set()
                for complaint in resolved_complaints:
                    complaint_id = str(complaint.get("id") or "")
                    document_type = str(complaint.get("document_type") or "")
                    matching_response = next(
                        (
                            document
                            for document in response_documents
                            if complaint_id
                            and complaint_id in str(document.get("title") or "")
                        ),
                        {},
                    )
                    if matching_response.get("id"):
                        shown_response_document_ids.add(str(matching_response.get("id")))
                    admin_response = (
                        complaint.get("admin_response")
                        or matching_response.get("note")
                        or ""
                    )
                    responded_by = (
                        complaint.get("responded_by")
                        or matching_response.get("uploaded_by")
                        or "admin"
                    )
                    responded_at = (
                        complaint.get("responded_at")
                        or matching_response.get("uploaded_at")
                        or ""
                    )
                    st.write(
                        f"**{type_labels.get(document_type, document_type)} reklamacio:** "
                        f"{complaint.get('message', '')}"
                    )
                    if admin_response:
                        st.success(f"Admin valasza: {admin_response}")
                    else:
                        st.info("Ehhez a lezart reklamaciohoz nincs rogzitett valaszszoveg.")
                    st.caption(f"Valaszolta: {responded_by} | {responded_at}")

                extra_response_documents = [
                    document
                    for document in response_documents
                    if str(document.get("id") or "") not in shown_response_document_ids
                ]
                for document in extra_response_documents:
                    st.write(f"**Valasz dokumentum:** {document.get('title', '')}")
                    if document.get("note"):
                        st.success(f"Admin valasza: {document.get('note')}")
                    st.caption(
                        f"Valaszolta: {document.get('uploaded_by') or 'admin'} | "
                        f"{document.get('uploaded_at') or ''}"
                    )

        render_admin_document_manager(
            selected["courier_id"],
            selected["courier_name"],
        )


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
                        "courier_id": details.get("courier_id"),
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
    default_start, default_end = previous_month_period(today)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.5])
    start_date = col1.date_input(
        "Elszamolasi honap kezdete",
        value=default_start,
        key="invoice_billing_start_date_v2",
    )
    end_date = col2.date_input(
        "Elszamolasi honap vege",
        value=default_end,
        key="invoice_billing_end_date_v2",
    )
    selected_sheet = col3.selectbox(
        "Telephely",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="invoice_sheet_filter",
    )

    try:
        data = read_invoice_data(
            start_date,
            end_date,
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

    full_final_df = final_df.copy()
    if selected_sheet != "Mind":
        selected_warehouse_df = filter_by_worksheet(
            full_final_df,
            selected_sheet,
        )
        selected_driver_keys = set()
        if (
            selected_warehouse_df is not None
            and not selected_warehouse_df.empty
            and "driver_name" in selected_warehouse_df.columns
        ):
            selected_driver_keys = set(
                selected_warehouse_df["driver_name"]
                .dropna()
                .astype(str)
                .map(normalize_person_key)
            )
        if selected_driver_keys and "driver_name" in full_final_df.columns:
            final_df = full_final_df[
                full_final_df["driver_name"]
                .astype(str)
                .map(normalize_person_key)
                .isin(selected_driver_keys)
            ].copy()
        else:
            final_df = full_final_df.iloc[0:0].copy()
    else:
        final_df = full_final_df

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

    driver_options = ["Mind"] + drivers
    pending_driver_filter = st.session_state.pop("invoice_driver_filter_pending", "")
    if pending_driver_filter in driver_options:
        st.session_state["invoice_driver_filter"] = pending_driver_filter

    selected_driver = col4.selectbox(
        "Futar / nev szuro",
        driver_options,
        key="invoice_driver_filter",
    )

    feedback_driver_summary = build_driver_invoice_summary(
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
        target_reserve_df=data.get("target_reserve", pd.DataFrame()),
        period_start=start_date,
    )
    target_reserve_errors = []
    if "target_reserve_lookup_error" in feedback_driver_summary.columns:
        target_reserve_errors = [
            str(value)
            for value in feedback_driver_summary["target_reserve_lookup_error"].dropna().unique()
            if str(value).strip()
        ]
    if target_reserve_errors:
        st.error(f"Celtartalek DB lookup hiba: {target_reserve_errors[0]}")
    render_settlement_feedback_overview(
        feedback_driver_summary,
        start_date,
        selected_driver,
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

    driver_summary = filter_by_driver(
        feedback_driver_summary,
        selected_driver,
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
    st.caption(
        "A futar havi osszesitoje egy sor: ha BUD1 es BUD2 raktarban is dolgozott, "
        "a raktaras route ertekek osszeadva jelennek meg, a futar szintu tetelek pedig egyszer."
    )
    display_summary = build_display_driver_summary(driver_summary)
    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True,
    )
    if selected_driver != "Mind" and not driver_summary.empty:
        selected_debug_row = driver_summary.iloc[0]
        debug_courier_id, debug_courier_name = resolve_settlement_identity(
            selected_debug_row,
            selected_driver,
        )
        with st.expander("Celtartalek / biztositas DB ellenorzes", expanded=True):
            if st.button(
                "Cache torlese es ujraszamolas",
                key=f"clear_invoice_cache_{selected_driver}_{start_date.isoformat()}",
            ):
                st.cache_data.clear()
                st.rerun()

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Futar": debug_courier_name or selected_driver,
                            "courier_id az elszamolasban": debug_courier_id or "",
                            "DB insurance_active a szamitasban": bool(
                                selected_debug_row.get("target_reserve_active", False)
                            ),
                            "Levonasok elotti fizetendo": format_huf(
                                selected_debug_row.get("payable_before_reserve_huf", 0)
                            ),
                            "Celtartalek levonas": format_huf(
                                selected_debug_row.get("target_reserve_deduction_huf", 0)
                            ),
                            "Biztositas levonas": format_huf(
                                selected_debug_row.get("insurance_deduction_huf", 0)
                            ),
                            "Celtartalek DB lookup hiba": str(
                                selected_debug_row.get("target_reserve_lookup_error", "")
                                or ""
                            ),
                        }
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

            if debug_courier_id:
                try:
                    reserve_debug_df = read_target_reserve_for_courier_ids(
                        [debug_courier_id]
                    )
                except Exception as exc:
                    reserve_debug_df = pd.DataFrame()
                    st.error(f"DB lekerdezes hiba: {exc}")

                if reserve_debug_df.empty:
                    st.error(
                        "Nincs talalat a courier_target_reserve tablaban erre a courier_ID-ra."
                    )
                else:
                    st.caption("DB sor a courier_target_reserve tablabol:")
                    st.dataframe(
                        reserve_debug_df,
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.error(
                    "Az elszamolas sorban nincs courier_id, ezert ID alapjan nem tud DB sort keresni."
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
        courier_id, courier_name = resolve_settlement_identity(selected_row, selected_driver)
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
                complaints.get("status", pd.Series(dtype=str)).astype(str).str.strip().str.lower() != "resolved"
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
                                reopen_peopleforce_acceptance_after_complaint(
                                    courier_id=courier_id,
                                    courier_name=courier_name,
                                    document_type="settlement",
                                    document_month=month_start_from_date(start_date),
                                    updated_by=str(st.session_state.get("username", "admin")),
                                )
                                st.success("A választ elküldtük a futárnak, a reklamáció lezárva.")
                                st.rerun()
                        if st.button(
                            "Lezárás válasz nélkül",
                            key=f"resolve_invoice_complaint_{complaint_id}",
                        ):
                            update_peopleforce_complaint_status(complaint_id, "resolved")
                            reopen_peopleforce_acceptance_after_complaint(
                                courier_id=courier_id,
                                courier_name=courier_name,
                                document_type="settlement",
                                document_month=month_start_from_date(start_date),
                                updated_by=str(st.session_state.get("username", "admin")),
                            )
                            st.success("A reklamáció lezárva.")
                            st.rerun()
    pdf_title = (
        f"JITT elszamolas {start_date.isoformat()} - {end_date.isoformat()}"
    )
    try:
        filename_driver = "osszes"
        if selected_driver != "Mind" and not driver_summary.empty:
            selected_row = driver_summary.iloc[0]
            courier_id, _courier_name = resolve_settlement_identity(
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
        download_file_name = (
            f"jitt_elszamolas_{filename_driver}_{start_date.isoformat()}_{end_date.isoformat()}.pdf"
        )
        if selected_driver != "Mind" and not driver_summary.empty:
            selected_row = driver_summary.iloc[0]
            download_courier_id, download_courier_name = resolve_settlement_identity(
                selected_row,
                selected_driver,
            )
            download_file_name = prefixed_document_filename(
                "e",
                download_courier_id,
                download_courier_name,
                month_start_from_date(start_date),
                download_file_name,
            )
        if selected_driver == "Mind":
            st.download_button(
                "PDF generalasa",
                data=pdf_bytes,
                file_name=download_file_name,
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
                    bulk_courier_id, bulk_courier_name = resolve_settlement_identity(
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
                        base_single_file_name = (
                            f"jitt_elszamolas_{bulk_courier_id}_"
                            f"{slugify_filename(bulk_courier_name)}_"
                            f"{start_date.isoformat()}_{end_date.isoformat()}.pdf"
                        )
                        single_file_name = prefixed_document_filename(
                            "t",
                            bulk_courier_id,
                            bulk_courier_name,
                            document_month,
                            base_single_file_name,
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

            st.divider()
            st.subheader("Tomeges TIG feltoltes")
            st.caption(
                "A rendszer a szurt futarlistara TIG PDF-et general, majd feltolti a futar profiljaba."
            )
            tig_bulk_confirm = st.checkbox(
                f"Megerositem {len(driver_summary)} futar TIG dokumentumanak tomeges feltolteset.",
                key=f"tig_bulk_confirm_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
            )
            tig_only_accepted_settlement = st.checkbox(
                "Csak azoknak kuldje, akik elfogadtak az elszamolast",
                value=True,
                key=f"tig_bulk_only_accepted_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
            )
            document_month = month_start_from_date(start_date)
            try:
                master_df_for_tig = read_courier_master()
            except Exception as exc:
                master_df_for_tig = pd.DataFrame()
                st.warning(f"Szamlazasi torzsadat nem olvashato: {exc}")
            master_lookup_for_tig = build_courier_master_lookup(master_df_for_tig)
            try:
                settlement_status_lookup_for_tig = _latest_status_by_courier_and_action(
                    read_peopleforce_card_statuses_for_month(document_month, "settlement")
                )
            except Exception as exc:
                settlement_status_lookup_for_tig = {}
                st.warning(f"Elszamolas elfogadasi statusz nem olvashato: {exc}")

            tig_preview_rows = []
            tig_sendable_count = 0
            for _, preview_row in driver_summary.reset_index(drop=True).iterrows():
                preview_driver_name = str(preview_row.get("driver_name") or "").strip()
                preview_courier_id, preview_courier_name = resolve_settlement_identity(
                    preview_row,
                    preview_driver_name,
                )
                preview_courier_id = normalize_courier_id(preview_courier_id)
                preview_master_row = master_lookup_for_tig.get(preview_courier_id, {})
                preview_accepted = _is_done(
                    settlement_status_lookup_for_tig.get((preview_courier_id, "settlement"))
                )
                missing_billing_fields = [
                    label
                    for label, value in [
                        ("cegnev", preview_master_row.get("company_name")),
                        ("cim", preview_master_row.get("company_address")),
                        ("adoszam", preview_master_row.get("tax_number")),
                    ]
                    if not str(value or "").strip()
                ]
                passes_acceptance_filter = (
                    preview_accepted or not tig_only_accepted_settlement
                )
                sendable = bool(
                    preview_courier_id
                    and passes_acceptance_filter
                    and not missing_billing_fields
                )
                if sendable:
                    tig_sendable_count += 1
                tig_preview_rows.append(
                    {
                        "Futar": preview_courier_name or preview_driver_name,
                        "courier_id": preview_courier_id or "Hianyzik",
                        "Elszamolas elfogadva": "Igen" if preview_accepted else "Nem",
                        "Szamlazasi adatok": (
                            "OK" if not missing_billing_fields else "Hianyos"
                        ),
                        "Hianyzo adat": ", ".join(missing_billing_fields),
                        "Kuldheto TIG": "Igen" if sendable else "Nem",
                    }
                )
            with st.expander("TIG kuldesi elokeszites es szamlazasi adatok", expanded=False):
                st.caption(
                    "A TIG a courier_master szamlazasi adataibol toltodik automatikusan: "
                    "cegnev, cim, adoszam. Csak a kuldheto sorokra indul a tomeges TIG."
                )
                st.metric("Kuldheto TIG dokumentum", tig_sendable_count)
                if tig_preview_rows:
                    st.dataframe(
                        pd.DataFrame(tig_preview_rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Nincs futar a jelenlegi szuresben.")

            with st.expander("Tomeges szamlazasi adatkitoltes", expanded=False):
                st.caption(
                    "A jelenlegi szurt futarlistahoz megprobalja a "
                    "courier_master_sheet_import staging tabla alapjan kitolteni a "
                    "courier_master szamlazasi adatait. Elsodlegesen courier_id, "
                    "masodlagosan egyedi telefonszam alapjan parosit."
                )
                billing_sync_key = (
                    f"billing_sync_preview_{start_date.isoformat()}_"
                    f"{end_date.isoformat()}_{selected_sheet}"
                )
                current_courier_ids = [
                    str(row.get("courier_id") or "").strip()
                    for row in tig_preview_rows
                    if str(row.get("courier_id") or "").strip()
                    and str(row.get("courier_id") or "").strip() != "Hianyzik"
                ]
                if st.button(
                    "Tomeges kitoltes elonezetenek frissitese",
                    use_container_width=True,
                    key=f"billing_sync_preview_button_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
                ):
                    try:
                        st.session_state[billing_sync_key] = build_billing_staging_update_preview(
                            current_courier_ids
                        )
                    except Exception as exc:
                        st.session_state.pop(billing_sync_key, None)
                        st.error(f"Szamlazasi adat elonezet hiba: {exc}")

                billing_sync_preview = st.session_state.get(billing_sync_key)
                if billing_sync_preview:
                    sync_updates = billing_sync_preview.get("updates", [])
                    sync_inserts = billing_sync_preview.get("inserts", [])
                    sync_metric1, sync_metric2 = st.columns(2)
                    sync_metric1.metric("Frissitheto futar", len(sync_updates))
                    sync_metric2.metric("Ujkent felveheto futar", len(sync_inserts))
                    if sync_updates:
                        st.markdown("**Meglevo courier_master sorok frissitese**")
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "courier_id": row.get("courier_id"),
                                        "Futar": row.get("courier_name"),
                                        "Forras nev": row.get("source_name"),
                                        "Frissulo mezok": ", ".join(
                                            key
                                            for key in (row.get("patch") or {}).keys()
                                            if key not in {
                                                "billing_data_source",
                                                "billing_data_updated_at",
                                                "updated_at",
                                            }
                                        ),
                                    }
                                    for row in sync_updates
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    if sync_inserts:
                        st.markdown("**Uj courier_master sorok felvetele**")
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "courier_id": row.get("courier_id"),
                                        "Futar": row.get("courier_name"),
                                        "Telefon": (row.get("row") or {}).get("phone_number"),
                                        "Email": (row.get("row") or {}).get("email"),
                                        "Cegnev": (row.get("row") or {}).get("company_name"),
                                        "Adoszam": (row.get("row") or {}).get("tax_number"),
                                    }
                                    for row in sync_inserts
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    if not sync_updates and not sync_inserts:
                        st.info("Nincs frissitendo vagy ujkent felveheto adat a jelenlegi szuresben.")
                    billing_sync_confirm = st.checkbox(
                        "Megerősitem a tomeges courier_master szamlazasi adatfrissitest.",
                        key=f"billing_sync_confirm_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
                    )
                    if st.button(
                        "Tomeges szamlazasi adatok kitoltese",
                        type="primary",
                        use_container_width=True,
                        disabled=(not billing_sync_confirm or (not sync_updates and not sync_inserts)),
                        key=f"billing_sync_apply_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
                    ):
                        try:
                            result = apply_billing_staging_updates(sync_updates, sync_inserts)
                            st.session_state.pop(billing_sync_key, None)
                            st.cache_data.clear()
                            if result["failures"]:
                                st.warning(
                                    f"Frissitve: {result['success']}, "
                                    f"uj felvetel: {result.get('inserted', 0)}, "
                                    f"hibas: {len(result['failures'])}."
                                )
                                st.dataframe(
                                    pd.DataFrame(result["failures"]),
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            else:
                                st.success(
                                    f"Tomeges szamlazasi adatkitoltes kesz. "
                                    f"Frissitve: {result['success']} futar, "
                                    f"uj felvetel: {result.get('inserted', 0)}."
                                )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Tomeges szamlazasi adatkitoltes hiba: {exc}")

            if st.button(
                "Tomeges TIG generalasa es feltoltese",
                type="primary",
                use_container_width=True,
                disabled=(not tig_bulk_confirm or tig_sendable_count <= 0),
                key=f"tig_bulk_upload_{start_date.isoformat()}_{end_date.isoformat()}_{selected_sheet}",
            ):
                master_lookup = master_lookup_for_tig
                settlement_status_lookup = settlement_status_lookup_for_tig

                uploaded_count = 0
                skipped_count = 0
                failed_rows = []
                progress = st.progress(0)
                status_box = st.empty()
                total_rows = len(driver_summary)
                for row_index, bulk_row in driver_summary.reset_index(drop=True).iterrows():
                    driver_name = str(bulk_row.get("driver_name") or "").strip()
                    courier_id, courier_name = resolve_settlement_identity(bulk_row, driver_name)
                    courier_id = normalize_courier_id(courier_id)
                    status_box.write(
                        f"TIG keszites: {courier_name or driver_name or 'Ismeretlen futar'} "
                        f"({row_index + 1}/{total_rows})"
                    )
                    try:
                        if not courier_id:
                            raise ValueError("Nincs courier ID.")
                        if (
                            tig_only_accepted_settlement
                            and not _is_done(settlement_status_lookup.get((courier_id, "settlement")))
                        ):
                            skipped_count += 1
                            failed_rows.append(
                                {
                                    "Futar": courier_name or driver_name,
                                    "Allapot": "Kihagyva",
                                    "Hiba": "Az elszamolast meg nem fogadta el.",
                                }
                            )
                            progress.progress((row_index + 1) / total_rows)
                            continue
                        master_row = master_lookup.get(normalize_courier_id(courier_id), {})
                        seller_name = str(master_row.get("company_name") or courier_name or driver_name).strip()
                        seller_address = str(master_row.get("company_address") or "").strip()
                        seller_tax_number = str(master_row.get("tax_number") or "").strip()
                        if not seller_name or not seller_address or not seller_tax_number:
                            raise ValueError("Hianyos torzsadat: cegnev/cim/adoszam szukseges.")
                        transfer_amount = int(
                            round(float(bulk_row.get("payable_total_huf", 0) or 0))
                        )
                        tig_bytes = build_tig_pdf_bytes(
                            courier_name=seller_name,
                            courier_address=seller_address,
                            courier_tax_number=seller_tax_number,
                            courier_id=courier_id,
                            document_month=document_month,
                            transfer_amount_huf=max(transfer_amount, 0),
                            cash_amount_huf=abs(int(round(float(bulk_row.get("atm_balance_huf", 0) or 0)))),
                        )
                        base_tig_file_name = (
                            f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_"
                            f"{document_month.strftime('%Y-%m')}.pdf"
                        )
                        tig_file_name = prefixed_document_filename(
                            "t",
                            courier_id,
                            courier_name,
                            document_month,
                            base_tig_file_name,
                        )
                        upload_peopleforce_document_bytes(
                            courier_id=courier_id,
                            courier_name=courier_name,
                            document_type="tig",
                            document_month=document_month,
                            title=f"TIG - {document_month.strftime('%Y-%m')}",
                            note="Admin altal tomegesen generalt teljesitesi igazolas.",
                            file_name=tig_file_name,
                            mime_type="application/pdf",
                            file_bytes=tig_bytes,
                            uploaded_by=str(st.session_state.get("username", "admin")),
                        )
                        upsert_peopleforce_card_status(
                            courier_id=courier_id,
                            courier_name=courier_name,
                            action_key="tig",
                            document_month=document_month,
                            status="open",
                            status_note="TIG tomegesen feltoltve, futar elfogadasara var.",
                            updated_by=str(st.session_state.get("username", "admin")),
                        )
                        uploaded_count += 1
                    except Exception as exc:
                        failed_rows.append(
                            {
                                "Futar": courier_name or driver_name,
                                "Allapot": "Hiba",
                                "Hiba": str(exc),
                            }
                        )
                    progress.progress((row_index + 1) / total_rows)
                status_box.empty()
                st.cache_data.clear()
                st.success(
                    f"Tomeges TIG feltoltes kesz. Feltoltve: {uploaded_count}, "
                    f"kihagyva: {skipped_count}, hibas: "
                    f"{sum(1 for row in failed_rows if row.get('Allapot') == 'Hiba')}."
                )
                if failed_rows:
                    st.dataframe(pd.DataFrame(failed_rows), use_container_width=True, hide_index=True)

        if selected_driver != "Mind":
            st.divider()
            st.subheader("Egyedi elszamolas es TIG PDF")
            st.download_button(
                "Egyedi elszamolas / szamla PDF letoltese",
                data=pdf_bytes,
                file_name=download_file_name,
                mime="application/pdf",
                use_container_width=True,
                key=f"individual_invoice_pdf_{selected_driver}_{start_date.isoformat()}",
            )
            selected_row = driver_summary.iloc[0]
            courier_id, courier_name = resolve_settlement_identity(
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
                    base_file_name = (
                        f"jitt_elszamolas_{courier_id}_{slugify_filename(courier_name)}_"
                        f"{start_date.isoformat()}_{end_date.isoformat()}.pdf"
                    )
                    file_name = prefixed_document_filename(
                        "e",
                        courier_id,
                        courier_name,
                        document_month,
                        base_file_name,
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

            master_row = read_courier_master_row_by_id(courier_id)

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
            try:
                default_cash_amount = abs(
                    int(round(float(selected_row.get("atm_balance_huf", 0) or 0)))
                )
            except (TypeError, ValueError):
                default_cash_amount = 0


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
                    "Készpénzes számla összege (Ft, ATM egyenleg alapján)",
                    min_value=0,
                    value=default_cash_amount,
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
                base_tig_file_name = (
                    f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_"
                    f"{document_month.strftime('%Y-%m')}.pdf"
                )
                tig_file_name = prefixed_document_filename(
                    "e",
                    courier_id,
                    courier_name,
                    document_month,
                    base_tig_file_name,
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
