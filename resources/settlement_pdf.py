from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _font_names() -> tuple[str, str]:
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("Settlement-Regular", str(regular)))
            pdfmetrics.registerFont(TTFont("Settlement-Bold", str(bold)))
            return "Settlement-Regular", "Settlement-Bold"
    return "Helvetica", "Helvetica-Bold"


def _money(value: Any) -> str:
    return f"{float(value or 0):,.0f} Ft".replace(",", " ")


def build_settlement_pdf(courier: dict[str, Any], routes: list[dict[str, Any]], amounts: dict[str, float]) -> bytes:
    regular, bold = _font_names()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName=bold, fontSize=20, leading=25, textColor=colors.HexColor("#17351F"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=regular, fontSize=9, leading=12)
    section = ParagraphStyle("section", parent=body, fontName=bold, fontSize=12, textColor=colors.HexColor("#17351F"))
    story = [Paragraph("JITT - Futár elszámolás", title), Spacer(1, 4 * mm)]
    header = [[f"Futár: {courier.get('name', '')}", f"Courier ID: {courier.get('id', '')}"], [f"Branch: {courier.get('branch', 'JIT')} | Raktár: {courier.get('warehouse', '')}", f"Státusz: {courier.get('status', '')}"]]
    table = Table(header, colWidths=[110 * mm, 65 * mm])
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F7F3")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#C9D8CC")), ("PADDING", (0, 0), (-1, -1), 7)]))
    story += [table, Spacer(1, 6 * mm), Paragraph("Teljesítés route-típus és naptípus szerint", section), Spacer(1, 2 * mm)]
    route_rows = [["Túratípus", "Naptípus", "Túrák", "Alapdíj", "Borravaló", "Bónuszok"]]
    for item in routes:
        route_rows.append([str(item.get("Túratípus", "")), str(item.get("Naptípus", "")), str(int(item.get("Túrák", 0))), _money(item.get("Alapdíj")), _money(item.get("Borravaló")), _money(item.get("Bónuszok"))])
    route_table = Table(route_rows, colWidths=[30 * mm, 31 * mm, 17 * mm, 32 * mm, 31 * mm, 34 * mm])
    route_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTNAME", (0, 0), (-1, 0), bold), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17351F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD8CF")), ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story += [route_table, Spacer(1, 6 * mm), Paragraph("Havi elszámolás", section), Spacer(1, 2 * mm)]
    labels = [("Alapdíj", "base"), ("Borravaló", "tip"), ("Bónuszok", "bonus"), ("Máluszok", "malus"), ("ATM levonás", "atm"), ("Egyéb kiadás", "other"), ("Ügyfélértékelési bónusz", "customer_rating"), ("Kifizetendő", "payable")]
    summary_rows = [["Tétel", "Összeg"]] + [[label, _money(amounts.get(key))] for label, key in labels]
    summary = Table(summary_rows, colWidths=[110 * mm, 65 * mm])
    summary.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, -1), (-1, -1), bold), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17351F")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DFF1E4")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD8CF")), ("ALIGN", (1, 1), (1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 7)]))
    story += [summary, Spacer(1, 7 * mm), Paragraph("A dokumentum az aktuális elszámolási adatokból készült.", body)]
    doc.build(story)
    return buffer.getvalue()
