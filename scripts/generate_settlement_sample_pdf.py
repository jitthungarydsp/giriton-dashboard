from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "jitt_elszamolasi_minta.pdf"
FONT = Path("C:/Windows/Fonts/arial.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")


def money(value: int) -> str:
    return f"{value:,.0f} Ft".replace(",", " ")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial", str(FONT)))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_BOLD)))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="Arial-Bold", fontSize=20, textColor=colors.HexColor("#17351F"), leading=25)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Arial", fontSize=9, leading=13)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = [Paragraph("JITT - Futár elszámolás (minta)", title), Spacer(1, 4 * mm)]
    header = Table([
        [Paragraph("Futár: <b>Abonyi György Zoltán</b>", body), Paragraph("Elszámolási időszak: <b>2026. július</b>", right)],
        [Paragraph("Courier ID: 6498 | Branch: JIT | Raktár: BUD1", body), Paragraph("Státusz: <b>Előkészítve</b>", right)],
    ], colWidths=[90 * mm, 85 * mm])
    header.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F7F3")), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9D8CC")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DCE8DF")), ("PADDING", (0, 0), (-1, -1), 8)]))
    story += [header, Spacer(1, 7 * mm), Paragraph("Teljesítés route-típus és naptípus szerint", ParagraphStyle("section", parent=body, fontName="Arial-Bold", fontSize=12, textColor=colors.HexColor("#17351F"))), Spacer(1, 2 * mm)]
    routes = [["Túratípus", "Naptípus", "Túrák", "Alapdíj", "Borravaló", "Bónuszok"], ["Normál", "Normál nap", "54", money(243000), money(7104), money(0)], ["Expressz", "Kiemelt nap", "8", money(52000), money(0), money(12000)], ["Regionális", "Normál nap", "3", money(19500), money(0), money(0)]]
    route_table = Table(routes, colWidths=[30 * mm, 31 * mm, 17 * mm, 32 * mm, 31 * mm, 34 * mm])
    route_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Arial"), ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17351F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CF")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF8")]), ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story += [route_table, Spacer(1, 7 * mm), Paragraph("Havi elszámolás", ParagraphStyle("section2", parent=body, fontName="Arial-Bold", fontSize=12, textColor=colors.HexColor("#17351F"))), Spacer(1, 2 * mm)]
    settlement = [["Tétel", "Összeg"], ["Alapdíj", money(314500)], ["Borravaló", money(7104)], ["Bónuszok", money(12000)], ["Máluszok", money(0)], ["ATM levonás", money(0)], ["Egyéb kiadás", money(0)], ["Ügyfélértékelési bónusz", money(5000)], ["Kifizetendő", money(338604)]]
    settlement_table = Table(settlement, colWidths=[110 * mm, 65 * mm])
    settlement_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Arial"), ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Arial-Bold"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17351F")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DFF1E4")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CF")), ("ALIGN", (1, 1), (1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 7)]))
    story += [settlement_table, Spacer(1, 8 * mm), Paragraph("Ez minta dokumentum. A végleges PDF az adatbázisban tárolt, jóváhagyott elszámolási tételekből készül.", body)]
    doc.build(story)


if __name__ == "__main__":
    main()
