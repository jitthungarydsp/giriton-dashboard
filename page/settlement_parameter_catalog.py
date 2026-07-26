from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from resources.settlement_parameters import (
    delete_periodic_bonus,
    delete_rate_parameter,
    parameter_status,
    read_periodic_bonuses,
    read_rate_parameters,
    save_periodic_bonus,
    save_rate_parameter,
)


RATE_KIND_LABELS = {
    "base_rate": "Alapdíj",
    "delay_bonus": "Delay bónusz",
    "compliance_bonus": "Compliance bónusz",
    "customer_rating_bonus": "Ügyfélértékelési bónusz",
    "other": "Egyéb díjparaméter",
}
DAY_TYPE_LABELS = {
    "any": "Bármely nap",
    "highlighted": "Kiemelt nap",
    "not_highlighted": "Nem kiemelt nap",
}
ROUTE_TYPE_LABELS = {
    "any": "Bármely túra",
    "express": "Expressz",
    "normal": "Normál / City",
    "regional": "Regionális",
}
CALCULATION_UNIT_LABELS = {
    "fixed": "Fix összeg",
    "per_route": "Ft / túra",
    "per_order": "Ft / cím",
    "per_hour": "Ft / óra",
    "percent": "%",
}
CONDITION_LABELS = {
    "none": "Nincs külön feltétel",
    "orders_per_route": "Címek száma túránként",
    "routes_per_day": "Túrák száma naponta",
    "routes_in_period": "Túrák száma az időszakban",
    "orders_in_period": "Címek száma az időszakban",
}
WEEKDAY_LABELS = {
    1: "Hétfő",
    2: "Kedd",
    3: "Szerda",
    4: "Csütörtök",
    5: "Péntek",
    6: "Szombat",
    7: "Vasárnap",
}
GROUP_LABELS = {
    "rate": "Díj- és teljesítményparaméter",
    "periodic": "Időszakos bónusz",
}


def _actor() -> str:
    user = st.session_state.get("user", {})
    return str(user.get("username") or "unknown").strip()


def _clean(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _text(value: Any) -> str:
    return str(_clean(value, "") or "").strip()


def _number(value: Any, default: float = 0.0) -> float:
    value = _clean(value, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    return int(round(_number(value, default)))


def _date(value: Any, default: date | None = None) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value))
    except ValueError:
        return default or date.today()


def _list(value: Any) -> list[Any]:
    value = _clean(value, [])
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _choice_index(options: list[Any], value: Any) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _format_money(value: Any) -> str:
    return f"{_integer(value):,} Ft".replace(",", " ")


def _format_range(
    minimum: Any,
    maximum: Any,
    suffix: str = "",
) -> str:
    minimum = _clean(minimum)
    maximum = _clean(maximum)
    if minimum is None and maximum is None:
        return ""
    if minimum is None:
        return f"≤ {maximum:g}{suffix}"
    if maximum is None:
        return f"≥ {minimum:g}{suffix}"
    return f"{minimum:g}–{maximum:g}{suffix}"


def _rate_condition(row: dict[str, Any]) -> str:
    parts: list[str] = []
    threshold = _format_range(
        _clean(row.get("threshold_min")),
        _clean(row.get("threshold_max")),
        "%",
    )
    if threshold:
        parts.append(threshold)
    duration = _format_range(
        _clean(row.get("planned_duration_min_hours")),
        _clean(row.get("planned_duration_max_hours")),
        " óra",
    )
    if duration:
        parts.append(duration)
    warehouse = _text(row.get("warehouse_code"))
    if warehouse:
        parts.append(warehouse)
    return " · ".join(parts) or "Nincs külön feltétel"


def _periodic_condition(row: dict[str, Any]) -> str:
    metric = _text(row.get("condition_metric")) or "none"
    parts = [CONDITION_LABELS.get(metric, metric)]
    value_range = _format_range(
        _clean(row.get("condition_min")),
        _clean(row.get("condition_max")),
    )
    if value_range:
        parts.append(value_range)
    warehouse = _text(row.get("warehouse_code"))
    if warehouse:
        parts.append(warehouse)
    return " · ".join(parts)


def _catalog_records(
    rates: pd.DataFrame,
    bonuses: pd.DataFrame,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rates.to_dict("records"):
        status = parameter_status(
            row.get("valid_from"),
            row.get("valid_to"),
            bool(row.get("is_active", True)),
        )
        records.append(
            {
                "_source": "rate",
                "_id": str(row.get("id") or ""),
                "_raw": row,
                "Kategória": RATE_KIND_LABELS.get(
                    _text(row.get("parameter_kind")),
                    _text(row.get("parameter_kind")),
                ),
                "Level": _text(row.get("level_code")),
                "Megnevezés": _text(row.get("parameter_name")),
                "JITT": _format_money(row.get("company_amount_huf")),
                "Futár": _format_money(row.get("courier_amount_huf")),
                "Naptípus": DAY_TYPE_LABELS.get(
                    _text(row.get("day_type")),
                    _text(row.get("day_type")),
                ),
                "Túratípus": ROUTE_TYPE_LABELS.get(
                    _text(row.get("route_type")),
                    _text(row.get("route_type")),
                ),
                "Feltétel": _rate_condition(row),
                "Érvényes ettől": _text(row.get("valid_from")),
                "Érvényes eddig": _text(row.get("valid_to")) or "Folyamatos",
                "Státusz": status,
            }
        )

    for row in bonuses.to_dict("records"):
        status = parameter_status(
            row.get("valid_from"),
            row.get("valid_to"),
            bool(row.get("is_active", True)),
        )
        records.append(
            {
                "_source": "periodic",
                "_id": str(row.get("id") or ""),
                "_raw": row,
                "Kategória": "Időszakos bónusz",
                "Level": "",
                "Megnevezés": _text(row.get("bonus_name")),
                "JITT": _format_money(row.get("company_amount_huf")),
                "Futár": _format_money(row.get("courier_amount_huf")),
                "Naptípus": DAY_TYPE_LABELS.get(
                    _text(row.get("day_type")),
                    _text(row.get("day_type")),
                ),
                "Túratípus": ROUTE_TYPE_LABELS.get(
                    _text(row.get("route_type")),
                    _text(row.get("route_type")),
                ),
                "Feltétel": _periodic_condition(row),
                "Érvényes ettől": _text(row.get("valid_from")),
                "Érvényes eddig": _text(row.get("valid_to")) or "Folyamatos",
                "Státusz": status,
            }
        )
    return records


def _render_rate_form(
    client: Any,
    edit_row: dict[str, Any] | None,
) -> None:
    row = edit_row or {}
    edit_id = _text(row.get("id")) or None
    form_key = f"parameter_rate_form_{edit_id or 'new'}"
    st.markdown(
        "#### Díjparaméter szerkesztése"
        if edit_id
        else "#### Új díj- vagy teljesítményparaméter"
    )

    with st.form(form_key):
        left, right = st.columns(2)
        with left:
            name = st.text_input(
                "Megnevezés",
                value=_text(row.get("parameter_name")),
                placeholder="Például: Delay bónusz – Szint 1",
            )
            rate_options = list(RATE_KIND_LABELS)
            parameter_kind = st.selectbox(
                "Paraméter típusa",
                rate_options,
                index=_choice_index(
                    rate_options,
                    _text(row.get("parameter_kind")) or "base_rate",
                ),
                format_func=RATE_KIND_LABELS.get,
            )
            level_code = st.text_input(
                "Level / szint",
                value=_text(row.get("level_code")),
                placeholder="Például: Szint 1",
            )
            amount1, amount2 = st.columns(2)
            company_amount = amount1.number_input(
                "JITT összege (Ft)",
                min_value=0,
                value=_integer(row.get("company_amount_huf")),
                step=100,
            )
            courier_amount = amount2.number_input(
                "Futár összege (Ft)",
                min_value=0,
                value=_integer(row.get("courier_amount_huf")),
                step=100,
            )
            unit_options = list(CALCULATION_UNIT_LABELS)
            calculation_unit = st.selectbox(
                "Elszámolási egység",
                unit_options,
                index=_choice_index(
                    unit_options,
                    _text(row.get("calculation_unit")) or "per_route",
                ),
                format_func=CALCULATION_UNIT_LABELS.get,
            )

        with right:
            day_options = list(DAY_TYPE_LABELS)
            day_type = st.selectbox(
                "Naptípus",
                day_options,
                index=_choice_index(
                    day_options,
                    _text(row.get("day_type")) or "any",
                ),
                format_func=DAY_TYPE_LABELS.get,
            )
            route_options = list(ROUTE_TYPE_LABELS)
            route_type = st.selectbox(
                "Túratípus",
                route_options,
                index=_choice_index(
                    route_options,
                    _text(row.get("route_type")) or "any",
                ),
                format_func=ROUTE_TYPE_LABELS.get,
            )
            weekdays = st.multiselect(
                "Érintett napok",
                list(WEEKDAY_LABELS),
                default=[
                    int(value)
                    for value in _list(row.get("weekdays"))
                    if str(value).isdigit()
                ],
                format_func=WEEKDAY_LABELS.get,
                help=(
                    "Üresen hagyva a naptípus minden napjára érvényes. "
                    "Nincs ünnep előtti vagy utáni automatikus szabály."
                ),
            )
            warehouse_code = st.text_input(
                "Raktár",
                value=_text(row.get("warehouse_code")),
                placeholder="Üres = minden raktár",
            )
            priority = st.number_input(
                "Prioritás",
                value=_integer(row.get("priority"), 100),
                step=1,
                help="Ütköző szabályoknál a kisebb szám az erősebb.",
            )

        st.markdown("##### Mutatósáv (opcionális)")
        threshold1, threshold2, threshold3, threshold4 = st.columns(4)
        threshold_min_enabled = threshold1.checkbox(
            "Van alsó határ",
            value=_clean(row.get("threshold_min")) is not None,
        )
        threshold_min = threshold1.number_input(
            "Mutató alsó határa",
            value=_number(row.get("threshold_min")),
            step=0.01,
        )
        threshold_min_inclusive = threshold2.checkbox(
            "Alsó határ beleértve",
            value=bool(row.get("threshold_min_inclusive", True)),
        )
        threshold_max_enabled = threshold3.checkbox(
            "Van felső határ",
            value=_clean(row.get("threshold_max")) is not None,
        )
        threshold_max = threshold3.number_input(
            "Mutató felső határa",
            value=_number(row.get("threshold_max")),
            step=0.01,
        )
        threshold_max_inclusive = threshold4.checkbox(
            "Felső határ beleértve",
            value=bool(row.get("threshold_max_inclusive", True)),
        )

        st.markdown("##### Tervezett túrahossz (opcionális)")
        duration1, duration2 = st.columns(2)
        duration_min_enabled = duration1.checkbox(
            "Van minimum túrahossz",
            value=_clean(row.get("planned_duration_min_hours")) is not None,
        )
        duration_min = duration1.number_input(
            "Minimum túrahossz (óra)",
            min_value=0.0,
            value=_number(row.get("planned_duration_min_hours")),
            step=0.5,
        )
        duration_max_enabled = duration2.checkbox(
            "Van maximum túrahossz",
            value=_clean(row.get("planned_duration_max_hours")) is not None,
        )
        duration_max = duration2.number_input(
            "Maximum túrahossz (óra)",
            min_value=0.0,
            value=_number(row.get("planned_duration_max_hours")),
            step=0.5,
        )

        period1, period2 = st.columns(2)
        valid_from = period1.date_input(
            "Érvényes ettől",
            value=_date(row.get("valid_from")),
        )
        has_end = period2.checkbox(
            "Van záródátum",
            value=_clean(row.get("valid_to")) is not None,
        )
        valid_to = period2.date_input(
            "Érvényes eddig",
            value=_date(row.get("valid_to")),
            help="Csak akkor kerül mentésre, ha a „Van záródátum” be van jelölve.",
        )
        is_active = st.checkbox(
            "Engedélyezett szabály",
            value=bool(row.get("is_active", True)),
        )
        note = st.text_area(
            "Megjegyzés",
            value=_text(row.get("note")),
            height=80,
        )
        submitted = st.form_submit_button(
            "Módosítások mentése" if edit_id else "Paraméter mentése",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            save_rate_parameter(
                client,
                {
                    "parameter_name": name,
                    "parameter_kind": parameter_kind,
                    "level_code": level_code,
                    "day_type": day_type,
                    "weekdays": weekdays,
                    "route_type": route_type,
                    "warehouse_code": warehouse_code,
                    "threshold_min": (
                        threshold_min
                        if threshold_min_enabled
                        else None
                    ),
                    "threshold_max": (
                        threshold_max
                        if threshold_max_enabled
                        else None
                    ),
                    "threshold_min_inclusive": threshold_min_inclusive,
                    "threshold_max_inclusive": threshold_max_inclusive,
                    "planned_duration_min_hours": (
                        duration_min
                        if duration_min_enabled
                        else None
                    ),
                    "planned_duration_max_hours": (
                        duration_max
                        if duration_max_enabled
                        else None
                    ),
                    "company_amount_huf": company_amount,
                    "courier_amount_huf": courier_amount,
                    "calculation_unit": calculation_unit,
                    "valid_from": valid_from,
                    "valid_to": valid_to if has_end else None,
                    "priority": priority,
                    "is_active": is_active,
                    "note": note,
                },
                _actor(),
                edit_id,
            )
            st.session_state.pop("parameter_catalog_edit", None)
            st.success("A díjparaméter mentve.")
            st.rerun()
        except Exception as exc:
            st.error(f"A díjparaméter nem menthető: {exc}")


def _render_periodic_form(
    client: Any,
    edit_row: dict[str, Any] | None,
) -> None:
    row = edit_row or {}
    edit_id = _text(row.get("id")) or None
    form_key = f"parameter_periodic_form_{edit_id or 'new'}"
    st.markdown(
        "#### Időszakos bónusz szerkesztése"
        if edit_id
        else "#### Új időszakos bónusz"
    )

    with st.form(form_key):
        left, right = st.columns(2)
        with left:
            name = st.text_input(
                "Megnevezés",
                value=_text(row.get("bonus_name")),
                placeholder="Például: Júniusi 12 címes túrabónusz",
            )
            amount1, amount2 = st.columns(2)
            company_amount = amount1.number_input(
                "JITT összege (Ft)",
                min_value=0,
                value=_integer(row.get("company_amount_huf")),
                step=100,
            )
            courier_amount = amount2.number_input(
                "Futár összege (Ft)",
                min_value=0,
                value=_integer(row.get("courier_amount_huf")),
                step=100,
            )
            unit_options = list(CALCULATION_UNIT_LABELS)
            calculation_unit = st.selectbox(
                "Elszámolási egység",
                unit_options,
                index=_choice_index(
                    unit_options,
                    _text(row.get("calculation_unit")) or "per_route",
                ),
                format_func=CALCULATION_UNIT_LABELS.get,
            )
            condition_options = list(CONDITION_LABELS)
            condition_metric = st.selectbox(
                "Bónusz feltétele",
                condition_options,
                index=_choice_index(
                    condition_options,
                    _text(row.get("condition_metric")) or "none",
                ),
                format_func=CONDITION_LABELS.get,
            )
            condition1, condition2 = st.columns(2)
            condition_min = condition1.number_input(
                "Minimum érték",
                min_value=0.0,
                value=_number(row.get("condition_min")),
                step=1.0,
                help="A „Nincs külön feltétel” opciónál nem kerül mentésre.",
            )
            condition_max_enabled = condition2.checkbox(
                "Maximum feltétel",
                value=_clean(row.get("condition_max")) is not None,
            )
            condition_max = condition2.number_input(
                "Maximum érték",
                min_value=0.0,
                value=_number(row.get("condition_max")),
                step=1.0,
                help="Csak a „Maximum feltétel” jelöléssel kerül mentésre.",
            )

        with right:
            day_options = list(DAY_TYPE_LABELS)
            day_type = st.selectbox(
                "Naptípus",
                day_options,
                index=_choice_index(
                    day_options,
                    _text(row.get("day_type")) or "any",
                ),
                format_func=DAY_TYPE_LABELS.get,
            )
            route_options = list(ROUTE_TYPE_LABELS)
            route_type = st.selectbox(
                "Túratípus",
                route_options,
                index=_choice_index(
                    route_options,
                    _text(row.get("route_type")) or "any",
                ),
                format_func=ROUTE_TYPE_LABELS.get,
            )
            weekdays = st.multiselect(
                "Érintett napok",
                list(WEEKDAY_LABELS),
                default=[
                    int(value)
                    for value in _list(row.get("weekdays"))
                    if str(value).isdigit()
                ],
                format_func=WEEKDAY_LABELS.get,
                help="Üresen hagyva a naptípus minden napjára érvényes.",
            )
            warehouse_code = st.text_input(
                "Raktár",
                value=_text(row.get("warehouse_code")),
                placeholder="Üres = minden raktár",
            )
            courier_ids = st.text_input(
                "Futárazonosítók",
                value=", ".join(str(value) for value in _list(row.get("courier_ids"))),
                placeholder="Üres = minden futár; több ID vesszővel",
            )
            company_names = st.text_input(
                "Vállalkozások",
                value=", ".join(str(value) for value in _list(row.get("company_names"))),
                placeholder="Üres = minden vállalkozás",
            )

        cap1, cap2 = st.columns(2)
        maximum_enabled = cap1.checkbox(
            "Jóváírások számának korlátozása",
            value=_clean(row.get("maximum_awards_per_courier")) is not None,
        )
        maximum_awards = cap1.number_input(
            "Maximum jóváírás futáronként",
            min_value=0,
            value=_integer(row.get("maximum_awards_per_courier")),
            step=1,
            help="Csak a korlátozás bekapcsolásakor kerül mentésre.",
        )
        priority = cap2.number_input(
            "Prioritás",
            value=_integer(row.get("priority"), 100),
            step=1,
            help="Ütköző szabályoknál a kisebb szám az erősebb.",
        )

        period1, period2 = st.columns(2)
        valid_from = period1.date_input(
            "Érvényes ettől",
            value=_date(row.get("valid_from")),
        )
        has_end = period2.checkbox(
            "Van záródátum",
            value=_clean(row.get("valid_to")) is not None,
        )
        valid_to = period2.date_input(
            "Érvényes eddig",
            value=_date(row.get("valid_to")),
            help="Csak akkor kerül mentésre, ha a „Van záródátum” be van jelölve.",
        )

        invoice1, invoice2 = st.columns(2)
        separate_invoice_line = invoice1.checkbox(
            "Külön soron jelenjen meg a számlán",
            value=bool(row.get("show_as_separate_invoice_line", False)),
        )
        invoice_line_note = invoice2.text_input(
            "Számlasor megjegyzése",
            value=_text(row.get("invoice_line_note")),
            help="Kötelező, ha a külön számlasor be van jelölve.",
        )
        is_active = st.checkbox(
            "Engedélyezett bónusz",
            value=bool(row.get("is_active", True)),
        )
        note = st.text_area(
            "Megjegyzés",
            value=_text(row.get("note")),
            height=80,
        )
        submitted = st.form_submit_button(
            "Módosítások mentése" if edit_id else "Időszakos bónusz mentése",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            save_periodic_bonus(
                client,
                {
                    "bonus_name": name,
                    "day_type": day_type,
                    "weekdays": weekdays,
                    "route_type": route_type,
                    "warehouse_code": warehouse_code,
                    "courier_ids": courier_ids,
                    "company_names": company_names,
                    "condition_metric": condition_metric,
                    "condition_min": (
                        condition_min if condition_metric != "none" else None
                    ),
                    "condition_max": (
                        condition_max
                        if condition_metric != "none" and condition_max_enabled
                        else None
                    ),
                    "company_amount_huf": company_amount,
                    "courier_amount_huf": courier_amount,
                    "calculation_unit": calculation_unit,
                    "maximum_awards_per_courier": (
                        maximum_awards if maximum_enabled else None
                    ),
                    "valid_from": valid_from,
                    "valid_to": valid_to if has_end else None,
                    "priority": priority,
                    "is_active": is_active,
                    "show_as_separate_invoice_line": separate_invoice_line,
                    "invoice_line_note": invoice_line_note,
                    "note": note,
                },
                _actor(),
                edit_id,
            )
            st.session_state.pop("parameter_catalog_edit", None)
            st.success("Az időszakos bónusz mentve.")
            st.rerun()
        except Exception as exc:
            st.error(f"Az időszakos bónusz nem menthető: {exc}")


def render_parameter_catalog(client: Any) -> None:
    st.subheader("Paraméterértékek katalógusa")
    st.caption(
        "JITT- és futárdíjak, Delay/Compliance szabályok és külön kezelt "
        "időszakos bónuszok teljes érvényességi idővel."
    )

    try:
        rates = read_rate_parameters(client)
        bonuses = read_periodic_bonuses(client)
    except Exception as exc:
        st.error(
            "A paramétertáblák még nem érhetők el. Futtasd a "
            "`docs/supabase_jitt_parameter_catalog.sql` migrációt. "
            f"Részlet: {exc}"
        )
        return

    records = _catalog_records(rates, bonuses)
    filter1, filter2 = st.columns(2)
    categories = sorted({row["Kategória"] for row in records})
    category_filter = filter1.selectbox(
        "Kategória",
        ["Összes", *categories],
        key="ui_parameter_category_filter",
    )
    status_filter = filter2.selectbox(
        "Státusz",
        ["Összes", "Aktív", "Jövőbeni", "Lejárt", "Inaktív"],
        key="ui_parameter_status_filter",
    )

    filtered = [
        row
        for row in records
        if (
            category_filter == "Összes"
            or row["Kategória"] == category_filter
        )
        and (
            status_filter == "Összes"
            or row["Státusz"] == status_filter
        )
    ]
    display_columns = [
        "Kategória",
        "Level",
        "Megnevezés",
        "JITT",
        "Futár",
        "Naptípus",
        "Túratípus",
        "Feltétel",
        "Érvényes ettől",
        "Érvényes eddig",
        "Státusz",
    ]
    if filtered:
        st.dataframe(
            pd.DataFrame(filtered)[display_columns],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("A szűrésnek megfelelő paraméter még nincs rögzítve.")

    selected_record: dict[str, Any] | None = None
    if filtered:
        selectable = {
            (
                f"{row['Megnevezés']} · {row['Kategória']} · "
                f"{row['Érvényes ettől']} · {row['_id'][:8]}"
            ): row
            for row in filtered
        }
        selected_label = st.selectbox(
            "Kezelendő paraméter",
            list(selectable),
            key="ui_parameter_selected",
        )
        selected_record = selectable[selected_label]

    edit_col, delete_col = st.columns(2)
    if edit_col.button(
        "Kiválasztott szerkesztése",
        use_container_width=True,
        disabled=selected_record is None,
        key="ui_parameter_edit",
    ):
        st.session_state["parameter_catalog_edit"] = {
            "source": selected_record["_source"],
            "id": selected_record["_id"],
        }
        st.rerun()

    confirm_delete = delete_col.checkbox(
        "Törlés megerősítése",
        key="ui_parameter_delete_confirm",
        disabled=selected_record is None,
    )
    if delete_col.button(
        "Kiválasztott törlése",
        use_container_width=True,
        disabled=selected_record is None,
        key="ui_parameter_delete",
    ):
        if not confirm_delete:
            st.warning("A törléshez jelöld be a megerősítést.")
        else:
            try:
                if selected_record["_source"] == "rate":
                    delete_rate_parameter(
                        client,
                        selected_record["_id"],
                        _actor(),
                    )
                else:
                    delete_periodic_bonus(
                        client,
                        selected_record["_id"],
                        _actor(),
                    )
                current_edit = st.session_state.get("parameter_catalog_edit", {})
                if current_edit.get("id") == selected_record["_id"]:
                    st.session_state.pop("parameter_catalog_edit", None)
                st.success("A kiválasztott paraméter törölve.")
                st.rerun()
            except Exception as exc:
                st.error(f"A paraméter nem törölhető: {exc}")

    st.divider()
    edit_state = st.session_state.get("parameter_catalog_edit") or {}
    edit_source = edit_state.get("source")
    edit_id = edit_state.get("id")
    lookup = {
        (record["_source"], record["_id"]): record["_raw"]
        for record in records
    }
    edit_row = lookup.get((edit_source, edit_id))
    if edit_id and edit_row is None:
        st.session_state.pop("parameter_catalog_edit", None)
        edit_source = None

    if edit_source:
        header1, header2 = st.columns([4, 1])
        header1.info(
            "Szerkesztési mód: a mentés a kiválasztott rekordot frissíti."
        )
        if header2.button(
            "Szerkesztés megszakítása",
            use_container_width=True,
        ):
            st.session_state.pop("parameter_catalog_edit", None)
            st.rerun()
        parameter_group = edit_source
    else:
        parameter_group = st.selectbox(
            "Új paraméter csoportja",
            list(GROUP_LABELS),
            format_func=GROUP_LABELS.get,
            key="ui_parameter_group",
        )

    if parameter_group == "rate":
        _render_rate_form(client, edit_row if edit_source == "rate" else None)
    else:
        _render_periodic_form(
            client,
            edit_row if edit_source == "periodic" else None,
        )
