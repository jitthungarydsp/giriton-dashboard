# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "tmp" / "invoice_racz" / "racz_csaba_source.xlsx"
OUT = PROJECT_ROOT / "output" / "pdf"
OUT.mkdir(parents=True, exist_ok=True)
AUDIT = PROJECT_ROOT / "output" / "racz_csaba_jit_elszamolas_audit.csv"
TIG = OUT / "2875_Racz_Csaba_TIG_2026-06.pdf"
HELP = OUT / "2875_Racz_Csaba_szamla_kitoltesi_segedlet_2026-06.pdf"
SETTLEMENT = OUT / "2875_Racz_Csaba_JIT_futar_elszamolas_2026-06.pdf"
COMBINED = OUT / "2875_Racz_Csaba_szamla_es_elszamolas_2026-06.pdf"

COURIER = {
    "id": "2875",
    "name": "Rácz Csaba",
    "company_name": "RÁCZ CSABA MIKLÓS E.V.",
    "company_address": "MAGYARORSZÁG, 2173 KARTAL SZABADSÁG ÚT 54",
    "tax_number": "59479930-1-33",
    "bank_account": "109180010000002770970000",
}
BUYER = {
    "name": "Just in Time Transport Hungary Kft.",
    "address": "1201 Budapest, Atléta utca 44.",
    "tax_number": "32649460-2-43",
}

# Futár oldali JIT elszámolási alapdíjak.
BASE_RATE = {
    ("EXPRESSZ", "KIEMELT"): 3350,
    ("CITY", "KIEMELT"): 6500,
    ("REGIO", "KIEMELT"): 9000,
    ("EXPRESSZ", "SIMA"): 2650,
    ("CITY", "SIMA"): 4500,
    ("REGIO", "SIMA"): 6300,
}

# A meglévő alkalmazásban szereplő futár oldali bónusz-átfordítás.
BONUS_OVERRIDE = {750: 500}


def huf_num(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = (
        str(value)
        .strip()
        .replace("Ft", "")
        .replace("HUF", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )
    if not text or text.lower() in {"nan", "none", "null"}:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def huf(value) -> str:
    return f"{int(round(float(value or 0))):,}".replace(",", " ") + " Ft"


def parse_date(value) -> date:
    if isinstance(value, (datetime, date)):
        return pd.Timestamp(value).date()
    return datetime.strptime(str(value).strip(), "%d.%m.%Y").date()


def service_type(value) -> str:
    text = str(value or "").lower()
    if "exp" in text:
        return "EXPRESSZ"
    if "reg" in text or "rég" in text:
        return "REGIO"
    return "CITY"


def day_type(work_date: date) -> str:
    # JIT jelenlegi kódlogika: kiemelt nap = hétfő, péntek, szombat, vasárnap.
    return "KIEMELT" if work_date.weekday() in [0, 4, 5, 6] else "SIMA"


def bonus_amount(value) -> int:
    raw = int(round(huf_num(value)))
    return BONUS_OVERRIDE.get(raw, raw)


def vat_code(tax_number: str) -> str:
    match = re.search(r"\b\d{8}-(\d)-\d{2}\b", str(tax_number or ""))
    return match.group(1) if match else ""


def vat_breakdown(net_amount: float, tax_number: str) -> tuple[int, int, int, str]:
    net = int(round(net_amount or 0))
    if vat_code(tax_number) == "2":
        vat = int(round(net * 0.27))
        return net, vat, net + vat, "27%"
    return net, 0, net, "AAM"


def register_font() -> tuple[str, str]:
    candidates = [
        ("Arial", Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (
            "DejaVuSans",
            Path(r"C:\Windows\Fonts\DejaVuSans.ttf"),
            Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf"),
        ),
    ]
    for name, regular, bold in candidates:
        if not regular.exists():
            continue
        pdfmetrics.registerFont(TTFont(name, str(regular)))
        if bold.exists():
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold)))
            return name, f"{name}-Bold"
        return name, name
    return "Helvetica", "Helvetica-Bold"


def table_style(header_bg: str, font: str, bold_font: str) -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, 0), (-1, 0), bold_font),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d0d0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )


def build_pdf(path: Path, story) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    doc.build(story)


def calculate():
    raw = pd.read_excel(SRC, sheet_name="BUD1_Dynamic", header=2)
    mask = raw["Driver"].astype(str).str.contains("Racz|Rácz|RĂ|RÃ", case=False, na=False)
    df = raw[mask].copy()
    if df.empty:
        raise RuntimeError("Nincs Rácz Csaba sor a forrásban.")

    df["work_date"] = df["Date"].map(parse_date)
    df["service_type"] = df["Route Type"].map(service_type)
    df["day_type"] = df["work_date"].map(day_type)
    df["courier_base_huf"] = df.apply(
        lambda row: BASE_RATE.get((row["service_type"], row["day_type"]), 0),
        axis=1,
    )
    df["orders_count"] = df["Orders"].map(huf_num).astype(int)
    df["route_count"] = df["Routen"].map(huf_num).astype(int)
    df["tip_huf"] = df["Tip"].map(huf_num)
    df["delay_bonus_courier_huf"] = df["Delay Bonus"].map(bonus_amount)
    df["compliance_bonus_courier_huf"] = df["Compliance Bonus"].map(bonus_amount)
    df["fuel_bonus_huf"] = df["Fuel Bonus"].map(huf_num)
    df["car_fridge_bonus_huf"] = df["Car & Fridge Bonus"].map(huf_num)
    df["branding_huf"] = df["Branding"].map(huf_num)
    df["fill_rate_ignored_huf"] = df["Fill Rate Bonus"].map(huf_num)
    df["route_without_tip_huf"] = (
        df["courier_base_huf"]
        + df["delay_bonus_courier_huf"]
        + df["compliance_bonus_courier_huf"]
    )
    df["route_total_huf"] = df["route_without_tip_huf"] + df["tip_huf"]

    audit_cols = [
        "work_date",
        "Driver",
        "Route Unique ID",
        "service_type",
        "day_type",
        "orders_count",
        "route_count",
        "courier_base_huf",
        "delay_bonus_courier_huf",
        "compliance_bonus_courier_huf",
        "fuel_bonus_huf",
        "car_fridge_bonus_huf",
        "branding_huf",
        "fill_rate_ignored_huf",
        "tip_huf",
        "route_without_tip_huf",
        "route_total_huf",
    ]
    df[audit_cols].to_csv(AUDIT, index=False, encoding="utf-8-sig")

    summary = {
        "orders": int(df["orders_count"].sum()),
        "routes": int(df["route_count"].sum()),
        "express_routes": int((df["service_type"] == "EXPRESSZ").sum()),
        "city_routes": int((df["service_type"] == "CITY").sum()),
        "kiemelt_routes": int((df["day_type"] == "KIEMELT").sum()),
        "sima_routes": int((df["day_type"] == "SIMA").sum()),
        "base": df["courier_base_huf"].sum(),
        "delay": df["delay_bonus_courier_huf"].sum(),
        "compliance": df["compliance_bonus_courier_huf"].sum(),
        "fuel": df["fuel_bonus_huf"].sum(),
        "car_fridge": df["car_fridge_bonus_huf"].sum(),
        "branding": df["branding_huf"].sum(),
        "fill_ignored": df["fill_rate_ignored_huf"].sum(),
        "tip": df["tip_huf"].sum(),
        "without_tip": df["route_without_tip_huf"].sum(),
        "total": df["route_total_huf"].sum(),
    }
    type_day = (
        df.groupby(["service_type", "day_type"])
        .agg(
            routes=("route_count", "sum"),
            orders=("orders_count", "sum"),
            base=("courier_base_huf", "sum"),
        )
        .reset_index()
    )
    weekdays = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
    by_weekday = (
        df.assign(weekday=df["work_date"].map(lambda d: weekdays[d.weekday()]))
        .groupby("weekday")
        .agg(routes=("route_count", "sum"), orders=("orders_count", "sum"), total=("route_total_huf", "sum"))
        .reindex(weekdays)
        .fillna(0)
        .reset_index()
    )
    return summary, type_day, by_weekday


def main():
    font, bold_font = register_font()
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=styles["Normal"], fontName=font, fontSize=9, leading=11)
    small = ParagraphStyle(
        "s", parent=normal, fontSize=8, leading=10, textColor=colors.HexColor("#555555")
    )
    title = ParagraphStyle(
        "t", parent=normal, fontName=bold_font, fontSize=20, leading=24, spaceAfter=6
    )
    heading = ParagraphStyle(
        "h2", parent=normal, fontName=bold_font, fontSize=12, leading=14, spaceBefore=6, spaceAfter=4
    )

    summary, type_day, by_weekday = calculate()
    net, vat, gross, vat_label = vat_breakdown(summary["without_tip"], COURIER["tax_number"])
    transfer = int(round(summary["without_tip"] + summary["tip"]))

    build_pdf(
        TIG,
        [
            Paragraph("TELJESÍTÉSI IGAZOLÁS", title),
            Spacer(1, 3 * mm),
            Table(
                [
                    [Paragraph("SZOLGÁLTATÓ", heading), Paragraph("MEGBÍZÓ", heading)],
                    [
                        Paragraph(
                            f"<b>{COURIER['company_name']}</b><br/>{COURIER['company_address']}<br/>"
                            f"Adószám: <b>{COURIER['tax_number']}</b><br/>"
                            f"Futár: {COURIER['name']} #{COURIER['id']}",
                            normal,
                        ),
                        Paragraph(
                            f"<b>{BUYER['name']}</b><br/>{BUYER['address']}<br/>"
                            f"Adószám: <b>{BUYER['tax_number']}</b>",
                            normal,
                        ),
                    ],
                ],
                colWidths=[83 * mm, 83 * mm],
                style=table_style("#4a4a4a", font, bold_font),
            ),
            Spacer(1, 5 * mm),
            Paragraph("Időszak: 2026. június", heading),
            Table(
                [
                    ["Tétel", "Nettó", "ÁFA", "Bruttó"],
                    ["Szállítási díj (494107)", huf(net), vat_label if vat == 0 else huf(vat), huf(gross)],
                    ["Borravaló - külön tétel", huf(summary["tip"]), "0 Ft", huf(summary["tip"])],
                    ["Átutalandó összesen", huf(transfer), "", huf(transfer)],
                ],
                colWidths=[75 * mm, 30 * mm, 30 * mm, 35 * mm],
                style=table_style("#202020", font, bold_font),
            ),
            Spacer(1, 5 * mm),
            Paragraph(f"Megjegyzésbe kötelező azonosító: <b>{COURIER['id']}</b>", normal),
            Spacer(1, 3 * mm),
            Paragraph(
                "A számítás a JIT futár elszámolási díjtáblája alapján készült: "
                "kiemelt / nem kiemelt nap és route típus szerint.",
                small,
            ),
        ],
    )

    invoice_rows = [
        ["Eladó / vállalkozó neve", COURIER["company_name"]],
        ["Eladó címe", COURIER["company_address"]],
        ["Eladó adószáma", COURIER["tax_number"]],
        ["Bankszámlaszám", COURIER["bank_account"]],
        ["Vevő neve", BUYER["name"]],
        ["Vevő címe", BUYER["address"]],
        ["Vevő adószáma", BUYER["tax_number"]],
        ["Időszak", "2026. június"],
        ["Számla megjegyzés / azonosító", COURIER["id"]],
        ["Fizetési mód", "Átutalás"],
        ["Teljesítési és fizetési határidő", "Kiállítás napja + 8 nap"],
        ["Tétel", "Szállítási díj (494107)"],
        ["Nettó szolgáltatási díj", huf(net)],
        ["ÁFA", vat_label if vat == 0 else huf(vat)],
        ["Bruttó szolgáltatási díj", huf(gross)],
        ["Borravaló", huf(summary["tip"])],
        ["Átutalandó összesen", huf(transfer)],
    ]
    invoice_story = [
            Paragraph("Számla kiállítási segédlet", title),
            Paragraph(
                "Ez nem hivatalos számla, hanem a számla kiállításához szükséges JIT elszámolási adatlap.",
                normal,
            ),
            Spacer(1, 4 * mm),
            Table(invoice_rows, colWidths=[62 * mm, 105 * mm], style=table_style("#5f8f2f", font, bold_font)),
            Spacer(1, 5 * mm),
            Paragraph("Összetevők", heading),
            Table(
                [
                    ["Megnevezés", "Összeg"],
                    ["Alapdíj", huf(summary["base"])],
                    ["Késedelmi bónusz", huf(summary["delay"])],
                    ["Túramegfelelési bónusz", huf(summary["compliance"])],
                ],
                colWidths=[80 * mm, 45 * mm],
                style=table_style("#2f5d2f", font, bold_font),
            ),
    ]

    type_rows = [["Típus", "Nap típus", "Kör", "Cím", "Alapdíj"]]
    for _, row in type_day.iterrows():
        type_rows.append([row["service_type"], row["day_type"], int(row["routes"]), int(row["orders"]), huf(row["base"])])

    week_rows = [["Nap", "Kör", "Cím", "Összeg borravalóval"]]
    for _, row in by_weekday.iterrows():
        week_rows.append([row["weekday"], int(row["routes"]), int(row["orders"]), huf(row["total"])])

    summary_rows = [
        ["Tétel", "Összeg"],
        ["Alapdíj", huf(summary["base"])],
        ["Késedelmi bónusz", huf(summary["delay"])],
        ["Túramegfelelési bónusz", huf(summary["compliance"])],
        ["Szolgáltatás borravaló nélkül", huf(summary["without_tip"])],
        ["Borravaló", huf(summary["tip"])],
        ["Összesen", huf(summary["total"])],
    ]
    settlement_story = [
            Paragraph("JIT futár elszámolás - Rácz Csaba", title),
            Paragraph("Időszak: 2026. június", normal),
            Spacer(1, 4 * mm),
            Table(
                [
                    ["Futár ID", "Körök", "Címek", "Expressz", "City", "Kiemelt kör", "Nem kiemelt kör"],
                    [
                        COURIER["id"],
                        summary["routes"],
                        summary["orders"],
                        summary["express_routes"],
                        summary["city_routes"],
                        summary["kiemelt_routes"],
                        summary["sima_routes"],
                    ],
                ],
                colWidths=[22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 28 * mm, 32 * mm],
                style=table_style("#253d18", font, bold_font),
            ),
            Spacer(1, 5 * mm),
            Paragraph("Kiemelt / nem kiemelt és típus bontás", heading),
            Table(type_rows, colWidths=[35 * mm, 35 * mm, 25 * mm, 25 * mm, 35 * mm], style=table_style("#5f8f2f", font, bold_font)),
            Spacer(1, 5 * mm),
            Paragraph("Napi bontás", heading),
            Table(week_rows, colWidths=[50 * mm, 25 * mm, 25 * mm, 45 * mm], style=table_style("#5f8f2f", font, bold_font)),
            Spacer(1, 5 * mm),
            Paragraph("Összesítő", heading),
            Table(summary_rows, colWidths=[85 * mm, 45 * mm], style=table_style("#202020", font, bold_font)),
    ]
    build_pdf(COMBINED, invoice_story + [PageBreak()] + settlement_story)

    print("orders", summary["orders"])
    print("routes", summary["routes"])
    print("base", int(round(summary["base"])))
    print("without_tip", int(round(summary["without_tip"])))
    print("tip", int(round(summary["tip"])))
    print("total", int(round(summary["total"])))
    print(AUDIT)
    print(TIG)
    print(COMBINED)


if __name__ == "__main__":
    main()
