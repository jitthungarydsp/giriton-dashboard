import math
import uuid
from datetime import date, datetime
from io import BytesIO
from typing import Any, BinaryIO

import pandas as pd
from supabase import Client, create_client
from supabase.client import ClientOptions


SUPABASE_SCHEMA = "settlement"
IMPORT_TABLE = "excel_import"
PREVIEW_VIEW = "vw_excel_preview"


def get_supabase_client(
    url: str,
    service_role_key: str,
) -> Client:
    """
    Supabase kliens létrehozása a settlement sémához.
    """

    if not url:
        raise ValueError("A Supabase URL nincs megadva.")

    if not service_role_key:
        raise ValueError("A Supabase SERVICE_ROLE_KEY nincs megadva.")

    return create_client(
        url,
        service_role_key,
        options=ClientOptions(
            schema=SUPABASE_SCHEMA,
            postgrest_client_timeout=60,
        ),
    )


def clean_value(value: Any) -> Any:
    """
    Pandas- és NumPy-értékek JSON-kompatibilis értékké alakítása.
    """

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if hasattr(value, "item"):
        value = value.item()

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

    return value


def dataframe_to_import_rows(
    dataframe: pd.DataFrame,
    session_id: str,
) -> list[dict[str, Any]]:
    """
    A DataFrame minden sorából létrehoz egy Supabase-be menthető rekordot.
    """

    rows: list[dict[str, Any]] = []

    for row_number, (_, row) in enumerate(
        dataframe.iterrows(),
        start=1,
    ):
        row_data = {
            str(column): clean_value(value)
            for column, value in row.items()
        }

        rows.append(
            {
                "session_id": session_id,
                "row_no": row_number,
                "data": row_data,
            }
        )

    return rows


def read_uploaded_excel(
    uploaded_file: BinaryIO | BytesIO,
) -> pd.DataFrame:
    """
    Beolvassa a Streamlit által feltöltött Excel-fájlt.
    """

    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass

    dataframe = pd.read_excel(uploaded_file)

    if dataframe.empty:
        raise ValueError(
            "A feltöltött Excel-fájl nem tartalmaz adatokat."
        )

    if len(dataframe.columns) == 0:
        raise ValueError(
            "A feltöltött Excel-fájl nem tartalmaz oszlopokat."
        )

    return dataframe


def save_excel_to_supabase(
    uploaded_file: BinaryIO | BytesIO,
    supabase: Client,
    batch_size: int = 500,
) -> dict[str, Any]:
    """
    Beolvassa az Excel-fájlt, majd az adatokat kötegenként
    elmenti a settlement.excel_import táblába.

    Visszatér:
        {
            "session_id": "...",
            "inserted_rows": 123,
            "columns": [...]
        }
    """

    dataframe = read_uploaded_excel(uploaded_file)
    session_id = str(uuid.uuid4())

    import_rows = dataframe_to_import_rows(
        dataframe=dataframe,
        session_id=session_id,
    )

    inserted_rows = 0

    try:
        for start_index in range(0, len(import_rows), batch_size):
            batch = import_rows[
                start_index:start_index + batch_size
            ]

            response = (
                supabase
                .table(IMPORT_TABLE)
                .insert(batch)
                .execute()
            )

            inserted_rows += len(response.data or batch)

    except Exception:
        # Ha valamelyik köteg hibás, az addig bekerült sorokat is töröljük.
        try:
            (
                supabase
                .table(IMPORT_TABLE)
                .delete()
                .eq("session_id", session_id)
                .execute()
            )
        except Exception:
            pass

        raise

    return {
        "session_id": session_id,
        "inserted_rows": inserted_rows,
        "columns": [str(column) for column in dataframe.columns],
    }


def get_import_preview(
    supabase: Client,
    session_id: str,
) -> pd.DataFrame:
    """
    Az adott import visszaolvasása a vw_excel_preview view-ból.
    """

    response = (
        supabase
        .table(PREVIEW_VIEW)
        .select("session_id,row_no,data,created_at")
        .eq("session_id", session_id)
        .order("row_no")
        .execute()
    )

    records = response.data or []

    if not records:
        return pd.DataFrame()

    preview_rows: list[dict[str, Any]] = []

    for record in records:
        data = record.get("data") or {}

        preview_rows.append(
            {
                "row_no": record.get("row_no"),
                **data,
                "created_at": record.get("created_at"),
            }
        )

    return pd.DataFrame(preview_rows)


def delete_excel_import(
    supabase: Client,
    session_id: str,
) -> int:
    """
    Az adott session_id-hoz tartozó importált sorok törlése.
    """

    response = (
        supabase
        .table(IMPORT_TABLE)
        .delete()
        .eq("session_id", session_id)
        .select("id")
        .execute()
    )

    return len(response.data or [])