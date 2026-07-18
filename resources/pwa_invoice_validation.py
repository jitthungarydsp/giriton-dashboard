import io
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any


MAX_INVOICE_BYTES = 10 * 1024 * 1024
ALLOWED_INVOICE_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def _tokens(value: Any) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", _fold(value)).strip().split()


def _parse_huf(value: Any) -> int:
    text = str(value or "").strip()
    text = re.sub(r"([,.])\d{2}\b", "", text)
    digits = re.sub(r"[^0-9-]", "", text)
    try:
        return int(digits)
    except (TypeError, ValueError):
        return 0


def _parse_date(value: str) -> date | None:
    match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", value or "")
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def _extract_labeled_date(text: str, label: str) -> date | None:
    match = re.search(
        rf"{label}\s*:?\s*(20\d{{2}}\s*[.\-/]\s*\d{{1,2}}\s*[.\-/]\s*\d{{1,2}})",
        _fold(text),
        flags=re.IGNORECASE,
    )
    return _parse_date(match.group(1)) if match else None


def _extract_first_labeled_date(text: str, labels: list[str]) -> date | None:
    for label in labels:
        value = _extract_labeled_date(text, label)
        if value:
            return value
    return None


def _extract_invoice_number(text: str) -> str:
    original_match = re.search(
        r"\b(?:számlaszám|szamlaszam|sorszám|sorszam|e\s*[- ]?\s*számla\s*sorszám|e\s*[- ]?\s*szamla\s*sorszam)\s*:?\s*([A-Za-z0-9][A-Za-z0-9/_-]{3,})",
        text or "",
        flags=re.IGNORECASE,
    )
    if original_match:
        return original_match.group(1)

    folded = _fold(text)
    lines = [line.strip() for line in folded.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        if line == "szamla":
            candidate = lines[index + 1].strip()
            if re.fullmatch(r"[a-z0-9][a-z0-9/_-]{3,}", candidate):
                return candidate

    match = re.search(
        r"\b(?:szamlaszam|sorszam|e\s*szamla\s*sorszam)\s*:?\s*([a-z0-9][a-z0-9/_-]{3,})",
        folded,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_invoice_periods(text: str) -> set[tuple[int, int]]:
    periods = set()
    for year, month in re.findall(r"\b(20\d{2})\s*[-/.]\s*(\d{1,2})\b", text or ""):
        try:
            month_int = int(month)
            if 1 <= month_int <= 12:
                periods.add((int(year), month_int))
        except ValueError:
            continue
    return periods


def _extract_gross_total(text: str) -> int:
    folded = _fold(text)
    patterns = [
        r"fizetendo\s+brutto\s+vegosszeg\s*:?\s*([\d\s]+(?:[,.]\d{2})?)\s*(?:ft|huf)",
        r"szamla\s+brutto\s+vegosszege\s*:?\s*([\d\s]+(?:[,.]\d{2})?)\s*(?:ft|huf)",
        r"fizetendo\s+osszeg\s*:?\s*([\d\s]+(?:[,.]\d{2})?)\s*(?:ft|huf)",
        r"ellen(?:ertek|ertek)\s*/\s*ellen(?:ertek|ertek)\s+afaval\s+egyutt.*?([\d\s]+(?:[,.]\d{2})?)",
    ]
    amounts = []
    for pattern in patterns:
        amounts.extend(re.findall(pattern, folded, flags=re.IGNORECASE | re.DOTALL))
    parsed = [_parse_huf(amount) for amount in amounts]
    return max(parsed, default=0)


def extract_pdf_text(content: bytes) -> str:
    if not content:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def parse_invoice_pdf(content: bytes) -> dict[str, Any]:
    text = extract_pdf_text(content)
    tax_numbers = re.findall(r"\b\d{8}-\d-\d{2}\b", text)
    return {
        "text": text,
        "seller_tax_number": tax_numbers[0] if tax_numbers else "",
        "buyer_tax_number": tax_numbers[1] if len(tax_numbers) > 1 else "",
        "issue_date": _extract_first_labeled_date(text, [r"szamla\s+kelte", r"keltezes", r"kiallitas\s+datuma"]),
        "performance_date": _extract_first_labeled_date(text, [r"teljesites\s+kelte", r"teljesites"]),
        "due_date": _extract_first_labeled_date(text, [r"fizetesi\s+hatarido"]),
        "invoice_periods": _extract_invoice_periods(text),
        "gross_total": _extract_gross_total(text),
        "invoice_number": _extract_invoice_number(text),
    }


def invoice_file_signature_ok(file_name: str, content: bytes) -> tuple[bool, str]:
    extension = Path(file_name).suffix.lower()
    if extension == ".pdf":
        return content.startswith(b"%PDF"), "PDF"
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff"), "JPEG"
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n"), "PNG"
    return False, "ismeretlen"


def _format_huf(value: Any) -> str:
    try:
        return f"{int(float(value or 0)):,} Ft".replace(",", " ")
    except (TypeError, ValueError):
        return "0 Ft"


def validate_invoice(
    *,
    file_name: str,
    content: bytes,
    invoice_month: date,
    courier_name: str,
    courier_id: str,
    expected_gross_amount: int = 0,
    invoice_number: str = "",
    gross_amount: int = 0,
    require_submission_fields: bool = False,
    expected_seller_tax_number: str = "",
    expected_seller_address: str = "",
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(status: str, title: str, detail: str) -> None:
        checks.append({"status": status, "title": title, "detail": detail})

    file_name = str(file_name or "ismeretlen_fajl").strip()
    content = content or b""
    extension = Path(file_name).suffix.lower().lstrip(".")

    add("ok" if content else "error", "Fájl olvasható", f"{file_name} ({len(content)} bájt)" if content else "A fájl üres.")
    add("ok" if extension in ALLOWED_INVOICE_EXTENSIONS else "error", "Fájltípus", extension.upper() if extension else "Nincs kiterjesztés")
    add("ok" if len(content) <= MAX_INVOICE_BYTES else "error", "Fájlméret", "10 MB alatt van." if len(content) <= MAX_INVOICE_BYTES else "A fájl nagyobb 10 MB-nál.")

    signature_ok, signature_label = invoice_file_signature_ok(file_name, content)
    add("ok" if signature_ok else "error", "Fájlfejléc", f"Valódi {signature_label} fájl." if signature_ok else "A kiterjesztés és a belső formátum nem egyezik.")

    fields = parse_invoice_pdf(content) if extension == "pdf" else {}
    text = str(fields.get("text") or "")
    normalized_tokens = set(_tokens(text))
    if extension == "pdf":
        add("ok" if text else "error", "PDF szövege", "A számla géppel olvasható." if text else "A PDF-ből nem olvasható ki szöveg.")
    else:
        add("error", "Képfájl szövegfelismerése", "Első körben szöveges PDF számla szükséges az automatikus ellenőrzéshez.")

    expected_name_tokens = _tokens(courier_name)
    add(
        "ok" if expected_name_tokens and all(token in normalized_tokens for token in expected_name_tokens) else "error",
        "Eladó neve",
        f"Javítandó: az eladó neve egyezzen a profilban szereplő névvel: {courier_name}.",
    )

    buyer_name_tokens = _tokens("Just in Time Transport Hungary Kft.")
    add("ok" if all(token in normalized_tokens for token in buyer_name_tokens) else "error", "Vevő neve", "Just in Time Transport Hungary Kft.")
    buyer_address_tokens = {"1201", "budapest", "atleta", "utca", "44"}
    add("ok" if buyer_address_tokens.issubset(normalized_tokens) else "error", "Vevő címe", "1201 Budapest, Atléta utca 44.")

    seller_tax = str(fields.get("seller_tax_number") or "")
    if expected_seller_tax_number:
        add("ok" if seller_tax == expected_seller_tax_number else "error", "Eladó adószáma", f"Javítandó: az eladó adószáma legyen {expected_seller_tax_number}. Talált: {seller_tax or 'nincs'}.")
    else:
        add("warn" if re.fullmatch(r"\d{8}-\d-\d{2}", seller_tax) else "error", "Eladó adószáma", f"Talált: {seller_tax or 'nincs'}; a profilban még nincs összehasonlítási alapadat.")

    buyer_tax = str(fields.get("buyer_tax_number") or "")
    add("ok" if buyer_tax == "32649460-2-43" else "error", "Vevő adószáma", f"Javítandó: a vevő adószáma legyen 32649460-2-43. Talált: {buyer_tax or 'nincs'}.")

    expected_address_tokens = _tokens(expected_seller_address)
    if expected_address_tokens:
        add("ok" if all(token in normalized_tokens for token in expected_address_tokens) else "error", "Eladó címe", f"Javítandó: az eladó címe egyezzen a profilban szereplő címmel: {expected_seller_address}.")
    else:
        add("warn", "Eladó címe", "A futárprofilban még nincs cím az összehasonlításhoz.")

    issue_date = fields.get("issue_date")
    performance_date = fields.get("performance_date")
    due_date = fields.get("due_date")
    for title, value in (("Számla kelte", issue_date), ("Teljesítés kelte", performance_date), ("Fizetési határidő", due_date)):
        add("ok" if value else "error", title, value.isoformat() if value else "Nem található vagy nem értelmezhető.")

    if issue_date and due_date:
        days = (due_date - issue_date).days
        add("ok" if days == 8 else "error", "8 napos fizetési szabály", f"Javítandó: a fizetési határidő a számla keltétől számított 8. nap legyen. Most {days} nap.")
    if issue_date and performance_date:
        if performance_date >= issue_date:
            days = (performance_date - issue_date).days
            add("ok" if days <= 8 else "error", "8 napos teljesítési szabály", f"Javítandó: a teljesítés kelte legfeljebb 8 nappal lehet a számla kelte után. Most {days} nap.")
        else:
            days = (issue_date - performance_date).days
            add("ok" if days <= 8 else "error", "8 napos kiállítási szabály", f"Javítandó: a számlát a teljesítéshez képest 8 napon belül kell kiállítani. Most {days} nap.")
    if performance_date:
        same_month = (performance_date.year, performance_date.month) == (invoice_month.year, invoice_month.month)
        invoice_periods = fields.get("invoice_periods") or set()
        note_matches_month = (invoice_month.year, invoice_month.month) in invoice_periods
        add(
            "ok" if same_month or note_matches_month else "error",
            "TIG időszaka",
            (
                f"Rendben: a számla megjegyzése tartalmazza a TIG hónapot ({invoice_month:%Y-%m})."
                if note_matches_month and not same_month
                else f"Javítandó: a számlán szerepeljen a TIG hónapja ({invoice_month:%Y-%m}) a teljesítésben vagy a megjegyzésben. Teljesítés: {performance_date:%Y-%m}."
            ),
        )
    pdf_gross = int(fields.get("gross_total") or 0)
    if expected_gross_amount:
        add("ok" if pdf_gross == expected_gross_amount else "error", "TIG szerinti végösszeg", f"Számla: {_format_huf(pdf_gross)}; TIG: {_format_huf(expected_gross_amount)}.")
    elif pdf_gross:
        add("warn", "TIG szerinti végösszeg", f"A számlán {_format_huf(pdf_gross)} szerepel, de a TIG-ből nem olvasható ki összeg.")

    if require_submission_fields:
        add("ok" if invoice_number.strip() else "error", "Számlaszám", invoice_number.strip() or "Kötelező mező.")
        pdf_number = str(fields.get("invoice_number") or "")
        if invoice_number.strip() and pdf_number:
            add("ok" if _tokens(invoice_number) == _tokens(pdf_number) else "error", "Számlaszám egyezése", f"Javítandó: a megadott számlaszám egyezzen a PDF-ben szereplővel. Megadva: {invoice_number}; PDF: {pdf_number}.")
        add("ok" if gross_amount > 0 else "error", "Bruttó összeg", _format_huf(gross_amount) if gross_amount > 0 else "0 Ft fölötti összeg szükséges.")
        if gross_amount > 0 and pdf_gross:
            add("ok" if gross_amount == pdf_gross else "error", "Megadott bruttó összeg", f"Megadva: {_format_huf(gross_amount)}; PDF: {_format_huf(pdf_gross)}.")

    errors = sum(check["status"] == "error" for check in checks)
    warnings = sum(check["status"] == "warn" for check in checks)
    passed = sum(check["status"] == "ok" for check in checks)
    score = round((passed / max(len(checks), 1)) * 100)
    return {
        "ok": errors == 0,
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "parsed": {
            "invoiceNumber": str(fields.get("invoice_number") or ""),
            "grossTotal": pdf_gross,
            "issueDate": issue_date.isoformat() if issue_date else None,
            "performanceDate": performance_date.isoformat() if performance_date else None,
            "dueDate": due_date.isoformat() if due_date else None,
        },
    }


def extract_expected_amount(content: bytes) -> int:
    fields = parse_invoice_pdf(content)
    if fields.get("gross_total"):
        return int(fields["gross_total"])
    amounts = [_parse_huf(value) for value in re.findall(r"([\d\s]+)\s*Ft", fields.get("text") or "", flags=re.IGNORECASE)]
    return max(amounts, default=0)
