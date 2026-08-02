from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


GREEN = colors.HexColor("#2f7d32")
RED = colors.HexColor("#e00000")
ORANGE = colors.HexColor("#ff9800")
BLUE = colors.HexColor("#0b57d0")
LIGHT_BORDER = colors.HexColor("#dddddd")
LIGHT_BG = colors.HexColor("#fafafa")
MUTED = colors.HexColor("#666666")


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


def _month_label(value: Any) -> str:
    if isinstance(value, date):
        months = [
            "január", "február", "március", "április", "május", "június",
            "július", "augusztus", "szeptember", "október", "november", "december",
        ]
        return f"{value.year}. {months[value.month - 1]}"
    text = str(value or "").strip()
    return text or "-"


def _styles(regular: str, bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=bold, fontSize=18, leading=22, alignment=0),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=bold, fontSize=21, leading=25),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=bold, fontSize=13, leading=17),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=regular, fontSize=9.2, leading=12),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=regular, fontSize=8, leading=10, textColor=MUTED),
        "red": ParagraphStyle("red", parent=base["BodyText"], fontName=bold, fontSize=11, leading=14, textColor=RED, alignment=1),
        "center": ParagraphStyle("center", parent=base["BodyText"], fontName=regular, fontSize=9.5, leading=12, alignment=1),
        "big_green": ParagraphStyle("big_green", parent=base["Title"], fontName=bold, fontSize=24, leading=28, textColor=colors.HexColor("#39df43"), alignment=1),
    }


def _table(data: list[list[Any]], widths: list[float], style: list[tuple]) -> Table:
    table = Table(data, colWidths=widths, hAlign="CENTER")
    table.setStyle(TableStyle(style))
    return table


def _email_header(story: list[Any], title: str, courier: dict[str, Any], styles: dict[str, ParagraphStyle], regular: str, bold: str) -> None:
    account = courier.get("email") or "elszamolas@jitt.hu"
    story.append(_table(
        [["Gmail", f"{courier.get('name', '')} <{account}>"]],
        [125 * mm, 125 * mm],
        [
            ("FONTNAME", (0, 0), (0, 0), bold),
            ("FONTSIZE", (0, 0), (0, 0), 21),
            ("TEXTCOLOR", (0, 0), (0, 0), RED),
            ("FONTNAME", (1, 0), (1, 0), bold),
            ("FONTSIZE", (1, 0), (1, 0), 9),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 0.7, colors.HexColor("#999999")),
        ],
    ))
    story += [Spacer(1, 4 * mm), Paragraph(title, styles["title"])]
    story.append(_table(
        [[Paragraph(f"Zoltán Bagoly &lt;zoltan.bagoly@jitt.hu&gt;<br/>Címzett: {account}", styles["body"]), _month_label(courier.get("document_month"))]],
        [170 * mm, 80 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LINEABOVE", (0, 0), (-1, -1), 0.7, colors.HexColor("#999999")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ],
    ))
    story.append(Spacer(1, 8 * mm))


def _document_header(story: list[Any], title: str, courier: dict[str, Any], period: str, styles: dict[str, ParagraphStyle], regular: str, bold: str) -> None:
    story.append(_table(
        [[Paragraph(f"<b>{title}</b>", styles["title"]), Paragraph(f"Elszámolási hónap:<br/><b>{period}</b>", styles["body"])]],
        [170 * mm, 70 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 1.2, RED),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ],
    ))
    story.append(Paragraph(f"{courier.get('name', '')} | Futár ID: {courier.get('id', '')}", styles["body"]))
    story.append(Spacer(1, 8 * mm))


def build_settlement_pdf(courier: dict[str, Any], routes: list[dict[str, Any]], amounts: dict[str, float]) -> bytes:
    regular, bold = _font_names()
    styles = _styles(regular, bold)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=12 * mm,
    )
    period = _month_label(courier.get("document_month"))
    total_income = (
        float(amounts.get("base") or 0)
        + float(amounts.get("tip") or 0)
        + float(amounts.get("bonus") or 0)
        + float(amounts.get("customer_rating") or 0)
    )
    total_expense = (
        float(amounts.get("malus") or 0)
        + float(amounts.get("atm") or 0)
        + float(amounts.get("other") or 0)
        + float(amounts.get("salary_advance") or 0)
        + float(amounts.get("reserve") or 0)
        + float(amounts.get("insurance") or 0)
    )
    payable = float(amounts.get("payable") or (total_income - total_expense))
    deliveries = int(sum(float(item.get("Rendelések") or item.get("Címek") or 0) for item in routes) or 0)
    index_value = total_income / max(deliveries, 1)

    story: list[Any] = []
    _document_header(story, "Összesítő", courier, period, styles, regular, bold)
    story.append(_table(
        [[
            Paragraph(f"<b>{courier.get('name', '')}</b><br/><br/>", styles["h1"]),
            Paragraph(f"Időszak: <b>{period}</b>", styles["body"]),
        ]],
        [180 * mm, 70 * mm],
        [
            ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, RED),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 14),
        ],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [[Paragraph("<b>TELJESÍTMÉNY INDEX</b><br/><br/>Minden egyes kiszállított címed átlagosan ennyit ért ebben a hónapban:<br/><br/>"
                    f"<font size='18'><b>kb. {_money(index_value)} / {deliveries}</b></font><br/>FT / KISZÁLLÍTOTT CÍM", styles["center"])]],
        [250 * mm],
        [
            ("BOX", (0, 0), (-1, -1), 1.2, ORANGE),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#e65100")),
            ("PADDING", (0, 0), (-1, -1), 16),
        ],
    ))
    story.append(Spacer(1, 7 * mm))
    story.append(_table(
        [
            [Paragraph("<b>ALAPADATOK ÉS CÉLTARTALÉK</b>", styles["body"]), Paragraph("<b>BÓNUSZOK ÉS TELJESÍTMÉNY</b>", styles["body"])],
            [
                Paragraph(
                    f"Alap címpénz (Ft/db): <b>{int(amounts.get('base_rate') or 0) or '-'}</b><br/>"
                    f"Nyitó céltartalék: <b>{_money(amounts.get('reserve_before'))}</b><br/>"
                    f"Feltöltés (+): <b>{_money(amounts.get('reserve'))}</b><br/>"
                    f"<font color='red'><b>Záró egyenleg: {_money(amounts.get('reserve_after'))}</b></font>",
                    styles["body"],
                ),
                Paragraph(
                    f"Normál / DSP címek: <b>{deliveries} / 0</b><br/>"
                    f"Just in Time / Értékelés: <b>{_money(amounts.get('bonus'))} / {_money(amounts.get('customer_rating'))}</b><br/>"
                    f"<font color='green'><b>Minőségi Prémium Alap: + {_money(amounts.get('customer_rating'))}</b></font><br/>"
                    f"Sorzók összesen: <b>{_money(amounts.get('base_rate'))}</b>",
                    styles["body"],
                ),
            ],
        ],
        [122 * mm, 122 * mm],
        [
            ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 10),
        ],
    ))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("KP Elszámolás: az automata által be nem fizetett KP a bevételi oldalon üzemanyagként jelenik meg.", styles["body"]))
    story.append(Spacer(1, 4 * mm))
    rows = [
        ["Bevételek", "Ft", "Kiadások", "Ft"],
        ["Szállítási díj:", _money(amounts.get("base")), "Maluszok", _money(amounts.get("malus"))],
        ["DSP (Alap + Bónusz):", f"{_money(amounts.get('base'))} + {_money(amounts.get('bonus'))}", "Károkozás:", _money(amounts.get("damage"))],
        ["Délutáni / Hétvégi b.:", _money(amounts.get("weekend_bonus")), "Telefonhasználat:", _money(amounts.get("phone"))],
        ["EXP / Normál kör (EXP):", _money(amounts.get("express_bonus")), "Biztosítás:", _money(amounts.get("insurance"))],
        ["Minőségi Prémium / CT Felh.:", _money(amounts.get("customer_rating")), "Be nem fiz. KP", _money(amounts.get("atm"))],
        ["Táska / Borravaló / Oktatás:", _money(amounts.get("tip")), "Egyéb (Eszköz/Kár):", _money(amounts.get("other"))],
        ["Üzemanyag megelőleg.", _money(amounts.get("fuel_advance")), "Céltartalék képzése(+):", _money(amounts.get("reserve"))],
        ["BEVÉTELEK ÖSSZESEN", _money(total_income), "KIADÁSOK ÖSSZESEN", _money(total_expense)],
    ]
    story.append(_table(
        rows,
        [75 * mm, 45 * mm, 75 * mm, 45 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTNAME", (0, -1), (-1, -1), bold),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#aaaaaa")),
            ("TEXTCOLOR", (2, 1), (2, -2), colors.black),
            ("TEXTCOLOR", (3, 4), (3, 5), colors.HexColor("#c62828")),
            ("GRID", (0, 0), (-1, -1), 0.35, LIGHT_BORDER),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 7),
        ],
    ))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("PÉNZÜGYILEG RENDEZENDŐ EGYENLEG:", styles["center"]))
    story.append(Paragraph(_money(payable), styles["big_green"]))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [[Paragraph("<b>Elvétett lehetőségek részletezése:</b><br/><br/>Késés (0,5% alatt): <b>0 Ft</b><br/>Mennyiség (750 felett): <b>0 Ft</b>", styles["body"]),
          Paragraph("<br/><br/>Értékelés (4,92 felett): <b>0 Ft</b><br/>Folyamatok/Foglalás: <b>0 Ft</b>", styles["body"])]],
        [120 * mm, 120 * mm],
        [("BOX", (0, 0), (-1, -1), 0.8, ORANGE), ("PADDING", (0, 0), (-1, -1), 10)],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Javított részletező. Észrevétel: elszamolas@jitt.hu | Kifizetés: 18.-ig.", styles["small"]))
    doc.build(story)
    return buffer.getvalue()


def build_tig_pdf(courier: dict[str, Any], amounts: dict[str, float]) -> bytes:
    regular, bold = _font_names()
    styles = _styles(regular, bold)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=12 * mm,
    )
    period = _month_label(courier.get("document_month"))
    gross = float(amounts.get("payable") or 0)
    courier_id = str(courier.get("id") or "")
    story: list[Any] = []
    _document_header(story, f"TIG {period}-ra", courier, period, styles, regular, bold)
    story.append(_table(
        [[Paragraph(
            f"<font color='red'><b>Tisztelt {str(courier.get('company_name') or courier.get('name') or '').upper()}!</b></font><br/><br/>"
            "<font size='18'><b>KÉRJÜK FIGYELMESEN ELOLVASNI VÉGIG!</b></font><br/><br/>"
            "<font color='#999999'><b>KLIKK IDE: SZÁMLABEFOGADÓ RENDSZER</b></font><br/><br/>"
            "<font color='red'><b>A számlákat e-mailben nem tudjuk fogadni! Csak az itt feltöltött bizonylatokat tudjuk feldolgozni és fizetni.</b></font>",
            styles["center"],
        )]],
        [250 * mm],
        [("BOX", (0, 0), (-1, -1), 1.2, RED), ("PADDING", (0, 0), (-1, -1), 16)],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [
            [
                Paragraph("<b>PRO TIPP: Quick kérelem</b><br/>Ha a számlázódban fizetési kérelmet küldesz, előre veszed magad a kifizetési sorban.", styles["body"]),
                Paragraph("<b>Banki adatok:</b><br/>Kérjük, ellenőrizd a bankszámlaszámod a számlán! Ha eltér, jelezd a feltöltésnél.", styles["body"]),
            ]
        ],
        [120 * mm, 120 * mm],
        [
            ("BOX", (0, 0), (0, 0), 0.8, GREEN),
            ("BOX", (1, 0), (1, 0), 0.8, ORANGE),
            ("PADDING", (0, 0), (-1, -1), 10),
        ],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("TELJESÍTÉSI IGAZOLÁS", styles["h1"]))
    story.append(_table(
        [
            [Paragraph("<b>SZOLGÁLTATÓ (ELADÓ):</b>", styles["small"]), Paragraph("<b>MEGBÍZÓ (VEVŐ):</b>", styles["small"])],
            [
                Paragraph(
                    f"<b>{courier.get('company_name') or courier.get('name') or ''}</b><br/>"
                    f"<font color='blue'>{courier.get('address') or ''}</font><br/>"
                    f"Adószám: <b>{courier.get('tax_number') or '-'}</b>",
                    styles["body"],
                ),
                Paragraph("<font color='red'><b>Just in Time Transport Hungary Kft.</b><br/>1201 Budapest, Atléta utca 44<br/>Adószám: 32649460-2-43</font>", styles["body"]),
            ],
        ],
        [115 * mm, 115 * mm],
        [("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER), ("PADDING", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP")],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [
            ["Számlázott időszak", "Teljesítés napja", "Fizetési határidő", "Fizetés módja"],
            [period, "Kiállítás napja + 8 nap", "Kiállítás napja + 8 nap", "Átutalás"],
        ],
        [58 * mm, 65 * mm, 65 * mm, 42 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTNAME", (0, 1), (-1, 1), bold),
            ("TEXTCOLOR", (1, 1), (2, 1), RED),
            ("GRID", (0, 0), (-1, -1), 0.35, LIGHT_BORDER),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("PADDING", (0, 0), (-1, -1), 8),
        ],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [
            ["Tétel megnevezése", "Nettó (Ft)", "ÁFA (Ft)", "Bruttó (Ft)"],
            [f"Szállítási díj ({courier.get('document_reference') or courier_id})", _money(gross), "AAM", _money(gross)],
            ["", "", "VÉGÖSSZEG:", _money(gross)],
        ],
        [90 * mm, 50 * mm, 42 * mm, 48 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTNAME", (2, -1), (-1, -1), bold),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#999999")),
            ("TEXTCOLOR", (3, -1), (3, -1), RED),
            ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#333333")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 8),
        ],
    ))
    story.append(Spacer(1, 5 * mm))
    story.append(_table(
        [[Paragraph(f"<b>Megjegyzésbe kötelező az azonosító:</b> <font color='red'><b>{courier_id}</b></font>", styles["body"])]],
        [230 * mm],
        [("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#777777")), ("PADDING", (0, 0), (-1, -1), 9)],
    ))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("<b>SZÁMLÁZÁSI SZABÁLYOK:</b><br/>- A teljesítési és fizetési határidőt is a kiállítás napja + 8 napra állítsd!<br/>- Hibás számla esetén nettó 5.000 Ft adminisztrációs költséget érvényesítünk.", styles["body"]))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("Gépi úton készült igazolás, aláírás nélkül is hiteles.<br/><b>Just in Time Transport Hungary Kft.</b><br/>Észrevétel és kifogások: elszamolas@jitt.hu", styles["center"]))
    doc.build(story)
    return buffer.getvalue()
