"""Regression tests based on real settlement workbook structures."""

from __future__ import annotations

import unittest

from resources.settlement_parser import (
    ImportedExcelRow,
    PerformanceIndicatorParser,
    SettlementImportParser,
    debug_sheet_detection,
    debug_workbook_detection,
)


SESSION_ID = "00000000-0000-0000-0000-000000000002"


def make_rows(
    matrix: list[list[object]],
    sheet_name: str = "Arbitrary source",
) -> list[ImportedExcelRow]:
    """Build raw import rows in settlement.excel_import format."""

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


class RealSettlementStructureTests(unittest.TestCase):
    """Exercise content recognition against production-like rows."""

    def test_recognizes_atm_balance_without_sheet_name(self) -> None:
        rows = make_rows(
            [
                ["Name", "Balance", "DSP", "Standort"],
                ["Varga Romano", 283054, "JIT", "BUD1"],
                ["Gurzo Balazs", 18789, "JIT", "BUD2"],
            ],
            sheet_name="Unrelated 01",
        )

        parsed = SettlementImportParser(object()).parse_sheet(rows)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sheet_type, "atm_balance")
        self.assertEqual(len(parsed.records), 2)

    def test_recognizes_bonus_routes_without_sheet_name(self) -> None:
        rows = make_rows(
            [
                ["DSP", "Site", "ID", "Driver", "Routes", "Bonus HUF"],
                [
                    "Just in Time Kft. - DSP",
                    "Budapest",
                    2875,
                    "Racz Csaba",
                    11,
                    11000,
                ],
                [
                    "Just in Time Kft. - BUD2",
                    "BUD2",
                    7486,
                    "Papp Nikolett",
                    9,
                    9000,
                ],
            ],
            sheet_name="Unrelated 02",
        )

        parsed = SettlementImportParser(object()).parse_sheet(rows)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sheet_type, "bonus")
        self.assertEqual(len(parsed.records), 2)

    def test_performance_rows_without_entity_id_are_accepted(self) -> None:
        rows = make_rows(
            [
                [
                    "Tervezett turahossz",
                    "Kesedelmi mutato",
                    "<=2,0 ora",
                    "3,0 ora",
                    "4,5 ora",
                ],
                ["Szint 1", "<=1,5%", 1333, 2000, 3000],
                ["JITT-1", None, 1333, 2000, 3000],
            ],
            sheet_name="Metrics A",
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.rejected_rows, 0)
        self.assertEqual(parsed.records[0]["indicator_type"], "delay")
        self.assertEqual(parsed.records[0]["entity_name"], "Szint 1")
        self.assertEqual(parsed.records[1]["numeric_value"], 1333.0)
        self.assertTrue(
            all(
                issue.severity != "error"
                for issue in parsed.validation_issues
            )
        )

    def test_aggregate_kpi_uses_stable_source_key(self) -> None:
        rows = make_rows(
            [
                ["Compliance KPI", "Period", "Value"],
                [None, "2026-06", "95,0 %"],
            ],
            sheet_name="Metrics B",
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        record = parsed.records[0]
        self.assertEqual(record["entity_type"], "aggregate")
        self.assertIsNone(record["entity_id"])
        self.assertIsNone(record["entity_name"])
        self.assertEqual(record["source_key"], "Metrics B:2")
        self.assertEqual(record["numeric_value"], 95.0)
        self.assertEqual(record["unit"], "percent")
        self.assertEqual(parsed.rejected_rows, 0)

    def test_missing_entity_is_warning_not_error(self) -> None:
        rows = make_rows(
            [
                ["Delay KPI", "Month", "Value"],
                [None, "2026-06", "2%"],
            ]
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        missing = [
            issue
            for issue in parsed.validation_issues
            if issue.error_code == "MISSING_ENTITY"
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].severity, "warning")
        self.assertEqual(len(parsed.records), 1)

    def test_tour_compliance_realistic_matrix(self) -> None:
        rows = make_rows(
            [
                [
                    "Tervezett turahossz",
                    "Turameg(nem)felelesi mutato",
                    "<=2,0 ora",
                    "3,0 ora",
                    "4,5 ora",
                ],
                ["Szint 1", "<=2%", 1333, 2000, 3000],
                ["JITT-1", None, 1333, 2000, 3000],
            ],
            sheet_name="Metrics C",
        )

        parsed = PerformanceIndicatorParser(rows).parse()

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(len(parsed.records), 2)
        self.assertTrue(
            all(
                record["indicator_type"] == "tour_compliance"
                for record in parsed.records
            )
        )

    def test_debug_report_contains_scores_and_selection(self) -> None:
        rows = make_rows(
            [
                ["Name", "Balance", "DSP", "Standort"],
                ["Example Driver", 1000, "JIT", "BUD1"],
            ]
        )

        report = debug_sheet_detection(rows)

        self.assertEqual(report["detected_type"], "atm_balance")
        self.assertEqual(report["header_source_row_no"], 1)
        self.assertEqual(
            report["normalized_headers"],
            ["Name", "Balance", "DSP", "Standort"],
        )
        self.assertTrue(report["parser_scores"])
        self.assertIsNone(report["rejection_reason"])

    def test_non_matching_sheet_debugs_rejection_reason(self) -> None:
        rows = make_rows(
            [
                ["Free text", "Comment"],
                ["Hello", "World"],
            ]
        )

        report = debug_sheet_detection(rows)

        self.assertIsNone(report["detected_type"])
        self.assertEqual(
            report["rejection_reason"],
            "no_parser_accepted_sheet",
        )

    def test_jit_sheet_name_has_priority_over_bonus_content(self) -> None:
        rows = make_rows(
            [
                ["DSP", "Site", "ID", "Driver", "Routes", "Bonus HUF"],
                ["JIT", "BUD1", 7644, "Gurzo Balazs", 3, 3000],
            ],
            sheet_name="BUD1_JIT",
        )

        parsed = SettlementImportParser(object()).parse_sheet(rows)
        report = debug_sheet_detection(rows)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sheet_type, "jit")
        self.assertEqual(report["name_based_type"], "jit")
        self.assertEqual(report["content_based_type"], "bonus")
        self.assertEqual(report["final_type"], "jit")
        self.assertEqual(report["confidence"], 1.0)
        self.assertIn("sheet_name", report["decision_reason"])

    def test_real_workbook_sheet_names_have_expected_primary_types(
        self,
    ) -> None:
        sheet_samples = {
            "ATM Balance": (
                [["Name", "Balance"], ["Driver A", 1000]],
                "atm_balance",
            ),
            "Bonus routes": (
                [
                    ["DSP", "Driver", "Routes", "Bonus HUF"],
                    ["JIT", "Driver A", 2, 2000],
                ],
                "bonus",
            ),
            "BUD1_JIT": (
                [
                    [
                        "Location",
                        "Driver",
                        "Route Unique ID",
                        "Fixed Rate",
                    ],
                    ["Budapest", "Driver A", 123, 12500],
                ],
                "jit",
            ),
            "BUD2_JIT": (
                [
                    [
                        "Location",
                        "Driver",
                        "Route Unique ID",
                        "Fixed Rate",
                    ],
                    ["BUD2", "Driver B", 456, 12500],
                ],
                "jit",
            ),
            "Regional_JIT": (
                [
                    [
                        "Location",
                        "Driver",
                        "Route Unique ID",
                        "Fixed Rate",
                    ],
                    ["Region", "Driver C", 789, 12500],
                ],
                "jit",
            ),
            "Penalties": (
                [
                    ["Driver", "Penalty", "Amount"],
                    ["Driver A", "Late", 500],
                ],
                "penalties",
            ),
            "Késedelmi mutató": (
                [
                    ["KPI", "Partner", "Value"],
                    ["Delay", "JIT", "1,5 %"],
                ],
                "performance_indicator",
            ),
            "Túramegfelelési mutató": (
                [
                    ["KPI", "Partner", "Value"],
                    ["Tour compliance", "JIT", "98 %"],
                ],
                "performance_indicator",
            ),
        }

        for sheet_name, (matrix, expected_type) in sheet_samples.items():
            with self.subTest(sheet_name=sheet_name):
                rows = make_rows(matrix, sheet_name=sheet_name)
                parsed = SettlementImportParser(object()).parse_sheet(rows)
                report = debug_sheet_detection(rows)

                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual(parsed.sheet_type, expected_type)
                self.assertEqual(
                    report["name_based_type"],
                    expected_type,
                )
                self.assertEqual(report["final_type"], expected_type)
                self.assertEqual(report["confidence"], 1.0)

    def test_debug_workbook_detection_reports_decision_columns(
        self,
    ) -> None:
        workbook_rows = (
            make_rows(
                [
                    ["DSP", "Site", "ID", "Driver", "Routes", "Bonus HUF"],
                    ["JIT", "BUD1", 1, "Driver A", 2, 2000],
                ],
                sheet_name="BUD1_JIT",
            )
            + make_rows(
                [["Name", "Balance"], ["Driver A", 1000]],
                sheet_name="ATM Balance",
            )
        )

        reports = debug_workbook_detection(workbook_rows)

        self.assertEqual(len(reports), 2)
        for report in reports:
            self.assertIn("sheet_name", report)
            self.assertIn("name_based_type", report)
            self.assertIn("content_based_type", report)
            self.assertIn("final_type", report)
            self.assertIn("confidence", report)
            self.assertIn("decision_reason", report)


if __name__ == "__main__":
    unittest.main()
