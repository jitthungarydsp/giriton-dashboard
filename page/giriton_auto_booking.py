from datetime import date, timedelta
import subprocess

import pandas as pd
import streamlit as st

from resources.giriton_auto_booking import (
    PROJECT_ROOT,
    get_t_plus_booking_candidates,
    latest_log_by_serial,
    read_giriton_booking_log,
)


ROBOT_FILE = PROJECT_ROOT / "giriton_auto_booking_github.robot"


def _date_text(value):
    if not value:
        return ""

    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _robot_command(start_date, end_date, dry_run, serial=""):
    return [
        "robot",
        "--variable",
        f"AUTO_BOOK_START_DATE:{_date_text(start_date)}",
        "--variable",
        f"AUTO_BOOK_END_DATE:{_date_text(end_date)}",
        "--variable",
        f"AUTO_BOOK_DRY_RUN:{str(bool(dry_run)).lower()}",
        "--variable",
        f"AUTO_BOOK_SERIAL:{serial}",
        str(ROBOT_FILE),
    ]


def _command_text(command):
    return " ".join(
        f'"{item}"' if " " in str(item) else str(item)
        for item in command
    )


def _run_robot(start_date, end_date, dry_run, serial=""):
    command = _robot_command(start_date, end_date, dry_run, serial=serial)

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60 * 60,
        check=False,
    )

    return completed


def _candidate_dataframe(candidates, log_df):
    df = pd.DataFrame(candidates)

    if df.empty:
        return df

    latest = latest_log_by_serial(log_df)
    statuses = []
    messages = []
    logged_at = []

    for row in df.to_dict("records"):
        log_row = latest.get(str(row.get("serial") or "").strip(), {})
        statuses.append(log_row.get("status", "NINCS_LOG"))
        messages.append(log_row.get("message", ""))
        logged_at.append(log_row.get("created_at", ""))

    df["last_status"] = statuses
    df["last_message"] = messages
    df["last_log_at"] = logged_at
    return df


def _candidate_label(row):
    return (
        f"{row.get('work_date', '')} | {row.get('warehouse', '')} "
        f"{row.get('shift_start', '')} | {row.get('courier_name', '')} "
        f"({row.get('courier_id', '')}) | {row.get('serial', '')}"
    )


def show_giriton_auto_booking_page():
    st.title("Giriton Auto Booking")
    st.caption(
        "Foglalasok alapjan Giriton Shift Subscription automatizalas, dry-run ellenorzessel es loggal."
    )

    today = date.today()
    col1, col2, col3 = st.columns([1, 1, 1])
    start_date = col1.date_input(
        "Kezdo datum",
        value=today + timedelta(days=3),
        key="giriton_auto_booking_start",
    )
    end_date = col2.date_input(
        "Zaro datum",
        value=today + timedelta(days=3),
        key="giriton_auto_booking_end",
    )
    limit = col3.number_input(
        "Log limit",
        min_value=50,
        max_value=5000,
        value=500,
        step=50,
        key="giriton_auto_booking_log_limit",
    )

    if end_date < start_date:
        st.error("A zaro datum nem lehet korabbi, mint a kezdo datum.")
        return

    try:
        candidates = get_t_plus_booking_candidates(
            start_date=_date_text(start_date),
            end_date=_date_text(end_date),
        )
    except Exception as exc:
        st.error(f"Foglalasok olvasasi hiba: {exc}")
        return

    try:
        log_df = read_giriton_booking_log(
            start_date=_date_text(start_date),
            end_date=_date_text(end_date),
            limit=limit,
        )
    except Exception as exc:
        st.warning(f"Auto booking log olvasasi hiba: {exc}")
        log_df = pd.DataFrame()

    candidate_df = _candidate_dataframe(candidates, log_df)

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Jelolt", len(candidate_df))
    metric2.metric(
        "Dry-run OK",
        int((candidate_df.get("last_status", pd.Series(dtype=str)) == "DRY_RUN_FOUND").sum())
        if not candidate_df.empty
        else 0,
    )
    metric3.metric(
        "Mar foglalt",
        int((candidate_df.get("last_status", pd.Series(dtype=str)) == "ALREADY_BOOKED").sum())
        if not candidate_df.empty
        else 0,
    )
    metric4.metric(
        "Hibas / hianyzo",
        int(
            candidate_df.get("last_status", pd.Series(dtype=str))
            .isin(
                [
                    "SHIFT_NOT_FOUND",
                    "COURIER_NOT_FOUND",
                    "SUBSCRIBED_TAB_NOT_FOUND",
                    "ADD_BUTTON_NOT_FOUND",
                    "CHOOSE_BUTTON_NOT_FOUND",
                    "COURIER_SELECTED_NOT_VERIFIED",
                ]
            )
            .sum()
        )
        if not candidate_df.empty
        else 0,
    )

    selected_serial = ""
    selected_label = "Minden jelolt"

    if not candidate_df.empty:
        candidate_rows = candidate_df.to_dict("records")
        candidate_options = {
            "Minden jelolt": "",
            **{
                _candidate_label(row): str(row.get("serial") or "").strip()
                for row in candidate_rows
            },
        }
        selected_label = st.selectbox(
            "Feldolgozando ember / foglalas",
            list(candidate_options.keys()),
            key="giriton_auto_booking_selected_candidate",
        )
        selected_serial = candidate_options.get(selected_label, "")

    st.subheader("Robot futtatas")
    dry_command = _robot_command(start_date, end_date, True, selected_serial)
    live_command = _robot_command(start_date, end_date, False, selected_serial)

    st.code(_command_text(dry_command), language="powershell")

    run_col1, run_col2 = st.columns([1, 2])

    if run_col1.button("Dry-run inditas", type="primary", use_container_width=True):
        with st.spinner("Giriton auto booking dry-run fut..."):
            result = _run_robot(start_date, end_date, True, selected_serial)

        if result.returncode == 0:
            st.success("Dry-run lefutott.")
        else:
            st.error(f"Dry-run hiba, exit code: {result.returncode}")

        st.text_area("Robot stdout", result.stdout, height=220)
        st.text_area("Robot stderr", result.stderr, height=160)

    enable_live = run_col2.checkbox(
        "Eles foglalas engedelyezese a kivalasztott emberre",
        key="giriton_auto_booking_enable_live",
    )

    if enable_live:
        if not selected_serial:
            st.error("Eles foglalashoz valassz ki egy konkret embert/foglalast.")
            return

        st.warning(
            f"Eles modban a robot csak ezt a kivalasztott sort dolgozza fel: {selected_label}"
        )
        st.code(_command_text(live_command), language="powershell")
        confirmation = st.text_input(
            "Megerősites: ird be pontosan, hogy ELES",
            key="giriton_auto_booking_live_confirmation",
        )

        if st.button("Eles foglalas inditasa", use_container_width=True):
            if confirmation != "ELES":
                st.error("Eles inditashoz a megerosito mezobe ezt ird: ELES")
            else:
                with st.spinner("Giriton auto booking eles futas..."):
                    result = _run_robot(start_date, end_date, False, selected_serial)

                if result.returncode == 0:
                    st.success("Eles robot futas lefutott.")
                else:
                    st.error(f"Eles robot hiba, exit code: {result.returncode}")

                st.text_area("Robot stdout", result.stdout, height=220)
                st.text_area("Robot stderr", result.stderr, height=160)

    st.subheader("Foglalasi jeloltek")

    if candidate_df.empty:
        st.info("Nincs feldolgozhato Foglalasok sor erre az idoszakra.")
    else:
        status_options = ["Mind"] + sorted(
            status
            for status in candidate_df["last_status"].dropna().astype(str).unique()
            if status
        )
        selected_status = st.selectbox(
            "Statusz szures",
            status_options,
            key="giriton_auto_booking_status_filter",
        )
        visible_df = candidate_df.copy()

        if selected_status != "Mind":
            visible_df = visible_df[visible_df["last_status"] == selected_status]

        display_columns = [
            "work_date",
            "warehouse",
            "shift_start",
            "shift_text",
            "courier_id",
            "courier_name",
            "email",
            "booking_code",
            "serial",
            "last_status",
            "last_message",
            "last_log_at",
        ]
        display_columns = [
            column for column in display_columns if column in visible_df.columns
        ]

        st.dataframe(
            visible_df[display_columns].rename(
                columns={
                    "work_date": "Datum",
                    "warehouse": "Raktar",
                    "shift_start": "Kezdes",
                    "shift_text": "Muszak",
                    "courier_id": "Courier ID",
                    "courier_name": "Futar",
                    "email": "E-mail",
                    "booking_code": "Foglalasi kod",
                    "serial": "Serial",
                    "last_status": "Utolso statusz",
                    "last_message": "Uzenet",
                    "last_log_at": "Log ideje",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Utolso robot logok")

    if log_df.empty:
        st.info(
            "Nincs auto booking log. Ha meg nincs tabla, futtasd: docs/supabase_giriton_auto_booking_log.sql"
        )
    else:
        st.dataframe(
            log_df.rename(
                columns={
                    "created_at": "Ido",
                    "work_date": "Datum",
                    "courier_id": "Courier ID",
                    "courier_name": "Futar",
                    "warehouse": "Raktar",
                    "shift_start": "Kezdes",
                    "shift_text": "Muszak",
                    "status": "Statusz",
                    "message": "Uzenet",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
