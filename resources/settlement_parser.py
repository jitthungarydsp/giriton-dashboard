"""Name-first, content-fallback parsers for raw settlement Excel imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, Mapping, Sequence, TYPE_CHECKING
import re
import unicodedata

import pandas as pd

if TYPE_CHECKING:
    from supabase import Client
else:
    Client = Any


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
class SheetNameDetection:
    """Certain sheet type inferred from the normalized source sheet name."""

    sheet_type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class SheetRule:
    """Rule that identifies a logical sheet type by header content."""

    sheet_type: str
    required_groups: tuple[tuple[str, ...], ...]
    optional_groups: tuple[tuple[str, ...], ...] = ()


@dataclass
class ParserValidationIssue:
    """Validation issue produced while parsing one source sheet."""

    error_code: str
    severity: str
    message: str
    source_row_no: int | None = None
    raw_data: dict[str, Any] | None = None


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
    validation_issues: list[ParserValidationIssue] = field(
        default_factory=list
    )
    source_data_rows: int = 0
    rejected_rows: int = 0

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
                    "rejected_rows": sheet.rejected_rows,
                    "issue_count": len(sheet.validation_issues),
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
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_sheet_type_from_name(
    sheet_name: str,
) -> SheetNameDetection | None:
    """Return a certain type when the normalized sheet name is known.

    Name rules intentionally run before content scoring. Content detection is
    reserved for sheets whose normalized name has no explicit mapping.
    """

    normalized_name = normalize_text(sheet_name)
    exact_types = {
        "atm": "atm_balance",
        "atm balance": "atm_balance",
        "bonus routes": "bonus",
        "penalties": "penalties",
        "kesedelmi mutato": "performance_indicator",
        "turamegfelelesi mutato": "performance_indicator",
    }

    exact_type = exact_types.get(normalized_name)
    if exact_type is not None:
        return SheetNameDetection(
            sheet_type=exact_type,
            confidence=1.0,
            reason=f"exact_normalized_sheet_name:{normalized_name}",
        )

    name_tokens = set(normalized_name.split())
    if "jit" in name_tokens or normalized_name.endswith(" jit"):
        return SheetNameDetection(
            sheet_type="jit",
            confidence=1.0,
            reason=f"normalized_sheet_name_contains:JIT ({normalized_name})",
        )

    return None


def column_number(column_key: str) -> int:
    """Return the numeric part from column_1, column_2, ... keys."""

    match = re.search(r"(\d+)$", str(column_key))
    if not match:
        return 0
    return int(match.group(1))


def build_matrix(rows: Sequence[ImportedExcelRow]) -> list[list[Any]]:
    """Build a row matrix while preserving empty Excel column positions."""

    matrix: list[list[Any]] = []

    for row in sorted(rows, key=lambda item: item.source_row_no):
        numbered_values = {
            column_number(key): value
            for key, value in row.data.items()
            if column_number(key) > 0
        }
        highest_column = max(numbered_values, default=0)
        matrix.append(
            [
                numbered_values.get(index)
                for index in range(1, highest_column + 1)
            ]
        )

    return matrix


def is_empty_row(row: Sequence[Any]) -> bool:
    """Return True when every cell in a row is empty-like."""

    return all(
        cell is None or str(cell).strip() == ""
        for cell in row
    )


def make_unique_header(
    header: str,
    used_headers: set[str],
    index: int,
) -> str:
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
    return any(
        alias and alias in row_text
        for alias in normalized_aliases
    )


def first_matching_index(
    values: Sequence[Any],
    aliases: Iterable[str],
    excluded_indexes: set[int] | None = None,
) -> int | None:
    """Return the first index whose normalized text matches an alias."""

    excluded = excluded_indexes or set()
    for index, value in enumerate(values):
        if index in excluded:
            continue
        if group_matches(normalize_text(value), aliases):
            return index
    return None


class BaseSheetParser:
    """Base class for content-based settlement sheet parsers."""

    RULE: ClassVar[SheetRule]
    MIN_CONFIDENCE: ClassVar[float] = 0.65

    def __init__(self, rows: Sequence[ImportedExcelRow]) -> None:
        self.rows = sorted(
            rows,
            key=lambda item: item.source_row_no,
        )
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
            source_data_rows=len(records),
        )

    def parse_with_forced_type(self) -> ParsedSheet | None:
        """Parse a name-identified sheet even when content confidence is low."""

        detection = self.detect_header() or self.detect_generic_header()
        if detection is None:
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
            confidence=1.0,
            headers=headers,
            records=records,
            source_data_rows=len(records),
        )

    def detect_generic_header(self) -> HeaderDetection | None:
        """Find a plausible tabular header for a name-identified sheet."""

        best: HeaderDetection | None = None

        for index, row in enumerate(self.matrix):
            non_empty_indexes = [
                cell_index
                for cell_index, cell in enumerate(row)
                if cell is not None and str(cell).strip()
            ]
            if len(non_empty_indexes) < 2:
                continue

            normalized_cells = [
                normalize_text(row[cell_index])
                for cell_index in non_empty_indexes
            ]
            text_cells = sum(
                1
                for cell_index in non_empty_indexes
                if isinstance(row[cell_index], str)
                and normalize_text(row[cell_index])
            )
            unique_cells = len(set(normalized_cells))
            if text_cells < 2 or unique_cells < 2:
                continue

            following_support = 0
            for following_row in self.matrix[index + 1:index + 6]:
                populated = sum(
                    1
                    for cell_index in non_empty_indexes
                    if cell_index < len(following_row)
                    and following_row[cell_index] is not None
                    and str(following_row[cell_index]).strip()
                )
                if populated >= min(2, len(non_empty_indexes)):
                    following_support += 1

            score = (
                text_cells * 2
                + unique_cells
                + following_support * 3
                + len(non_empty_indexes) / 100
                - index / 1000
            )
            candidate = HeaderDetection(
                header_index=index,
                score=score,
                matched_required_groups=0,
                matched_optional_groups=0,
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best

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
            non_empty_count = sum(
                1
                for cell in row
                if str(cell).strip()
            )
            score = (
                required_matches * 10
                + optional_matches * 2
                + non_empty_count / 100
            )

            candidate = HeaderDetection(
                header_index=index,
                score=score,
                matched_required_groups=required_matches,
                matched_optional_groups=optional_matches,
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def calculate_confidence(
        self,
        detection: HeaderDetection,
    ) -> float:
        """Calculate parser confidence from matched rule groups."""

        required_total = max(len(self.RULE.required_groups), 1)
        optional_total = max(len(self.RULE.optional_groups), 1)
        required_score = (
            detection.matched_required_groups / required_total
        )
        optional_score = (
            detection.matched_optional_groups / optional_total
        )

        if not self.RULE.optional_groups:
            return required_score

        return min(
            1.0,
            required_score * 0.85 + optional_score * 0.15,
        )

    def normalize_headers(
        self,
        header_row: Sequence[Any],
    ) -> list[str]:
        """Normalize raw header cells into unique dictionary keys."""

        used_headers: set[str] = set()
        return [
            make_unique_header(
                str(cell or "").strip(),
                used_headers,
                index,
            )
            for index, cell in enumerate(header_row)
        ]

    def normalize_records(
        self,
        header_index: int,
        headers: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Convert rows below the header to list[dict] records."""

        records: list[dict[str, Any]] = []

        for raw_row in self.matrix[header_index + 1:]:
            if is_empty_row(raw_row):
                continue

            record: dict[str, Any] = {}
            for index, header in enumerate(headers):
                value = (
                    raw_row[index]
                    if index < len(raw_row)
                    else None
                )
                record[header] = value

            if any(
                value is not None and str(value).strip()
                for value in record.values()
            ):
                records.append(record)

        return records


class JITParser(BaseSheetParser):
    """Parser for the main JIT invoice/performance table."""

    RULE = SheetRule(
        sheet_type="jit",
        required_groups=(
            ("route", "route id", "kor"),
            ("driver", "courier", "futar", "nev"),
            (
                "amount",
                "total",
                "osszeg",
                "fizetendo",
                "fixed rate",
                "alapdij",
            ),
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
        required_groups=(),
    )
    MIN_CONFIDENCE = 0.65

    BALANCE_ALIASES: ClassVar[tuple[str, ...]] = (
        "balance",
        "egyenleg",
        "deduction",
        "deductions",
        "levonas",
        "hiany",
        "tobblet",
    )
    ENTITY_ALIASES: ClassVar[tuple[str, ...]] = (
        "name",
        "nev",
        "driver",
        "courier",
        "futar",
        "partner",
    )
    ORGANIZATION_ALIASES: ClassVar[tuple[str, ...]] = (
        "dsp",
        "site",
        "standort",
        "warehouse",
        "depot",
        "raktar",
    )
    CASH_ALIASES: ClassVar[tuple[str, ...]] = (
        "atm",
        "cash",
        "wallet",
        "kp",
        "keszpenz",
    )
    AMOUNT_ALIASES: ClassVar[tuple[str, ...]] = (
        "amount",
        "osszeg",
        "huf",
        "currency",
        "penznem",
    )

    def detect_header(self) -> HeaderDetection | None:
        """Find a balance table from several independent content signals."""

        best: HeaderDetection | None = None

        for index, row in enumerate(self.matrix):
            row_text = " ".join(normalize_text(cell) for cell in row)
            if not row_text:
                continue

            balance_match = group_matches(
                row_text,
                self.BALANCE_ALIASES,
            )
            entity_match = group_matches(row_text, self.ENTITY_ALIASES)
            organization_match = group_matches(
                row_text,
                self.ORGANIZATION_ALIASES,
            )
            cash_match = group_matches(row_text, self.CASH_ALIASES)
            amount_match = group_matches(row_text, self.AMOUNT_ALIASES)
            numeric_match = self._has_numeric_data(index)

            # "Balance" alone is too generic. Require a row owner and a
            # numeric-looking data column as independent evidence.
            if not balance_match or not entity_match or not numeric_match:
                continue

            confidence = min(
                1.0,
                0.35
                + 0.20
                + (0.15 if organization_match else 0.0)
                + (0.10 if cash_match else 0.0)
                + (0.10 if amount_match else 0.0)
                + 0.20,
            )
            candidate = HeaderDetection(
                header_index=index,
                score=confidence,
                matched_required_groups=3,
                matched_optional_groups=sum(
                    (organization_match, cash_match, amount_match)
                ),
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def calculate_confidence(
        self,
        detection: HeaderDetection,
    ) -> float:
        """Return the weighted content score."""

        return detection.score

    def _has_numeric_data(self, header_index: int) -> bool:
        """Check that nearby rows contain a meaningful numeric value."""

        sample_rows = self.matrix[header_index + 1:header_index + 7]
        return any(
            isinstance(cell, (int, float)) and not isinstance(cell, bool)
            for row in sample_rows
            for cell in row
        )


class BonusParser(BaseSheetParser):
    """Parser for bonus tables."""

    RULE = SheetRule(
        sheet_type="bonus",
        required_groups=(),
    )
    MIN_CONFIDENCE = 0.65

    BONUS_ALIASES: ClassVar[tuple[str, ...]] = (
        "bonus",
        "bonusz",
        "premium",
        "jutalom",
    )
    ROUTE_ALIASES: ClassVar[tuple[str, ...]] = (
        "route",
        "routes",
        "tour",
        "tura",
        "kor",
    )
    ENTITY_ALIASES: ClassVar[tuple[str, ...]] = (
        "id",
        "driver",
        "courier",
        "futar",
        "name",
        "nev",
    )
    AMOUNT_ALIASES: ClassVar[tuple[str, ...]] = (
        "amount",
        "osszeg",
        "huf",
        "ft",
        "currency",
        "penznem",
    )
    CONTEXT_ALIASES: ClassVar[tuple[str, ...]] = (
        "dsp",
        "site",
        "warehouse",
        "depot",
        "raktar",
    )

    def detect_header(self) -> HeaderDetection | None:
        """Find route bonus tables using weighted, independent signals."""

        best: HeaderDetection | None = None

        for index, row in enumerate(self.matrix):
            row_text = " ".join(normalize_text(cell) for cell in row)
            if not row_text:
                continue

            bonus_match = group_matches(row_text, self.BONUS_ALIASES)
            route_match = group_matches(row_text, self.ROUTE_ALIASES)
            entity_match = group_matches(row_text, self.ENTITY_ALIASES)
            amount_match = group_matches(row_text, self.AMOUNT_ALIASES)
            context_match = group_matches(row_text, self.CONTEXT_ALIASES)
            numeric_match = self._has_numeric_data(index)

            if not bonus_match:
                continue
            if sum((route_match, entity_match, amount_match)) < 2:
                continue
            if not numeric_match:
                continue

            confidence = min(
                1.0,
                0.30
                + (0.20 if route_match else 0.0)
                + (0.20 if entity_match else 0.0)
                + (0.15 if amount_match else 0.0)
                + (0.05 if context_match else 0.0)
                + 0.10,
            )
            candidate = HeaderDetection(
                header_index=index,
                score=confidence,
                matched_required_groups=sum(
                    (bonus_match, route_match, numeric_match)
                ),
                matched_optional_groups=sum(
                    (entity_match, amount_match, context_match)
                ),
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def calculate_confidence(
        self,
        detection: HeaderDetection,
    ) -> float:
        """Return the weighted content score."""

        return detection.score

    def _has_numeric_data(self, header_index: int) -> bool:
        """Check that nearby rows contain numeric route/amount data."""

        sample_rows = self.matrix[header_index + 1:header_index + 7]
        numeric_cells = sum(
            1
            for row in sample_rows
            for cell in row
            if isinstance(cell, (int, float))
            and not isinstance(cell, bool)
        )
        return numeric_cells >= 2


class PerformanceIndicatorParser(BaseSheetParser):
    """Parser for delay, compliance, and other performance indicators."""

    RULE = SheetRule(
        sheet_type="performance_indicator",
        required_groups=(),
    )
    MIN_CONFIDENCE = 0.65
    UNCERTAIN_CONFIDENCE = 0.78

    INDICATOR_ALIASES: ClassVar[tuple[str, ...]] = (
        "indicator",
        "metric",
        "measure",
        "kpi",
        "mutato",
        "teljesitmeny",
    )
    PERFORMANCE_ALIASES: ClassVar[tuple[str, ...]] = (
        "delay",
        "late",
        "lateness",
        "keses",
        "kesedelmi",
        "keseedelmi",
        "compliance",
        "tour compliance",
        "route compliance",
        "turamegfeleles",
        "turameg nem feleles",
        "meg nem felelesi mutato",
        "megfeleles",
        "teljesitesi arany",
        "no show",
    )
    VALUE_ALIASES: ClassVar[tuple[str, ...]] = (
        "value",
        "ertek",
        "rate",
        "ratio",
        "percentage",
        "percent",
        "szazalek",
        "score",
        "mutato",
    )
    ENTITY_ALIASES: ClassVar[tuple[str, ...]] = (
        "courier",
        "driver",
        "futar",
        "partner",
        "depot",
        "warehouse",
        "raktar",
        "route",
        "tour",
        "tura",
        "entity",
        "azonosito",
        "user",
        "name",
        "nev",
        "license plate",
        "licence plate",
        "rendszam",
        "code",
        "kod",
        "site",
        "standort",
    )
    PERIOD_ALIASES: ClassVar[tuple[str, ...]] = (
        "period",
        "idoszak",
        "date",
        "datum",
        "week",
        "het",
        "month",
        "honap",
        "year",
        "ev",
    )
    ENTITY_ID_ALIASES: ClassVar[tuple[str, ...]] = (
        "courier id",
        "driver id",
        "partner id",
        "route id",
        "tour id",
        "entity id",
        "user id",
        "user number",
        "futar id",
        "azonosito",
    )
    ENTITY_NAME_ALIASES: ClassVar[tuple[str, ...]] = (
        "courier name",
        "driver name",
        "partner name",
        "entity name",
        "futar neve",
        "futar",
        "name",
        "nev",
        "depot",
        "warehouse",
        "raktar",
        "route",
        "tour",
        "tura",
        "license plate",
        "licence plate",
        "rendszam",
        "code",
        "kod",
        "site",
        "standort",
    )
    UNIT_ALIASES: ClassVar[tuple[str, ...]] = (
        "unit",
        "egyseg",
        "mertekegyseg",
    )
    DELAY_ALIASES: ClassVar[tuple[str, ...]] = (
        "delay",
        "late",
        "lateness",
        "keses",
        "kesedelmi",
        "keseedelmi",
    )
    TOUR_COMPLIANCE_ALIASES: ClassVar[tuple[str, ...]] = (
        "tour compliance",
        "route compliance",
        "turamegfeleles",
        "tura megfeleles",
        "turameg nem feleles",
        "meg nem felelesi mutato",
        "compliance",
        "megfeleles",
        "teljesitesi arany",
    )

    def detect_header(self) -> HeaderDetection | None:
        """Find the strongest multi-signal performance header."""

        best: HeaderDetection | None = None

        for index, row in enumerate(self.matrix):
            row_text = " ".join(normalize_text(cell) for cell in row)
            if not row_text:
                continue

            indicator_match = group_matches(
                row_text,
                self.INDICATOR_ALIASES,
            )
            performance_match = group_matches(
                row_text,
                self.PERFORMANCE_ALIASES,
            )
            value_match = group_matches(
                row_text,
                self.VALUE_ALIASES,
            )
            entity_match = group_matches(
                row_text,
                self.ENTITY_ALIASES,
            )
            period_match = group_matches(
                row_text,
                self.PERIOD_ALIASES,
            )
            percentage_match = self._has_percentage_signal(
                index,
                row,
            )

            semantic_signals = sum(
                (
                    indicator_match,
                    performance_match,
                    value_match,
                    entity_match,
                    period_match,
                    percentage_match,
                )
            )

            if not (indicator_match or performance_match):
                continue
            if not (value_match or percentage_match):
                continue
            if semantic_signals < 3:
                continue

            confidence = min(
                1.0,
                (0.15 if indicator_match else 0.0)
                + (0.25 if performance_match else 0.0)
                + (0.20 if value_match else 0.0)
                + (0.15 if entity_match else 0.0)
                + (0.10 if period_match else 0.0)
                + (0.15 if percentage_match else 0.0),
            )
            candidate = HeaderDetection(
                header_index=index,
                score=confidence,
                matched_required_groups=sum(
                    (
                        indicator_match,
                        performance_match,
                        value_match,
                    )
                ),
                matched_optional_groups=sum(
                    (
                        entity_match,
                        period_match,
                        percentage_match,
                    )
                ),
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def calculate_confidence(
        self,
        detection: HeaderDetection,
    ) -> float:
        """Return the weighted content-based score."""

        return detection.score

    def parse(self) -> ParsedSheet | None:
        """Parse and validate a performance indicator sheet."""

        detection = self.detect_header()
        if detection is None:
            return None

        confidence = self.calculate_confidence(detection)
        if confidence < self.MIN_CONFIDENCE:
            return None

        header_row = self.matrix[detection.header_index]
        headers = self.normalize_headers(header_row)
        (
            records,
            issues,
            source_data_rows,
            rejected_rows,
        ) = self._normalize_performance_records(
            detection.header_index,
            headers,
        )

        if confidence < self.UNCERTAIN_CONFIDENCE:
            issues.append(
                ParserValidationIssue(
                    error_code="UNCERTAIN_HEADER",
                    severity="warning",
                    message=(
                        "A performance fejléc felismerése bizonytalan."
                    ),
                    source_row_no=(
                        self.rows[detection.header_index].source_row_no
                    ),
                    raw_data={"confidence": confidence},
                )
            )

        return ParsedSheet(
            sheet_name=self.rows[0].sheet_name if self.rows else "",
            sheet_type=self.sheet_type(),
            parser_name=self.__class__.__name__,
            header_source_row_no=(
                self.rows[detection.header_index].source_row_no
            ),
            confidence=confidence,
            headers=headers,
            records=records,
            validation_issues=issues,
            source_data_rows=source_data_rows,
            rejected_rows=rejected_rows,
        )

    def _has_percentage_signal(
        self,
        header_index: int,
        header_row: Sequence[Any],
    ) -> bool:
        """Return True when header or nearby values imply percentages."""

        if any(
            "%" in str(cell)
            or group_matches(
                normalize_text(cell),
                ("percent", "percentage", "szazalek", "rate", "ratio"),
            )
            for cell in header_row
        ):
            return True

        sample_rows = self.matrix[header_index + 1:header_index + 6]
        return any(
            isinstance(cell, str) and "%" in cell
            for row in sample_rows
            for cell in row
        )

    def _normalize_performance_records(
        self,
        header_index: int,
        headers: Sequence[str],
    ) -> tuple[
        list[dict[str, Any]],
        list[ParserValidationIssue],
        int,
        int,
    ]:
        """Normalize data rows and collect non-fatal validation issues."""

        header_values = self.matrix[header_index]
        indexes = self._resolve_column_indexes(header_values)
        records: list[dict[str, Any]] = []
        issues: list[ParserValidationIssue] = []
        source_data_rows = 0
        rejected_rows = 0

        for matrix_index in range(
            header_index + 1,
            len(self.matrix),
        ):
            raw_row = self.matrix[matrix_index]
            source_row_no = self.rows[matrix_index].source_row_no

            if is_empty_row(raw_row):
                issues.append(
                    ParserValidationIssue(
                        error_code="EMPTY_DATA_ROW",
                        severity="info",
                        message="Az adatsor üres, ezért kimaradt.",
                        source_row_no=source_row_no,
                    )
                )
                continue

            source_data_rows += 1
            raw_record = self._row_as_dict(headers, raw_row)
            entity_id = self._value_at(
                raw_row,
                indexes["entity_id"],
            )
            entity_name = self._value_at(
                raw_row,
                indexes["entity_name"],
            )

            value_index = indexes["value"]
            raw_value = self._value_at(raw_row, value_index)
            percentage_context = self._is_percentage_context(
                header_values,
                value_index,
                raw_value,
            )
            numeric_value, unit = normalize_indicator_value(
                raw_value,
                percentage_context=percentage_context,
            )

            if numeric_value is None:
                fallback_value_index = self._find_fallback_value_index(
                    raw_row,
                    excluded_indexes={
                        index
                        for index in (
                            indexes["entity_id"],
                            indexes["entity_name"],
                            indexes["period"],
                            indexes["unit"],
                        )
                        if index is not None
                    },
                )
                if fallback_value_index is not None:
                    value_index = fallback_value_index
                    raw_value = self._value_at(raw_row, value_index)
                    percentage_context = self._is_percentage_context(
                        header_values,
                        value_index,
                        raw_value,
                    )
                    numeric_value, unit = normalize_indicator_value(
                        raw_value,
                        percentage_context=percentage_context,
                    )

            if numeric_value is None:
                issues.append(
                    ParserValidationIssue(
                        error_code="INVALID_INDICATOR_VALUE",
                        severity="error",
                        message=(
                            "A mutatóérték nem alakítható biztonságosan "
                            "számmá."
                        ),
                        source_row_no=source_row_no,
                        raw_data=raw_record,
                    )
                )
                rejected_rows += 1
                continue

            entity_type = "entity"
            if self._is_empty(entity_id) and self._is_empty(entity_name):
                entity_name, entity_type = self._find_fallback_entity(
                    header_values,
                    raw_row,
                    excluded_indexes={
                        index
                        for index in (
                            value_index,
                            indexes["period"],
                            indexes["unit"],
                        )
                        if index is not None
                    },
                )

            source_key = (
                f"{self.rows[0].sheet_name if self.rows else ''}:"
                f"{source_row_no}"
            )

            if self._is_empty(entity_id):
                issues.append(
                    ParserValidationIssue(
                        error_code="MISSING_ENTITY_ID",
                        severity="warning",
                        message=(
                            "Nincs explicit entity_id; a rekord stabil "
                            "source_key azonosítóval került mentésre."
                        ),
                        source_row_no=source_row_no,
                        raw_data={
                            "source_key": source_key,
                            "entity_name": entity_name,
                        },
                    )
                )

            if self._is_empty(entity_id) and self._is_empty(entity_name):
                entity_type = "aggregate"
                issues.append(
                    ParserValidationIssue(
                        error_code="MISSING_ENTITY",
                        severity="warning",
                        message=(
                            "Nincs személy- vagy partnerazonosító; "
                            "a KPI aggregate rekordként került mentésre."
                        ),
                        source_row_no=source_row_no,
                        raw_data={"source_key": source_key},
                    )
                )

            indicator_text = self._indicator_text(
                header_values,
                raw_row,
                indexes,
            )
            indicator_type = detect_indicator_type(indicator_text)

            if indicator_type == "other":
                issues.append(
                    ParserValidationIssue(
                        error_code="UNKNOWN_INDICATOR_TYPE",
                        severity="warning",
                        message=(
                            "A mutató típusa nem azonosítható biztosan; "
                            "other értékkel került mentésre."
                        ),
                        source_row_no=source_row_no,
                        raw_data={"indicator_text": indicator_text},
                    )
                )

            explicit_unit = self._value_at(
                raw_row,
                indexes["unit"],
            )
            if not self._is_empty(explicit_unit):
                unit = str(explicit_unit).strip()

            mapped_indexes = {
                index
                for index in indexes.values()
                if index is not None
            }
            extra = {
                header: raw_record.get(header)
                for index, header in enumerate(headers)
                if index not in mapped_indexes
                and not self._is_empty(raw_record.get(header))
            }

            records.append(
                {
                    "indicator_type": indicator_type,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "source_key": source_key,
                    "period": self._value_at(
                        raw_row,
                        indexes["period"],
                    ),
                    "raw_value": raw_value,
                    "numeric_value": numeric_value,
                    "unit": unit,
                    "source_row_no": source_row_no,
                    "extra": extra,
                }
            )

        return records, issues, source_data_rows, rejected_rows

    def _find_fallback_value_index(
        self,
        raw_row: Sequence[Any],
        excluded_indexes: set[int],
    ) -> int | None:
        """Find the first safely numeric KPI value in another column."""

        for index, value in enumerate(raw_row):
            if index in excluded_indexes or self._is_empty(value):
                continue
            numeric_value, _unit = normalize_indicator_value(
                value,
                percentage_context=(
                    isinstance(value, str) and "%" in value
                ),
            )
            if numeric_value is not None:
                return index
        return None

    def _find_fallback_entity(
        self,
        header_values: Sequence[Any],
        raw_row: Sequence[Any],
        excluded_indexes: set[int],
    ) -> tuple[Any, str]:
        """Find a row label when no explicit ID/name column exists."""

        semantic_aliases: tuple[tuple[str, tuple[str, ...]], ...] = (
            (
                "partner",
                ("partner", "courier", "driver", "futar", "name", "nev"),
            ),
            ("route", ("route", "tour", "tura", "kor")),
            ("depot", ("depot", "warehouse", "raktar", "site", "standort")),
            (
                "vehicle",
                ("license plate", "licence plate", "rendszam"),
            ),
            ("code", ("code", "kod", "azonosito")),
        )

        for entity_type, aliases in semantic_aliases:
            index = first_matching_index(
                header_values,
                aliases,
                excluded_indexes,
            )
            value = self._value_at(raw_row, index)
            if not self._is_empty(value):
                return value, entity_type

        for index, value in enumerate(raw_row):
            if index in excluded_indexes or self._is_empty(value):
                continue
            if isinstance(value, str):
                if normalize_text(value) and not re.fullmatch(
                    r"[-+]?\d+(?:[.,]\d+)?\s*%?",
                    value.strip(),
                ):
                    return value, "source"

        return None, "aggregate"

    def _resolve_column_indexes(
        self,
        header_values: Sequence[Any],
    ) -> dict[str, int | None]:
        """Resolve semantic columns from header content."""

        entity_id_index = first_matching_index(
            header_values,
            self.ENTITY_ID_ALIASES,
        )
        entity_name_index = first_matching_index(
            header_values,
            self.ENTITY_NAME_ALIASES,
            excluded_indexes=(
                {entity_id_index}
                if entity_id_index is not None
                else set()
            ),
        )
        indicator_index = first_matching_index(
            header_values,
            self.PERFORMANCE_ALIASES,
        )
        if indicator_index is None:
            indicator_index = first_matching_index(
                header_values,
                self.INDICATOR_ALIASES,
            )

        value_index = first_matching_index(
            header_values,
            self.VALUE_ALIASES,
        )
        if value_index is None:
            value_index = indicator_index

        return {
            "entity_id": entity_id_index,
            "entity_name": entity_name_index,
            "indicator": indicator_index,
            "value": value_index,
            "period": first_matching_index(
                header_values,
                self.PERIOD_ALIASES,
            ),
            "unit": first_matching_index(
                header_values,
                self.UNIT_ALIASES,
            ),
        }

    @staticmethod
    def _row_as_dict(
        headers: Sequence[str],
        raw_row: Sequence[Any],
    ) -> dict[str, Any]:
        """Convert one row to its original header/value mapping."""

        return {
            header: raw_row[index] if index < len(raw_row) else None
            for index, header in enumerate(headers)
        }

    @staticmethod
    def _value_at(
        row: Sequence[Any],
        index: int | None,
    ) -> Any:
        """Read a row value safely."""

        if index is None or index >= len(row):
            return None
        return row[index]

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """Return True for empty-like values."""

        return value is None or str(value).strip() == ""

    def _indicator_text(
        self,
        header_values: Sequence[Any],
        raw_row: Sequence[Any],
        indexes: Mapping[str, int | None],
    ) -> str:
        """Build indicator context from header and optional row value."""

        indicator_index = indexes["indicator"]
        value_index = indexes["value"]
        parts: list[str] = []

        if indicator_index is not None:
            parts.append(str(header_values[indicator_index]))
            indicator_value = self._value_at(
                raw_row,
                indicator_index,
            )
            if (
                indicator_index != value_index
                and not self._is_empty(indicator_value)
            ):
                parts.append(str(indicator_value))

        if value_index is not None:
            parts.append(str(header_values[value_index]))

        return " ".join(parts)

    def _is_percentage_context(
        self,
        header_values: Sequence[Any],
        value_index: int | None,
        raw_value: Any,
    ) -> bool:
        """Determine whether a value represents percentage points."""

        if isinstance(raw_value, str) and "%" in raw_value:
            return True
        if value_index is None:
            return False

        header = str(header_values[value_index])
        return (
            "%" in header
            or group_matches(
                normalize_text(header),
                (
                    "percent",
                    "percentage",
                    "szazalek",
                    "rate",
                    "ratio",
                    "mutato",
                    "compliance",
                    "megfeleles",
                    "delay",
                    "late",
                    "kesedelmi",
                ),
            )
        )


def detect_indicator_type(value: Any) -> str:
    """Classify indicator context as delay, tour compliance, or other."""

    normalized = normalize_text(value)
    if group_matches(
        normalized,
        PerformanceIndicatorParser.DELAY_ALIASES,
    ):
        return "delay"
    if group_matches(
        normalized,
        PerformanceIndicatorParser.TOUR_COMPLIANCE_ALIASES,
    ):
        return "tour_compliance"
    return "other"


def normalize_indicator_value(
    value: Any,
    percentage_context: bool = False,
) -> tuple[float | None, str | None]:
    """Normalize a number or percentage to a documented representation.

    Percentage values are stored as percentage points on a 0-100 scale:
    ``95%``, ``"95,0 %"`` and decimal ``0.95`` in percentage context all
    become ``95.0`` with unit ``percent``.
    """

    if value is None or isinstance(value, bool):
        return None, None

    explicit_percent = isinstance(value, str) and "%" in value
    number: float | None

    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("\u00a0", " ")
        if not text:
            return None, None

        numeric_match = re.search(
            r"[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)",
            text.replace(" ", ""),
        )
        if not numeric_match:
            return None, None

        numeric_text = numeric_match.group(0)
        if "," in numeric_text and "." in numeric_text:
            if numeric_text.rfind(",") > numeric_text.rfind("."):
                numeric_text = numeric_text.replace(".", "")
                numeric_text = numeric_text.replace(",", ".")
            else:
                numeric_text = numeric_text.replace(",", "")
        else:
            numeric_text = numeric_text.replace(",", ".")

        try:
            number = float(numeric_text)
        except ValueError:
            return None, None

    is_percentage = explicit_percent or percentage_context
    if is_percentage and abs(number) <= 1:
        number *= 100

    return number, "percent" if is_percentage else "number"


DEFAULT_PARSERS: tuple[type[BaseSheetParser], ...] = (
    JITParser,
    PenaltyParser,
    ATMParser,
    BonusParser,
    PerformanceIndicatorParser,
)


def _parser_class_for_type(
    sheet_type: str,
    parser_classes: Sequence[type[BaseSheetParser]],
) -> type[BaseSheetParser] | None:
    """Return the registered parser class for a logical sheet type."""

    return next(
        (
            parser_class
            for parser_class in parser_classes
            if parser_class.sheet_type() == sheet_type
        ),
        None,
    )


def _parse_name_identified_sheet(
    rows: Sequence[ImportedExcelRow],
    detection: SheetNameDetection,
    parser_classes: Sequence[type[BaseSheetParser]],
) -> ParsedSheet | None:
    """Parse with the parser selected by the primary sheet-name rule."""

    parser_class = _parser_class_for_type(
        detection.sheet_type,
        parser_classes,
    )
    if parser_class is None:
        return None

    parser = parser_class(rows)
    parsed = parser.parse()
    if parsed is None and detection.sheet_type != "performance_indicator":
        parsed = parser.parse_with_forced_type()

    if parsed is not None:
        parsed.confidence = detection.confidence

    return parsed


def debug_sheet_detection(
    rows: Sequence[ImportedExcelRow],
    parser_classes: Sequence[type[BaseSheetParser]] | None = None,
) -> dict[str, Any]:
    """Return header/parser scoring details for one source sheet.

    This helper performs no database writes. It is intended for integration
    diagnostics when a real workbook structure is not recognized as expected.
    """

    classes = tuple(parser_classes or DEFAULT_PARSERS)
    parser_scores: list[dict[str, Any]] = []
    content_candidates: list[ParsedSheet] = []
    sheet_name = rows[0].sheet_name if rows else ""
    name_detection = detect_sheet_type_from_name(sheet_name)

    for parser_class in classes:
        parser = parser_class(rows)
        detection = parser.detect_header()

        if detection is None:
            parser_scores.append(
                {
                    "parser": parser_class.__name__,
                    "sheet_type": parser_class.sheet_type(),
                    "confidence": 0.0,
                    "header_source_row_no": None,
                    "normalized_headers": [],
                    "accepted": False,
                    "rejection_reason": "no_matching_header",
                }
            )
            continue

        confidence = parser.calculate_confidence(detection)
        headers = parser.normalize_headers(
            parser.matrix[detection.header_index]
        )
        parsed = parser.parse()
        rejection_reason: str | None = None

        if confidence < parser.MIN_CONFIDENCE:
            rejection_reason = "confidence_below_threshold"
        elif parsed is None:
            rejection_reason = "parser_rejected"
        elif not parsed.records:
            rejection_reason = "no_accepted_records"
        else:
            content_candidates.append(parsed)

        parser_scores.append(
            {
                "parser": parser_class.__name__,
                "sheet_type": parser_class.sheet_type(),
                "confidence": confidence,
                "header_source_row_no": (
                    rows[detection.header_index].source_row_no
                    if rows
                    else None
                ),
                "normalized_headers": headers,
                "accepted": parsed is not None,
                "accepted_rows": (
                    len(parsed.records) if parsed is not None else 0
                ),
                "rejection_reason": rejection_reason,
            }
        )

    content_selected = (
        max(content_candidates, key=lambda item: item.confidence)
        if content_candidates
        else None
    )
    name_selected = (
        _parse_name_identified_sheet(
            rows,
            name_detection,
            classes,
        )
        if name_detection is not None
        else None
    )
    final_selected = name_selected or content_selected

    if name_detection is not None:
        final_type = name_detection.sheet_type
        final_confidence = name_detection.confidence
        decision_reason = name_detection.reason
    elif content_selected is not None:
        final_type = content_selected.sheet_type
        final_confidence = content_selected.confidence
        decision_reason = (
            "content_fallback:highest_confidence_accepted_parser"
        )
    else:
        final_type = None
        final_confidence = 0.0
        decision_reason = "content_fallback:no_parser_accepted_sheet"

    return {
        "sheet_name": sheet_name,
        "name_based_type": (
            name_detection.sheet_type
            if name_detection is not None
            else None
        ),
        "content_based_type": (
            content_selected.sheet_type
            if content_selected is not None
            else None
        ),
        "final_type": final_type,
        "confidence": final_confidence,
        "decision_reason": decision_reason,
        "selected_parser": (
            final_selected.parser_name
            if final_selected is not None
            else None
        ),
        "detected_type": final_type,
        "header_source_row_no": (
            final_selected.header_source_row_no
            if final_selected is not None
            else None
        ),
        "normalized_headers": (
            final_selected.headers if final_selected is not None else []
        ),
        "parser_scores": parser_scores,
        "rejection_reason": (
            None
            if final_type is not None
            else "no_parser_accepted_sheet"
        ),
    }


def debug_workbook_detection(
    rows: Sequence[ImportedExcelRow],
    parser_classes: Sequence[type[BaseSheetParser]] | None = None,
) -> list[dict[str, Any]]:
    """Return detection diagnostics for every sheet in imported rows."""

    grouped = SettlementImportParser.group_by_sheet(rows)
    return [
        debug_sheet_detection(sheet_rows, parser_classes)
        for sheet_rows in grouped.values()
    ]


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
        self.parser_classes = tuple(
            parser_classes or DEFAULT_PARSERS
        )
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

    def read_session_rows(
        self,
        session_id: str,
    ) -> list[ImportedExcelRow]:
        """Read a complete import session from settlement.excel_import."""

        if not session_id or not str(session_id).strip():
            raise ValueError("session_id is required.")

        records: list[dict[str, Any]] = []
        offset = 0

        while True:
            response = (
                self.supabase
                .table(self.table_name)
                .select(
                    "session_id,row_no,sheet_name,source_row_no,data"
                )
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
                source_row_no=int(
                    record.get("source_row_no") or 0
                ),
                data=record.get("data") or {},
            )
            for record in records
        ]

    @staticmethod
    def group_by_sheet(
        rows: Sequence[ImportedExcelRow],
    ) -> dict[str, list[ImportedExcelRow]]:
        """Group raw rows by source sheet name."""

        grouped: dict[str, list[ImportedExcelRow]] = {}

        for row in rows:
            grouped.setdefault(row.sheet_name, []).append(row)

        return grouped

    def parse_sheet(
        self,
        rows: Sequence[ImportedExcelRow],
    ) -> ParsedSheet | None:
        """Use a certain name match first, then content scoring as fallback."""

        sheet_name = rows[0].sheet_name if rows else ""
        name_detection = detect_sheet_type_from_name(sheet_name)
        if name_detection is not None:
            return _parse_name_identified_sheet(
                rows,
                name_detection,
                self.parser_classes,
            )

        candidates: list[ParsedSheet] = []

        for parser_class in self.parser_classes:
            parsed_sheet = parser_class(rows).parse()
            if parsed_sheet is not None:
                candidates.append(parsed_sheet)

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda sheet: sheet.confidence,
        )


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
