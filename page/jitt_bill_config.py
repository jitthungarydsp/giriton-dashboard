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
    st.title("Elszámolási konfiguráció")

    st.caption(
        "Új díjtételek és konfigurációs értékek felvétele "
        "a jitt_bill_config táblába."
    )

    user = st.session_state.get(
        "user",
        {
            "username": "unknown",
        },
    )

    username = user.get("username", "unknown")

    new_tab, list_tab = st.tabs(
        [
            "Új konfiguráció",
            "Meglévő konfigurációk",
        ]
    )

    # ======================================================
    # ÚJ KONFIGURÁCIÓ
    # ======================================================

    with new_tab:
        with st.form(
            "jitt_bill_config_form",
            clear_on_submit=True,
        ):
            st.subheader("Új érték felvétele")

            col1, col2 = st.columns(2)

            with col1:
                config_category = st.selectbox(
                    "Kategória",
                    [
                        "ROUTE",
                        "BONUS",
                        "MALUS",
                        "INSURANCE",
                        "RESERVE",
                        "OTHER",
                    ],
                )

                config_key = st.text_input(
                    "Konfigurációs kulcs",
                    placeholder="Például: PEAK_DAY_CITY",
                    help=(
                        "Egy technikai azonosító. "
                        "Azonos kulcs módosításakor új verzió jön létre."
                    ),
                )

                config_name = st.text_input(
                    "Megnevezés",
                    placeholder="Például: Kiemelt nap – City",
                )

            with col2:
                calculation_type = st.selectbox(
                    "Számítás típusa",
                    [
                        "fixed",
                        "per_route",
                        "per_order",
                        "per_day",
                        "per_month",
                        "percentage",
                        "manual",
                    ],
                    index=1,
                )

                unit = st.selectbox(
                    "Mértékegység",
                    [
                        "HUF",
                        "%",
                        "DB",
                    ],
                )

                valid_from = st.date_input(
                    "Érvényesség kezdete",
                    value=date.today(),
                )

            st.markdown("#### Értékek")

            value_col1, value_col2 = st.columns(2)

            with value_col1:
                company_value = st.number_input(
                    "Vállalkozói érték",
                    min_value=0.0,
                    value=0.0,
                    step=100.0,
                    format="%.2f",
                )

            with value_col2:
                courier_value = st.number_input(
                    "Futár értéke",
                    min_value=0.0,
                    value=0.0,
                    step=100.0,
                    format="%.2f",
                )

            description = st.text_area(
                "Megjegyzés",
                placeholder=(
                    "Például: kiemelt napi City kör díja, "
                    "lojalitási bónusszal."
                ),
            )

            submitted = st.form_submit_button(
                "Mentés az adatbázisba",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            normalized_key = config_key.strip().upper().replace(" ", "_")
            normalized_name = config_name.strip()

            errors = []

            if not normalized_key:
                errors.append(
                    "A konfigurációs kulcs megadása kötelező."
                )

            if not normalized_name:
                errors.append(
                    "A megnevezés megadása kötelező."
                )

            if company_value == 0 and courier_value == 0:
                errors.append(
                    "Legalább a vállalkozói vagy a futár értékét meg kell adni."
                )

            if errors:
                for error in errors:
                    st.error(error)

            else:
                try:
                    insert_bill_config(
                        config_key=normalized_key,
                        config_name=normalized_name,
                        config_category=config_category,
                        company_value=company_value,
                        courier_value=courier_value,
                        calculation_type=calculation_type,
                        unit=unit,
                        valid_from=valid_from,
                        description=description.strip(),
                        created_by=username,
                    )

                    st.success(
                        f"A(z) „{normalized_name}” konfiguráció "
                        "sikeresen bekerült az adatbázisba."
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        "Nem sikerült elmenteni a konfigurációt."
                    )

                    st.exception(error)

    # ======================================================
    # MEGLÉVŐ KONFIGURÁCIÓK
    # ======================================================

    with list_tab:
        st.subheader("jitt_bill_config tartalma")

        filter_col1, filter_col2, filter_col3 = st.columns(
            [
                2,
                1,
                1,
            ]
        )

        with filter_col1:
            category_filter = st.selectbox(
                "Kategória szűrése",
                [
                    "Összes",
                    "ROUTE",
                    "BONUS",
                    "MALUS",
                    "INSURANCE",
                    "RESERVE",
                    "OTHER",
                ],
                key="bill_config_category_filter",
            )

        with filter_col2:
            active_only = st.checkbox(
                "Csak aktív",
                value=True,
            )

        with filter_col3:
            refresh = st.button(
                "Frissítés",
                use_container_width=True,
            )

        try:
            configs = load_bill_configs(
                category=category_filter,
                active_only=active_only,
            )

            if configs.empty:
                st.info(
                    "A kiválasztott feltételekkel nincs konfiguráció."
                )
            else:
                display_columns = {
                    "id": "ID",
                    "config_key": "Kulcs",
                    "config_name": "Megnevezés",
                    "config_category": "Kategória",
                    "company_value": "Vállalkozó",
                    "courier_value": "Futár",
                    "calculation_type": "Számítás",
                    "unit": "Egység",
                    "version": "Verzió",
                    "valid_from": "Érvényes ettől",
                    "valid_to": "Érvényes eddig",
                    "is_active": "Aktív",
                    "description": "Megjegyzés",
                    "created_by": "Létrehozta",
                    "created_at": "Létrehozva",
                }

                st.dataframe(
                    configs[list(display_columns.keys())].rename(
                        columns=display_columns
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        except Exception as error:
            st.error(
                "Nem sikerült lekérni a jitt_bill_config adatokat."
            )

            st.exception(error)