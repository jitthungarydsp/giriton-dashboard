from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from resources.coordinator_adjustments import (
    create_adjustment_item,
    create_compensation_rule,
    read_adjustment_items,
    read_compensation_rules,
    set_adjustment_item_active,
    set_compensation_rule_active,
)


DAY_LABELS = {
    "normal": "Sima nap",
    "highlighted": "Kiemelt nap",
    "any": "Bármely nap",
}
WEEKDAYS = {
    1: "Hétfő",
    2: "Kedd",
    3: "Szerda",
    4: "Csütörtök",
    5: "Péntek",
    6: "Szombat",
    7: "Vasárnap",
}
TOUR_LABELS = {"express": "Express", "city": "City", "region": "Régió"}
METRIC_LABELS = {
    "none": "Nincs minőségi mutató",
    "delay": "Késedelmi mutató",
    "compliance": "Túramegfelelési mutató",
    "customer_rating": "Ügyfélértékelés",
}
CATEGORY_LABELS = {
    "base_rate": "Alapdíj",
    "quality_bonus": "Minőségi díj / bónusz",
    "temporary_bonus": "Időszakos bónusz",
}


def _actor() -> str:
    user = st.session_state.get("user", {})
    return str(user.get("username") or "admin").strip()


def render_adjustment_item_settings() -> None:
    st.subheader("Bónusz / Málusz")
    st.caption(
        "Ezt a dinamikus listát csak az admin kezeli. A koordinátor kizárólag az aktív tételeket látja."
    )
    bonus_tab, malus_tab = st.tabs(["Bónusz tételek", "Málusz tételek"])
    for tab, kind, label in (
        (bonus_tab, "bonus", "Bónusz"),
        (malus_tab, "malus", "Málusz"),
    ):
        with tab:
            with st.form(f"new_{kind}_item", clear_on_submit=True):
                st.text_input(
                    "Tétel típusa",
                    value=f"{label} tétel",
                    disabled=True,
                )
                col1, col2 = st.columns([1.6, 0.8])
                item_name = col1.text_input("Tétel neve")
                default_amount = col2.number_input(
                    "Alapértelmezett összeg (Ft)", min_value=0, step=500
                )
                description = st.text_input("Admin megjegyzés / leírás")
                add_clicked = st.form_submit_button(
                    f"{label} tétel hozzáadása", type="primary", use_container_width=True
                )
            if add_clicked:
                try:
                    create_adjustment_item(
                        kind, item_name, default_amount, description, _actor()
                    )
                    st.success(f"{label} tétel létrehozva.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"A tétel nem menthető: {exc}")

            try:
                items = read_adjustment_items(kind, active_only=False)
            except Exception as exc:
                st.error(
                    "A tételtábla nem érhető el. Futtasd a "
                    f"docs/supabase_coordinator_adjustments.sql migrációt. Részlet: {exc}"
                )
                continue
            if items.empty:
                st.caption("Még nincs beállított tétel.")
                continue
            view = items.rename(
                columns={
                    "item_name": "Tétel",
                    "default_amount_huf": "Alapösszeg",
                    "description": "Leírás",
                    "is_active": "Aktív",
                    "created_by": "Létrehozta",
                    "created_at": "Létrehozva",
                }
            )
            view.insert(0, "Típus", f"{label} tétel")
            st.dataframe(
                view[["Típus", "Tétel", "Alapösszeg", "Leírás", "Aktív", "Létrehozta", "Létrehozva"]],
                use_container_width=True,
                hide_index=True,
            )
            rows = items.to_dict("records")
            by_label = {str(row.get("item_name")): row for row in rows}
            selected = st.selectbox("Kezelendő tétel", list(by_label), key=f"manage_{kind}_item")
            selected_row = by_label[selected]
            new_active = st.toggle(
                "Aktív a koordinátori listában",
                value=bool(selected_row.get("is_active")),
                key=f"active_{kind}_{selected_row.get('id')}",
            )
            if st.button("Állapot mentése", key=f"save_{kind}_item_state"):
                try:
                    set_adjustment_item_active(
                        kind, selected_row["id"], new_active, _actor()
                    )
                    st.success("A tétel állapota mentve.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Az állapot nem menthető: {exc}")


def render_compensation_rule_settings() -> None:
    st.divider()
    st.subheader("Elszámolási alap- és minőségi díjszabályok")
    st.info(
        "Előkészítő konfiguráció: ezek a szabályok még nem módosítják sem az elszámolást, "
        "sem a TIG-et, sem a számlát."
    )
    with st.form("new_compensation_rule", clear_on_submit=True):
        rule_name = st.text_input("Feltétel / szabály neve")
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox(
            "Szabály típusa",
            list(CATEGORY_LABELS),
            format_func=CATEGORY_LABELS.get,
        )
        day_type = col2.selectbox(
            "Naptípus", list(DAY_LABELS), format_func=DAY_LABELS.get
        )
        quality_metric = col3.selectbox(
            "Minőségi mutató",
            list(METRIC_LABELS),
            format_func=METRIC_LABELS.get,
        )
        weekdays = st.multiselect(
            "Érintett napok",
            list(WEEKDAYS),
            default=list(WEEKDAYS),
            format_func=WEEKDAYS.get,
            help="Kiemelt ünnepnapok külön szabályként, saját időszakkal is felvehetők.",
        )
        tour_types = st.multiselect(
            "Túratípusok",
            list(TOUR_LABELS),
            default=list(TOUR_LABELS),
            format_func=TOUR_LABELS.get,
        )
        level_col, min_col, max_col, unit_col = st.columns(4)
        level_no = level_col.selectbox("Szint", [None, 1, 2, 3], format_func=lambda value: "-" if value is None else f"Level {value}")
        threshold_min = min_col.number_input("Alsó küszöb", value=0.0, step=0.01)
        threshold_max = max_col.number_input("Felső küszöb", value=0.0, step=0.01)
        threshold_unit = unit_col.selectbox(
            "Küszöb mértékegysége",
            ["percent", "score", "count", "none"],
            format_func={
                "percent": "%",
                "score": "Pontszám",
                "count": "Darab",
                "none": "Nincs",
            }.get,
        )
        amount1, amount2 = st.columns(2)
        company_amount = amount1.number_input("Vállalkozói díj (Ft)", value=0, step=100)
        courier_amount = amount2.number_input("Futár díj (Ft)", value=0, step=100)
        period1, period2 = st.columns(2)
        valid_from = period1.date_input("Érvényes ettől", value=date.today())
        valid_to_enabled = period2.checkbox("Záró dátum megadása")
        valid_to = period2.date_input("Érvényes eddig", value=date.today(), disabled=not valid_to_enabled)
        is_active = st.checkbox("Szabály nyitva / aktív", value=True)
        ignore_classification = st.checkbox(
            "Megbízható / sima / tréningelhető futárbesorolás figyelmen kívül hagyása",
            value=True,
            disabled=True,
        )
        separate_invoice_line = st.checkbox("Külön soron jelenjen majd meg a számlán")
        invoice_line_note = st.text_input(
            "Számlán megjelenő megjegyzés",
            placeholder="Kötelező, ha külön számlasort jelölsz.",
        )
        note = st.text_area("Belső megjegyzés", height=90)
        save_rule = st.form_submit_button(
            "Új szabály mentése", type="primary", use_container_width=True
        )

    if save_rule:
        if not rule_name.strip():
            st.error("A szabály neve kötelező.")
        elif not tour_types:
            st.error("Legalább egy túratípust válassz.")
        elif separate_invoice_line and not invoice_line_note.strip():
            st.error("A külön számlasorhoz számlamegjegyzés szükséges.")
        elif valid_to_enabled and valid_to < valid_from:
            st.error("A záró dátum nem lehet korábbi a kezdő dátumnál.")
        else:
            try:
                create_compensation_rule(
                    {
                        "rule_name": rule_name.strip(),
                        "rule_category": category,
                        "day_type": day_type,
                        "weekdays": weekdays,
                        "tour_types": tour_types,
                        "quality_metric": quality_metric,
                        "level_no": level_no if quality_metric != "none" else None,
                        "threshold_min": threshold_min if quality_metric != "none" else None,
                        "threshold_max": threshold_max if quality_metric != "none" else None,
                        "threshold_unit": threshold_unit if quality_metric != "none" else "none",
                        "company_amount_huf": int(company_amount),
                        "courier_amount_huf": int(courier_amount),
                        "valid_from": valid_from.isoformat(),
                        "valid_to": valid_to.isoformat() if valid_to_enabled else None,
                        "is_active": is_active,
                        "ignore_courier_classification": ignore_classification,
                        "show_as_separate_invoice_line": separate_invoice_line,
                        "invoice_line_note": invoice_line_note.strip(),
                        "note": note.strip(),
                    },
                    _actor(),
                )
                st.success("Az új elszámolási szabály mentve.")
                st.rerun()
            except Exception as exc:
                st.error(f"A szabály nem menthető: {exc}")

    try:
        rules = read_compensation_rules(active_only=False)
    except Exception as exc:
        st.error(
            "A szabálytábla nem érhető el. Futtasd a "
            f"docs/supabase_coordinator_adjustments.sql migrációt. Részlet: {exc}"
        )
        return
    if rules.empty:
        st.caption("Még nincs rögzített díjszabály.")
        return

    display = rules.copy()
    display["rule_category"] = display["rule_category"].map(CATEGORY_LABELS).fillna(display["rule_category"])
    display["day_type"] = display["day_type"].map(DAY_LABELS).fillna(display["day_type"])
    display["quality_metric"] = display["quality_metric"].map(METRIC_LABELS).fillna(display["quality_metric"])
    display = display.rename(
        columns={
            "rule_name": "Szabály",
            "rule_category": "Típus",
            "day_type": "Naptípus",
            "quality_metric": "Mutató",
            "level_no": "Szint",
            "company_amount_huf": "Vállalkozói díj",
            "courier_amount_huf": "Futár díj",
            "valid_from": "Kezdet",
            "valid_to": "Vége",
            "is_active": "Aktív",
            "show_as_separate_invoice_line": "Külön számlasor",
        }
    )
    st.dataframe(
        display[["Szabály", "Típus", "Naptípus", "Mutató", "Szint", "Vállalkozói díj", "Futár díj", "Kezdet", "Vége", "Aktív", "Külön számlasor"]],
        use_container_width=True,
        hide_index=True,
    )
    rows = rules.to_dict("records")
    by_label = {
        f"{row.get('rule_name')} · {row.get('valid_from')} · {str(row.get('id'))[:8]}": row
        for row in rows
    }
    selected_label = st.selectbox("Kezelendő szabály", list(by_label))
    selected_rule = by_label[selected_label]
    active = st.toggle(
        "Szabály aktív",
        value=bool(selected_rule.get("is_active")),
        key=f"comp_rule_active_{selected_rule.get('id')}",
    )
    if st.button("Szabály állapotának mentése"):
        try:
            set_compensation_rule_active(selected_rule["id"], active, _actor())
            st.success("A szabály állapota mentve.")
            st.rerun()
        except Exception as exc:
            st.error(f"A szabály állapota nem menthető: {exc}")


def show_compensation_configuration_page() -> None:
    user = st.session_state.get("user", {})
    if str(user.get("role") or "").strip().lower() != "admin":
        st.error("A konfigurációt csak admin kezelheti.")
        return
    st.title("Elszámolási konfiguráció")
    render_adjustment_item_settings()
    render_compensation_rule_settings()
