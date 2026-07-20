from datetime import date, timedelta

import pandas as pd
import streamlit as st

from resources.invoice_summary import (
    build_driver_invoice_summary,
    format_huf,
    read_invoice_data,
)


def previous_month_period(reference_date=None):
    reference_date = reference_date or date.today()
    current_month_start = reference_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return previous_month_start, previous_month_end


def normalize_courier_id(value):
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def to_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def filter_by_worksheet(df, selected_sheet):
    if df is None or df.empty or selected_sheet == "Mind":
        return df
    if "worksheet_name" not in df.columns:
        return df.iloc[0:0].copy()
    return df[
        df["worksheet_name"]
        .astype(str)
        .str.strip()
        .eq(str(selected_sheet).strip())
    ].copy()


def build_driver_label(row):
    courier_id = normalize_courier_id(row.get("courier_id"))
    name = str(row.get("driver_name") or "").strip() or "Nevtelen futar"
    warehouse = str(row.get("worksheet_name") or "").strip()
    prefix = f"#{courier_id} - " if courier_id else ""
    suffix = f" ({warehouse})" if warehouse else ""
    return f"{prefix}{name}{suffix}"


def line_row(code, label, note, amount, source, quantity=1, unit_price=None):
    amount = int(round(to_number(amount)))
    if unit_price is None:
        unit_price = amount if quantity else 0
    return {
        "Aktiv": True,
        "Kod": code,
        "Megnevezes": label,
        "Szoveg": note,
        "Mennyiseg": quantity,
        "Egysegar (Ft)": int(round(to_number(unit_price))),
        "Osszeg (Ft)": amount,
        "Forras": source,
        "Torles": False,
    }


def build_default_invoice_lines(summary_row):
    fixed_amount = to_number(summary_row.get("fixed_rate_huf"))
    highlighted_amount = to_number(summary_row.get("kiemelt_base_huf"))
    normal_amount = to_number(summary_row.get("sima_base_huf"))

    lines = [
        line_row(
            "base_total",
            "Alapdij osszesen",
            (
                f"Kiemelt kor: {int(to_number(summary_row.get('kiemelt_routes')))} db / "
                f"{format_huf(highlighted_amount)}; sima kor: "
                f"{int(to_number(summary_row.get('sima_routes')))} db / "
                f"{format_huf(normal_amount)}."
            ),
            fixed_amount,
            "Szamolt route dij",
        ),
        line_row(
            "delay_bonus",
            "Kesedelmi bonusz",
            "Szerzodeses kesedelmi mutato alapjan szamolt futari resz.",
            summary_row.get("delay_bonus_huf"),
            "Invoice bonusz tabla",
        ),
        line_row(
            "compliance_bonus",
            "Turamegfelelesi bonusz",
            "Szerzodeses turamegfelelesi mutato alapjan szamolt futari resz.",
            summary_row.get("compliance_bonus_huf"),
            "Invoice bonusz tabla",
        ),
        line_row(
            "customer_rating_bonus",
            "Ugyfelertekelesi bonusz",
            "Ugyfelertekeles alapjan szamolt havi bonusz.",
            summary_row.get("customer_rating_bonus_huf"),
            "Ugyfelertekeles",
        ),
        line_row(
            "monthly_adjustment",
            "Havi korrekcio",
            "Havi zarasbol erkezo bonusz, malusz, leadott vagy felvett kor hatasa.",
            summary_row.get("monthly_adjustment_effect_huf"),
            "Havi zaras",
        ),
        line_row(
            "atm_effect",
            "KP / ATM hatas",
            "KP egyenleg elszamolasi hatasa.",
            summary_row.get("atm_effect_huf"),
            "ATM / KP",
        ),
        line_row(
            "cash_missing",
            "Be nem fizetett KP",
            "Manualisan rogzitett KP hiany.",
            summary_row.get("cash_missing_huf"),
            "Manualis tetel",
        ),
        line_row(
            "damage",
            "Karokozas",
            "Manualisan rogzitett karokozas vagy levonas.",
            summary_row.get("damage_huf"),
            "Manualis tetel",
        ),
        line_row(
            "instructor_fee",
            "Oktatoi dij",
            "Manualisan rogzitett oktatoi dij.",
            summary_row.get("instructor_fee_huf"),
            "Manualis tetel",
        ),
        line_row(
            "loyalty_bonus",
            "Lojalitasi bonusz",
            "Lojalitas szabaly alapjan szamolt bonusz.",
            summary_row.get("loyalty_bonus_huf"),
            "Lojalitas",
        ),
        line_row(
            "other_income",
            "Egyeb bevetel",
            "Manualisan rogzitett plusz tetel.",
            summary_row.get("other_income_huf"),
            "Manualis tetel",
        ),
        line_row(
            "other_deduction",
            "Egyeb levonas",
            "Manualisan rogzitett levonas.",
            summary_row.get("other_deduction_huf"),
            "Manualis tetel",
        ),
        line_row(
            "tip",
            "Borravalo",
            "Futarnak atadando borravalo.",
            summary_row.get("tip_huf"),
            "Invoice",
        ),
        line_row(
            "target_reserve",
            "Celtartalek levonas",
            "Celtartalek szabaly szerinti levonas.",
            -abs(to_number(summary_row.get("target_reserve_deduction_huf"))),
            "Celtartalek",
        ),
        line_row(
            "insurance",
            "Biztositas",
            "Biztositas levonas.",
            -abs(to_number(summary_row.get("insurance_deduction_huf"))),
            "Celtartalek",
        ),
    ]

    non_zero_lines = [row for row in lines if int(row["Osszeg (Ft)"]) != 0]
    return pd.DataFrame(non_zero_lines or lines)


def normalize_editor_df(df):
    if df is None or df.empty:
        df = pd.DataFrame(
            columns=[
                "Aktiv",
                "Kod",
                "Megnevezes",
                "Szoveg",
                "Mennyiseg",
                "Egysegar (Ft)",
                "Osszeg (Ft)",
                "Forras",
                "Torles",
            ]
        )
    df = df.copy()
    for column, default in {
        "Aktiv": True,
        "Kod": "",
        "Megnevezes": "",
        "Szoveg": "",
        "Mennyiseg": 1,
        "Egysegar (Ft)": 0,
        "Osszeg (Ft)": 0,
        "Forras": "Manualis",
        "Torles": False,
    }.items():
        if column not in df.columns:
            df[column] = default
    df["Aktiv"] = df["Aktiv"].fillna(True).astype(bool)
    df["Torles"] = df["Torles"].fillna(False).astype(bool)
    for column in ["Mennyiseg", "Egysegar (Ft)", "Osszeg (Ft)"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df[
        [
            "Aktiv",
            "Kod",
            "Megnevezes",
            "Szoveg",
            "Mennyiseg",
            "Egysegar (Ft)",
            "Osszeg (Ft)",
            "Forras",
            "Torles",
        ]
    ]


def show_monthly_invoice_editor_page():
    st.title("Havi szamla")
    st.caption(
        "A PDF-ben szereplo elszamolasi tetelek szerkesztheto munkanezete. "
        "Itt egyelore kezzel tudsz sort hozzaadni, osszeget modositani vagy sort kivenni."
    )

    default_start, default_end = previous_month_period()
    col1, col2, col3 = st.columns([1, 1, 1])
    start_date = col1.date_input(
        "Honap kezdete",
        value=default_start,
        key="monthly_invoice_editor_start",
    )
    end_date = col2.date_input(
        "Honap vege",
        value=default_end,
        key="monthly_invoice_editor_end",
    )
    selected_sheet = col3.selectbox(
        "Telephely",
        ["Mind", "BUD1_JIT", "BUD2_JIT"],
        key="monthly_invoice_editor_sheet",
    )

    try:
        data = read_invoice_data(start_date, end_date)
    except Exception as exc:
        st.error(f"Elszamolasi adatok betoltese sikertelen: {exc}")
        return

    final_df = filter_by_worksheet(data.get("final", pd.DataFrame()), selected_sheet)
    if final_df is None or final_df.empty:
        st.warning("Nincs elszamolasi route adat erre a szuresre.")
        return

    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df=data.get("bonus", pd.DataFrame()),
        penalty_df=data.get("penalties", pd.DataFrame()),
        manual_df=data.get("manual", pd.DataFrame()),
        day_rates_df=data.get("day_rates", pd.DataFrame()),
        raw_route_df=data.get("routes", pd.DataFrame()),
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        atm_balance_df=data.get("atm_balance", pd.DataFrame()),
        customer_rating_df=data.get("customer_rating", pd.DataFrame()),
        monthly_adjustment_df=data.get("monthly_adjustments", pd.DataFrame()),
        target_reserve_df=data.get("target_reserve", pd.DataFrame()),
        period_start=start_date,
    )
    if driver_summary.empty:
        st.warning("A futar szintu osszesito ures erre a szuresre.")
        return

    driver_summary = driver_summary.reset_index(drop=True)
    options = list(driver_summary.index)
    labels = {
        index: build_driver_label(row)
        for index, row in driver_summary.iterrows()
    }
    selected_index = st.selectbox(
        "Futar",
        options,
        format_func=lambda index: labels.get(index, str(index)),
        key="monthly_invoice_editor_driver",
    )
    summary_row = driver_summary.loc[selected_index]

    courier_id = normalize_courier_id(summary_row.get("courier_id"))
    state_key = (
        f"monthly_invoice_lines_"
        f"{start_date:%Y%m%d}_{end_date:%Y%m%d}_"
        f"{courier_id or selected_index}_"
        f"{summary_row.get('worksheet_name', '')}"
    )
    default_lines = normalize_editor_df(build_default_invoice_lines(summary_row))

    top_cols = st.columns([1, 1, 1, 1])
    top_cols[0].metric("Route", int(to_number(summary_row.get("route_count"))))
    top_cols[1].metric("Order", int(to_number(summary_row.get("orders"))))
    top_cols[2].metric("PDF szerinti osszeg", format_huf(summary_row.get("payable_total_huf")))
    top_cols[3].metric("Borravalo", format_huf(summary_row.get("tip_huf")))

    if state_key not in st.session_state:
        st.session_state[state_key] = default_lines

    action_cols = st.columns([1, 1, 4])
    if action_cols[0].button("Alaphelyzet", key=f"{state_key}_reset"):
        st.session_state[state_key] = default_lines
        st.rerun()
    if action_cols[1].button("Ures sor hozzaadasa", key=f"{state_key}_add"):
        current = normalize_editor_df(st.session_state[state_key])
        new_row = pd.DataFrame(
            [
                line_row(
                    "manual",
                    "Uj manualis tetel",
                    "Kezzel rogzitett sor.",
                    0,
                    "Manualis",
                )
            ]
        )
        st.session_state[state_key] = pd.concat(
            [current, new_row],
            ignore_index=True,
        )
        st.rerun()

    edited = st.data_editor(
        normalize_editor_df(st.session_state[state_key]),
        key=f"{state_key}_editor",
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Aktiv": st.column_config.CheckboxColumn("Aktiv"),
            "Kod": st.column_config.TextColumn("Kod"),
            "Megnevezes": st.column_config.TextColumn("Megnevezes"),
            "Szoveg": st.column_config.TextColumn("Szoveg", width="large"),
            "Mennyiseg": st.column_config.NumberColumn("Mennyiseg", step=1),
            "Egysegar (Ft)": st.column_config.NumberColumn("Egysegar (Ft)", step=100),
            "Osszeg (Ft)": st.column_config.NumberColumn("Osszeg (Ft)", step=100),
            "Forras": st.column_config.TextColumn("Forras"),
            "Torles": st.column_config.CheckboxColumn("Torles"),
        },
    )
    edited = normalize_editor_df(edited)
    st.session_state[state_key] = edited

    if st.button("Torlesre jelolt sorok kivetele", key=f"{state_key}_delete"):
        st.session_state[state_key] = edited[~edited["Torles"]].reset_index(drop=True)
        st.rerun()

    payable_rows = edited[(edited["Aktiv"]) & (~edited["Torles"])].copy()
    payable_total = int(round(payable_rows["Osszeg (Ft)"].sum())) if not payable_rows.empty else 0
    delta = payable_total - int(round(to_number(summary_row.get("payable_total_huf"))))

    st.divider()
    result_cols = st.columns([1, 1, 1])
    result_cols[0].metric("Szerkesztett vegosszeg", format_huf(payable_total))
    result_cols[1].metric("Aktiv sorok", len(payable_rows))
    result_cols[2].metric("Elteres a PDF alaphoz kepest", format_huf(delta))

    export_df = payable_rows.copy()
    export_df.insert(0, "Courier ID", courier_id)
    export_df.insert(1, "Futar", summary_row.get("driver_name", ""))
    export_df.insert(2, "Honap kezdete", str(start_date))
    export_df.insert(3, "Honap vege", str(end_date))

    st.download_button(
        "Szerkesztett havi szamla letoltese CSV-ben",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"havi_szamla_{courier_id or 'futar'}_{start_date:%Y_%m}.csv",
        mime="text/csv",
    )

    st.info(
        "Ez a nezet most szerkeszto munkalap. A kovetkezo lepesben ugyanennek tudunk "
        "DB mentest es PDF generalast adni, ha a sorlogika igy rendben van."
    )
