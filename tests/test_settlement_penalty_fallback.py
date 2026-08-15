"""Regression test for raw positional Penalties Excel imports."""

from __future__ import annotations

import sys
import types

supabase_stub = types.ModuleType("supabase")
supabase_stub.Client = object
sys.modules.setdefault("supabase", supabase_stub)

from resources.settlement_parser import ImportedExcelRow
from resources.settlement_processor import _process_sheet


SESSION_ID = "00000000-0000-0000-0000-000000000003"
RUN_ID = "00000000-0000-0000-0000-000000000004"


def test_penalties_position_fallback_builds_penalty_rows() -> None:
    rows = [
        ImportedExcelRow(
            session_id=SESSION_ID,
            row_no=5,
            sheet_name="Penalties",
            source_row_no=5,
            data={
                "column_1": "BUD1",
                "column_2": "2026-07-30T00:00:00",
                "column_3": "Stumpf Andras Istvan",
                "column_4": "Szabalysertesi / Kozigazgatasi / Parkolasi birsag.",
                "column_5": (
                    "AILV519 - 2026.07.18. 07:18-kor, "
                    "- Stumpf Andras Istvan - gyorshajtas"
                ),
                "column_6": 50000,
            },
        )
    ]

    report, issues, target_table, normalized_rows = _process_sheet(
        RUN_ID,
        SESSION_ID,
        "Penalties",
        rows,
    )

    assert issues == []
    assert report.status == "completed"
    assert target_table == "penalty_row"
    assert len(normalized_rows) == 1

    data = normalized_rows[0]["normalized_data"]
    assert data["courier_name"] == "Stumpf Andras Istvan"
    assert data["warehouse"] == "BUD1"
    assert data["penalty_date"] == "2026-07-30"
    assert data["malus_huf"] == 50000
    assert data["penalty_huf"] == 50000
    assert data["penalty_type"].startswith("Szabalysertesi")
    assert data["note"].startswith("AILV519")
