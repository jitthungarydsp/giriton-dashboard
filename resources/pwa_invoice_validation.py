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
    digits = re.sub(r"[^0-9-]", "", str(value or ""))
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
    folded = _fold(text)
    tax_numbers = re.findall(r"\b\d{8}-\d-\d{2}\b", text)
    totals = re.findall(
        r"fizetendo\s+brutto\s+vegosszeg\s*:?\s*([\d\s]+)\s*ft",
        folded,
        flags=re.IGNORECASE,
    )
    invoice_number_match = re.search(
        r"(?:szamlaszam\s*:?|szamla\s*\n)\s*([a-z0-9][a-z0-9/_-]{3,})",
        folded,
        flags=re.IGNORECASE,
    )
    return {
        "text": text,
        "seller_tax_number": tax_numbers[0] if tax_numbers else "",
        "buyer_tax_number": tax_numbers[1] if len(tax_numbers) > 1 else "",
        "issue_date": _extract_labeled_date(text, r"szamla\s+kelte"),
        "performance_date": _extract_labeled_date(text, r"teljesites\s+kelte"),
        "due_date": _extract_labeled_date(text, r"fizetesi\s+hatarido"),
        "gross_total": _parse_huf(totals[-1]) if totals else 0,
        "invoice_number": invoice_number_match.group(1) if invoice_number_match else "",
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
        f"A várt név: {courier_name}.",
    )

    buyer_name_tokens = _tokens("Just in Time Transport Hungary Kft.")
    add("ok" if all(token in normalized_tokens for token in buyer_name_tokens) else "error", "Vevő neve", "Just in Time Transport Hungary Kft.")
    buyer_address_tokens = {"1201", "budapest", "atleta", "utca", "44"}
    add("ok" if buyer_address_tokens.issubset(normalized_tokens) else "error", "Vevő címe", "1201 Budapest, Atléta utca 44.")

    seller_tax = str(fields.get("seller_tax_number") or "")
    if expected_seller_tax_number:
        add("ok" if seller_tax == expected_seller_tax_number else "error", "Eladó adószáma", f"Talált: {seller_tax or 'nincs'}; várt: {expected_seller_tax_number}.")
    else:
        add("warn" if re.fullmatch(r"\d{8}-\d-\d{2}", seller_tax) else "error", "Eladó adószáma", f"Talált: {seller_tax or 'nincs'}; a profilban még nincs összehasonlítási alapadat.")

    buyer_tax = str(fields.get("buyer_tax_number") or "")
    add("ok" if buyer_tax == "32649460-2-43" else "error", "Vevő adószáma", f"Talált: {buyer_tax or 'nincs'}; várt: 32649460-2-43.")

    expected_address_tokens = _tokens(expected_seller_address)
    if expected_address_tokens:
        add("ok" if all(token in normalized_tokens for token in expected_address_tokens) else "error", "Eladó címe", expected_seller_address)
    else:
        add("warn", "Eladó címe", "A futárprofilban még nincs cím az összehasonlításhoz.")

    issue_date = fields.get("issue_date")
    performance_date = fields.get("performance_date")
    due_date = fields.get("due_date")
    for title, value in (("Számla kelte", issue_date), ("Teljesítés kelte", performance_date), ("Fizetési határidő", due_date)):
        add("ok" if value else "error", title, value.isoformat() if value else "Nem található vagy nem értelmezhető.")

    if issue_date and due_date:
        days = (due_date - issue_date).days
        add("ok" if days == 8 else "error", "8 napos fizetési szabály", f"A két dátum között {days} nap van.")
    if issue_date and performance_date:
        days = (issue_date - performance_date).days
        add("ok" if 0 <= days <= 8 else "error", "8 napos kiállítási szabály", f"A számla a teljesítéshez képest {days} nap eltéréssel készült.")
    if performance_date:
        same_month = (performance_date.year, performance_date.month) == (invoice_month.year, invoice_month.month)
        add("ok" if same_month else "error", "TIG időszaka", f"Teljesítés: {performance_date:%Y-%m}; TIG: {invoice_month:%Y-%m}.")

    pdf_gross = int(fields.get("gross_total") or 0)
    if expected_gross_amount:
        add("ok" if pdf_gross == expected_gross_amount else "error", "TIG szerinti végösszeg", f"Számla: {_format_huf(pdf_gross)}; TIG: {_format_huf(expected_gross_amount)}.")
    elif pdf_gross:
        add("warn", "TIG szerinti végösszeg", f"A számlán {_format_huf(pdf_gross)} szerepel, de a TIG-ből nem olvasható ki összeg.")

    if require_submission_fields:
        add("ok" if invoice_number.strip() else "error", "Számlaszám", invoice_number.strip() or "Kötelező mező.")
        pdf_number = str(fields.get("invoice_number") or "")
        if invoice_number.strip() and pdf_number:
            add("ok" if _tokens(invoice_number) == _tokens(pdf_number) else "error", "Számlaszám egyezése", f"Megadva: {invoice_number}; PDF: {pdf_number}.")
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
