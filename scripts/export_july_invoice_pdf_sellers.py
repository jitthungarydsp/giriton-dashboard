from __future__ import annotations

import argparse
import base64
import csv
import io
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.pwa_invoice_validation import parse_invoice_pdf  # noqa: E402
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error  # noqa: E402


COMPANY_SUFFIX_RE = re.compile(
    r"\b(kft\.?|bt\.?|zrt\.?|nyrt\.?|ev\.?|e\.v\.?|egy[eé]ni v[aá]llalkoz[oó])\b",
    flags=re.IGNORECASE,
)


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_noise_line(line: str) -> bool:
    text = clean_text(line).casefold()
    if not text:
        return True
    blocked = {
        "szamla", "számla", "invoice", "elado", "eladó", "szallito", "szállító",
        "vevo", "vevő", "megrendelo", "megrendelő", "fizetesi mod", "fizetési mód",
        "adoszam", "adószám", "bankszamlaszam", "bankszámlaszám",
    }
    if text in blocked:
        return True
    if any(token in text for token in ("adószám", "adoszam", "bankszámla", "bankszamla")):
        return True
    if re.search(r"\d{4}\s+[a-záéíóöőúüű]", text):
        return True
    if re.fullmatch(r"[\d\s./:-]+", text):
        return True
    return False


def candidate_score(line: str) -> int:
    text = clean_text(line)
    score = 0
    if COMPANY_SUFFIX_RE.search(text):
        score += 100
    if re.search(r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+", text):
        score += 15
    if not re.search(r"\d", text):
        score += 10
    if len(text) <= 80:
        score += 5
    return score


def extract_pdf_seller_name(text: str, seller_tax_number: str = "") -> str:
    lines = [clean_text(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    label_patterns = ("elado", "eladó", "szallito", "szállító", "kiallito", "kiállító")
    for index, line in enumerate(lines):
        normalized = line.casefold()
        if any(label in normalized for label in label_patterns):
            candidates = [item for item in lines[index + 1:index + 6] if not is_noise_line(item)]
            if candidates:
                return max(candidates, key=candidate_score)
    if seller_tax_number:
        for index, line in enumerate(lines):
            if seller_tax_number in line:
                candidates = [item for item in lines[max(0, index - 6):index] if not is_noise_line(item)]
                if candidates:
                    return max(candidates, key=candidate_score)
    suffix_candidates = [
        line for line in lines[:30]
        if not is_noise_line(line) and COMPANY_SUFFIX_RE.search(line)
    ]
    if suffix_candidates:
        return max(suffix_candidates, key=candidate_score)
    candidates = [line for line in lines[:20] if not is_noise_line(line)]
    return max(candidates, key=candidate_score) if candidates else ""


def is_cash_invoice(row: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(row.get(key) or "").casefold()
        for key in ("title", "file_name", "note")
    )
    return (
        haystack.startswith("kp ")
        or "kp számla" in haystack
        or "kp szamla" in haystack
        or "kp_szamla" in haystack
        or "kps" in haystack
        or "fizetési mód: kp" in haystack
        or "fizetesi mod: kp" in haystack
    )


def decode_document_content(value: object) -> bytes:
    if not value:
        return b""
    return base64.b64decode(str(value).encode("ascii"))


def month_start(value: str) -> date:
    year, month = str(value).split("-", 1)
    return date(int(year), int(month), 1)


def fetch_invoice_documents(document_month: date) -> list[dict[str, Any]]:
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beallitas.")
    response = requests.get(
        f"{supabase_url.rstrip('/')}/rest/v1/peopleforce_documents",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params={
            "select": "id,courier_id,courier_name,document_month,title,file_name,mime_type,note,uploaded_at,file_content_base64",
            "document_month": f"eq.{document_month.isoformat()}",
            "document_type": "eq.invoice",
            "order": "courier_name.asc,uploaded_at.desc",
            "limit": "10000",
        },
        timeout=120,
    )
    raise_for_supabase_error(response)
    return response.json() or []


def export_rows(document_month: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in fetch_invoice_documents(document_month):
        if is_cash_invoice(document):
            continue
        file_name = str(document.get("file_name") or "")
        mime_type = str(document.get("mime_type") or "")
        if "pdf" not in mime_type.casefold() and not file_name.casefold().endswith(".pdf"):
            rows.append({
                "courier_id": document.get("courier_id") or "",
                "futar_nev": document.get("courier_name") or "",
                "pdf_szamlazo_nev": "",
                "pdf_szamla_osszeg_huf": 0,
                "pdf_szamlaszam": "",
                "file_name": file_name,
                "uploaded_at": document.get("uploaded_at") or "",
                "hiba": "Nem PDF fajl",
            })
            continue
        try:
            parsed = parse_invoice_pdf(decode_document_content(document.get("file_content_base64")))
            seller_name = extract_pdf_seller_name(
                str(parsed.get("text") or ""),
                str(parsed.get("seller_tax_number") or ""),
            )
            rows.append({
                "courier_id": document.get("courier_id") or "",
                "futar_nev": document.get("courier_name") or "",
                "pdf_szamlazo_nev": seller_name,
                "pdf_szamla_osszeg_huf": int(parsed.get("gross_total") or 0),
                "pdf_szamlaszam": parsed.get("invoice_number") or "",
                "file_name": file_name,
                "uploaded_at": document.get("uploaded_at") or "",
                "hiba": "",
            })
        except Exception as exc:
            rows.append({
                "courier_id": document.get("courier_id") or "",
                "futar_nev": document.get("courier_name") or "",
                "pdf_szamlazo_nev": "",
                "pdf_szamla_osszeg_huf": 0,
                "pdf_szamlaszam": "",
                "file_name": file_name,
                "uploaded_at": document.get("uploaded_at") or "",
                "hiba": str(exc),
            })
    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "courier_id",
        "futar_nev",
        "pdf_szamlazo_nev",
        "pdf_szamla_osszeg_huf",
        "pdf_szamlaszam",
        "file_name",
        "uploaded_at",
        "hiba",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF szamlazo nev es vegosszeg export PeopleForce szamlakbol.")
    parser.add_argument("--month", default="2026-07", help="Honap YYYY-MM formaban. Alap: 2026-07")
    parser.add_argument("--output", default="", help="CSV kimenet. Alap: results/invoice_pdf_sellers_<honap>.csv")
    args = parser.parse_args()

    document_month = month_start(args.month)
    output_path = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"invoice_pdf_sellers_{document_month:%Y_%m}.csv"
    rows = export_rows(document_month)
    write_csv(rows, output_path)

    total = sum(int(row.get("pdf_szamla_osszeg_huf") or 0) for row in rows)
    print(f"ROWS={len(rows)}")
    print(f"TOTAL_HUF={total}")
    print(f"OUTPUT={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
