from __future__ import annotations

import argparse
import base64
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pwa_api
from resources.pwa_invoice_validation import parse_invoice_pdf


OUTPUT_DIR = Path("exports")
COMPANY_SUFFIX_RE = re.compile(
    r"\b(kft\.?|bt\.?|zrt\.?|nyrt\.?|ev\.?|e\.v\.?|egy[eé]ni v[aá]llalkoz[oó])\b",
    flags=re.IGNORECASE,
)


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_noise_line(line: str) -> bool:
    text = compact_text(line).casefold()
    if not text:
        return True
    blocked = {
        "szamla",
        "számla",
        "invoice",
        "elado",
        "eladó",
        "szallito",
        "szállító",
        "vevo",
        "vevő",
        "megrendelo",
        "megrendelő",
        "fizetesi mod",
        "fizetési mód",
        "adoszam",
        "adószám",
        "bankszamlaszam",
        "bankszámlaszám",
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
    text = compact_text(line)
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


def extract_seller_name_from_text(text: str, seller_tax_number: str = "") -> str:
    lines = [compact_text(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    label_patterns = ("elado", "eladó", "szallito", "szállító", "kiallito", "kiállító")
    for index, line in enumerate(lines):
        normalized = line.casefold()
        if any(label in normalized for label in label_patterns):
            window = lines[index + 1 : index + 6]
            candidates = [item for item in window if not is_noise_line(item)]
            if candidates:
                return max(candidates, key=candidate_score)

    if seller_tax_number:
        for index, line in enumerate(lines):
            if seller_tax_number in line:
                window = lines[max(0, index - 6) : index]
                candidates = [item for item in window if not is_noise_line(item)]
                if candidates:
                    return max(candidates, key=candidate_score)

    suffix_candidates = [line for line in lines[:30] if not is_noise_line(line) and COMPANY_SUFFIX_RE.search(line)]
    if suffix_candidates:
        return max(suffix_candidates, key=candidate_score)

    candidates = [line for line in lines[:20] if not is_noise_line(line)]
    return max(candidates, key=candidate_score) if candidates else ""


def chunks(items: list[str], size: int = 80) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def load_profiles(courier_ids: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in chunks([item for item in courier_ids if item]):
        rows = pwa_api.supabase_rest(
            "GET",
            "courier_master",
            params={
                "select": "courier_id,courier_name,company_name,tax_number,billing_email,company_address",
                "courier_id": f"in.({','.join(chunk)})",
                "limit": str(len(chunk)),
            },
            timeout=60,
        )
        for row in rows or []:
            result[str(row.get("courier_id") or "").strip()] = row
    return result


def load_invoice_documents(limit: int) -> list[dict[str, Any]]:
    return pwa_api.supabase_rest(
        "GET",
        "peopleforce_documents",
        params={
            "select": "id,courier_id,courier_name,document_month,title,file_name,mime_type,file_size,note,uploaded_by,uploaded_at,file_content_base64",
            "document_type": "eq.invoice",
            "order": "uploaded_at.desc",
            "limit": str(limit),
        },
        timeout=120,
    )


def parse_document(row: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    content_base64 = str(row.get("file_content_base64") or "")
    mime_type = str(row.get("mime_type") or "")
    file_name = str(row.get("file_name") or "")
    if content_base64 and ("pdf" in mime_type.casefold() or file_name.casefold().endswith(".pdf")):
        try:
            content = base64.b64decode(content_base64, validate=True)
            parsed = parse_invoice_pdf(content)
        except Exception as exc:
            parsed = {"parse_error": str(exc)}
    seller_name = extract_seller_name_from_text(
        str(parsed.get("text") or ""),
        str(parsed.get("seller_tax_number") or ""),
    )
    return {
        "invoice_seller_name": seller_name,
        "invoice_seller_tax_number": str(parsed.get("seller_tax_number") or ""),
        "invoice_number": str(parsed.get("invoice_number") or ""),
        "invoice_gross_total_huf": int(parsed.get("gross_total") or 0),
        "parse_error": str(parsed.get("parse_error") or ""),
    }


def export_uploaded_invoice_billing_names(limit: int, output: Path | None = None) -> Path:
    rows = load_invoice_documents(limit)
    courier_ids = sorted({str(row.get("courier_id") or "").strip() for row in rows if row.get("courier_id")})
    profiles = load_profiles(courier_ids)
    output_path = output or OUTPUT_DIR / f"uploaded_invoice_billing_names_{datetime.now():%Y%m%d_%H%M%S}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "courier_id",
        "courier_name_document",
        "profile_courier_name",
        "profile_company_name",
        "invoice_seller_name",
        "profile_tax_number",
        "invoice_seller_tax_number",
        "document_month",
        "invoice_number",
        "invoice_gross_total_huf",
        "file_name",
        "uploaded_at",
        "document_id",
        "needs_company_name_update",
        "parse_error",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            courier_id = str(row.get("courier_id") or "").strip()
            profile = profiles.get(courier_id, {})
            parsed = parse_document(row)
            profile_company_name = compact_text(profile.get("company_name"))
            invoice_seller_name = compact_text(parsed.get("invoice_seller_name"))
            writer.writerow(
                {
                    "courier_id": courier_id,
                    "courier_name_document": compact_text(row.get("courier_name")),
                    "profile_courier_name": compact_text(profile.get("courier_name")),
                    "profile_company_name": profile_company_name,
                    "invoice_seller_name": invoice_seller_name,
                    "profile_tax_number": compact_text(profile.get("tax_number")),
                    "invoice_seller_tax_number": compact_text(parsed.get("invoice_seller_tax_number")),
                    "document_month": str(row.get("document_month") or "")[:10],
                    "invoice_number": compact_text(parsed.get("invoice_number")),
                    "invoice_gross_total_huf": parsed.get("invoice_gross_total_huf") or 0,
                    "file_name": compact_text(row.get("file_name")),
                    "uploaded_at": str(row.get("uploaded_at") or ""),
                    "document_id": str(row.get("id") or ""),
                    "needs_company_name_update": (
                        "yes"
                        if invoice_seller_name and profile_company_name.casefold() != invoice_seller_name.casefold()
                        else ""
                    ),
                    "parse_error": compact_text(parsed.get("parse_error")),
                }
            )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export uploaded invoice seller names by courier.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output_path = export_uploaded_invoice_billing_names(args.limit, args.output)
    print(f"Export kesz: {output_path}")


if __name__ == "__main__":
    main()
