"""Minimal Streamlit integration example for settlement processing."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from resources.settlement_processor import process_settlement_session


def render_processing_result(supabase: object, session_id: str) -> None:
    """Process a session and render its compact result."""

    report = process_settlement_session(
        supabase_client=supabase,
        session_id=session_id,
    )

    st.write(f"Státusz: {report.status}")

    columns = st.columns(5)
    columns[0].metric("Felismert sheet", report.recognized_sheets)
    columns[1].metric("Ismeretlen sheet", report.unknown_sheets)
    columns[2].metric("Elfogadott sor", report.accepted_rows)
    columns[3].metric("Elutasított sor", report.rejected_rows)
    columns[4].metric("Kritikus hiba", report.critical_errors)

    if report.sheets:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Sheet": sheet.sheet_name,
                        "Típus": sheet.detected_type or "ismeretlen",
                        "Státusz": sheet.status,
                        "Összes sor": sheet.total_rows,
                        "Elfogadott": sheet.accepted_rows,
                        "Elutasított": sheet.rejected_rows,
                        "Bizonyosság": sheet.confidence,
                    }
                    for sheet in report.sheets
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    if report.errors:
        with st.expander("Feldolgozási hibák és figyelmeztetések"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Súlyosság": issue.severity,
                            "Kód": issue.error_code,
                            "Sheet": issue.sheet_name,
                            "Forrássor": issue.source_row_no,
                            "Üzenet": issue.message,
                        }
                        for issue in report.errors
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
