import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from resources.giriton_shift_admin import (
    can_run_robot_locally,
    command_text,
    delete_command,
    filter_booked_shift_rows,
    log_admin_action,
    next_days_window,
    raw_export_command,
    read_admin_action_log,
    read_next_giriton_shifts,
    run_command,
)
from resources.courier_db_sheet import (
    sync_courier_db_from_drivers,
    upsert_couriers,
    )
from resources.courier_master_db import read_courier_master
from resources.email_sender import send_login_credentials, validate_email
from resources.pwa_users_db import sync_pwa_users_from_json_users, upsert_pwa_user_with_password
from resources.supabase_raw import get_supabase_config, raise_for_supabase_error
from resources.users import (
    USERS_FILE,
    build_courier_master_sync_preview,
    load_users,
    create_user,
    reset_password,
    sync_users_from_courier_master,
    update_role,
    toggle_active,
    update_trainer,
    delete_user,
    approve_pwa_registration_user,
)


PWA_REGISTRATION_TABLE = "pwa_registration_requests"


def normalize_courier_id(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_email_lookup():
    courier_master_df = read_courier_master()
    if courier_master_df is None or courier_master_df.empty:
        return {}
    if "courier_id" not in courier_master_df.columns:
        return {}

    lookup = {}
    for _, row in courier_master_df.iterrows():
        courier_id = normalize_courier_id(row.get("courier_id"))
        if not courier_id:
            continue
        email = str(row.get("email") or row.get("billing_email") or "").strip()
        lookup[courier_id] = email
    return lookup


def get_user_courier_id(user):
    return normalize_courier_id(
        user.get("courierId") or user.get("courier_id") or ""
    )


def get_existing_password(user):
    return str(user.get("password") or "").strip()


def get_courier_email(user, email_lookup):
    return str(email_lookup.get(get_user_courier_id(user)) or "").strip()


def send_existing_credentials(user, recipient_email):
    username = str(user.get("username") or "").strip()
    password = get_existing_password(user)

    if not username:
        raise ValueError("Hiányzik a felhasználónév.")
    if not password:
        raise ValueError(
            "Nincs olvasható password mező a users.json fájlban. "
            "A passwordHash értékből a jelszó nem állítható vissza."
        )

    recipient_email = validate_email(recipient_email)
    return send_login_credentials(recipient_email, username, password)


def _supabase_headers(prefer=""):
    _supabase_url, service_role_key = get_supabase_config()
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def read_pwa_registration_requests(limit=100):
    supabase_url, _service_role_key = get_supabase_config()
    response = requests.get(
        f"{supabase_url.rstrip('/')}/rest/v1/{PWA_REGISTRATION_TABLE}",
        headers=_supabase_headers(),
        params={
            "select": "id,courier_id,courier_name,phone_number,email,status,admin_note,created_at,updated_at",
            "order": "updated_at.desc",
            "limit": str(limit),
        },
        timeout=30,
    )
    raise_for_supabase_error(response)
    return pd.DataFrame(response.json() or [])


def update_pwa_registration_request(request_id, payload):
    supabase_url, _service_role_key = get_supabase_config()
    response = requests.patch(
        f"{supabase_url.rstrip('/')}/rest/v1/{PWA_REGISTRATION_TABLE}",
        headers=_supabase_headers("return=minimal"),
        params={"id": f"eq.{int(request_id)}"},
        json={**payload, "updated_at": datetime.now(timezone.utc).isoformat()},
        timeout=30,
    )
    raise_for_supabase_error(response)


def _admin_actor():
    user = st.session_state.get("user", {})
    return str(user.get("username") or "admin").strip()


def show_pwa_registration_admin_section():
    st.divider()
    st.subheader("PWA admin - regisztrációk")
    st.caption(
        "A futár mobil regisztrációs kérelmek jóváhagyása. Jóváhagyáskor "
        "PWA felhasználó készül vagy frissül, majd e-mailben kimegy a belépés."
    )
    st.caption(f"Belépési DB tábla: `public.pwa_users` · legacy fájl tartaléknak: `{USERS_FILE}`")

    if st.button("users.json → pwa_users szinkron", key="sync_users_json_to_pwa_users"):
        try:
            sync_result = sync_pwa_users_from_json_users(load_users().get("users", []))
            st.success(
                f"PWA user szinkron kész. Átvitt: {sync_result['synced']}, "
                f"kihagyott: {sync_result['skipped']}."
            )
        except Exception as exc:
            st.error(f"A pwa_users szinkron sikertelen: {exc}")

    try:
        requests_df = read_pwa_registration_requests()
    except Exception as exc:
        st.error(f"A PWA regisztrációk nem olvashatók: {exc}")
        return

    if requests_df.empty:
        st.info("Nincs PWA regisztrációs kérelem.")
        return

    status_filter = st.selectbox(
        "Státusz szűrő",
        ["new", "approved", "rejected", "mind"],
        key="pwa_registration_status_filter",
    )
    visible = requests_df.copy()
    if status_filter != "mind" and "status" in visible.columns:
        visible = visible[visible["status"].astype(str) == status_filter]

    metrics = requests_df["status"].fillna("").astype(str).value_counts().to_dict()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Új", metrics.get("new", 0))
    m2.metric("Jóváhagyott", metrics.get("approved", 0))
    m3.metric("Elutasított", metrics.get("rejected", 0))
    m4.metric("Összes", len(requests_df))

    st.dataframe(
        visible[
            [
                column
                for column in [
                    "id",
                    "courier_id",
                    "courier_name",
                    "phone_number",
                    "email",
                    "status",
                    "admin_note",
                    "created_at",
                    "updated_at",
                ]
                if column in visible.columns
            ]
        ],
        use_container_width=True,
        hide_index=True,
        height=260,
    )

    approval_statuses = ["approved"] if status_filter == "approved" else ["new", "pending"]
    pending = requests_df[requests_df["status"].fillna("").astype(str).isin(approval_statuses)]
    if pending.empty:
        if status_filter == "approved":
            st.info("Nincs újraküldhető, már jóváhagyott regisztráció.")
        else:
            st.info("Nincs jóváhagyható regisztráció.")
        return

    labels = []
    by_label = {}
    for row in pending.to_dict("records"):
        label = (
            f"{row.get('courier_name')} · {row.get('courier_id')} · "
            f"{row.get('email')} · #{row.get('id')}"
        )
        labels.append(label)
        by_label[label] = row

    selected_label = st.selectbox(
        "Újraküldendő kérelem" if status_filter == "approved" else "Jóváhagyandó kérelem",
        labels,
        key="pwa_registration_approval_select",
    )
    selected = by_label[selected_label]

    with st.form(f"pwa_registration_decision_{selected.get('id')}"):
        c1, c2, c3 = st.columns(3)
        courier_name = c1.text_input("Futár neve", value=str(selected.get("courier_name") or ""))
        courier_id = c2.text_input("Courier ID", value=str(selected.get("courier_id") or ""))
        recipient_email = c3.text_input("E-mail", value=str(selected.get("email") or ""))
        admin_note = st.text_area("Admin megjegyzés", value=str(selected.get("admin_note") or ""), height=80)
        confirm_approve = st.checkbox(
            "Megerősítem: PWA user létrehozása/frissítése és belépési e-mail küldése.",
            key=f"pwa_registration_confirm_approve_{selected.get('id')}",
        )
        approve = st.form_submit_button("Újraküldés + e-mail" if status_filter == "approved" else "Jóváhagyás + e-mail", type="primary")
        reject = st.form_submit_button("Elutasítás")

    if approve:
        if not confirm_approve:
            st.error("A jóváhagyáshoz jelöld be a megerősítést.")
            return
        try:
            recipient_email = validate_email(recipient_email)
            try:
                result = upsert_pwa_user_with_password(
                    courier_id=courier_id,
                    username=courier_name,
                    recipient_email=recipient_email,
                )
                send_login_credentials(recipient_email, result["username"], result["password"])
            except Exception as db_exc:
                result = approve_pwa_registration_user(
                    courier_id,
                    courier_name,
                    recipient_email,
                    send_login_credentials,
                )
                result["action"] = f"{result.get('action', 'legacy')} (legacy fallback: {db_exc})"
            try:
                upsert_couriers(
                    [{
                        "courier_id": int(normalize_courier_id(courier_id)),
                        "name": courier_name,
                        "email": recipient_email,
                        "phone": selected.get("phone_number"),
                        "source": "pwa_registration",
                        "active": "True",
                    }]
                )
                load_courier_email_lookup.clear()
            except Exception as exc:
                st.warning(f"A user elkészült, de a CourierDB_JITT frissítés nem sikerült: {exc}")

            update_pwa_registration_request(
                selected.get("id"),
                {
                    "status": "approved",
                    "admin_note": (
                        f"{admin_note.strip()}\n"
                        f"Jóváhagyta: {_admin_actor()}; e-mail: {result['recipient']}; action: {result['action']}"
                    ).strip(),
                },
            )
            st.success(
                f"Jóváhagyva. {result['username']} belépési adatai elküldve: {result['recipient']}"
            )
            st.rerun()
        except Exception as exc:
            st.error(f"A jóváhagyás sikertelen: {exc}")

    if reject:
        try:
            update_pwa_registration_request(
                selected.get("id"),
                {
                    "status": "rejected",
                    "admin_note": (
                        f"{admin_note.strip()}\nElutasította: {_admin_actor()}"
                    ).strip(),
                },
            )
            st.success("A regisztrációs kérelem elutasítva.")
            st.rerun()
        except Exception as exc:
            st.error(f"Az elutasítás sikertelen: {exc}")


def _display_shift_admin_df(df):
    columns = [
        "Torles",
        "work_date",
        "warehouse",
        "start_time",
        "end_time",
        "occupancy",
        "booked",
        "maximum",
        "courier_id",
        "courier_name",
        "email",
        "serial",
        "fetched_at",
    ]
    columns = [column for column in columns if column in df.columns]
    return df[columns].rename(
        columns={
            "Torles": "Torles",
            "work_date": "Datum",
            "warehouse": "Raktar",
            "start_time": "Kezdes",
            "end_time": "Vege",
            "occupancy": "Foglaltsag",
            "booked": "Foglalt",
            "maximum": "Maximum",
            "courier_id": "Courier ID",
            "courier_name": "Futar",
            "email": "E-mail",
            "serial": "Serial",
            "fetched_at": "DB frissites",
        }
    )


def _run_and_log_admin_command(action, command, payload):
    actor = _admin_actor()
    log_admin_action(
        action,
        "STARTED",
        actor=actor,
        payload=payload,
        message=command_text(command),
    )
    result = run_command(command)
    status = "OK" if result.returncode == 0 else "FAILED"
    log_admin_action(
        action,
        status,
        actor=actor,
        payload={
            **payload,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
        },
        message=f"exit_code={result.returncode}",
    )
    return result


def show_giriton_shift_admin_section():
    st.divider()
    st.subheader("Giriton muszak admin")
    st.caption(
        "Kovetkezo 10 nap Shift Subscription adatai, frissites es Giriton torles audit loggal."
    )

    start_date, end_date = next_days_window(10)
    can_run = can_run_robot_locally()
    raw_command = raw_export_command(start_date=start_date.isoformat(), days=10)

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Idoszak kezdete", start_date.isoformat())
    c2.metric("Idoszak vege", end_date.isoformat())

    if c3.button(
        "Kovetkezo 10 nap Giriton lekerese",
        type="primary",
        use_container_width=True,
        disabled=not can_run,
    ):
        with st.spinner("Giriton raw export fut..."):
            result = _run_and_log_admin_command(
                "RAW_EXPORT_NEXT_10_DAYS",
                raw_command,
                {"start_date": start_date.isoformat(), "days": 10},
            )
        if result.returncode == 0:
            st.success("Lekerdezes kesz, DB frissitve.")
            st.cache_data.clear()
        else:
            st.error(f"Lekerdezes sikertelen, exit code: {result.returncode}")
        st.text_area("Robot stdout", result.stdout, height=180)
        st.text_area("Robot stderr", result.stderr, height=120)

    if not can_run:
        st.warning(
            "Ezen a Streamlit hoston nem futtathato helyben a Giriton robot. "
            "GitHub Actionsbol inditsd: Giriton Raw Export / Giriton Shift Delete."
        )
        st.code(command_text(raw_command), language="powershell")

    try:
        all_shifts = read_next_giriton_shifts(days=10)
    except Exception as exc:
        st.error(f"Giriton muszak DB olvasasi hiba: {exc}")
        all_shifts = pd.DataFrame()

    booked = filter_booked_shift_rows(all_shifts)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("DB sor", len(all_shifts))
    m2.metric("Foglalt sor", len(booked))
    m3.metric(
        "Nap",
        booked["work_date"].nunique()
        if not booked.empty and "work_date" in booked.columns
        else 0,
    )
    m4.metric(
        "Futar",
        booked["courier_id"].nunique()
        if not booked.empty and "courier_id" in booked.columns
        else 0,
    )

    if booked.empty:
        st.info("Nincs foglalt Giriton muszak a kovetkezo 10 nap DB adatai kozott.")
    else:
        filters = st.columns(3)
        warehouse_filter = filters[0].selectbox(
            "Raktar",
            ["Mind"] + sorted(str(x) for x in booked["warehouse"].dropna().unique()),
            key="admin_giriton_shift_warehouse_filter",
        )
        date_filter = filters[1].selectbox(
            "Datum",
            ["Mind"] + sorted(str(x)[:10] for x in booked["work_date"].dropna().unique()),
            key="admin_giriton_shift_date_filter",
        )
        courier_filter = filters[2].text_input(
            "Futar / ID / serial szures",
            key="admin_giriton_shift_courier_filter",
        )

        visible = booked.copy()
        if warehouse_filter != "Mind":
            visible = visible[visible["warehouse"].astype(str) == warehouse_filter]
        if date_filter != "Mind":
            visible = visible[visible["work_date"].astype(str).str[:10] == date_filter]
        if courier_filter.strip():
            needle = courier_filter.strip().casefold()
            visible = visible[
                visible["courier_name"].astype(str).str.casefold().str.contains(needle, na=False)
                | visible["courier_id"].astype(str).str.contains(needle, na=False)
                | visible["serial"].astype(str).str.casefold().str.contains(needle, na=False)
            ]

        editable = visible.copy()
        editable.insert(0, "Torles", False)
        display_df = _display_shift_admin_df(editable)
        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            disabled=[column for column in display_df.columns if column != "Torles"],
            key="admin_giriton_shift_delete_editor",
            height=420,
        )

        selected_rows = (
            edited[edited["Torles"] == True]
            if "Torles" in edited.columns
            else pd.DataFrame()
        )
        st.caption(f"Kijelolt torlesre: {len(selected_rows)} sor")

        confirm_bulk = st.checkbox(
            "Megerősítem a kijelölt Giriton foglalások törlését.",
            key="admin_giriton_bulk_delete_confirm",
        )
        if st.button(
            "Kijeloltek torlese Giritonbol",
            type="primary",
            disabled=not can_run or not confirm_bulk or selected_rows.empty,
            use_container_width=True,
        ):
            failures = []
            progress = st.progress(0)
            rows = selected_rows.to_dict("records")
            for index, row in enumerate(rows, start=1):
                cmd = delete_command(
                    serial=row.get("Serial"),
                    work_date=str(row.get("Datum"))[:10],
                    warehouse=row.get("Raktar"),
                    shift_start=row.get("Kezdes"),
                    courier_id=row.get("Courier ID"),
                    courier_name=row.get("Futar"),
                )
                result = _run_and_log_admin_command(
                    "DELETE_SHIFT_SUBSCRIPTION",
                    cmd,
                    row,
                )
                if result.returncode != 0:
                    failures.append({
                        "Serial": row.get("Serial"),
                        "Futar": row.get("Futar"),
                        "Hiba": result.stderr[-1000:] or result.stdout[-1000:],
                    })
                progress.progress(index / len(rows))
            if failures:
                st.error(f"{len(failures)} torles hibas.")
                st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)
            else:
                st.success("Kijelolt torlesek lefutottak.")
            st.cache_data.clear()

        st.markdown("**Torles serial / ID alapjan**")
        with st.form("admin_giriton_single_delete_form"):
            s1, s2, s3 = st.columns(3)
            serial = s1.text_input("Serial")
            work_date = s2.date_input("Datum", value=start_date)
            warehouse = s3.selectbox("Raktar", ["BUD1", "BUD2"])
            s4, s5, s6 = st.columns(3)
            shift_start = s4.text_input("Kezdes", placeholder="10:00")
            courier_id = s5.text_input("Courier ID")
            courier_name = s6.text_input("Futar nev")
            confirm_text = st.text_input("Megerősítéshez írd be: TORLES")
            submit_delete = st.form_submit_button(
                "Egyedi torles inditasa",
                type="primary",
                disabled=not can_run,
            )
        if submit_delete:
            if confirm_text != "TORLES":
                st.error("A torleshez a megerosito mezobe ezt ird: TORLES")
            elif not shift_start.strip() or (not courier_id.strip() and not courier_name.strip()):
                st.error("Kezdes es legalabb Courier ID vagy futar nev kotelezo.")
            else:
                cmd = delete_command(
                    serial=serial,
                    work_date=work_date.isoformat(),
                    warehouse=warehouse,
                    shift_start=shift_start,
                    courier_id=courier_id,
                    courier_name=courier_name,
                )
                with st.spinner("Giriton torles fut..."):
                    result = _run_and_log_admin_command(
                        "DELETE_SHIFT_SUBSCRIPTION_MANUAL",
                        cmd,
                        {
                            "serial": serial,
                            "work_date": work_date.isoformat(),
                            "warehouse": warehouse,
                            "shift_start": shift_start,
                            "courier_id": courier_id,
                            "courier_name": courier_name,
                        },
                    )
                if result.returncode == 0:
                    st.success("Torles lefutott.")
                else:
                    st.error(f"Torles sikertelen, exit code: {result.returncode}")
                st.text_area("Torles stdout", result.stdout, height=160)
                st.text_area("Torles stderr", result.stderr, height=120)

    st.markdown("**Admin muveleti log**")
    try:
        log_df = read_admin_action_log(limit=200)
    except Exception as exc:
        st.warning(f"Admin log nem olvashato: {exc}")
        log_df = pd.DataFrame()
    if log_df.empty:
        st.info("Nincs admin action log, vagy meg nincs letrehozva a Supabase tabla.")
    else:
        st.dataframe(log_df, use_container_width=True, hide_index=True)


def show_admin_page():
    st.title("👑 Admin")

    created_user = st.session_state.pop("admin_created_user", None)
    if created_user:
        st.success(
            f"Felhasználó létrehozva: {created_user['username']} | "
            f"Jelszó: {created_user['password']}"
        )

    show_giriton_shift_admin_section()
    show_pwa_registration_admin_section()

    data = load_users()
    users = data.get("users", [])

    st.subheader("👥 Felhasználók")

    show_passwords = st.toggle(
        "Jelszavak megjelenítése",
        value=False,
        help="Csak adminisztrációs célra használd.",
    )

    display_users = []
    for user in users:
        display_user = user.copy()

        if not show_passwords:
            if display_user.get("password"):
                display_user["password"] = "••••••••"
            if display_user.get("passwordHash"):
                display_user["passwordHash"] = "beállítva"

        if display_user.get("token"):
            display_user["token"] = "aktív"

        display_users.append(display_user)

    st.dataframe(
        pd.DataFrame(display_users),
        use_container_width=True,
        height=500,
        hide_index=True,
    )

    st.divider()
    st.subheader("🔄 users.json frissítése a courier_master alapján")

    st.caption(
        "A courier_id alapján frissíti a users.json fájlt. "
        "Az admin jogosultságú felhasználók és Bagoly Zoltán változatlanok maradnak. "
        "A többi meglévő felhasználó új jelszót kap."
    )

    try:
        courier_master_for_sync = read_courier_master()
    except Exception as exc:
        courier_master_for_sync = pd.DataFrame()
        st.error(f"A courier_master nem olvasható: {exc}")

    if not courier_master_for_sync.empty:
        courier_rows = courier_master_for_sync.to_dict("records")
        sync_preview = build_courier_master_sync_preview(courier_rows)
        sync_preview_df = pd.DataFrame(sync_preview)

        if not sync_preview_df.empty:
            action_counts = sync_preview_df["action"].value_counts().to_dict()
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Új", action_counts.get("Új felhasználó", 0))
            p2.metric(
                "Reset + frissítés",
                action_counts.get("Frissítés + jelszó reset", 0),
            )
            p3.metric(
                "Védett",
                action_counts.get("Védett – változatlan", 0),
            )
            p4.metric("Összes", len(sync_preview_df))

            with st.expander("Szinkron előnézet", expanded=False):
                st.dataframe(
                    sync_preview_df,
                    use_container_width=True,
                    hide_index=True,
                )

        confirm_sync = st.checkbox(
            "Megerősítem a users.json frissítését és a nem védett felhasználók jelszó-resetjét.",
            key="confirm_users_json_sync",
        )

        if st.button(
            "users.json frissítése",
            type="primary",
            disabled=not confirm_sync,
        ):
            try:
                result = sync_users_from_courier_master(
                    courier_rows,
                    reset_existing=True,
                )
                st.session_state["last_users_sync_passwords"] = result.get(
                    "passwords",
                    [],
                )
                st.success(
                    "Frissítés kész. "
                    f"Új: {result['created']}, "
                    f"frissített: {result['updated']}, "
                    f"resetelt: {result['reset']}, "
                    f"védett: {result['protected']}, "
                    f"kihagyott: {result['skipped']}."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"A users.json frissítése sikertelen: {exc}")

    generated_passwords = st.session_state.get(
        "last_users_sync_passwords",
        [],
    )

    if generated_passwords:
        with st.expander(
            "Legutóbbi szinkronban generált jelszavak",
            expanded=True,
        ):
            show_generated_passwords = st.toggle(
                "Generált jelszavak megjelenítése",
                value=False,
                key="show_generated_passwords",
            )
            generated_df = pd.DataFrame(generated_passwords)

            if (
                not show_generated_passwords
                and "password" in generated_df.columns
            ):
                generated_df["password"] = "••••••••"

            st.dataframe(
                generated_df,
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "Jelszólista elrejtése",
                key="clear_generated_passwords",
            ):
                st.session_state.pop(
                    "last_users_sync_passwords",
                    None,
                )
                st.rerun()

    st.divider()
    st.subheader("🚚 CourierDB_JITT törzsadat")
    st.caption(
        "ID, név, e-mail, telefonszám és raktár frissítése a DSP driver API-ból. "
        "A courier_id lesz a biztos azonosító."
    )

    if st.button("CourierDB_JITT frissítése"):
        try:
            result = sync_courier_db_from_drivers()
            load_courier_email_lookup.clear()
            st.success(
                f"CourierDB_JITT frissítve: {result['updated']} API rekord, "
                f"összesen {result['total']} futár."
            )
        except Exception as exc:
            st.error(f"CourierDB_JITT frissítés sikertelen: {exc}")

    st.divider()
    st.subheader("➕ Új felhasználó")

    with st.form("new_user"):
        username = st.text_input("Név")
        courier_id = st.number_input("Courier ID", step=1)
        email = st.text_input("E-mail cím")
        phone = st.text_input("Telefonszám")
        role = st.selectbox("Jogosultság", ["user", "trainer", "coordinator", "admin"])
        trainer = st.text_input("Trainer")
        submitted = st.form_submit_button("Létrehozás")

        if submitted:
            try:
                password = create_user(username, int(courier_id), role, trainer)
                try:
                    upsert_couriers(
                        [{
                            "courier_id": int(courier_id),
                            "name": username,
                            "email": email,
                            "phone": phone,
                            "source": "admin",
                            "active": "True",
                        }]
                    )
                    load_courier_email_lookup.clear()
                except Exception as exc:
                    st.warning(
                        "A felhasználó elkészült, de a CourierDB_JITT "
                        f"frissítés nem sikerült: {exc}"
                    )

                st.session_state["admin_created_user"] = {
                    "username": username,
                    "password": password,
                }
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    try:
        email_lookup = load_courier_email_lookup()
    except Exception as exc:
        email_lookup = {}
        st.error(f"A courier_master e-mail címei nem tölthetők be: {exc}")

    st.divider()
    st.subheader("📨 Tömeges belépési adatok kiküldése")
    st.caption(
        "Az aktív felhasználók users.json fájlban tárolt jelenlegi jelszavát küldi ki. "
        "Nem generál új jelszót."
    )

    active_users = [u for u in users if bool(u.get("active", True))]
    bulk_candidates = []
    missing_email_users = []
    missing_password_users = []

    for user in active_users:
        email_address = get_courier_email(user, email_lookup)
        password = get_existing_password(user)

        if not email_address:
            missing_email_users.append(str(user.get("username") or "Ismeretlen"))
            continue
        if not password:
            missing_password_users.append(str(user.get("username") or "Ismeretlen"))
            continue

        bulk_candidates.append({"user": user, "email": email_address})

    c1, c2, c3 = st.columns(3)
    c1.metric("Aktív felhasználó", len(active_users))
    c2.metric("Küldhető", len(bulk_candidates))
    c3.metric(
        "Kihagyandó",
        len(missing_email_users) + len(missing_password_users),
    )

    with st.expander("Tömeges küldés ellenőrzése", expanded=False):
        preview = []
        for item in bulk_candidates:
            preview.append({
                "Felhasználó": item["user"].get("username"),
                "Courier ID": get_user_courier_id(item["user"]),
                "E-mail": item["email"],
                "Küldhető": "Igen",
            })
        for name in missing_email_users:
            preview.append({
                "Felhasználó": name,
                "Courier ID": "",
                "E-mail": "",
                "Küldhető": "Nem – nincs e-mail",
            })
        for name in missing_password_users:
            preview.append({
                "Felhasználó": name,
                "Courier ID": "",
                "E-mail": "",
                "Küldhető": "Nem – nincs olvasható jelszó",
            })
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

    bulk_confirm = st.checkbox(
        f"Megerősítem {len(bulk_candidates)} belépési e-mail kiküldését.",
        key="bulk_credentials_confirm",
    )

    if st.button(
        "📨 Belépési adatok kiküldése mindenkinek",
        type="primary",
        disabled=not bulk_confirm or not bulk_candidates,
    ):
        sent_count = 0
        failed_rows = []
        progress = st.progress(0)
        status_box = st.empty()

        for index, item in enumerate(bulk_candidates, start=1):
            user = item["user"]
            recipient = item["email"]
            username_value = str(user.get("username") or "").strip()
            status_box.write(f"Küldés: {username_value} → {recipient}")

            try:
                send_existing_credentials(user, recipient)
                sent_count += 1
            except Exception as exc:
                failed_rows.append({
                    "Felhasználó": username_value,
                    "E-mail": recipient,
                    "Hiba": str(exc),
                })

            progress.progress(index / len(bulk_candidates))
            time.sleep(0.15)

        status_box.empty()
        st.success(
            f"Tömeges küldés kész. Elküldve: {sent_count}, "
            f"hibás: {len(failed_rows)}, "
            f"kihagyva: {len(missing_email_users) + len(missing_password_users)}."
        )

        if failed_rows:
            st.dataframe(
                pd.DataFrame(failed_rows),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    st.subheader("⚙️ Felhasználó kezelése")

    if not users:
        st.info("Még nincs kezelhető felhasználó.")
        return

    selected_user = st.selectbox(
        "Felhasználó",
        [u["username"] for u in users],
    )
    selected_data = next(
        u for u in users if u["username"] == selected_user
    )

    col1, col2 = st.columns(2)

    with col1:
        roles = ["user", "trainer", "coordinator", "admin"]
        current_role = selected_data.get("role", "user")
        if current_role not in roles:
            current_role = "user"

        new_role = st.selectbox(
            "Jogosultság",
            roles,
            index=roles.index(current_role),
        )
        trainer = st.text_input(
            "Trainer",
            value=selected_data.get("trainer", ""),
        )
        active = st.checkbox(
            "Aktív",
            value=selected_data.get("active", True),
        )

        if st.button("💾 Mentés"):
            update_role(selected_user, new_role)
            update_trainer(selected_user, trainer)
            toggle_active(selected_user, active)
            st.success("Mentve")
            st.rerun()

    with col2:
        st.markdown("**Belépési adatok küldése**")

        selected_password = get_existing_password(selected_data)
        show_selected_password = st.toggle(
            "Jelszó megjelenítése",
            value=False,
            key=f"show_selected_password_{selected_user}",
        )
        st.text_input(
            "Jelenlegi jelszó",
            value=(
                selected_password
                if show_selected_password
                else "••••••••"
            ),
            disabled=True,
            key=f"selected_password_{selected_user}_{show_selected_password}",
        )

        selected_courier_id = get_user_courier_id(selected_data)
        default_email = get_courier_email(selected_data, email_lookup)
        existing_password = get_existing_password(selected_data)

        if not selected_courier_id:
            st.warning("Ehhez a felhasználóhoz nincs Courier ID beállítva.")
        if not default_email:
            st.warning("Ehhez a futárhoz nincs e-mail-cím a courier_master táblában.")
        if not existing_password:
            st.warning(
                "Ehhez a felhasználóhoz nincs olvasható password mező a users.json fájlban."
            )

        with st.form(f"send_login_credentials_form_{selected_user}"):
            recipient_email = st.text_input(
                "Futár e-mail-címe",
                value=default_email,
                key=f"admin_credential_email_{selected_courier_id or selected_user}",
            )
            confirm_send = st.checkbox(
                "Megerősítem a jelenlegi belépési adatok kiküldését.",
                key=f"confirm_credentials_send_{selected_user}",
            )
            send_credentials = st.form_submit_button(
                "Belépési adatok elküldése",
                type="primary",
                disabled=not bool(existing_password),
            )

        if send_credentials:
            if not confirm_send:
                st.error("A kiküldést jóvá kell hagyni.")
            else:
                try:
                    result = send_existing_credentials(
                        selected_data,
                        recipient_email,
                    )
                    st.success(
                        "A jelenlegi belépési adatok elküldve ide: "
                        f"{result['recipient']}"
                    )
                except Exception as exc:
                    st.error(f"A levélküldés sikertelen: {exc}")

        st.divider()

        if st.button("🔑 Jelszó reset"):
            password = reset_password(selected_user)
            st.success(f"Új jelszó: {password}")
            st.info(
                "A reset után az új jelszót külön küldd ki a "
                "„Belépési adatok elküldése” gombbal."
            )

        st.divider()

        delete_confirm = st.checkbox(
            "Megerősítem a felhasználó törlését.",
            key=f"delete_user_confirm_{selected_user}",
        )

        if st.button(
            "🗑️ Felhasználó törlése",
            disabled=not delete_confirm,
        ):
            delete_user(selected_user)
            st.success("Felhasználó törölve")
            st.rerun()
