import os
from datetime import date

import psycopg2
import pandas as pd
import streamlit as st

# ==========================================================
# ADATBÁZIS-KAPCSOLAT
# ==========================================================

def get_database_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        try:
            database_url = st.secrets["DATABASE_URL"]
        except Exception:
            database_url = None

    if not database_url:
        raise RuntimeError(
            "A DATABASE_URL nincs beállítva sem környezeti változóként, "
            "sem a Streamlit secrets fájlban."
        )

    return psycopg2.connect(database_url)


# ==========================================================
# AKTUÁLIS VERZIÓ LEKÉRÉSE
# ==========================================================

def get_next_version(config_key: str) -> int:
    sql = """
        SELECT COALESCE(MAX(version), 0) + 1
        FROM public.jitt_bill_config
        WHERE config_key = %s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (config_key,))
            result = cursor.fetchone()

    return int(result[0])


# ==========================================================
# AKTÍV KORÁBBI VERZIÓ LEZÁRÁSA
# ==========================================================

def close_previous_version(
    connection,
    config_key: str,
    new_valid_from: date,
    updated_by: str,
):
    sql = """
        UPDATE public.jitt_bill_config
        SET
            valid_to = %s::date - INTERVAL '1 day',
            is_active = FALSE,
            updated_by = %s,
            updated_at = NOW()
        WHERE config_key = %s
          AND is_active = TRUE;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (
                new_valid_from,
                updated_by,
                config_key,
            ),
        )


# ==========================================================
# ÚJ KONFIGURÁCIÓ MENTÉSE
# ==========================================================

def insert_bill_config(
    config_key: str,
    config_name: str,
    config_category: str,
    company_value: float,
    courier_value: float,
    calculation_type: str,
    unit: str,
    valid_from: date,
    description: str,
    created_by: str,
):
    version = get_next_version(config_key)

    insert_sql = """
        INSERT INTO public.jitt_bill_config (
            config_key,
            config_name,
            config_category,
            company_value,
            courier_value,
            calculation_type,
            unit,
            version,
            valid_from,
            valid_to,
            is_active,
            description,
            created_by,
            created_at,
            updated_by,
            updated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            NULL,
            TRUE,
            %s,
            %s,
            NOW(),
            %s,
            NOW()
        );
    """

    connection = get_database_connection()

    try:
        close_previous_version(
            connection=connection,
            config_key=config_key,
            new_valid_from=valid_from,
            updated_by=created_by,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                insert_sql,
                (
                    config_key,
                    config_name,
                    config_category,
                    company_value,
                    courier_value,
                    calculation_type,
                    unit,
                    version,
                    valid_from,
                    description,
                    created_by,
                    created_by,
                ),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ==========================================================
# KONFIGURÁCIÓK LEKÉRÉSE
# ==========================================================

def load_bill_configs(
    category: str | None = None,
    active_only: bool = False,
) -> pd.DataFrame:
    conditions = []
    parameters = []

    if category and category != "Összes":
        conditions.append("config_category = %s")
        parameters.append(category)

    if active_only:
        conditions.append("is_active = TRUE")

    where_sql = ""

    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            id,
            config_key,
            config_name,
            config_category,
            company_value,
            courier_value,
            calculation_type,
            unit,
            version,
            valid_from,
            valid_to,
            is_active,
            description,
            created_by,
            created_at,
            updated_by,
            updated_at
        FROM public.jitt_bill_config
        {where_sql}
        ORDER BY
            config_category,
            config_key,
            version DESC;
    """

    connection = get_database_connection()

    try:
        return pd.read_sql_query(
            sql,
            connection,
            params=parameters,
        )
    finally:
        connection.close()


# ==========================================================
# STREAMLIT OLDAL
# ==========================================================

def show_bill_config_page():
    st.title("JITT Bill konfiguráció")

    st.caption(
        "A jitt_bill_config tábla adatainak kézi feltöltése."
    )

    with st.form("jitt_bill_config_form"):

        st.subheader("Alapadatok")

        id_value = st.number_input(
            "id",
            min_value=0,
            step=1,
            value=0,
            help="Ha az adatbázis automatikusan generálja, később ezt kivesszük.",
        )

        config_key = st.text_input(
            "config_key"
        )

        config_name = st.text_input(
            "config_name"
        )

        config_category = st.text_input(
            "config_category"
        )

        st.divider()

        st.subheader("Értékek")

        company_value = st.number_input(
            "company_value",
            value=0.0,
            step=100.0,
            format="%.2f",
        )

        courier_value = st.number_input(
            "courier_value",
            value=0.0,
            step=100.0,
            format="%.2f",
        )

        calculation_type = st.text_input(
            "calculation_type"
        )

        unit = st.text_input(
            "unit"
        )

        st.divider()

        st.subheader("Verzió és érvényesség")

        version = st.number_input(
            "version",
            min_value=1,
            step=1,
            value=1,
        )

        valid_from = st.date_input(
            "valid_from",
            value=date.today(),
        )

        use_valid_to = st.checkbox(
            "valid_to megadása"
        )

        if use_valid_to:
            valid_to = st.date_input(
                "valid_to",
                value=date.today(),
            )
        else:
            valid_to = None

        is_active = st.checkbox(
            "is_active",
            value=True,
        )

        st.divider()

        st.subheader("Megjegyzés és naplózás")

        description = st.text_area(
            "description"
        )

        created_by = st.text_input(
            "created_by"
        )

        updated_by = st.text_input(
            "updated_by"
        )

        submitted = st.form_submit_button(
            "Adatok ellenőrzése",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        form_data = {
            "id": id_value,
            "config_key": config_key,
            "config_name": config_name,
            "config_category": config_category,
            "company_value": company_value,
            "courier_value": courier_value,
            "calculation_type": calculation_type,
            "unit": unit,
            "version": version,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "is_active": is_active,
            "description": description,
            "created_by": created_by,
            "updated_by": updated_by,
        }

        st.success("Az adatok kitöltésre kerültek.")

        st.subheader("Rögzítendő adatok")

        st.json(
            {
                key: str(value) if value is not None else None
                for key, value in form_data.items()
            }
        )