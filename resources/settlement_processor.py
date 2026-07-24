"""Normalize one imported settlement workbook session.

Parser integration
------------------
This module expects the existing ``resources.settlement_parser`` module.
If that module's public result types change, only
``analyze_and_parse_sheet`` and ``_pair_records_with_source_rows`` need to be
adapted. No sheet recognition rules are duplicated here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

from supabase import Client

from resources.settlement_parser import (
    DEFAULT_PARSERS,
    ImportedExcelRow,
    ParsedSheet,
    is_empty_row,
)


SCHEMA_NAME = "settlement"
IMPORT_TABLE = "excel_import"
PROCESSING_RUN_TABLE = "processing_run"
SHEET_RESULT_TABLE = "sheet_processing_result"
VALIDATION_ERROR_TABLE = "validation_error"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_BATCH_SIZE = 500



DATE_FORMATS = (
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%Y/%m/%d",
)

INTEGER_FIELDS = {
    "orders",
    "routen",
    "routes",
    "route count",
    "order count",
    "count",
}

DECIMAL_FIELDS = {
    "tip",
    "fixed rate",
    "delay bonus",
    "compliance bonus",
    "fuel bonus",
    "car & fridge bonus",
    "fill rate bonus",
    "branding",
    "balance",
    "bonus",
    "penalty",
    "amount",
    "indicator value",
    "value",
    "score",
    "percentage",
    "percent",
}

DECIMAL_FIELD_TOKENS = {
    "bonus",
    "balance",
    "penalty",
    "amount",
    "rate",
    "score",
    "percentage",
    "percent",
    "tip",
    "fee",
    "cost",
    "total",
    "payout",
}

TYPE_TO_TARGET_TABLE = {
    "jit": "jit_row",
    "penalties": "penalty_row",
    "penalty": "penalty_row",
    "atm_balance": "atm_balance_row",
    "bonus": "bonus_route_row",
    "bonus_route": "bonus_route_row",
    "bonus_routes": "bonus_route_row",
    "performance_indicator": "performance_indicator_row",
}


@dataclass
class ValidationIssue:
    """One validation or processing issue."""

    error_code: str
    severity: str
    message: str
    sheet_name: str | None = None
    source_row_no: int | None = None
    raw_data: dict[str, Any] | None = None


@dataclass
class SheetProcessingReport:
    """Processing summary for one workbook sheet."""

    sheet_name: str
    detected_type: str | None
    header_row: int | None
    confidence: float | None
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingReport:
    """Complete result of one settlement session processing run."""

    processing_run_id: str
    session_id: str
    status: str
    total_sheets: int = 0
    recognized_sheets: int = 0
    unknown_sheets: int = 0
    total_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    critical_errors: int = 0
    sheets: list[SheetProcessingReport] = field(default_factory=list)
    errors: list[ValidationIssue] = field(default_factory=list)


@dataclass
class SheetAnalysis:
    """Adapter result between the parser and the processor."""

    parsed_sheet: ParsedSheet | None
    source_rows: list[ImportedExcelRow]




def _normalized_field_name(field_name: Any) -> str:
    """Return a stable lowercase field name for type classification."""

    return " ".join(str(field_name or "").strip().casefold().split())


def _parse_localized_decimal(value: Any) -> Decimal | None:
    """Parse Hungarian/German or standard decimal text safely."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("\u00a0", "").replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        parts = text.split(".")
        text = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _decimal_to_json_number(value: Decimal, prefer_integer: bool) -> int | float:
    """Convert Decimal to a JSON-serializable numeric value."""

    if prefer_integer and value == value.to_integral_value():
        return int(value)
    return float(value)


def _is_decimal_field(field_name: str) -> bool:
    """Return whether a field should be stored as a JSON number."""

    if field_name in DECIMAL_FIELDS:
        return True
    tokens = set(field_name.replace("/", " ").replace("&", " ").split())
    return bool(tokens & DECIMAL_FIELD_TOKENS)


def _normalize_scalar(field_name: Any, value: Any) -> Any:
    """Normalize one parser value without guessing unrelated identifiers."""

    normalized_name = _normalized_field_name(field_name)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        value = stripped

    if "date" in normalized_name or normalized_name == "datum":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, str):
            for date_format in DATE_FORMATS:
                try:
                    return datetime.strptime(value, date_format).date().isoformat()
                except ValueError:
                    continue

    if normalized_name in INTEGER_FIELDS:
        parsed_number = _parse_localized_decimal(value)
        if parsed_number is not None:
            return _decimal_to_json_number(parsed_number, prefer_integer=True)

    if _is_decimal_field(normalized_name):
        parsed_number = _parse_localized_decimal(value)
        if parsed_number is not None:
            return _decimal_to_json_number(parsed_number, prefer_integer=False)

    return value


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a parser record into JSON-safe database values."""

    normalized: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            normalized[key] = _normalize_record(value)
        elif isinstance(value, list):
            normalized[key] = [
                _normalize_record(item) if isinstance(item, dict)
                else _normalize_scalar(key, item)
                for item in value
            ]
        else:
            normalized[key] = _normalize_scalar(key, value)
    return normalized


def _table(client: Client, table_name: str) -> Any:
    """Return a table query builder in the settlement schema."""

    schema_method = getattr(client, "schema", None)
    if callable(schema_method):
        return schema_method(SCHEMA_NAME).table(table_name)
    return client.table(table_name)


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _chunks(
    rows: Sequence[dict[str, Any]],
    batch_size: int,
) -> Iterable[list[dict[str, Any]]]:
    """Yield rows in fixed-size batches."""

    for start in range(0, len(rows), batch_size):
        yield list(rows[start:start + batch_size])


def _response_rows(response: Any) -> list[dict[str, Any]]:
    """Read list data from a Supabase response."""

    data = getattr(response, "data", None)
    if not data:
        return []
    return list(data)


def _read_session_rows(
    client: Client,
    session_id: str,
    page_size: int,
) -> list[ImportedExcelRow]:
    """Read all raw import rows for one session without modifying them."""

    records: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            _table(client, IMPORT_TABLE)
            .select("session_id,row_no,sheet_name,source_row_no,data")
            .eq("session_id", session_id)
            .order("sheet_name")
            .order("source_row_no")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = _response_rows(response)
        records.extend(page)

        if len(page) < page_size:
            break
        offset += page_size

    return [
        ImportedExcelRow(
            session_id=str(record.get("session_id") or ""),
            row_no=int(record.get("row_no") or 0),
            sheet_name=str(record.get("sheet_name") or ""),
            source_row_no=int(record.get("source_row_no") or 0),
            data=record.get("data") or {},
        )
        for record in records
    ]


def _group_by_sheet(
    rows: Sequence[ImportedExcelRow],
) -> dict[str, list[ImportedExcelRow]]:
    """Group raw rows by source sheet without using its name as a rule."""

    grouped: dict[str, list[ImportedExcelRow]] = {}
    for row in rows:
        grouped.setdefault(row.sheet_name, []).append(row)
    return grouped


def analyze_and_parse_sheet(
    sheet_name: str,
    rows: list[dict[str, Any]] | Sequence[ImportedExcelRow],
) -> SheetAnalysis:
    """Run the registered parser classes and return the best match.

    ``sheet_name`` is used only as source metadata. Sheet type detection is
    performed exclusively by the existing parser rules.
    """

    imported_rows: list[ImportedExcelRow] = []

    for index, row in enumerate(rows, start=1):
        if isinstance(row, ImportedExcelRow):
            imported_rows.append(row)
            continue

        imported_rows.append(
            ImportedExcelRow(
                session_id=str(row.get("session_id") or ""),
                row_no=int(row.get("row_no") or index),
                sheet_name=sheet_name,
                source_row_no=int(row.get("source_row_no") or index),
                data=row.get("data") or {},
            )
        )

    candidates: list[ParsedSheet] = []
    for parser_class in DEFAULT_PARSERS:
        parsed = parser_class(imported_rows).parse()
        if parsed is not None:
            candidates.append(parsed)

    parsed_sheet = (
        max(candidates, key=lambda candidate: candidate.confidence)
        if candidates
        else None
    )
    return SheetAnalysis(
        parsed_sheet=parsed_sheet,
        source_rows=imported_rows,
    )


def _ordered_raw_values(row: ImportedExcelRow) -> list[Any]:
    """Return raw values in column_N order while preserving empty gaps."""

    numbered_values: dict[int, Any] = {}
    highest_column = 0

    for key, value in row.data.items():
        key_text = str(key)
        if not key_text.startswith("column_"):
            continue
        try:
            column_number = int(key_text.rsplit("_", 1)[1])
        except (TypeError, ValueError):
            continue
        numbered_values[column_number] = value
        highest_column = max(highest_column, column_number)

    return [
        numbered_values.get(column_number)
        for column_number in range(1, highest_column + 1)
    ]


def _pair_records_with_source_rows(
    parsed_sheet: ParsedSheet,
    source_rows: Sequence[ImportedExcelRow],
) -> tuple[
    list[tuple[int, dict[str, Any]]],
    list[ValidationIssue],
]:
    """Pair parser records with their original Excel row numbers."""

    source_rows_by_number = {
        row.source_row_no: row
        for row in source_rows
    }
    candidate_rows = [
        row
        for row in sorted(source_rows, key=lambda item: item.source_row_no)
        if row.source_row_no > parsed_sheet.header_source_row_no
        and not is_empty_row(_ordered_raw_values(row))
    ]
    issues: list[ValidationIssue] = []

    explicit_pairs: list[tuple[int, dict[str, Any]]] = []
    records_without_source_row: list[dict[str, Any]] = []
    for record in parsed_sheet.records:
        source_row_no = record.get("source_row_no")
        if (
            isinstance(source_row_no, int)
            and source_row_no in source_rows_by_number
        ):
            explicit_pairs.append((source_row_no, record))
        else:
            records_without_source_row.append(record)

    if explicit_pairs and not records_without_source_row:
        return explicit_pairs, issues

    if explicit_pairs:
        issues.append(
            ValidationIssue(
                error_code="PARTIAL_SOURCE_ROW_MAPPING",
                severity="warning",
                message=(
                    "Csak a rekordok egy része tartalmazott érvényes "
                    "source_row_no értéket; a többi rekord pozíció alapján "
                    "került párosításra."
                ),
                sheet_name=parsed_sheet.sheet_name,
                raw_data={
                    "explicit_record_count": len(explicit_pairs),
                    "fallback_record_count": len(records_without_source_row),
                },
            )
        )

    if len(candidate_rows) != len(parsed_sheet.records):
        issues.append(
            ValidationIssue(
                error_code="SOURCE_ROW_MAPPING_MISMATCH",
                severity="error",
                message=(
                    "A normalizált rekordok és a forrássorok száma eltér: "
                    f"{len(parsed_sheet.records)} rekord, "
                    f"{len(candidate_rows)} forrássor."
                ),
                sheet_name=parsed_sheet.sheet_name,
                raw_data={
                    "record_count": len(parsed_sheet.records),
                    "source_row_count": len(candidate_rows),
                },
            )
        )

    used_source_rows = {
        source_row_no
        for source_row_no, _record in explicit_pairs
    }
    fallback_candidates = [
        row
        for row in candidate_rows
        if row.source_row_no not in used_source_rows
    ]
    fallback_count = min(
        len(fallback_candidates),
        len(records_without_source_row),
    )
    fallback_pairs = [
        (
            fallback_candidates[index].source_row_no,
            records_without_source_row[index],
        )
        for index in range(fallback_count)
    ]
    return explicit_pairs + fallback_pairs, issues


def _convert_parser_issues(
    parsed_sheet: ParsedSheet,
) -> list[ValidationIssue]:
    """Convert parser-level issues to persistent processor issues."""

    return [
        ValidationIssue(
            error_code=issue.error_code,
            severity=issue.severity,
            message=issue.message,
            sheet_name=parsed_sheet.sheet_name,
            source_row_no=issue.source_row_no,
            raw_data=issue.raw_data,
        )
        for issue in parsed_sheet.validation_issues
    ]


def _create_processing_run(client: Client, session_id: str) -> str:
    """Create and return a running processing run identifier."""

    response = (
        _table(client, PROCESSING_RUN_TABLE)
        .insert(
            {
                "session_id": session_id,
                "status": "running",
            }
        )
        .execute()
    )
    rows = _response_rows(response)
    if not rows or not rows[0].get("id"):
        raise RuntimeError("A processing_run rekord nem jött létre.")
    return str(rows[0]["id"])


def _upsert_normalized_rows(
    client: Client,
    table_name: str,
    rows: Sequence[dict[str, Any]],
    batch_size: int,
) -> None:
    """Batch-upsert normalized rows using their stable source identity."""

    for batch in _chunks(rows, batch_size):
        (
            _table(client, table_name)
            .upsert(
                batch,
                on_conflict="session_id,source_sheet,source_row_no",
                returning="minimal",
            )
            .execute()
        )


def _insert_sheet_reports(
    client: Client,
    processing_run_id: str,
    session_id: str,
    reports: Sequence[SheetProcessingReport],
    batch_size: int,
) -> None:
    """Persist sheet-level reports in batches."""

    payload = [
        {
            "processing_run_id": processing_run_id,
            "session_id": session_id,
            "sheet_name": report.sheet_name,
            "detected_type": report.detected_type,
            "header_row": report.header_row,
            "confidence": report.confidence,
            "total_rows": report.total_rows,
            "accepted_rows": report.accepted_rows,
            "rejected_rows": report.rejected_rows,
            "status": report.status,
            "details": report.details,
        }
        for report in reports
    ]

    for batch in _chunks(payload, batch_size):
        (
            _table(client, SHEET_RESULT_TABLE)
            .upsert(
                batch,
                on_conflict="processing_run_id,sheet_name",
                returning="minimal",
            )
            .execute()
        )


def _insert_validation_issues(
    client: Client,
    processing_run_id: str,
    session_id: str,
    issues: Sequence[ValidationIssue],
    batch_size: int,
) -> None:
    """Persist validation issues in batches."""

    payload = [
        {
            "processing_run_id": processing_run_id,
            "session_id": session_id,
            "sheet_name": issue.sheet_name,
            "source_row_no": issue.source_row_no,
            "error_code": issue.error_code,
            "severity": issue.severity,
            "message": issue.message,
            "raw_data": issue.raw_data,
        }
        for issue in issues
    ]

    for batch in _chunks(payload, batch_size):
        (
            _table(client, VALIDATION_ERROR_TABLE)
            .insert(batch, returning="minimal")
            .execute()
        )


def _report_summary(report: ProcessingReport) -> dict[str, Any]:
    """Build a compact JSON summary for processing_run."""

    return {
        "sheet_statuses": {
            sheet.sheet_name: sheet.status
            for sheet in report.sheets
        },
        "error_counts": {
            severity: sum(
                issue.severity == severity
                for issue in report.errors
            )
            for severity in ("info", "warning", "error", "critical")
        },
    }


def _finish_processing_run(
    client: Client,
    report: ProcessingReport,
) -> None:
    """Write final counters and status to processing_run."""

    (
        _table(client, PROCESSING_RUN_TABLE)
        .update(
            {
                "status": report.status,
                "finished_at": _utc_now_iso(),
                "total_sheets": report.total_sheets,
                "recognized_sheets": report.recognized_sheets,
                "unknown_sheets": report.unknown_sheets,
                "total_rows": report.total_rows,
                "accepted_rows": report.accepted_rows,
                "rejected_rows": report.rejected_rows,
                "critical_errors": report.critical_errors,
                "summary": _report_summary(report),
            }
        )
        .eq("id", report.processing_run_id)
        .execute()
    )


def _refresh_report_totals(report: ProcessingReport) -> None:
    """Recalculate top-level counters from sheet reports and issues."""

    report.total_sheets = len(report.sheets)
    report.recognized_sheets = sum(
        sheet.detected_type is not None
        for sheet in report.sheets
    )
    report.unknown_sheets = sum(
        sheet.detected_type is None
        for sheet in report.sheets
    )
    report.total_rows = sum(sheet.total_rows for sheet in report.sheets)
    report.accepted_rows = sum(
        sheet.accepted_rows
        for sheet in report.sheets
    )
    report.rejected_rows = sum(
        sheet.rejected_rows
        for sheet in report.sheets
    )
    report.critical_errors = sum(
        issue.severity == "critical"
        for issue in report.errors
    )


def _process_sheet(
    processing_run_id: str,
    session_id: str,
    sheet_name: str,
    source_rows: list[ImportedExcelRow],
) -> tuple[
    SheetProcessingReport,
    list[ValidationIssue],
    str | None,
    list[dict[str, Any]],
]:
    """Analyze one sheet and build its persistence payload."""

    analysis = analyze_and_parse_sheet(sheet_name, source_rows)
    parsed = analysis.parsed_sheet

    if parsed is None:
        issue = ValidationIssue(
            error_code="UNKNOWN_SHEET_TYPE",
            severity="warning",
            message=(
                "A munkalap típusa tartalom alapján nem volt felismerhető."
            ),
            sheet_name=sheet_name,
            raw_data={"raw_row_count": len(source_rows)},
        )
        return (
            SheetProcessingReport(
                sheet_name=sheet_name,
                detected_type=None,
                header_row=None,
                confidence=None,
                total_rows=len(source_rows),
                accepted_rows=0,
                rejected_rows=len(source_rows),
                status="unknown",
            ),
            [issue],
            None,
            [],
        )

    target_table = TYPE_TO_TARGET_TABLE.get(parsed.sheet_type)
    if target_table is None:
        issue = ValidationIssue(
            error_code="UNSUPPORTED_SHEET_TYPE",
            severity="warning",
            message=(
                "A felismert munkalaptípushoz nincs cél tábla: "
                f"{parsed.sheet_type}."
            ),
            sheet_name=sheet_name,
        )
        return (
            SheetProcessingReport(
                sheet_name=sheet_name,
                detected_type=parsed.sheet_type,
                header_row=parsed.header_source_row_no,
                confidence=parsed.confidence,
                total_rows=len(parsed.records),
                accepted_rows=0,
                rejected_rows=len(parsed.records),
                status="unsupported",
                details={"parser_name": parsed.parser_name},
            ),
            [issue],
            None,
            [],
        )

    pairs, mapping_issues = _pair_records_with_source_rows(
        parsed,
        source_rows,
    )
    issues = _convert_parser_issues(parsed) + mapping_issues
    normalized_rows = [
        {
            "processing_run_id": processing_run_id,
            "session_id": session_id,
            "source_sheet": sheet_name,
            "source_row_no": source_row_no,
            "normalized_data": _normalize_record(normalized_data),
        }
        for source_row_no, normalized_data in pairs
    ]
    rejected_rows = parsed.rejected_rows + max(
        len(parsed.records) - len(normalized_rows),
        0,
    )

    return (
        SheetProcessingReport(
            sheet_name=sheet_name,
            detected_type=parsed.sheet_type,
            header_row=parsed.header_source_row_no,
            confidence=parsed.confidence,
            total_rows=(
                parsed.source_data_rows
                if parsed.source_data_rows
                else len(parsed.records)
            ),
            accepted_rows=len(normalized_rows),
            rejected_rows=rejected_rows,
            status=(
                "completed"
                if not issues and rejected_rows == 0
                else "completed_with_warnings"
            ),
            details={
                "parser_name": parsed.parser_name,
                "target_table": target_table,
                "headers": parsed.headers,
            },
        ),
        issues,
        target_table,
        normalized_rows,
    )


def process_settlement_session(
    supabase_client: Client,
    session_id: str,
) -> ProcessingReport:
    """Process one imported settlement session into normalized tables.

    The raw ``settlement.excel_import`` rows are read-only. Reprocessing the
    same session uses source-based upserts, so it does not create duplicate
    normalized rows.
    """

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise ValueError("A session_id megadása kötelező.")

    processing_run_id = _create_processing_run(
        supabase_client,
        normalized_session_id,
    )
    report = ProcessingReport(
        processing_run_id=processing_run_id,
        session_id=normalized_session_id,
        status="running",
    )
    reports_persisted = False
    issues_persisted = False

    try:
        raw_rows = _read_session_rows(
            supabase_client,
            normalized_session_id,
            DEFAULT_PAGE_SIZE,
        )
        if not raw_rows:
            report.errors.append(
                ValidationIssue(
                    error_code="SESSION_NOT_FOUND",
                    severity="critical",
                    message=(
                        "A megadott session_id-hoz nincs nyers Excel sor."
                    ),
                )
            )
            report.status = "failed"
            _refresh_report_totals(report)
            _insert_validation_issues(
                supabase_client,
                processing_run_id,
                normalized_session_id,
                report.errors,
                DEFAULT_BATCH_SIZE,
            )
            issues_persisted = True
            _finish_processing_run(supabase_client, report)
            return report

        normalized_by_table: dict[str, list[dict[str, Any]]] = {}

        for sheet_name, sheet_rows in _group_by_sheet(raw_rows).items():
            (
                sheet_report,
                issues,
                target_table,
                normalized_rows,
            ) = _process_sheet(
                processing_run_id=processing_run_id,
                session_id=normalized_session_id,
                sheet_name=sheet_name,
                source_rows=sheet_rows,
            )
            report.sheets.append(sheet_report)
            report.errors.extend(issues)

            if target_table and normalized_rows:
                normalized_by_table.setdefault(target_table, []).extend(
                    normalized_rows
                )

        for table_name, normalized_rows in normalized_by_table.items():
            _upsert_normalized_rows(
                supabase_client,
                table_name,
                normalized_rows,
                DEFAULT_BATCH_SIZE,
            )

        _insert_sheet_reports(
            supabase_client,
            processing_run_id,
            normalized_session_id,
            report.sheets,
            DEFAULT_BATCH_SIZE,
        )
        reports_persisted = True

        _insert_validation_issues(
            supabase_client,
            processing_run_id,
            normalized_session_id,
            report.errors,
            DEFAULT_BATCH_SIZE,
        )
        issues_persisted = True

        _refresh_report_totals(report)
        has_warnings = bool(report.errors or report.rejected_rows)
        report.status = (
            "completed_with_warnings"
            if has_warnings
            else "completed"
        )
        _finish_processing_run(supabase_client, report)
        return report

    except Exception as exc:
        critical_issue = ValidationIssue(
            error_code="PROCESSING_FAILED",
            severity="critical",
            message=f"{type(exc).__name__}: {exc}",
        )
        report.errors.append(critical_issue)
        report.status = "failed"
        _refresh_report_totals(report)

        try:
            if report.sheets and not reports_persisted:
                _insert_sheet_reports(
                    supabase_client,
                    processing_run_id,
                    normalized_session_id,
                    report.sheets,
                    DEFAULT_BATCH_SIZE,
                )
        except Exception:
            pass

        try:
            issues_to_persist = (
                [critical_issue]
                if issues_persisted
                else report.errors
            )
            _insert_validation_issues(
                supabase_client,
                processing_run_id,
                normalized_session_id,
                issues_to_persist,
                DEFAULT_BATCH_SIZE,
            )
        except Exception:
            pass

        try:
            _finish_processing_run(supabase_client, report)
        except Exception:
            pass

        return report


def report_as_dict(report: ProcessingReport) -> dict[str, Any]:
    """Return a JSON-serializable representation of a report."""

    return asdict(report)