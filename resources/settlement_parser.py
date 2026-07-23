from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, Mapping, Sequence
import re
import unicodedata

import pandas as pd
from supabase import Client


IMPORT_TABLE = "excel_import"
DEFAULT_PAGE_SIZE = 1000


@dataclass(frozen=True)
class ImportedExcelRow:
    """One raw row from settlement.excel_import."""

    session_id: str
    row_no: int
    sheet_name: str
    source_row_no: int
    data: Mapping[str, Any]


@dataclass(frozen=True)
class HeaderDetection:
    """Result of a content-based header lookup inside one sheet."""

    header_index: int
    score: float
    matched_required_groups: int
    matched_optional_groups: int


@dataclass(frozen=True)
class SheetRule:
    """Rule that identifies a logical sheet type by header content."""

    sheet_type: str
    required_groups: tuple[tuple[str, ...], ...]
    optional_groups: tuple[tuple[str, ...], ...] = ()


@dataclass
class ParsedSheet:
    """Normalized output of one parsed sheet."""

    sheet_name: str
    sheet_type: str
    parser_name: str
    header_source_row_no: int
    confidence: float
    headers: list[str]
    records: list[dict[str, Any]] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Return records as a pandas DataFrame."""

        return pd.DataFrame(self.records)


@dataclass
class WorkbookParseResult:
    """Parse result for a full Excel import session."""

    session_id: str
    sheets: list[ParsedSheet] = field(default_factory=list)
    unknown_sheets: list[str] = field(default_factory=list)

    def by_type(self, sheet_type: str) -> list[ParsedSheet]:
        """Return all parsed sheets with the requested logical type."""

        normalized = normalize_text(sheet_type)
        return [
            sheet
            for sheet in self.sheets
            if normalize_text(sheet.sheet_type) == normalized
        ]

    def as_dict(self) -> dict[str, Any]:
        """Return a lightweight JSON-serializable summary."""

        return {
            "session_id": self.session_id,
            "parsed_sheets": [
                {
                    "sheet_name": sheet.sheet_name,
                    "sheet_type": sheet.sheet_type,
                    "parser_name": sheet.parser_name,
                    "header_source_row_no": sheet.header_source_row_no,
                    "confidence": sheet.confidence,
                    "row_count": len(sheet.records),
                    "headers": sheet.headers,
                }
                for sheet in self.sheets
            ],
            "unknown_sheets": self.unknown_sheets,
        }


def normalize_text(value: Any) -> str:
    """Normalize text for robust, accent-insensitive matching."""

    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def column_number(column_key: str) -> int:
    """Return the numeric part from column_1, column_2, ... keys."""

    match = re.search(r"(\d+)$", str(column_key))
    if not match:
        return 0
    return int(match.group(1))


def build_matrix(rows: Sequence[ImportedExcelRow]) -> list[list[Any]]:
    """Build a row matrix from raw JSONB column_N values."""

    matrix: list[list[Any]] = []

    for row in sorted(rows, key=lambda item: item.source_row_no):
        ordered_values = [
            value
            for _key, value in sorted(
                row.data.items(),
                key=lambda item: column_number(item[0]),
            )
        ]
        matrix.append(ordered_values)

    return matrix


def is_empty_row(row: Sequence[Any]) -> bool:
    """Return True when every cell in a row is empty-like."""

    return all(cell is None or str(cell).strip() == "" for cell in row)


def make_unique_header(header: str, used_headers: set[str], index: int) -> str:
    """Make a stable unique header name."""

    base = str(header).strip() if header is not None else ""
    if not base:
        base = f"unnamed_{index + 1}"

    candidate = base
    suffix = 2

    while candidate in used_headers:
        candidate = f"{base}_{suffix}"
        suffix += 1

    used_headers.add(candidate)
    return candidate


def group_matches(row_text: str, group: Iterable[str]) -> bool:
    """Return True if any alias from a rule group is present in row text."""

    normalized_aliases = [normalize_text(alias) for alias in group]
    return any(alias and alias in row_text for alias in normalized_aliases)


class BaseSheetParser:
    """Base class for content-based settlement sheet parsers."""

    RULE: ClassVar[SheetRule]
    MIN_CONFIDENCE: ClassVar[float] = 0.65

    def __init__(self, rows: Sequence[ImportedExcelRow]) -> None:
        self.rows = list(rows)
        self.matrix = build_matrix(self.rows)

    @classmethod
    def sheet_type(cls) -> str:
        """Return the logical sheet type handled by this parser."""

        return cls.RULE.sheet_type

    def parse(self) -> ParsedSheet | None:
        """Parse the sheet when the content matches this parser rule."""

        detection = self.detect_header()
        if detection is None:
            return None

        confidence = self.calculate_confidence(detection)
        if confidence < self.MIN_CONFIDENCE:
            return None

        header_row = self.matrix[detection.header_index]
        headers = self.normalize_headers(header_row)
        records = self.normalize_records(detection.header_index, headers)
        sheet_name = self.rows[0].sheet_name if self.rows else ""
        source_row_no = self.rows[detection.header_index].source_row_no

        return ParsedSheet(
            sheet_name=sheet_name,
            sheet_type=self.sheet_type(),
            parser_name=self.__class__.__name__,
            header_source_row_no=source_row_no,
            confidence=confidence,
            headers=headers,
            records=records,
        )

    def detect_header(self) -> HeaderDetection | None:
        """Find the best header row based on required/optional groups."""

        best: HeaderDetection | None = None

        for index, row in enumerate(self.matrix):
            row_text = " ".join(normalize_text(cell) for cell in row)
            if not row_text:
                continue

            required_matches = sum(
                1
                for group in self.RULE.required_groups
                if group_matches(row_text, group)
            )

            if required_matches < len(self.RULE.required_groups):
                continue

            optional_matches = sum(
                1
                for group in self.RULE.optional_groups
                if group_matches(row_text, group)
            )
            non_empty_count = sum(1 for cell in row if str(cell).strip())
            score = required_matches * 10 + optional_matches * 2 + non_empty_count / 100

            candidate = HeaderDetection(
                header_index=index,
                score=score,
                matched_required_groups=required_matches,
                matched_optional_groups=optional_matches,
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def calculate_confidence(self, detection: HeaderDetection) -> float:
        """Calculate parser confidence from matched rule groups."""

        required_total = max(len(self.RULE.required_groups), 1)
        optional_total = max(len(self.RULE.optional_groups), 1)
        required_score = detection.matched_required_groups / required_total
        optional_score = detection.matched_optional_groups / optional_total

        if not self.RULE.optional_groups:
            return required_score

        return min(1.0, required_score * 0.85 + optional_score * 0.15)

    def normalize_headers(self, header_row: Sequence[Any]) -> list[str]:
        """Normalize raw header cells into unique dictionary keys."""

        used_headers: set[str] = set()
        return [
            make_unique_header(str(cell or "").strip(), used_headers, index)
            for index, cell in enumerate(header_row)
        ]

    def normalize_records(
        self,
        header_index: int,
        headers: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Convert rows below the header to list[dict] records."""

        records: list[dict[str, Any]] = []

        for raw_row in self.matrix[header_index + 1 :]:
            if is_empty_row(raw_row):
                continue

            record: dict[str, Any] = {}
            for index, header in enumerate(headers):
                value = raw_row[index] if index < len(raw_row) else None
                record[header] = value

            if any(value is not None and str(value).strip() for value in record.values()):
                records.append(record)

        return records


class JITParser(BaseSheetParser):
    """Parser for the main JIT invoice/performance table."""

    RULE = SheetRule(
        sheet_type="jit",
        required_groups=(
            ("route", "route id", "kor"),
            ("driver", "courier", "futar", "nev"),
            ("amount", "total", "osszeg", "fizetendo"),
        ),
        optional_groups=(
            ("invoice", "szamla"),
            ("order", "rendeles"),
        ),
    )


class PenaltyParser(BaseSheetParser):
    """Parser for penalty/malus tables."""

    RULE = SheetRule(
        sheet_type="penalties",
        required_groups=(
            ("penalty", "malus", "levonas", "buntetes"),
            ("amount", "osszeg", "ft"),
        ),
        optional_groups=(
            ("driver", "courier", "futar", "nev"),
            ("reason", "indok", "megjegyzes"),
        ),
    )


class ATMParser(BaseSheetParser):
    """Parser for ATM / cash balance sheets."""

    RULE = SheetRule(
        sheet_type="atm_balance",
        required_groups=(
            ("atm", "cash", "kp"),
            ("balance", "egyenleg", "hiany", "tobblet"),
        ),
        optional_groups=(
            ("driver", "courier", "futar", "nev"),
            ("amount", "osszeg", "ft"),
        ),
    )


class BonusParser(BaseSheetParser):
    """Parser for bonus tables."""

    RULE = SheetRule(
        sheet_type="bonus",
        required_groups=(
            ("bonus", "bonusz", "premium"),
            ("amount", "osszeg", "ft"),
        ),
        optional_groups=(
            ("driver", "courier", "futar", "nev"),
            ("reason", "indok", "megjegyzes"),
        ),
    )


DEFAULT_PARSERS: tuple[type[BaseSheetParser], ...] = (
    JITParser,
    PenaltyParser,
    ATMParser,
    BonusParser,
)


class SettlementImportParser:
    """Parse a full settlement Excel import session from Supabase."""

    def __init__(
        self,
        supabase: Client,
        parser_classes: Sequence[type[BaseSheetParser]] | None = None,
        table_name: str = IMPORT_TABLE,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self.supabase = supabase
        self.parser_classes = tuple(parser_classes or DEFAULT_PARSERS)
        self.table_name = table_name
        self.page_size = page_size

    def parse_session(self, session_id: str) -> WorkbookParseResult:
        """Read and parse every row belonging to a session_id."""

        rows = self.read_session_rows(session_id)
        grouped_rows = self.group_by_sheet(rows)
        result = WorkbookParseResult(session_id=session_id)

        for sheet_name, sheet_rows in grouped_rows.items():
            parsed_sheet = self.parse_sheet(sheet_rows)
            if parsed_sheet is None:
                result.unknown_sheets.append(sheet_name)
            else:
                result.sheets.append(parsed_sheet)

        return result

    def read_session_rows(self, session_id: str) -> list[ImportedExcelRow]:
        """Read a complete import session from settlement.excel_import."""

        if not session_id or not str(session_id).strip():
            raise ValueError("session_id is required.")

        records: list[dict[str, Any]] = []
        offset = 0

        while True:
            response = (
                self.supabase
                .table(self.table_name)
                .select("session_id,row_no,sheet_name,source_row_no,data")
                .eq("session_id", session_id)
                .order("sheet_name")
                .order("source_row_no")
                .range(offset, offset + self.page_size - 1)
                .execute()
            )
            page = response.data or []
            records.extend(page)

            if len(page) < self.page_size:
                break

            offset += self.page_size

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

    @staticmethod
    def group_by_sheet(
        rows: Sequence[ImportedExcelRow],
    ) -> dict[str, list[ImportedExcelRow]]:
        """Group raw rows by sheet_name without using it for type detection."""

        grouped: dict[str, list[ImportedExcelRow]] = {}

        for row in rows:
            grouped.setdefault(row.sheet_name, []).append(row)

        return grouped

    def parse_sheet(
        self,
        rows: Sequence[ImportedExcelRow],
    ) -> ParsedSheet | None:
        """Run every registered parser and return the best matching result."""

        candidates: list[ParsedSheet] = []

        for parser_class in self.parser_classes:
            parsed_sheet = parser_class(rows).parse()
            if parsed_sheet is not None:
                candidates.append(parsed_sheet)

        if not candidates:
            return None

        return max(candidates, key=lambda sheet: sheet.confidence)


def parse_import_session(
    supabase: Client,
    session_id: str,
    parser_classes: Sequence[type[BaseSheetParser]] | None = None,
) -> WorkbookParseResult:
    """Convenience function for parsing one imported Excel session."""

    parser = SettlementImportParser(
        supabase=supabase,
        parser_classes=parser_classes,
    )
    return parser.parse_session(session_id)
