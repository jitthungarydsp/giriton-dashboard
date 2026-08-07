from datetime import date
from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd
import requests
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

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
    build_invoice_regeneration_candidates,
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
    read_peopleforce_documents,
    read_peopleforce_documents_for_courier,
    read_peopleforce_documents_for_month,
    read_peopleforce_document_content,
    read_peopleforce_card_statuses_for_month,
    respond_to_peopleforce_complaint,
    update_peopleforce_document,
    update_peopleforce_complaint_status,
    upload_peopleforce_document_bytes,
    upsert_peopleforce_card_status,
)
from resources.pwa_invoice_validation import extract_expected_amount, parse_invoice_pdf


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
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "A TIG PDF előállításához hiányzik a reportlab csomag. "
            "Telepítsd a requirements.txt függőségeit."
        )
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


WORKFLOW_BACKSTEP_TARGETS = {
    "settlement": {"label": "Elszamolas elfogadasara", "done": [], "open": ["settlement", "tig", "invoice_submit", "invoice_check", "invoice_payment"]},
    "tig": {"label": "TIG elfogadasara", "done": ["settlement"], "open": ["tig", "invoice_submit", "invoice_check", "invoice_payment"]},
    "invoice_submit": {"label": "Szamlafeltoltesre", "done": ["settlement", "tig"], "open": ["invoice_submit", "invoice_check", "invoice_payment"]},
    "invoice_check": {"label": "Szamlaellenorzesre", "done": ["settlement", "tig", "invoice_submit"], "open": ["invoice_check", "invoice_payment"]},
    "invoice_payment": {"label": "Kifizetesre", "done": ["settlement", "tig", "invoice_submit", "invoice_check"], "open": ["invoice_payment"]},
}


def backstep_peopleforce_workflow(*, courier_id, courier_name, document_month, target_action, updated_by, note=""):
    target = WORKFLOW_BACKSTEP_TARGETS.get(str(target_action or ""))
    if not target:
        return 0
    clean_note = str(note or "").strip() or f"Admin visszaleptette: {target['label']}."
    saved = 0
    for action_key in ["manual_invoice_skip", "invoice_validation_override"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="open", status_note=clean_note, updated_by=updated_by)
        saved += 1
    for action_key in target["done"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="done", status_note=clean_note, updated_by=updated_by)
        saved += 1
    for action_key in target["open"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="open", status_note=clean_note, updated_by=updated_by)
        saved += 1
    read_peopleforce_card_statuses_for_month.clear()
    return saved


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


def format_bank_account_number(value):
    """A bankszámlaszámot négyes csoportokban jeleníti meg."""
    compact = re.sub(r"[\s-]+", "", str(value or "").strip())
    if not compact:
        return "-"
    return "-".join(compact[index:index + 4] for index in range(0, len(compact), 4))


def _invoice_amount_by_name(driver_summary):
    result = {}
    if driver_summary is None or driver_summary.empty:
        return result
    for _, row in driver_summary.iterrows():
        name = str(row.get("driver_name") or "").strip()
        if not name:
            continue
        try:
            amount = int(round(float(row.get("payable_total_huf", 0) or 0)))
        except (TypeError, ValueError):
            amount = 0
        result[normalize_name(name)] = amount
    return result


def _invoice_summary_rows_by_name(driver_summary):
    result = {}
    if driver_summary is None or driver_summary.empty:
        return result
    for _, row in driver_summary.iterrows():
        name = str(row.get("driver_name") or "").strip()
        if name:
            result[normalize_name(name)] = row.to_dict()
    return result


def _short_task_text(value, limit=110):
    text = " ".join(str(value or "-").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _latest_rows_by_action(status_df):
    by_id = {}
    by_name = {}
    if status_df is None or status_df.empty:
        return by_id, by_name
    for _, row in status_df.iterrows():
        action = str(row.get("action_key") or "").strip().lower()
        courier_id = normalize_courier_id(row.get("courier_id"))
        name_key = normalize_name(row.get("courier_name"))
        if courier_id:
            by_id.setdefault((courier_id, action), row)
        if name_key:
            by_name.setdefault((name_key, action), row)
    return by_id, by_name


def _status_for_action(status_by_id, status_by_name, courier_id, name_key, action):
    row = status_by_id.get((courier_id, action))
    if row is None:
        row = status_by_name.get((name_key, action))
    return row


def _document_types_for_courier(documents_by_id, documents_by_name, courier_id, name_key):
    rows = documents_by_id.get(courier_id, []) if courier_id else []
    if not rows:
        rows = documents_by_name.get(name_key, [])
    return {str(row.get("document_type") or "").strip().lower() for row in rows}, rows


def _render_amount_check(courier_id, document_month, fallback_tig_amount=0):
    try:
        invoice_documents = read_peopleforce_documents(courier_id, document_month, "invoice")
        tig_documents = read_peopleforce_documents(courier_id, document_month, "tig")
    except Exception as exc:
        st.error(f"Az ellenőrzéshez szükséges dokumentumok nem tölthetők be: {exc}")
        return

    if invoice_documents.empty:
        st.warning("Ehhez a hónaphoz még nincs feltöltött számla.")
        return

    invoice_amounts = []
    unreadable_files = []
    for _, document in invoice_documents.iterrows():
        file_name = str(document.get("file_name") or "számla")
        content = decode_document_content(document.get("file_content_base64"))
        amount = int(parse_invoice_pdf(content).get("gross_total") or 0)
        if amount:
            invoice_amounts.append((file_name, amount))
        else:
            unreadable_files.append(file_name)

    tig_amount = 0
    if not tig_documents.empty:
        latest_tig = tig_documents.iloc[0]
        tig_amount = extract_expected_amount(
            decode_document_content(latest_tig.get("file_content_base64"))
        )
    if not tig_amount:
        try:
            tig_amount = int(round(float(fallback_tig_amount or 0)))
        except (TypeError, ValueError):
            tig_amount = 0

    if not invoice_amounts:
        st.warning("A feltöltött számlából nem sikerült kiolvasni a bruttó összeget.")
        return
    if not tig_amount:
        st.warning("A TIG-ből nem sikerült kiolvasni az összeget, ezért az összevetés nem végezhető el.")
        return

    invoice_total = sum(amount for _file_name, amount in invoice_amounts)
    st.dataframe(
        pd.DataFrame(
            [{"Számla": file_name, "Kiolvasott összeg": format_huf(amount)} for file_name, amount in invoice_amounts]
        ),
        use_container_width=True,
        hide_index=True,
    )
    difference = invoice_total - tig_amount
    if difference == 0 and not unreadable_files:
        st.success(f"Egyezik: a számla és a TIG összege is {format_huf(tig_amount)}.")
    elif difference == 0:
        st.warning(
            f"A kiolvasható számlák összege egyezik a TIG összegével ({format_huf(tig_amount)}), "
            f"de {len(unreadable_files)} fájl nem volt automatikusan olvasható."
        )
    else:
        st.error(
            f"Nem egyezik. Számla: {format_huf(invoice_total)}; TIG: {format_huf(tig_amount)}; "
            f"eltérés: {format_huf(difference)}."
        )
    if unreadable_files:
        st.caption("Nem olvasható automatikusan: " + ", ".join(unreadable_files))


def _render_open_complaints(courier_id, courier_name, document_month):
    try:
        complaints = read_peopleforce_complaints_for_month(document_month)
    except Exception as exc:
        st.error(f"A reklamációk nem tölthetők be: {exc}")
        return
    if complaints.empty:
        st.caption("Nincs nyitott reklamáció.")
        return
    courier_id = str(courier_id or "").strip()
    name_key = normalize_name(courier_name)
    complaint_ids = complaints.get("courier_id", pd.Series(dtype=str)).astype(str).str.strip()
    complaint_names = complaints.get("courier_name", pd.Series(dtype=str)).astype(str).map(normalize_name)
    statuses = complaints.get("status", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    open_complaints = complaints[
        ((complaint_ids == courier_id) | (complaint_names == name_key))
        & (~statuses.isin(["resolved", "closed", "done"]))
    ].copy()
    if open_complaints.empty:
        st.caption("Nincs nyitott reklamáció.")
        return
    if "created_at" in open_complaints.columns:
        open_complaints = open_complaints.sort_values("created_at", ascending=False)
    type_labels = {"settlement": "Elszámolás", "tig": "TIG", "invoice": "Számla"}
    for _, complaint in open_complaints.iterrows():
        complaint_type = str(complaint.get("document_type") or "folyamat")
        st.error(
            f"{type_labels.get(complaint_type, complaint_type)} · "
            f"{str(complaint.get('created_at') or '')[:16]}\n\n"
            f"{complaint.get('message') or 'Nincs megadott indok.'}"
        )


def _task_master_row(courier_id):
    try:
        master_df = read_courier_master()
    except Exception:
        return {}
    if master_df.empty or "courier_id" not in master_df.columns:
        return {}
    matches = master_df[
        master_df["courier_id"].astype(str).str.strip() == str(courier_id or "").strip()
    ]
    return matches.iloc[0].to_dict() if not matches.empty else {}


def _render_task_tig_generator(task_row, document_month):
    courier_id = str(task_row.get("_courier_id") or "").strip()
    courier_name = str(task_row.get("Futár") or "").strip()
    master_row = _task_master_row(courier_id)

    def first_value(*names, default=""):
        for name in names:
            value = master_row.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return default

    with st.expander("TIG generálása", expanded="TIG elkészítésére" in str(task_row.get("Mire vár?"))):
        with st.form(f"task_tig_generator_{courier_id}_{document_month}"):
            col1, col2 = st.columns(2)
            seller_name = col1.text_input(
                "Szolgáltató / vállalkozás neve",
                value=first_value("company_name", default=courier_name),
            )
            tax_number = col2.text_input(
                "Adószám",
                value=first_value("tax_number", "tax_id", "vat_number", "adoszam"),
            )
            address = st.text_input(
                "Vállalkozás székhelye",
                value=first_value(
                    "company_address", "courier_address", "address", "billing_address", "invoice_address"
                ),
            )
            amount1, amount2 = st.columns(2)
            transfer_amount = amount1.number_input(
                "Átutalásos összeg (Ft)",
                min_value=0,
                value=max(int(task_row.get("_tig_amount") or 0), 0),
                step=100,
            )
            cash_amount = amount2.number_input(
                "Készpénzes összeg (Ft)", min_value=0, value=0, step=100
            )
            generate = st.form_submit_button("TIG előállítása", use_container_width=True)

        state_key = f"task_generated_tig_{courier_id}_{document_month}"
        if generate:
            if not seller_name.strip() or not tax_number.strip() or not address.strip():
                st.warning("A szolgáltató neve, adószáma és címe kötelező.")
            else:
                try:
                    st.session_state[state_key] = build_tig_pdf_bytes(
                        courier_name=seller_name.strip(),
                        courier_address=address.strip(),
                        courier_tax_number=tax_number.strip(),
                        courier_id=courier_id,
                        document_month=month_start_from_date(document_month),
                        transfer_amount_huf=transfer_amount,
                        cash_amount_huf=cash_amount,
                    )
                    st.success("A TIG elkészült.")
                except Exception as exc:
                    st.error(f"A TIG előállítása sikertelen: {exc}")

        generated = st.session_state.get(state_key)
        if generated:
            file_name = (
                f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_"
                f"{month_start_from_date(document_month):%Y-%m}.pdf"
            )
            action1, action2 = st.columns(2)
            action1.download_button(
                "TIG letöltése",
                data=generated,
                file_name=file_name,
                mime="application/pdf",
                use_container_width=True,
                key=f"task_tig_download_{courier_id}_{document_month}",
            )
            if action2.button(
                "Feltöltés a futár profiljába",
                use_container_width=True,
                key=f"task_tig_upload_{courier_id}_{document_month}",
            ):
                try:
                    upload_peopleforce_document_bytes(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        document_type="tig",
                        document_month=document_month,
                        title=f"TIG - {month_start_from_date(document_month):%Y-%m}",
                        note="Admin által generált teljesítési igazolás.",
                        file_name=file_name,
                        mime_type="application/pdf",
                        file_bytes=generated,
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
                    st.session_state.pop(state_key, None)
                    st.cache_data.clear()
                    st.success("A TIG bekerült a futár profiljába.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"A TIG feltöltése sikertelen: {exc}")


def _render_task_manual_item_form(task_row, document_month):
    courier_name = str(task_row.get("Futár") or "").strip()
    default_sheet = str(task_row.get("_worksheet_name") or "BUD1_JIT")
    if default_sheet not in ["BUD1_JIT", "BUD2_JIT"]:
        default_sheet = "BUD1_JIT"
    with st.expander("Manuális tétel hozzáadása", expanded=False):
        with st.form(f"task_manual_item_{task_row.get('_courier_id')}_{document_month}"):
            col1, col2 = st.columns(2)
            item_date = col1.date_input("Tétel dátuma", value=month_start_from_date(document_month))
            worksheet_name = col2.selectbox(
                "Raktár fül",
                ["BUD1_JIT", "BUD2_JIT"],
                index=["BUD1_JIT", "BUD2_JIT"].index(default_sheet),
            )
            col3, col4 = st.columns(2)
            item_type = col3.selectbox(
                "Tétel típusa",
                list(MANUAL_ITEM_TYPES),
                format_func=lambda value: MANUAL_ITEM_TYPES[value],
            )
            amount_huf = col4.number_input("Összeg (Ft)", value=0, step=500)
            item_note = st.text_input("Megjegyzés")
            save_item = st.form_submit_button("Manuális tétel mentése", use_container_width=True)
        if save_item:
            try:
                table_name = create_manual_invoice_item(
                    item_date,
                    worksheet_name,
                    courier_name,
                    item_type,
                    amount_huf,
                    item_note,
                    created_by=str(st.session_state.get("username", "admin")),
                )
                st.cache_data.clear()
                st.success(f"Manuális tétel elmentve: {table_name}")
                st.rerun()
            except Exception as exc:
                st.error(f"A manuális tétel mentése sikertelen: {exc}")


@st.dialog("Futár havi feladata", width="large")
def render_invoice_task_dialog(task_row, document_month):
    st.markdown(
        """
        <style>
        div[data-testid="stDialog"] div[role="dialog"] {
            max-height: 92vh !important;
            overflow-y: auto !important;
            overscroll-behavior: contain;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    courier_id = str(task_row.get("_courier_id") or "").strip()
    courier_name = str(task_row.get("Futár") or "").strip()
    st.subheader(courier_name)
    info1, info2, info3 = st.columns([1, 1.2, 1.6])
    info1.markdown(f"**Utalandó**  \n{task_row.get('Utalandó összeg', '-')}")
    info2.markdown(f"**Bankszámlaszám**  \n{task_row.get('Bankszámlaszám', '-')}")
    info3.markdown(f"**Aktuális feladat**  \n{task_row.get('Mire vár?', '-')}")

    help_reason = str(task_row.get("Segítségkérés oka") or "-")
    note = str(task_row.get("Megjegyzés") or "-")
    override_note = str(task_row.get("_invoice_override_note") or "-")
    if help_reason != "-" or note != "-" or override_note != "-":
        with st.expander("Állapot részletei", expanded=help_reason != "-"):
            if help_reason != "-":
                st.error(help_reason)
            if note != "-" and note != help_reason:
                st.info(note)
            if override_note != "-":
                st.warning(override_note)

    st.markdown("#### Nyitott reklamációk")
    _render_open_complaints(courier_id, courier_name, document_month)

    try:
        documents = read_peopleforce_documents_for_courier(courier_id)
        if not documents.empty:
            documents = documents[
                documents["document_month"].astype(str).str[:7]
                == month_start_from_date(document_month).strftime("%Y-%m")
            ].copy()
            documents = documents[
                documents["document_type"].astype(str).str.lower() != "complaint_response"
            ].copy()
            if "uploaded_at" in documents.columns:
                documents = documents.sort_values("uploaded_at", ascending=False)
    except Exception as exc:
        st.error(f"A dokumentumlista nem tölthető be: {exc}")
        documents = pd.DataFrame()

    st.markdown("#### Havi dokumentumok")
    if documents.empty:
        st.info("Ehhez a hónaphoz még nincs feltöltött dokumentum.")
    else:
        type_labels = {"settlement": "Elszámolás", "tig": "TIG", "invoice": "Számla", "complaint_response": "Válasz"}
        document_rows = documents.to_dict("records")
        overview = pd.DataFrame(
            [
                {
                    "Időpont": str(row.get("uploaded_at") or "")[:16].replace("T", " "),
                    "Típus": type_labels.get(str(row.get("document_type") or ""), str(row.get("document_type") or "")),
                    "Fájl": row.get("file_name") or row.get("title") or "dokumentum",
                }
                for row in document_rows
            ]
        )
        st.dataframe(overview, use_container_width=True, hide_index=True, height=min(230, 36 + len(overview) * 35))
        rows_by_id = {str(row.get("id")): row for row in document_rows}
        selected_document_id = st.selectbox(
            "Dokumentum megnyitása",
            list(rows_by_id),
            format_func=lambda value: (
                f"{type_labels.get(str(rows_by_id[value].get('document_type') or ''), str(rows_by_id[value].get('document_type') or ''))} · "
                f"{rows_by_id[value].get('file_name') or rows_by_id[value].get('title')}"
            ),
            key=f"task_document_select_{courier_id}_{document_month}",
        )
        document = rows_by_id[selected_document_id]
        try:
            content_row = read_peopleforce_document_content(selected_document_id)
            file_bytes = decode_document_content(content_row.get("file_content_base64"))
        except Exception:
            file_bytes = b""
        if file_bytes:
            file_name = str(document.get("file_name") or "dokumentum")
            mime_type = str(document.get("mime_type") or "application/octet-stream")
            preview_col, download_col = st.columns([2, 1])
            preview_col.caption(str(document.get("note") or "Nincs megjegyzés."))
            download_col.download_button(
                "Letöltés",
                data=file_bytes,
                file_name=file_name,
                mime=mime_type,
                use_container_width=True,
                key=f"task_document_download_{selected_document_id}",
            )

    with st.expander("Folyamat visszaleptetese", expanded=False):
        backstep_options = list(WORKFLOW_BACKSTEP_TARGETS.keys())
        backstep_target = st.selectbox(
            "Melyik lepesre keruljon vissza?",
            backstep_options,
            format_func=lambda key: WORKFLOW_BACKSTEP_TARGETS[key]["label"],
            index=backstep_options.index("tig"),
            key=f"legacy_task_backstep_target_{courier_id}_{document_month}",
        )
        backstep_note = st.text_input(
            "Megjegyzes",
            value=f"Admin visszaleptetes: {WORKFLOW_BACKSTEP_TARGETS[backstep_target]['label']}.",
            key=f"legacy_task_backstep_note_{courier_id}_{document_month}",
        )
        if st.button(
            "Visszaleptetes mentese",
            type="primary",
            use_container_width=True,
            disabled=not bool(courier_id),
            key=f"legacy_task_backstep_save_{courier_id}_{document_month}",
        ):
            try:
                saved_count = backstep_peopleforce_workflow(
                    courier_id=courier_id,
                    courier_name=courier_name,
                    document_month=month_start_from_date(document_month),
                    target_action=backstep_target,
                    updated_by=str(st.session_state.get("username", "admin")),
                    note=backstep_note,
                )
                st.cache_data.clear()
                st.success(f"Folyamat visszaleptetve. Modositott statuszok: {saved_count}.")
                st.rerun()
            except Exception as exc:
                st.error(f"A folyamat visszaleptetese nem mentheto: {exc}")

    st.divider()
    _render_task_tig_generator(task_row, document_month)
    _render_task_manual_item_form(task_row, document_month)
    if st.button("Számla és TIG összegének ellenőrzése", use_container_width=True):
        _render_amount_check(courier_id, document_month, task_row.get("_tig_amount", 0))


def _render_invoice_task_rows(task_rows, document_month):
    if not task_rows:
        st.success("Nincs nyitott havi feladat.")
        return

    task_rows = sorted(
        task_rows,
        key=lambda row: (
            int(row.get("_workflow_priority") or 0),
            str(row.get("_updated_at") or ""),
        ),
        reverse=True,
    )
    st.caption(
        "A kifizetéshez legközelebbi feladatok vannak felül; azonos lépésen belül a frissebb az első. "
        "A futár nevére kattintva megnyílnak a részletek és a műveletek."
    )
    header = st.columns([1.35, 1.25, 0.8, 1.7, 1.4, 1.0, 0.65])
    for column, label in zip(
        header,
        [
            "Futár",
            "Bankszámlaszám",
            "Utalandó",
            "Mire vár?",
            "Segítség / megjegyzés",
            "Számla",
            "Zárás",
        ],
    ):
        column.markdown(f"**{label}**")

    for index, row in enumerate(task_rows):
        columns = st.columns(
            [1.35, 1.25, 0.8, 1.7, 1.4, 1.0, 0.65],
            vertical_alignment="center",
        )
        if columns[0].button(
            str(row.get("Futár") or "Ismeretlen futár"),
            key=f"invoice_task_open_{document_month}_{row.get('_courier_id')}_{index}",
            use_container_width=True,
        ):
            render_invoice_task_dialog(row, document_month)
        columns[1].caption(row.get("Bankszámlaszám", "-"))
        columns[2].caption(row.get("Utalandó összeg", "-"))
        columns[3].caption(row.get("Mire vár?", "-"))
        detail = row.get("Segítségkérés oka", "-") if row.get("Segítségkérés oka") != "-" else row.get("Megjegyzés", "-")
        columns[4].caption(_short_task_text(detail, 90))

        if row.get("_invoice_override_available"):
            if columns[5].button(
                "Számla továbbengedése",
                key=f"invoice_validation_override_{document_month}_{row.get('_courier_id')}_{index}",
                use_container_width=True,
                help=(
                    "Az eredeti ellenőrzési hibák megmaradnak, de a következő "
                    "számlaellenőrzésnél már nem blokkolják a futárt."
                ),
            ):
                try:
                    original_error = _short_task_text(row.get("_invoice_error_note"), 1200)
                    upsert_peopleforce_card_status(
                        courier_id=row.get("_courier_id"),
                        courier_name=row.get("Futár"),
                        action_key="invoice_validation_override",
                        document_month=document_month,
                        status="done",
                        status_note=(
                            "Admin által továbbengedve. Az eredeti ellenőrzési hibák: "
                            f"{original_error}"
                        )[:1500],
                        updated_by=str(st.session_state.get("username", "admin")),
                    )
                    st.cache_data.clear()
                    st.success(
                        f"{row.get('Futár')} számlája továbbengedve. "
                        "A futár most újra elindíthatja az ellenőrzést."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"A számla továbbengedése nem menthető: {exc}")
        elif row.get("_invoice_override_enabled"):
            columns[5].caption("Továbbengedve")
        else:
            columns[5].caption("–")

        if columns[6].button(
            "Havi zárás",
            key=f"invoice_month_close_{document_month}_{row.get('_courier_id')}_{index}",
            use_container_width=True,
            disabled=not bool(str(row.get("_courier_id") or "").strip()),
        ):
            try:
                upsert_peopleforce_card_status(
                    courier_id=row.get("_courier_id"),
                    courier_name=row.get("Futár"),
                    action_key="monthly_close",
                    document_month=document_month,
                    status="done",
                    status_note="Havi adminisztráció lezárva.",
                    updated_by=str(st.session_state.get("username", "admin")),
                )
                st.cache_data.clear()
                st.success(f"{row.get('Futár')} havi feladata lezárva.")
                st.rerun()
            except Exception as exc:
                st.error(f"A havi zárás nem menthető: {exc}")


def user_has_logged_in(user_row):
    if not isinstance(user_row, dict):
        return False
    for key in ["lastLoginAt", "last_login_at", "lastLogin", "last_login"]:
        if str(user_row.get(key) or "").strip():
            return True
    return bool(str(user_row.get("token") or "").strip())


def render_monthly_invoice_tasks(route_driver_names, document_month, driver_summary=None):
    """
    Admin visszajelzo: hol tart a futar az elszamolasi folyamatban.
    Piros sor: segitseget ker / nyitott reklamacio.
    Zold sor: elfogadta / lezart allapotban van.
    """
    # A nyitott feladatlista futárköre kizárólag a havi
    # peopleforce_card_statuses rekordokból épül. A route-, dokumentum- és
    # reklamációs adatok csak a státuszban már szereplő futár részleteit
    # egészítik ki, önállóan nem hoznak létre új listás sort.
    route_name_lookup = {}
    month_start = month_start_from_date(document_month)
    master_by_name, master_by_id, users_by_name, users_by_id = build_invoice_feedback_context()

    try:
        sent_lookup = read_sent_invoice_driver_names(month_start, "settlement")
    except Exception as exc:
        st.warning(
            f"A futar visszajelzo dokumentumallapota nem toltheto be: {exc}"
        )
        sent_lookup = {}

    try:
        status_df = read_peopleforce_card_statuses_for_month(month_start)
    except Exception as exc:
        st.warning(f"A futar visszajelzo statuszai nem tolthet?k be: {exc}")
        status_df = pd.DataFrame()

    try:
        complaints_df = read_peopleforce_complaints_for_month(month_start)
    except Exception as exc:
        st.warning(f"A reklamacios adatok nem tolthet?k be: {exc}")
        complaints_df = pd.DataFrame()

    def row_name_key(row):
        return normalize_name(row.get("courier_name", ""))

    def row_id_key(row):
        courier_id = str(row.get("courier_id") or "").strip()
        return courier_id if courier_id and courier_id.lower() != "nan" else ""

    status_by_id, status_by_name = _latest_rows_by_action(status_df)

    try:
        documents_df = read_peopleforce_documents_for_month(month_start)
    except Exception as exc:
        st.warning(f"A havi dokumentumlista nem tölthető be: {exc}")
        documents_df = pd.DataFrame()

    documents_by_name = {}
    documents_by_id = {}
    if not documents_df.empty:
        for _, document_row in documents_df.iterrows():
            name_key = row_name_key(document_row)
            id_key = row_id_key(document_row)
            if name_key:
                documents_by_name.setdefault(name_key, []).append(document_row)
            if id_key:
                documents_by_id.setdefault(id_key, []).append(document_row)

    open_complaints_by_name = {}
    open_complaints_by_id = {}
    if not complaints_df.empty:
        status_series = complaints_df.get("status", pd.Series(dtype=str))
        open_complaints = complaints_df[
            ~status_series.astype(str).str.strip().str.lower().isin(
                ["resolved", "closed", "done"]
            )
        ].copy()
        for _, complaint_row in open_complaints.iterrows():
            name_key = row_name_key(complaint_row)
            id_key = row_id_key(complaint_row)
            if name_key:
                open_complaints_by_name.setdefault(name_key, []).append(complaint_row)
            if id_key:
                open_complaints_by_id.setdefault(id_key, []).append(complaint_row)

    if not status_df.empty:
        for _, status_row in status_df.iterrows():
            name = str(status_row.get("courier_name") or "").strip()
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
    amount_by_name = _invoice_amount_by_name(driver_summary)
    summary_rows_by_name = _invoice_summary_rows_by_name(driver_summary)
    feedback_rows = []
    closed_count = 0
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

        settlement_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "settlement"
        )
        tig_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "tig"
        )
        invoice_check_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "invoice_check"
        )
        invoice_submit_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "invoice_submit"
        )
        invoice_payment_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "invoice_payment"
        )
        invoice_override_status = _status_for_action(
            status_by_id,
            status_by_name,
            courier_id,
            name_key,
            "invoice_validation_override",
        )
        monthly_close_status = _status_for_action(
            status_by_id, status_by_name, courier_id, name_key, "monthly_close"
        )
        invoice_override_enabled = (
            invoice_override_status is not None
            and str(invoice_override_status.get("status") or "").strip().lower() == "done"
        )
        process_is_done = any(
            status is not None and str(status.get("status") or "").strip().lower() == "done"
            for status in (invoice_payment_status, monthly_close_status)
        )
        if process_is_done:
            closed_count += 1
            continue
        status_row = settlement_status
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
        document_types, courier_documents = _document_types_for_courier(
            documents_by_id, documents_by_name, courier_id, name_key
        )
        if not uploaded_at:
            settlement_documents = [
                row for row in courier_documents
                if str(row.get("document_type") or "").lower() == "settlement"
            ]
            if settlement_documents:
                uploaded_at = str(settlement_documents[0].get("uploaded_at") or "").strip()
                has_uploaded_document = bool(uploaded_at)

        if complaint_rows:
            row_state = "help"
            lamp = "Piros"
            complaint = complaint_rows[0]
            complaint_type = str(complaint.get("document_type") or "").lower()
            workflow_priority = {
                "invoice": 55,
                "tig": 35,
                "settlement": 15,
            }.get(complaint_type, 0)
            complaint_labels = {"invoice": "számlafeltöltés", "tig": "TIG", "settlement": "elszámolás"}
            reason = str(complaint.get("message") or status_note or "Nincs megadott indok.").strip()
            step = f"Admin segítségére vár ({complaint_labels.get(complaint_type, complaint_type or 'folyamat')})"
            courier_feedback = "Segítséget kér"
            note = reason
        elif "settlement" not in document_types and not has_uploaded_document:
            row_state = "missing"
            lamp = "Szürke"
            workflow_priority = 10
            step = "Elszámolás elkészítésére és kiküldésére vár"
            courier_feedback = "Admin feladat"
            note = "Még nincs elszámolás feltöltve."
        elif status_value != "done":
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 20
            step = "A futár elszámolás-elfogadására vár"
            courier_feedback = "Futárnál"
            note = status_note or "Az elszámolás feltöltve."
        elif "tig" not in document_types:
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 30
            step = "TIG elkészítésére és feltöltésére vár"
            courier_feedback = "Admin feladat"
            note = "Az elszámolást a futár elfogadta."
        elif tig_status is None or str(tig_status.get("status") or "").lower() != "done":
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 35
            step = "A futár TIG-elfogadására vár"
            courier_feedback = "Futárnál"
            note = str(tig_status.get("status_note") or "A TIG feltöltve.") if tig_status is not None else "A TIG feltöltve."
        elif invoice_check_status is None or str(invoice_check_status.get("status") or "").lower() != "done":
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 40
            check_note = (
                str(invoice_check_status.get("status_note") or "").strip()
                if invoice_check_status is not None
                else ""
            )
            if check_note:
                if invoice_override_enabled:
                    step = "Számla továbbengedve; új ellenőrzésre vár"
                    note = f"{check_note} | Admin engedéllyel továbbengedve."
                else:
                    step = "Számlahiba javítására vár"
                    note = check_note
            else:
                step = "A futár számlaellenőrzésére vár"
                note = "A TIG-et a futár elfogadta, a számla ellenőrzése még nem készült el."
            courier_feedback = "Futárnál"
        elif invoice_submit_status is None or str(invoice_submit_status.get("status") or "").lower() != "done":
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 50
            submit_note = (
                str(invoice_submit_status.get("status_note") or "").strip()
                if invoice_submit_status is not None
                else ""
            )
            if submit_note:
                if invoice_override_enabled:
                    step = "Számla továbbengedve; új feltöltésre vár"
                    note = f"{submit_note} | Admin engedéllyel továbbengedve."
                else:
                    step = "Számlafeltöltési hiba javítására vár"
                    note = submit_note
            else:
                step = "A futár számlafeltöltésére vár"
                note = "A számlaellenőrzés kész, a feltöltés még nincs befejezve."
            courier_feedback = "Futárnál"
        elif "invoice" not in document_types:
            row_state = "waiting"
            lamp = "Sárga"
            workflow_priority = 55
            step = "A számladokumentum eltárolására vár"
            courier_feedback = "Rendszerfeladat"
            note = "A feltöltési státusz kész, de a számladokumentum nem található."
        elif invoice_payment_status is None or str(invoice_payment_status.get("status") or "").lower() != "done":
            row_state = "waiting"
            lamp = "Kék"
            workflow_priority = 60
            step = "Admin számlaelfogadására és kifizetésre vár"
            courier_feedback = "Admin feladat"
            note = (
                str(invoice_payment_status.get("status_note") or "").strip()
                if invoice_payment_status is not None
                else "A számla feltöltve; admin elfogadás és kifizetés szükséges."
            )
        else:
            closed_count += 1
            continue

        bank_account = first_invoice_contact_value(master_row, "bank_account_number")
        transfer_amount = amount_by_name.get(name_key, 0)
        summary_row = summary_rows_by_name.get(name_key, {})
        workflow_statuses = [
            settlement_status,
            tig_status,
            invoice_check_status,
            invoice_submit_status,
            invoice_payment_status,
            invoice_override_status,
        ]
        latest_update = max(
            [str(status.get("updated_at") or "") for status in workflow_statuses if status is not None]
            + [uploaded_at or ""]
        )
        help_reason = note if complaint_rows else "-"
        invoice_error_note = ""
        if invoice_check_status is not None and str(invoice_check_status.get("status") or "").lower() != "done":
            candidate = str(invoice_check_status.get("status_note") or "").strip()
            if "hiba" in candidate.lower():
                invoice_error_note = candidate
        if not invoice_error_note and invoice_submit_status is not None and str(invoice_submit_status.get("status") or "").lower() != "done":
            candidate = str(invoice_submit_status.get("status_note") or "").strip()
            if "hiba" in candidate.lower():
                invoice_error_note = candidate

        feedback_rows.append(
            {
                "Lámpa": lamp,
                "Futár": name,
                "Courier ID": courier_id or "-",
                "Bankszámlaszám": format_bank_account_number(bank_account),
                "Utalandó összeg": format_huf(transfer_amount),
                "Mire vár?": step,
                "Futár visszajelzés": courier_feedback,
                "Segítségkérés oka": help_reason,
                "Feltöltve": uploaded_at or "-",
                "Utolsó frissítés": updated_at or uploaded_at or "-",
                "E-mail": contact_email or "-",
                "Belépett": "Igen" if has_logged_in else "Nem",
                "Megjegyzés": note or "-",
                "_state": row_state,
                "_email": contact_email,
                "_username": username,
                "_has_logged_in": has_logged_in,
                "_courier_id": courier_id,
                "_tig_amount": transfer_amount,
                "_worksheet_name": str(summary_row.get("worksheet_name") or ""),
                "_updated_at": latest_update,
                "_workflow_priority": workflow_priority,
                "_invoice_error_note": invoice_error_note,
                "_invoice_override_available": bool(invoice_error_note) and not invoice_override_enabled,
                "_invoice_override_enabled": invoice_override_enabled,
                "_invoice_override_note": (
                    str(invoice_override_status.get("status_note") or "").strip()
                    if invoice_override_status is not None
                    else ""
                ),
            }
        )

    feedback_df = pd.DataFrame(feedback_rows)
    state_series = feedback_df.get("_state", pd.Series(dtype=str))
    help_count = int((state_series == "help").sum()) if not feedback_df.empty else 0
    waiting_count = int((state_series == "waiting").sum()) if not feedback_df.empty else 0
    completion = (closed_count / total_count * 100) if total_count else 0

    st.subheader("Nyitott havi feladatok")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Várakozó (db)", len(feedback_rows))
    metric2.metric("Utalandó összesen", format_huf(sum(row.get("_tig_amount", 0) for row in feedback_rows)))
    metric3.metric("Segítséget kér", help_count)
    metric4.metric("Már lezárt", closed_count)

    sub1, sub2 = st.columns(2)
    sub1.metric("Futárra vagy adminra vár", waiting_count)
    sub2.metric("Még nincs kiküldve", int((state_series == "missing").sum()) if not feedback_df.empty else 0)

    if total_count:
        st.progress(min(max(completion / 100, 0), 1))

    _render_invoice_task_rows(feedback_rows, month_start)

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
                    resend_candidates[["Futár", "Courier ID", "E-mail", "Mire vár?"]],
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
                            sent_rows.append({"Futar": candidate["Futár"], "Allapot": "Elkuldve", "Hiba": ""})
                        except Exception as exc:
                            sent_rows.append({"Futar": candidate["Futár"], "Allapot": "Hiba", "Hiba": str(exc)})
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

def show_new_invoice_summary_page():
    st.title("Új Elszámolási oldal")
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
        key="new_invoice_start_date",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today,
        key="new_invoice_end_date",
    )
    selected_sheet = col3.selectbox(
        "Raktar ful",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="new_invoice_sheet_filter",
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

    try:
        current_invoice_documents = read_peopleforce_documents_for_month(
            start_date.replace(day=1),
            document_type="settlement",
        )
    except Exception as exc:
        current_invoice_documents = pd.DataFrame()
        st.warning(f"A jelenlegi elszámolások darabszáma nem olvasható: {exc}")

    invoice_regeneration_candidates = build_invoice_regeneration_candidates(
        data.get("final", pd.DataFrame()),
        current_invoice_documents,
    )
    st.subheader("Újragenerálandó számlák")
    if invoice_regeneration_candidates.empty:
        st.success("Nincs több raktárban szereplő, újragenerálandó futár.")
    st.dataframe(
        invoice_regeneration_candidates,
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Újragenerálandó számlák CSV export",
        data=invoice_regeneration_candidates.to_csv(index=False).encode("utf-8-sig"),
        file_name=(
            f"invoice_regeneration_candidates_{start_date.isoformat()}_"
            f"{end_date.isoformat()}.csv"
        ),
        mime="text/csv",
        use_container_width=True,
    )

    all_period_final_df = data["final"].copy()
    final_df = all_period_final_df.copy()
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

    from page.invoice_feedback_legacy import render_legacy_invoice_delivery_status

    render_legacy_invoice_delivery_status(drivers, start_date)

    selected_driver = col4.selectbox(
        "Futar",
        ["Mind"] + drivers,
        key="new_invoice_driver_filter",
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
        target_reserve_df=data.get("target_reserve", pd.DataFrame()),
        period_start=start_date,
    )

    # PDFs and Peopleforce uploads always use the complete period across every
    # warehouse, independently from the warehouse filter used by the screen.
    pdf_final_df = filter_by_driver(all_period_final_df, selected_driver)
    pdf_driver_summary = build_driver_invoice_summary(
        pdf_final_df,
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

    st.subheader("Futár összesítő")
    st.caption(
        "Az Express, City és Régió darabszám route ID alapján készül. "
        "A túramegfelelési díj a route-számítás és a havi bónusz tábla összege."
    )
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
            pdf_driver_summary,
            pdf_final_df,
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
            st.subheader("Tömeges elszámolás-feltöltés")
            st.caption(
                "A rendszer futáronként egy PDF-et készít az időszak összes "
                "raktári adatából, majd ezt tölti fel a Peopleforce profilba."
            )

            # Bulk upload is period-wide and uses one already consolidated row
            # per courier.
            bulk_rows = pdf_driver_summary.reset_index(drop=True)
            bulk_sheet = "Minden raktár – futáronként összevonva"
            bulk_upload_count = len(bulk_rows)
            st.caption(
                "A feltöltés minden raktár adatát egyetlen futár-PDF-ben használja."
            )
            st.info(
                "Hatókör: minden raktár, futáronként összevonva | "
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
                    f"Megerősítem {bulk_upload_count} futár egyesített "
                    "elszámolásának feltöltését."
                ),
                key=(
                    f"invoice_bulk_upload_confirm_{start_date.isoformat()}_"
                    f"{end_date.isoformat()}_{bulk_sheet}"
                ),
            )

            if st.button(
                "Egyesített elszámolások feltöltése",
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
                        single_routes = filter_by_driver(
                            all_period_final_df,
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
                tig_source_rows = pdf_driver_summary.reset_index(drop=True)
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
            selected_row = pdf_driver_summary.iloc[0]
            courier_id, courier_name = resolve_courier_identity(
                selected_row,
                selected_driver,
            )

            if st.button(
                "Elszámolás feltöltése a futár profiljába",
                use_container_width=True,
                key="new_invoice_send_to_courier_card",
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
            key="new_invoice_manual_date",
        )
        manual_sheet = form_col2.selectbox(
            "Raktar ful",
            ["BUD1_JIT", "BUD2_JIT"],
            key="new_invoice_manual_sheet",
        )
        manual_driver_options = drivers or sorted(
            value
            for value in final_df.get("driver_name", pd.Series(dtype=str)).dropna().astype(str).unique()
            if value.strip()
        )
        manual_driver = form_col3.selectbox(
            "Futar",
            manual_driver_options,
            key="new_invoice_manual_driver",
        )
        form_col4, form_col5 = st.columns([1, 1])
        manual_type = form_col4.selectbox(
            "Tetel tipusa",
            list(MANUAL_ITEM_TYPES.keys()),
            format_func=lambda value: MANUAL_ITEM_TYPES[value],
            key="new_invoice_manual_type",
        )
        manual_amount = form_col5.number_input(
            "Osszeg Ft",
            value=0,
            step=500,
            key="new_invoice_manual_amount",
        )
        manual_note = st.text_input(
            "Megjegyzes",
            key="new_invoice_manual_note",
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
