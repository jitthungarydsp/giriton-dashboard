import pandas as pd
import streamlit as st

from page.invoice_summary import (
    build_invoice_feedback_context,
    first_invoice_contact_value,
    month_start_from_date,
    normalize_courier_id,
    normalize_name,
    read_sent_invoice_driver_names,
    user_has_logged_in,
)
from resources.email_sender import send_login_credentials
from resources.peopleforce_documents import (
    read_peopleforce_card_statuses_for_month,
    read_peopleforce_complaints_for_month,
)
from resources.users import reset_password_and_send


def render_legacy_invoice_delivery_status(route_driver_names, document_month):
    """
    Admin visszajelzo: hol tart a futar az elszamolasi folyamatban.
    Piros sor: segitseget ker / nyitott reklamacio.
    Zold sor: elfogadta / lezart allapotban van.
    """
    clean_names = sorted(
        {
            str(name or "").strip()
            for name in route_driver_names
            if str(name or "").strip()
        },
        key=lambda value: value.casefold(),
    )

    route_name_lookup = {
        normalize_name(name): name
        for name in clean_names
    }
    month_start = month_start_from_date(document_month)
    master_by_name, master_by_id, users_by_name, users_by_id = build_invoice_feedback_context()

    try:
        sent_lookup = read_sent_invoice_driver_names(month_start, "settlement")
    except Exception as exc:
        st.warning(
            f"A futar visszajelzo dokumentumallapota nem toltheto be: {exc}"
        )
        return

    try:
        status_df = read_peopleforce_card_statuses_for_month(
            month_start,
            action_key="settlement",
        )
    except Exception as exc:
        st.warning(f"A futar visszajelzo statuszai nem tolthet?k be: {exc}")
        status_df = pd.DataFrame()

    try:
        complaints_df = read_peopleforce_complaints_for_month(
            month_start,
            document_type="settlement",
        )
    except Exception as exc:
        st.warning(f"A reklamacios adatok nem tolthet?k be: {exc}")
        complaints_df = pd.DataFrame()

    def row_name_key(row):
        return normalize_name(row.get("courier_name", ""))

    def row_id_key(row):
        courier_id = str(row.get("courier_id") or "").strip()
        return courier_id if courier_id and courier_id.lower() != "nan" else ""

    status_by_name = {}
    status_by_id = {}
    if not status_df.empty:
        for _, status_row in status_df.iterrows():
            name_key = row_name_key(status_row)
            id_key = row_id_key(status_row)
            if name_key and name_key not in status_by_name:
                status_by_name[name_key] = status_row
            if id_key and id_key not in status_by_id:
                status_by_id[id_key] = status_row

    open_complaints_by_name = {}
    open_complaints_by_id = {}
    if not complaints_df.empty:
        status_series = complaints_df.get("status", pd.Series(dtype=str))
        open_complaints = complaints_df[
            status_series.astype(str).str.strip().str.lower().ne("resolved")
        ].copy()
        for _, complaint_row in open_complaints.iterrows():
            name_key = row_name_key(complaint_row)
            id_key = row_id_key(complaint_row)
            if name_key:
                open_complaints_by_name.setdefault(name_key, []).append(complaint_row)
            if id_key:
                open_complaints_by_id.setdefault(id_key, []).append(complaint_row)

    for details in sent_lookup.values():
        name = str(details.get("courier_name") or "").strip()
        if name:
            route_name_lookup.setdefault(normalize_name(name), name)
    if not status_df.empty:
        for _, status_row in status_df.iterrows():
            name = str(status_row.get("courier_name") or "").strip()
            if name:
                route_name_lookup.setdefault(normalize_name(name), name)
    if not complaints_df.empty:
        for _, complaint_row in complaints_df.iterrows():
            name = str(complaint_row.get("courier_name") or "").strip()
            if name:
                route_name_lookup.setdefault(normalize_name(name), name)

    sent_names = sorted(
        [
            route_name_lookup[key]
            for key in route_name_lookup
            if key in sent_lookup
        ],
        key=lambda value: value.casefold(),
    )

    missing_names = sorted(
        [
            route_name_lookup[key]
            for key in route_name_lookup
            if key not in sent_lookup
        ],
        key=lambda value: value.casefold(),
    )

    total_count = len(route_name_lookup)
    sent_count = len(sent_names)
    missing_count = len(missing_names)
    completion = (sent_count / total_count * 100) if total_count else 0

    feedback_rows = []
    for name_key, name in sorted(route_name_lookup.items(), key=lambda item: item[1].casefold()):
        sent_details = sent_lookup.get(name_key, {})
        courier_id = normalize_courier_id(sent_details.get("courier_id"))
        master_row = master_by_id.get(courier_id) if courier_id else None
        if master_row is None:
            master_row = master_by_name.get(name_key, {})
        if not courier_id and master_row:
            courier_id = normalize_courier_id(master_row.get("courier_id") or master_row.get("driver_id"))

        user_row = users_by_id.get(courier_id) if courier_id else None
        if user_row is None:
            user_row = users_by_name.get(name_key, {})

        contact_email = first_invoice_contact_value(
            master_row,
            "billing_email",
            "invoice_email",
            "email",
            "contact_email",
        ) or first_invoice_contact_value(user_row, "email", "contact_email")
        username = first_invoice_contact_value(user_row, "username", "name")
        has_logged_in = user_has_logged_in(user_row)

        status_row = status_by_id.get(courier_id) if courier_id else None
        if status_row is None:
            status_row = status_by_name.get(name_key)
        if status_row is not None and not courier_id:
            courier_id = row_id_key(status_row)

        complaint_rows = open_complaints_by_id.get(courier_id, []) if courier_id else []
        if not complaint_rows:
            complaint_rows = open_complaints_by_name.get(name_key, [])

        status_value = ""
        status_note = ""
        updated_at = ""
        if status_row is not None:
            status_value = str(status_row.get("status") or "").strip().lower()
            status_note = str(status_row.get("status_note") or "").strip()
            updated_at = str(status_row.get("updated_at") or "").strip()

        uploaded_at = str(sent_details.get("uploaded_at") or "").strip()
        has_uploaded_document = bool(uploaded_at)

        if complaint_rows:
            row_state = "help"
            lamp = "Piros"
            step = "Segitseget ker"
            courier_feedback = "Nyitott reklamacio"
            note = str(complaint_rows[0].get("message") or status_note or "").strip()
        elif status_value == "done":
            row_state = "done"
            lamp = "Zold"
            if "utal" in status_note.lower():
                step = "Sikeres elutalas"
            else:
                step = "Elfogadva"
            courier_feedback = "Rendben"
            note = status_note
        elif has_uploaded_document or status_value == "open":
            row_state = "waiting"
            lamp = "Sarga"
            step = "Futarnal"
            courier_feedback = "Visszajelzesre var"
            note = status_note or "Elszamolas feltoltve."
        else:
            row_state = "missing"
            lamp = "Szurke"
            step = "Meg nincs kikuldve"
            courier_feedback = "-"
            note = ""

        feedback_rows.append(
            {
                "Lampa": lamp,
                "Futar": name,
                "Courier ID": courier_id or "-",
                "Hol tart": step,
                "Futar visszajelzes": courier_feedback,
                "Feltoltve": uploaded_at or "-",
                "Utolso frissites": updated_at or uploaded_at or "-",
                "E-mail": contact_email or "-",
                "Belepett": "Igen" if has_logged_in else "Nem",
                "Megjegyzes": note or "-",
                "_state": row_state,
                "_email": contact_email,
                "_username": username,
                "_has_logged_in": has_logged_in,
            }
        )

    feedback_df = pd.DataFrame(feedback_rows)
    state_series = feedback_df.get("_state", pd.Series(dtype=str))
    done_count = int((state_series == "done").sum()) if not feedback_df.empty else 0
    help_count = int((state_series == "help").sum()) if not feedback_df.empty else 0
    waiting_count = int((state_series == "waiting").sum()) if not feedback_df.empty else 0

    st.subheader("Futar visszajelzo")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Futar osszesen", total_count)
    metric2.metric("Kikuldve", sent_count)
    metric3.metric("Segitseget ker", help_count)
    metric4.metric("Elfogadva / zold", done_count)

    sub1, sub2 = st.columns(2)
    sub1.metric("Visszajelzesre var", waiting_count)
    sub2.metric("Meg nincs kikuldve", missing_count)

    if total_count:
        st.progress(min(max(completion / 100, 0), 1))

    def style_feedback_rows(row):
        state = row.get("_state")
        if state == "help":
            return ["background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"] * len(row)
        if state == "done":
            return ["background-color: #dcfce7; color: #14532d; font-weight: 700;"] * len(row)
        if state == "waiting":
            return ["background-color: #fef9c3; color: #713f12;"] * len(row)
        return ["background-color: #f8fafc; color: #475569;"] * len(row)

    if not feedback_df.empty:
        display_feedback_df = feedback_df.drop(
            columns=["_state", "_email", "_username", "_has_logged_in"],
            errors="ignore",
        )

        def style_display_feedback_rows(row):
            state = feedback_df.loc[row.name, "_state"]
            if state == "help":
                return ["background-color: #fee2e2; color: #7f1d1d; font-weight: 700;"] * len(row)
            if state == "done":
                return ["background-color: #dcfce7; color: #14532d; font-weight: 700;"] * len(row)
            if state == "waiting":
                return ["background-color: #fef9c3; color: #713f12;"] * len(row)
            return ["background-color: #f8fafc; color: #475569;"] * len(row)

        st.dataframe(
            display_feedback_df.style.apply(style_display_feedback_rows, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    if missing_names:
        st.warning(
            f"{missing_count} futarnak meg nincs elszamolas dokumentuma "
            f"a(z) {month_start:%Y-%m} honapra."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Meg nincs elszamolas kikuldve": missing_names,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success(
            "Minden, az elszamolasi route adatokban szereplo futarnak "
            "ki lett kuldve az elszamolasa."
        )

    if not feedback_df.empty:
        resend_candidates = feedback_df[
            feedback_df["_state"].isin(["missing", "waiting"])
            & feedback_df["_username"].astype(str).str.strip().ne("")
            & feedback_df["_email"].astype(str).str.contains("@", na=False)
            & (~feedback_df["_has_logged_in"].astype(bool))
        ].copy()
        with st.expander("Belepesi adatok ujrakuldese azoknak, akik meg nem leptek be", expanded=False):
            if resend_candidates.empty:
                st.info("Nincs olyan futar, akinek van e-mail cime, felhasznaloja, es meg nem lepett be.")
            else:
                st.caption("Uj jelszot generalunk, es elkuldjuk a felhasznalonevet, jelszot, valamint hogy elkeszult az elszamolasa.")
                st.dataframe(
                    resend_candidates[["Futar", "Courier ID", "E-mail", "Hol tart"]],
                    use_container_width=True,
                    hide_index=True,
                )
                confirm_resend = st.checkbox(
                    f"Meger?sitem {len(resend_candidates)} futar belepesi adatainak ujrakuldeset.",
                    key=f"invoice_resend_login_confirm_{month_start.isoformat()}",
                )
                if st.button(
                    "Belepesi e-mail ujrakuldese",
                    disabled=not confirm_resend,
                    use_container_width=True,
                    key=f"invoice_resend_login_button_{month_start.isoformat()}",
                ):
                    sent_rows = []
                    for _, candidate in resend_candidates.iterrows():
                        try:
                            reset_password_and_send(
                                str(candidate["_username"]).strip(),
                                str(candidate["_email"]).strip(),
                                send_login_credentials,
                            )
                            sent_rows.append({"Futar": candidate["Futar"], "Allapot": "Elkuldve", "Hiba": ""})
                        except Exception as exc:
                            sent_rows.append({"Futar": candidate["Futar"], "Allapot": "Hiba", "Hiba": str(exc)})
                    st.dataframe(pd.DataFrame(sent_rows), use_container_width=True, hide_index=True)

    with st.expander("Kikuldott elszamolasok listaja", expanded=False):
        if sent_names:
            sent_rows = []
            for name in sent_names:
                details = sent_lookup.get(normalize_name(name), {})
                sent_rows.append(
                    {
                        "Futar": name,
                        "Courier ID": details.get("courier_id"),
                        "Feltoltve": details.get("uploaded_at"),
                    }
                )

            st.dataframe(
                pd.DataFrame(sent_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Ehhez a honaphoz meg nincs kikuldott elszamolas.")

