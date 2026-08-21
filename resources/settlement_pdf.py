from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
import unicodedata

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


def _int_money(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _tax_number_is_vat_payer(value: Any) -> bool:
    parts = str(value or "").replace(" ", "").split("-")
    return len(parts) >= 2 and parts[1] == "2"


def _ascii_tax_text(value: Any) -> str:
    text = str(value or "").casefold()
    replacements = {
        "Ăˇ": "a", "Ă©": "e", "Ă­": "i", "Ăł": "o", "Ă¶": "o",
        "Ĺ‘": "o", "Ăş": "u", "ĂĽ": "u", "Ĺ±": "u",
        "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o",
        "ő": "o", "ú": "u", "ü": "u", "ű": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _tig_kind(courier: dict[str, Any]) -> str:
    fields = [
        courier.get("tig_type"),
        courier.get("tig_mode"),
        courier.get("invoice_type"),
        courier.get("invoice_vat_type"),
        courier.get("vat_status"),
        courier.get("afa_status"),
    ]
    text = " ".join(str(value or "") for value in fields).casefold()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ö", "o")
        .replace("ő", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ű", "u")
    )
    text = _ascii_tax_text(text)
    employment_fields = [
        courier.get("employment_type"),
        courier.get("employment_status"),
        courier.get("employment"),
        courier.get("jogviszony"),
        courier.get("efo_status"),
    ]
    employment_text = _ascii_tax_text(" ".join(str(value or "") for value in employment_fields).casefold())
    if "efo" in employment_text or "efo" in text:
        return "aam"
    if "ellenoriz" in text or "ellenorz" in text:
        return "aam"
    if any(token in text for token in ["aam", "alanyi", "ado mentes", "adomentes", "nem afas", "nem afa", "non vat"]):
        return "aam"
    if any(token in text for token in ["afas", "afa", "vat", "27", "belfoldi adoalany", "belfoldi ado alany"]):
        return "vat"
    return "vat" if _tax_number_is_vat_payer(courier.get("tax_number")) else "aam"


def _split_gross_vat_amount(gross: Any) -> tuple[int, int, int]:
    gross_value = max(_int_money(gross), 0)
    net = int(round(gross_value / 1.27))
    vat = gross_value - net
    return net, vat, gross_value


def _add_vat_to_net(net: Any) -> tuple[int, int, int]:
    net_value = max(_int_money(net), 0)
    vat = int(round(net_value * 0.27))
    return net_value, vat, net_value + vat


def _document_month(value: Any) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10]).replace(day=1)
    except ValueError:
        return date.today().replace(day=1)


def _tig_document_dates(courier: dict[str, Any]) -> dict[str, str]:
    month_start = _document_month(courier.get("document_month"))
    month_end = month_start.replace(day=monthrange(month_start.year, month_start.month)[1])
    due_date = date.today() + timedelta(days=8)
    return {
        "periodStart": month_start.isoformat(),
        "periodEnd": month_end.isoformat(),
        "periodLabel": f"{month_start:%Y.%m.%d} - {month_end:%Y.%m.%d}",
        "performanceDate": due_date.isoformat(),
        "paymentDueDate": due_date.isoformat(),
        "note": f"Futár ID: {courier.get('id') or courier.get('courier_id') or '-'}",
    }


def _tig_cash_net_deduction(cash_amount_huf: Any, courier: dict[str, Any]) -> int:
    cash = max(_int_money(cash_amount_huf), 0)
    if _tig_kind(courier) == "vat":
        return _split_gross_vat_amount(cash)[0]
    return cash


def _tig_service_amount_without_cash_and_tip(amounts: dict[str, float], courier: dict[str, Any]) -> int:
    explicit_service = amounts.get("service") or amounts.get("service_amount") or amounts.get("transfer_service")
    if explicit_service is not None:
        return max(_int_money(explicit_service), 0)
    payable = max(_int_money(amounts.get("payable")), 0)
    tip = max(_int_money(amounts.get("tip") or amounts.get("tip_amount")), 0)
    return max(payable - tip, 0)


def build_tig_breakdown(courier: dict[str, Any], amounts: dict[str, float]) -> dict[str, Any]:
    service = _tig_service_amount_without_cash_and_tip(amounts, courier)
    cash = max(_int_money(amounts.get("cash") or amounts.get("cash_amount")), 0)
    tip = max(_int_money(amounts.get("tip") or amounts.get("tip_amount")), 0)
    payable = max(_int_money(amounts.get("payable")), 0)
    vat_payer = _tig_kind(courier) == "vat"
    if vat_payer:
        service_net, service_vat, service_gross = _add_vat_to_net(service)
        cash_net, cash_vat, cash_gross = _split_gross_vat_amount(cash)
        tax_label = "27%-os AFA"
    else:
        service_net, service_vat, service_gross = service, 0, service
        cash_net, cash_vat, cash_gross = cash, 0, cash
        tax_label = "AAM"
    final_total = max(service_gross + tip, 0)
    rows = [
        {
            "key": "transfer_service",
            "label": "Szállítási díj (494107) - átutalás",
            "netHuf": service_net,
            "vatHuf": service_vat,
            "grossHuf": service_gross,
            "vatLabel": "27%" if vat_payer else "AAM",
            "note": "KP és borravaló nélküli szolgaltátasi dij.",
        }
    ]
    if tip:
        tip_net, tip_vat, tip_gross = tip, 0, tip
        tip_vat_label = "TAM"
        rows.append({
            "key": "tip",
            "label": "Borravaló",
            "netHuf": tip_net,
            "vatHuf": tip_vat,
            "grossHuf": tip_gross,
            "vatLabel": tip_vat_label,
            "note": "Külön tétel.",
        })
    if cash:
        rows.append({
            "key": "cash_service",
            "label": "Szállítási díj (494107) - készpénz",
            "netHuf": cash_net,
            "vatHuf": cash_vat,
            "grossHuf": cash_gross,
            "vatLabel": "27%" if vat_payer else "AAM",
            "note": "Külön KP sor, nem növeli az átutalásos végösszeget.",
        })
    return {
        "available": payable > 0 or bool(rows),
        "payableHuf": payable,
        "transferServiceHuf": service,
        "tipHuf": tip,
        "cashGrossHuf": cash_gross,
        "cashNetDeductionHuf": cash_net,
        "cashVatHuf": cash_vat,
        "finalTotalHuf": final_total,
        "taxMode": "vat" if vat_payer else "aam",
        "taxLabel": tax_label,
        "documentMeta": _tig_document_dates(courier),
        "rows": rows,
    }


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


def _tig_pdf_rows_from_breakdown(tig_breakdown: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int] | None:
    if not isinstance(tig_breakdown, dict):
        return None
    rows = [row for row in (tig_breakdown.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return None
    cash_rows: list[dict[str, Any]] = []
    transfer_rows: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("key") or "")
        if key in {"cash_service", "cash_deduction", "tig_cash_deduction"}:
            cash_rows.append(row)
        else:
            transfer_rows.append(row)
    final_total = _int_money(tig_breakdown.get("finalTotalHuf"))
    if final_total <= 0:
        final_total = sum(_int_money(row.get("grossHuf")) for row in transfer_rows)
    return transfer_rows, cash_rows, final_total


def _tig_pdf_vat_cell(row: dict[str, Any]) -> str:
    vat_huf = _int_money(row.get("vatHuf"))
    if vat_huf:
        return _money(vat_huf)
    return str(row.get("vatLabel") or "")


def build_tig_pdf(courier: dict[str, Any], amounts: dict[str, float], tig_breakdown: dict[str, Any] | None = None) -> bytes:
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
    document_meta = _tig_document_dates(courier)
    service = _tig_service_amount_without_cash_and_tip(amounts, courier)
    cash = max(_int_money(amounts.get("cash") or amounts.get("cash_amount")), 0)
    tip = max(_int_money(amounts.get("tip") or amounts.get("tip_amount")), 0)
    vat_payer = _tig_kind(courier) == "vat"
    cash_net, cash_vat, cash_gross = _split_gross_vat_amount(cash) if vat_payer else (cash, 0, cash)
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
                Paragraph(
                    "<font color='red'><b>Just in Time Transport Hungary Kft.</b><br/>"
                    "1201 Budapest, Atléta utca 44<br/>"
                    "Adószám: 32649460-2-43</font><br/><br/>"
                    f"Teljesítési időszak: <b>{document_meta['periodLabel']}</b><br/>"
                    f"Teljesítés: <b>{document_meta['performanceDate']}</b><br/>"
                    f"Fizetési határidő: <b>{document_meta['paymentDueDate']}</b><br/>"
                    f"Megjegyzés: <b>{document_meta['note']}</b>",
                    styles["body"],
                ),
            ],
        ],
        [115 * mm, 115 * mm],
        [("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER), ("PADDING", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP")],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(_table(
        [
            ["Teljesítési időszak", "Teljesítés napja", "Fizetési határidő", "Fizetés módja"],
            [document_meta["periodLabel"], document_meta["performanceDate"], document_meta["paymentDueDate"], "Átutalás"],
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
    amount_rows: list[list[Any]] = [["Tétel megnevezése", "Nettó (Ft)", "ÁFA (Ft)", "Bruttó (Ft)"]]
    breakdown_pdf_rows = _tig_pdf_rows_from_breakdown(tig_breakdown)
    cash_breakdown_rows: list[dict[str, Any]] = []
    if breakdown_pdf_rows:
        transfer_breakdown_rows, cash_breakdown_rows, final_total = breakdown_pdf_rows
        for row in transfer_breakdown_rows:
            amount_rows.append([
                str(row.get("label") or "TIG tétel"),
                _money(_int_money(row.get("netHuf"))),
                _tig_pdf_vat_cell(row),
                _money(_int_money(row.get("grossHuf"))),
            ])
    elif vat_payer:
        service_net, service_vat, service_gross = _add_vat_to_net(service)
        amount_rows.append([
            f"Szállítási díj (494107) - átutalás ({courier.get('document_reference') or courier_id})",
            _money(service_net),
            _money(service_vat),
            _money(service_gross),
        ])
        if tip:
            amount_rows.append(["Borravaló - TAM", _money(tip), "TAM", _money(tip)])
        final_total = service_gross + tip
    else:
        service_net, service_vat, service_gross = service, 0, service
        amount_rows.append([
            f"Szállítási díj (494107) - átutalás ({courier.get('document_reference') or courier_id})",
            _money(service),
            "AAM",
            _money(service),
        ])
        if tip:
            amount_rows.append(["Borravaló - TAM", _money(tip), "TAM", _money(tip)])
        final_total = service_gross + tip
    total_row_index = len(amount_rows)
    amount_rows.append(["", "", "VÉGÖSSZEG:", _money(final_total)])
    story.append(_table(
        amount_rows,
        [90 * mm, 50 * mm, 42 * mm, 48 * mm],
        [
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTNAME", (2, -1), (-1, -1), bold),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#999999")),
            ("TEXTCOLOR", (3, -1), (3, -1), RED),
            ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#333333")),
            ("SPAN", (0, total_row_index), (1, total_row_index)),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 8),
        ],
    ))
    story.append(Spacer(1, 5 * mm))
    if cash_breakdown_rows:
        cash_amount_rows: list[list[Any]] = [["Tétel megnevezése", "Nettó", "ÁFA tartalom", "Bruttó"]]
        for row in cash_breakdown_rows:
            cash_amount_rows.append([
                str(row.get("label") or "Szállítási díj (494107) - készpénz"),
                _money(_int_money(row.get("netHuf"))),
                _tig_pdf_vat_cell(row),
                _money(_int_money(row.get("grossHuf"))),
            ])
        story.append(_table(
            cash_amount_rows,
            [90 * mm, 50 * mm, 42 * mm, 48 * mm],
            [
                ("FONTNAME", (0, 0), (-1, -1), regular),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf7ea")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#183b22")),
                ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#b7c7b7")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ],
        ))
        story.append(Spacer(1, 5 * mm))
    elif cash_gross:
        story.append(_table(
            [
                ["Tétel megnevezése", "Nettó", "ÁFA tartalom", "Bruttó"],
                [
                    "Szállítási díj (494107) - készpénz",
                    _money(cash_net),
                    _money(cash_vat) if vat_payer else "AAM",
                    _money(cash_gross),
                ],
            ],
            [90 * mm, 50 * mm, 42 * mm, 48 * mm],
            [
                ("FONTNAME", (0, 0), (-1, -1), regular),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf7ea")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#183b22")),
                ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#b7c7b7")),
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
    tax_label = "27%-os ÁFA" if vat_payer else "AAM"
    story.append(Paragraph(
        "<b>SZÁMLÁZÁSI SZABÁLYOK:</b><br/>"
        "- A teljesítési és fizetési határidőt is a kiállítás napja + 8 napra állítsd!<br/>"
        f"- Adózási mód a master TIG beállítás/adószám alapján: <b>{tax_label}</b>.<br/>"
        "- A borravaló külön, TAM tétel.",
        styles["body"],
    ))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("Gépi úton készült igazolás, aláírás nélkül is hiteles.<br/><b>Just in Time Transport Hungary Kft.</b><br/>Észrevétel és kifogások: elszamolas@jitt.hu", styles["center"]))
    doc.build(story)
    return buffer.getvalue()
