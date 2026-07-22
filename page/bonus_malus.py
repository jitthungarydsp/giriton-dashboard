from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from resources.coordinator_adjustments import (
    create_adjustment_entry,
    read_adjustment_entries,
    read_adjustment_items,
    soft_delete_adjustment_entry,
)
from resources.courier_master_db import read_courier_master


ALLOWED_ROLES = {"admin", "coordinator"}
KIND_LABELS = {"bonus": "Bónusz", "malus": "Málusz"}


def _actor() -> str:
    user = st.session_state.get("user", {})
    return str(user.get("username") or st.session_state.get("username") or "unknown").strip()


@st.cache_data(show_spinner=False, ttl=30)
def _courier_options() -> list[dict]:
    rows = read_courier_master()
    if rows is None or rows.empty:
        return []
    result = []
    for _, row in rows.iterrows():
        courier_id = str(row.get("courier_id") or "").strip()
        courier_name = str(row.get("courier_name") or row.get("name") or "").strip()
        if courier_id and courier_name:
            result.append(
                {
                    "courier_id": courier_id,
                    "courier_name": courier_name,
                    "label": f"{courier_name} · #{courier_id}",
                }
            )
    return sorted(result, key=lambda row: row["courier_name"].casefold())


def _load_kind(kind: str):
    return read_adjustment_items(kind, active_only=True), read_adjustment_entries(kind)


def _render_entry_form(kind: str, couriers: list[dict], items: pd.DataFrame) -> None:
    labels = [row["label"] for row in couriers]
    courier_by_label = {row["label"]: row for row in couriers}
    item_rows = items.to_dict("records") if not items.empty else []
    item_labels = [str(row.get("item_name") or "") for row in item_rows]
    item_by_label = {str(row.get("item_name") or ""): row for row in item_rows}

    if not item_labels:
        st.warning(
            f"Nincs aktív {KIND_LABELS[kind].lower()} tétel. "
            "Az admin a Beállítások oldalon tud létrehozni egyet."
        )
        return

    selected_item_state = st.session_state.get(f"adjustment_item_{kind}", item_labels[0])
    default_item = item_by_label.get(selected_item_state, item_rows[0])
    with st.form(f"coordinator_{kind}_entry", clear_on_submit=True):
        selected_courier = st.selectbox("Futár", labels, key=f"adjustment_courier_{kind}")
        selected_item = st.selectbox("Tétel", item_labels, key=f"adjustment_item_{kind}")
        current_item = item_by_label.get(selected_item, default_item)
        col1, col2 = st.columns(2)
        amount = col1.number_input(
            "Összeg (Ft)",
            min_value=1,
            value=max(int(current_item.get("default_amount_huf") or 0), 1),
            step=500,
        )
        effective_date = col2.date_input("Dátum", value=date.today())
        note = st.text_area(
            "Megjegyzés",
            placeholder="A rögzítés oka vagy rövid háttérinformáció.",
            height=90,
        )
        submitted = st.form_submit_button(
            f"{KIND_LABELS[kind]} hozzáadása",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        courier = courier_by_label[selected_courier]
        item = item_by_label[selected_item]
        try:
            create_adjustment_entry(
                kind=kind,
                courier_id=courier["courier_id"],
                courier_name=courier["courier_name"],
                item_id=item.get("id"),
                item_name=item.get("item_name"),
                amount_huf=amount,
                note=note,
                effective_date=effective_date,
                actor=_actor(),
            )
            st.success(
                f"{KIND_LABELS[kind]} rögzítve: {courier['courier_name']} · "
                f"{'+' if kind == 'bonus' else '-'}{int(amount):,} Ft".replace(",", " ")
            )
            st.rerun()
        except Exception as exc:
            st.error(f"A rögzítés nem sikerült: {exc}")


def _render_entries(kind: str, entries: pd.DataFrame) -> None:
    st.markdown("#### Legutóbbi rögzítések")
    if entries.empty:
        st.caption("Még nincs aktív rögzítés.")
        return

    sign = 1 if kind == "bonus" else -1
    display = entries.copy()
    display["Előjelhelyes összeg"] = (
        pd.to_numeric(display["amount_huf"], errors="coerce").fillna(0).astype(int) * sign
    ).map(lambda value: f"{value:+,} Ft".replace(",", " "))
    display = display.rename(
        columns={
            "courier_name": "Futár",
            "item_name": "Tétel",
            "note": "Megjegyzés",
            "effective_date": "Dátum",
            "recorded_by": "Rögzítette",
            "recorded_at": "Rögzítve",
        }
    )
    st.dataframe(
        display[["Futár", "Tétel", "Előjelhelyes összeg", "Megjegyzés", "Dátum", "Rögzítette", "Rögzítve"]],
        use_container_width=True,
        hide_index=True,
        height=min(390, 38 + len(display) * 35),
    )

    entry_rows = entries.to_dict("records")
    entry_by_label = {
        f"{row.get('courier_name')} · {row.get('item_name')} · {row.get('effective_date')} · "
        f"{int(row.get('amount_huf') or 0):,} Ft".replace(",", " "): row
        for row in entry_rows
    }
    with st.expander("Rögzítés visszavonása"):
        with st.form(f"delete_{kind}_entry"):
            selected_label = st.selectbox("Visszavonandó tétel", list(entry_by_label))
            reason = st.text_input("Visszavonás indoka")
            confirmed = st.checkbox("Megerősítem a visszavonást")
            delete_clicked = st.form_submit_button(
                "Visszavonás",
                disabled=not confirmed,
                use_container_width=True,
            )
        if delete_clicked:
            try:
                soft_delete_adjustment_entry(
                    kind,
                    entry_by_label[selected_label]["id"],
                    _actor(),
                    reason,
                )
                st.success("A tétel visszavonva; az auditnaplóban megmaradt.")
                st.rerun()
            except Exception as exc:
                st.error(f"A visszavonás nem sikerült: {exc}")


def show_bonus_malus_page() -> None:
    user = st.session_state.get("user", {})
    role = str(user.get("role") or "").strip().lower()
    if role not in ALLOWED_ROLES:
        st.error("Ehhez az oldalhoz koordinátori vagy admin jogosultság szükséges.")
        return

    st.title("Bónusz / Málusz")
    st.caption(
        "Önálló koordinátori rögzítő. Az itt felvitt tételek még nem kerülnek bele az elszámolásba."
    )
    try:
        couriers = _courier_options()
    except Exception as exc:
        st.error(f"A futárlista nem tölthető be: {exc}")
        return
    if not couriers:
        st.warning("Nincs választható futár a courier_master táblában.")
        return

    bonus_tab, malus_tab = st.tabs(["Bónusz (+)", "Málusz (-)"])
    for tab, kind in ((bonus_tab, "bonus"), (malus_tab, "malus")):
        with tab:
            try:
                items, entries = _load_kind(kind)
            except Exception as exc:
                st.error(
                    "Az új bónusz/málusz táblák nem érhetők el. Futtasd a "
                    f"docs/supabase_coordinator_adjustments.sql migrációt. Részlet: {exc}"
                )
                continue
            _render_entry_form(kind, couriers, items)
            _render_entries(kind, entries)
