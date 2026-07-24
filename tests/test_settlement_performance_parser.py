"""Tests for content-based performance indicator parsing."""

from __future__ import annotations

from types import ModuleType
import sys
import unittest

from resources.settlement_parser import (
    ImportedExcelRow,
    PerformanceIndicatorParser,
    SettlementImportParser,
    normalize_indicator_value,
)

# The processor only needs the Client symbol during import. Keeping this stub
# local makes the unit tests independent from the optional Supabase SDK.
if "supabase" not in sys.modules:
    supabase_stub = ModuleType("supabase")
    supabase_stub.Client = object
    sys.modules["supabase"] = supabase_stub

from resources.settlement_processor import (  # noqa: E402
    _pair_records_with_source_rows,
)


SESSION_ID = "00000000-0000-0000-0000-000000000001"


def make_rows(
    matrix: list[list[object]],
    sheet_name: str = "Arbitrary source",
) -> list[ImportedExcelRow]:
    """Build raw import rows without relying on the sheet name."""

    return [
        ImportedExcelRow(
            session_id=SESSION_ID,
            row_no=index,
            sheet_name=sheet_name,
            source_row_no=index,
            data={
                f"column_{column_index}": value
                for column_index, value in enumerate(row, start=1)
                if value is not None
            },
        )
        for index, row in enumerate(matrix, start=1)
    ]


class PerformanceIndicatorParserTests(unittest.TestCase):
    """Exercise recognition, normalization, and validation."""

    def test_detects_delay_indicator(self) -> None:
        rows = make_rows(
            [
                ["Report generated", None, None, None],
                [
                    "Courier ID",
                    "Courier name",
                    "Period",
                    "Delay %",
                ],
                [7644, "Test Driver", "2026-06", "1,5 %"],
            ]
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sheet_type, "performance_indicator")
        self.assertEqual(parsed.records[0]["indicator_type"], "delay")
        self.assertEqual(parsed.records[0]["numeric_value"], 1.5)
        self.assertEqual(parsed.records[0]["unit"], "percent")

    def test_detects_tour_compliance_indicator(self) -> None:
        rows = make_rows(
            [
                [
                    "Partner ID",
                    "Partner name",
                    "Week",
                    "Tour compliance rate",
                ],
                [6206, "Example Courier", "2026-W27", 0.95],
            ],
            sheet_name="Unrelated title",
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        record = parsed.records[0]
        self.assertEqual(
            record["indicator_type"],
            "tour_compliance",
        )
        self.assertEqual(record["numeric_value"], 95.0)
        self.assertEqual(record["unit"], "percent")

    def test_normalizes_percentage_variants(self) -> None:
        self.assertEqual(
            normalize_indicator_value("95%"),
            (95.0, "percent"),
        )
        self.assertEqual(
            normalize_indicator_value(
                0.95,
                percentage_context=True,
            ),
            (95.0, "percent"),
        )
        self.assertEqual(
            normalize_indicator_value("95,0 %"),
            (95.0, "percent"),
        )

    def test_handles_decimal_comma(self) -> None:
        self.assertEqual(
            normalize_indicator_value("1,25"),
            (1.25, "number"),
        )

    def test_incomplete_row_does_not_stop_sheet(self) -> None:
        rows = make_rows(
            [
                [
                    "Driver ID",
                    "Driver name",
                    "Month",
                    "Delay rate",
                ],
                [None, "Name only", "2026-06", "2,0 %"],
                [7644, "Valid Driver", "2026-06", "invalid"],
                [7645, "Second Driver", "2026-06", "1,0 %"],
            ]
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.rejected_rows, 1)
        issue_codes = {
            issue.error_code
            for issue in parsed.validation_issues
        }
        self.assertIn("MISSING_ENTITY_ID", issue_codes)
        self.assertIn("INVALID_INDICATOR_VALUE", issue_codes)

    def test_processor_uses_explicit_source_row_after_rejection(self) -> None:
        rows = make_rows(
            [
                [
                    "Driver ID",
                    "Driver name",
                    "Month",
                    "Delay rate",
                ],
                [7644, "First Driver", "2026-06", "1,0 %"],
                [7645, "Invalid Driver", "2026-06", "invalid"],
                [7646, "Second Driver", "2026-06", "2,0 %"],
            ]
        )
        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        pairs, issues = _pair_records_with_source_rows(parsed, rows)

        self.assertEqual(
            [source_row_no for source_row_no, _record in pairs],
            [2, 4],
        )
        self.assertEqual(issues, [])

    def test_rejects_non_performance_sheet(self) -> None:
        rows = make_rows(
            [
                ["Route", "Driver", "Amount"],
                ["R-1", "Test Driver", 1200],
            ]
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNone(parsed)

    def test_low_confidence_header_is_rejected(self) -> None:
        rows = make_rows(
            [
                ["KPI", "Value"],
                ["Metric A", "95%"],
            ]
        )
        parser = PerformanceIndicatorParser(rows)
        detection = parser.detect_header()

        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertLess(
            parser.calculate_confidence(detection),
            parser.MIN_CONFIDENCE,
        )
        self.assertIsNone(parser.parse())

    def test_registered_parser_uses_content_not_sheet_name(self) -> None:
        rows = make_rows(
            [
                [
                    "Courier ID",
                    "Courier",
                    "Date",
                    "Lateness percentage",
                ],
                [7644, "Test Driver", "2026-07-01", "3%"],
            ],
            sheet_name="Sheet 42",
        )
        parser = SettlementImportParser(supabase=object())

        parsed = parser.parse_sheet(rows)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sheet_type, "performance_indicator")


if __name__ == "__main__":
    unittest.main()
