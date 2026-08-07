from __future__ import annotations

from datetime import date
import json
from typing import Any, Callable

import pandas as pd
import streamlit as st

from resources.settlement_parameters import (
    BASE_RATE_TABLE,
    COMPLIANCE_TABLE,
    CUSTOMER_RATING_TABLE,
    DAY_TABLE,
    DELAY_TABLE,
    EFO_ASSIGNMENT_TABLE,
    LIFE_INSURANCE_TABLE,
    LOYALTY_BONUS_TABLE,
    PERIODIC_FEE_TABLE,
    RESERVE_INSURANCE_TABLE,
    parameter_status,
    read_items,
    recalculate_excel_base_rates,
    save_item,
    soft_delete_item,
    validate_base_rate,
    validate_customer_rating_rule,
    validate_day_definition,
    validate_efo_assignment,
    validate_performance_rule,
    validate_periodic_fee,
    validate_life_insurance_rule,
    validate_loyalty_bonus_rule,
    validate_reserve_insurance_rule,
)


DAY_LABELS = {"highlighted": "Kiemelt nap", "normal": "Normál nap", "any": "Bármely nap"}
ROUTE_LABELS = {"express": "Expressz", "normal": "Normál", "regional": "Regionális", "any": "Bármely túra"}
UNIT_LABELS = {"fixed": "Fix összeg", "per_route": "Ft / túra", "per_order": "Ft / cím", "per_hour": "Ft / óra"}
CALCULATION_MODE_LABELS = {"excel": "Közös / Excel", "api": "API előnyben", "custom": "Egyéni"}
CONDITION_LABELS = {"none": "Nincs feltétel", "orders_per_route": "Címek száma túránként", "routes_per_day": "Túrák száma naponta", "routes_in_period": "Túrák száma az időszakban", "orders_in_period": "Címek száma az időszakban"}
WEEKDAY_LABELS = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
CUSTOMER_RATING_DEFAULT_RULES = [
    {
        "level_code": "Customer rating normal 4.90-5.00",
        "route_type": "normal",
        "rating_min": 4.90,
        "rating_max": 5.00,
        "courier_amount_huf": 500,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 1,
        "is_active": True,
        "note": "Customer rating bonus: 4.90-5.00 average gives 500 HUF per route",
    },
    {
        "level_code": "Customer rating normal 4.80-4.89",
        "route_type": "normal",
        "rating_min": 4.80,
        "rating_max": 4.89,
        "courier_amount_huf": 300,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 2,
        "is_active": True,
        "note": "Customer rating bonus: 4.80-4.89 average gives 300 HUF per route",
    },
    {
        "level_code": "Customer rating normal 4.70-4.79",
        "route_type": "normal",
        "rating_min": 4.70,
        "rating_max": 4.79,
        "courier_amount_huf": 150,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 3,
        "is_active": True,
        "note": "Customer rating bonus: 4.70-4.79 average gives 150 HUF per route",
    },
    {
        "level_code": "Customer rating express 4.90-5.00",
        "route_type": "express",
        "rating_min": 4.90,
        "rating_max": 5.00,
        "courier_amount_huf": 500,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 1,
        "is_active": True,
        "note": "Customer rating bonus: 4.90-5.00 average gives 500 HUF per express route",
    },
    {
        "level_code": "Customer rating express 4.80-4.89",
        "route_type": "express",
        "rating_min": 4.80,
        "rating_max": 4.89,
        "courier_amount_huf": 300,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 2,
        "is_active": True,
        "note": "Customer rating bonus: 4.80-4.89 average gives 300 HUF per express route",
    },
    {
        "level_code": "Customer rating express 4.70-4.79",
        "route_type": "express",
        "rating_min": 4.70,
        "rating_max": 4.79,
        "courier_amount_huf": 150,
        "valid_from": date(2026, 5, 1),
        "valid_to": None,
        "priority": 3,
        "is_active": True,
        "note": "Customer rating bonus: 4.70-4.79 average gives 150 HUF per express route",
    },
]


def _actor() -> str:
    return str(st.session_state.get("user", {}).get("username") or "unknown").strip()


def _mark_parameters_changed(client: Any) -> None:
    st.session_state["settlement_parameter_revision"] = int(
        st.session_state.get("settlement_parameter_revision", 0)
    ) + 1
    try:
        recalculate_excel_base_rates(
            client,
        )
    except BaseException:
        # The parameter is saved even if the SQL migration is not deployed yet.
        pass


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
    try:
        return float(_clean(value, default))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    return int(round(_number(value, default)))


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value))
    except ValueError:
        return date.today()


def _index(options: list[str], value: Any) -> int:
    try:
        return options.index(_text(value))
    except ValueError:
        return 0


def _money(value: Any) -> str:
    return f"{_int(value):,} Ft".replace(",", " ")


def _excel_source_headers(client: Any) -> list[str]:
    """Read the real JITT Excel headers from already imported rows."""
    try:
        query = client.schema("settlement").table("jit_row").select("normalized_data").limit(1000)
        session_id = _text(st.session_state.get("settlement_import_session_id"))
        if session_id:
            query = query.eq("session_id", session_id)
        rows = query.execute().data or []
    except Exception:
        return []
    headers: set[str] = set()
    for row in rows:
        normalized_data = row.get("normalized_data") or {}
        if isinstance(normalized_data, str):
            try:
                normalized_data = json.loads(normalized_data)
            except json.JSONDecodeError:
                normalized_data = {}
        if isinstance(normalized_data, dict):
            headers.update(str(header).strip() for header in normalized_data if str(header).strip())
    return sorted(headers, key=str.casefold)


def _range(minimum: Any, maximum: Any, suffix: str = "") -> str:
    minimum, maximum = _clean(minimum), _clean(maximum)
    if minimum is None and maximum is None:
        return "-"
    if minimum is None:
        return f"≤ {float(maximum):g}{suffix}"
    if maximum is None:
        return f"≥ {float(minimum):g}{suffix}"
    return f"{float(minimum):g}–{float(maximum):g}{suffix}"


def _editor_row(data: pd.DataFrame, key: str, label_field: str) -> dict[str, Any] | None:
    rows = data.to_dict("records")
    choices = {"Új tétel": None}
    for row in rows:
        label = f"{_text(row.get(label_field))} · {_text(row.get('valid_from'))} · {_text(row.get('id'))[:8]}"
        choices[label] = row
    selected = st.selectbox("Szerkesztendő tétel", list(choices), key=f"{key}_select")
    return choices[selected]


def _delete_control(client: Any, table_name: str, row: dict[str, Any] | None, key: str) -> None:
    if not row:
        return
    confirmed = st.checkbox("Törlés megerősítése", key=f"{key}_confirm")
    if st.button("Kiválasztott törlése", key=f"{key}_delete"):
        if not confirmed:
            st.warning("A törléshez jelöld be a megerősítést.")
            return
        try:
            soft_delete_item(client, table_name, _text(row.get("id")), _actor())
            _mark_parameters_changed(client)
            st.success("A tétel törölve. A Paraméterértékek ablak nyitva marad.")
        except Exception as exc:
            st.error(f"A tétel nem törölhető: {exc}")


def _common_period(row: dict[str, Any], key: str) -> tuple[date, date, bool, int, bool, str]:
    row_key = f"{key}_{_text(row.get('id')) or 'new'}"
    col1, col2, col3 = st.columns(3)
    valid_from = col1.date_input("Érvényes ettől", value=_date(row.get("valid_from")), key=f"{row_key}_from")
    has_end = col2.checkbox("Van záródátum", value=_clean(row.get("valid_to")) is not None, key=f"{row_key}_has_end")
    valid_to = col2.date_input("Érvényes eddig", value=_date(row.get("valid_to")), key=f"{row_key}_to")
    if valid_to < date.today():
        has_end = True
    priority = col3.number_input("Prioritás", value=_int(row.get("priority"), 100), step=1, key=f"{row_key}_priority")
    is_active = st.checkbox("Engedélyezett", value=bool(row.get("is_active", True)), key=f"{row_key}_active")
    note = st.text_area("Megjegyzés", value=_text(row.get("note")), key=f"{row_key}_note", height=70)
    return valid_from, valid_to, has_end, priority, is_active, note


def _show_days(client: Any) -> None:
    st.caption("Itt állítható be, hogy az egyes időszakokban mely hétköznapok számítanak kiemeltnek vagy normálnak.")
    data = read_items(client, DAY_TABLE)
    table_slot = st.empty()

    def render_day_table(table_data: pd.DataFrame) -> None:
        if table_data.empty:
            table_slot.info("Még nincs mentett napbesorolás.")
            return
        view = table_data.copy()
        view["Naptípus"] = view["day_type"].map(DAY_LABELS)
        view["Napok"] = view["weekdays"].apply(lambda values: ", ".join(WEEKDAY_LABELS.get(int(value), str(value)) for value in (values or [])))
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        view["Státusz"] = [parameter_status(a, b, c) for a, b, c in zip(view["valid_from"], view["valid_to"], view["is_active"])]
        table_slot.dataframe(view[["Naptípus", "Napok", "valid_from", "Vége", "Státusz", "note"]], use_container_width=True, hide_index=True)

    render_day_table(data)
    row = _editor_row(data, "day", "day_type")
    form_key = f"day_form_{_text((row or {}).get('id')) or 'new'}"
    with st.form(form_key):
        types = ["highlighted", "normal"]
        day_type = st.selectbox("Naptípus", types, index=_index(types, (row or {}).get("day_type")), format_func=DAY_LABELS.get)
        weekdays = st.multiselect("Érintett napok", list(WEEKDAY_LABELS), default=[int(value) for value in ((row or {}).get("weekdays") or [])], format_func=WEEKDAY_LABELS.get, help="Egy bejegyzéshez több nap is kijelölhető.")
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "day")
        saved = st.form_submit_button("Módosítás mentése" if row else "Napbesorolás mentése", type="primary")
    if saved:
        try:
            save_item(client, DAY_TABLE, validate_day_definition({"day_type": day_type, "weekdays": weekdays, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            _mark_parameters_changed(client)
            render_day_table(read_items(client, DAY_TABLE))
            st.success("A napbesorolás mentve. A Paraméterértékek ablak nyitva marad.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, DAY_TABLE, row, "day")


def _show_base_rates(client: Any) -> None:
    st.caption("Az itt megadott vállalkozói és futár-alapdíj felülírja az Excel Fixed Rate értékét. Ugyanez lesz a központi szabály az API-s számításhoz is.")
    data = read_items(client, BASE_RATE_TABLE)
    table_slot = st.empty()

    def render_base_rate_table(table_data: pd.DataFrame) -> None:
        if table_data.empty:
            table_slot.info("Még nincs mentett alapdíj-szabály.")
            return
        view = table_data.copy(); view["Naptípus"] = view["day_type"].map(DAY_LABELS); view["Túratípus"] = view["route_type"].map(ROUTE_LABELS); view["JITT"] = view["company_amount_huf"].map(_money); view["Futár"] = view["courier_amount_huf"].map(_money); view["Vége"] = view["valid_to"].fillna("Folyamatos")
        table_slot.dataframe(view[["Naptípus", "Túratípus", "warehouse_code", "JITT", "Futár", "calculation_unit", "valid_from", "Vége", "note"]], use_container_width=True, hide_index=True)

    render_base_rate_table(data)
    row = _editor_row(data, "base", "route_type")
    form_key = f"base_form_{_text((row or {}).get('id')) or 'new'}"
    with st.form(form_key):
        left, right = st.columns(2)
        days, routes, units = list(DAY_LABELS), list(ROUTE_LABELS), list(UNIT_LABELS)
        day_type = left.selectbox("Naptípus", days, index=_index(days, (row or {}).get("day_type")), format_func=DAY_LABELS.get)
        route_type = right.selectbox("Túratípus", routes, index=_index(routes, (row or {}).get("route_type")), format_func=ROUTE_LABELS.get)
        warehouse = left.text_input("Raktár", value=_text((row or {}).get("warehouse_code")), placeholder="Üres = minden raktár")
        unit = right.selectbox("Elszámolási egység", units, index=_index(units, (row or {}).get("calculation_unit") or "per_route"), format_func=UNIT_LABELS.get)
        money1, money2 = st.columns(2); company = money1.number_input("Vállalkozói Fixed Rate (Ft)", min_value=0, value=_int((row or {}).get("company_amount_huf")), step=100); courier = money2.number_input("Futár Fixed Rate (Ft)", min_value=0, value=_int((row or {}).get("courier_amount_huf")), step=100)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "base")
        saved = st.form_submit_button("Módosítás mentése" if row else "Alapdíj mentése", type="primary")
    if saved:
        try:
            save_item(client, BASE_RATE_TABLE, validate_base_rate({"day_type": day_type, "route_type": route_type, "warehouse_code": warehouse, "company_amount_huf": company, "courier_amount_huf": courier, "calculation_unit": unit, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            _mark_parameters_changed(client)
            render_base_rate_table(read_items(client, BASE_RATE_TABLE))
            st.success("Az alapdíj mentve. A Paraméterértékek ablak nyitva marad.")
        except Exception as exc: st.error(f"Nem menthető: {exc}")
    _delete_control(client, BASE_RATE_TABLE, row, "base")


def _show_performance(client: Any, table: str, title: str, key: str) -> None:
    st.caption(f"{title}: a szabály közös Excelhez és API-hoz is. API-nál az elsődleges kulcs a szint + túratípus, például LEVEL-1 + Normál.")
    data = read_items(client, table)
    if not data.empty:
        view = data.copy(); view["Naptípus"] = view["day_type"].map(DAY_LABELS); view["Túratípus"] = view["route_type"].map(ROUTE_LABELS); view["Számítás módja"] = view["calculation_mode"].map(CALCULATION_MODE_LABELS); view["Mutatósáv"] = [_range(a, b, "%") for a, b in zip(view["threshold_min"], view["threshold_max"])]; view["Túrahossz"] = [_range(a, b, " óra") for a, b in zip(view["duration_min_hours"], view["duration_max_hours"])]; view["JITT"] = view["company_amount_huf"].map(_money); view["Futár"] = view["courier_amount_huf"].map(_money); view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["level_code", "Számítás módja", "Naptípus", "Túratípus", "Mutatósáv", "Túrahossz", "JITT", "Futár", "valid_from", "Vége"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, key, "level_code")
    form_key = f"{key}_form_{_text((row or {}).get('id')) or 'new'}"
    with st.form(form_key):
        left, right = st.columns(2); days, routes, units = list(DAY_LABELS), list(ROUTE_LABELS), list(UNIT_LABELS)
        level = left.text_input("Szint", value=_text((row or {}).get("level_code")), placeholder="Például: Szint 1")
        day_type = right.selectbox("Naptípus", days, index=_index(days, (row or {}).get("day_type")), format_func=DAY_LABELS.get)
        route_type = left.selectbox("Túratípus", routes, index=_index(routes, (row or {}).get("route_type")), format_func=ROUTE_LABELS.get)
        warehouse = right.text_input("Raktár", value=_text((row or {}).get("warehouse_code")), placeholder="Üres = minden raktár")
        source_headers = ["(nincs kiválasztva)"] + _excel_source_headers(client)
        stored_source = _text((row or {}).get("excel_source_field"))
        default_source = stored_source or ("Delay Bonus" if key == "delay" else "Compliance Bonus")
        if default_source not in source_headers:
            source_headers.append(default_source)
        excel_source_field = right.selectbox(
            "Excel forrásmező",
            source_headers,
            index=_index(source_headers, default_source),
            help="A feltöltött JITT Excelből beolvasott fejléc. API esetén a szabályt ugyanebből a sorból használjuk, a matchedTier + túratípus alapján.",
        )
        if len(source_headers) == 2 and source_headers[1] == default_source:
            st.info("A JITT Excel fejléc-lista még nem érhető el az adatbázisból. Ellenőrizd, hogy van-e betöltött settlement.jit_row adat.")
        st.markdown("##### Mutatósáv és tervezett túrahossz")
        c1,c2,c3,c4 = st.columns(4); threshold_min = c1.number_input("Mutató minimum (%)", value=_number((row or {}).get("threshold_min")), step=0.01); threshold_max = c2.number_input("Mutató maximum (%)", value=_number((row or {}).get("threshold_max")), step=0.01); duration_min = c3.number_input("Túrahossz minimum", value=_number((row or {}).get("duration_min_hours")), min_value=0.0, step=0.5); duration_max = c4.number_input("Túrahossz maximum", value=_number((row or {}).get("duration_max_hours")), min_value=0.0, step=0.5)
        bounds = st.columns(2); has_threshold_min = bounds[0].checkbox("Van alsó mutatóhatár", value=_clean((row or {}).get("threshold_min")) is not None); has_threshold_max = bounds[1].checkbox("Van felső mutatóhatár", value=_clean((row or {}).get("threshold_max")) is not None)
        durations = st.columns(2); has_duration_min = durations[0].checkbox("Van minimum túrahossz", value=_clean((row or {}).get("duration_min_hours")) is not None); has_duration_max = durations[1].checkbox("Van maximum túrahossz", value=_clean((row or {}).get("duration_max_hours")) is not None)
        m1,m2,m3,m4 = st.columns(4); company = m1.number_input("JITT összege (Ft)", min_value=0, value=_int((row or {}).get("company_amount_huf")), step=100); courier = m2.number_input("Futár összege (Ft)", min_value=0, value=_int((row or {}).get("courier_amount_huf")), step=100); unit = m3.selectbox("Elszámolási egység", units, index=_index(units, (row or {}).get("calculation_unit") or "per_route"), format_func=UNIT_LABELS.get); modes = list(CALCULATION_MODE_LABELS); calculation_mode = m4.selectbox("Számítás módja", modes, index=_index(modes, (row or {}).get("calculation_mode") or "excel"), format_func=CALCULATION_MODE_LABELS.get)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, key)
        saved = st.form_submit_button("Módosítás mentése" if row else f"{title} mentése", type="primary")
    if saved:
        try:
            save_item(client, table, validate_performance_rule({"level_code": level, "day_type": day_type, "route_type": route_type, "warehouse_code": warehouse, "threshold_min": threshold_min if has_threshold_min else None, "threshold_max": threshold_max if has_threshold_max else None, "duration_min": duration_min if has_duration_min else None, "duration_max": duration_max if has_duration_max else None, "company_amount_huf": company, "courier_amount_huf": courier, "calculation_unit": unit, "calculation_mode": calculation_mode, "excel_source_field": None if excel_source_field == "(nincs kiválasztva)" else excel_source_field, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            _mark_parameters_changed(client)
            st.success(f"{title} mentve. A Paraméterértékek ablak nyitva marad.")
        except Exception as exc: st.error(f"Nem menthető: {exc}")
    _delete_control(client, table, row, key)


def _show_periodic(client: Any) -> None:
    st.caption("Egyedi dátumtartományú díjak és bónuszok. Például: 2026-06-07–09 között, minimum 12 címes túrára 1 000 Ft.")
    data = read_items(client, PERIODIC_FEE_TABLE)
    if not data.empty:
        view=data.copy(); view["Naptípus"] = view["day_type"].map(DAY_LABELS); view["Túratípus"] = view["route_type"].map(ROUTE_LABELS); view["Feltétel"] = [f"{CONDITION_LABELS.get(c, c)} · {_range(a,b)}" for c,a,b in zip(view["condition_metric"],view["condition_min"],view["condition_max"])]; view["JITT"] = view["company_amount_huf"].map(_money); view["Futár"] = view["courier_amount_huf"].map(_money); view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["fee_name", "Naptípus", "Túratípus", "Feltétel", "JITT", "Futár", "valid_from", "Vége"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, "periodic", "fee_name")
    form_key = f"periodic_form_{_text((row or {}).get('id')) or 'new'}"
    with st.form(form_key):
        left,right=st.columns(2); days,routes,units,conditions=list(DAY_LABELS),list(ROUTE_LABELS),list(UNIT_LABELS),list(CONDITION_LABELS)
        fee_name = left.text_input("Megnevezés", value=_text((row or {}).get("fee_name")), placeholder="Például: 12 címes túrabónusz")
        day_type = right.selectbox("Naptípus", days, index=_index(days,(row or {}).get("day_type")), format_func=DAY_LABELS.get)
        route_type = left.selectbox("Túratípus", routes, index=_index(routes,(row or {}).get("route_type")), format_func=ROUTE_LABELS.get)
        warehouse = right.text_input("Raktár", value=_text((row or {}).get("warehouse_code")), placeholder="Üres = minden raktár")
        condition = left.selectbox("Feltétel", conditions, index=_index(conditions,(row or {}).get("condition_metric") or "none"), format_func=CONDITION_LABELS.get)
        c1,c2=right.columns(2); condition_min=c1.number_input("Minimum érték", min_value=0.0, value=_number((row or {}).get("condition_min")), step=1.0); condition_max=c2.number_input("Maximum érték", min_value=0.0, value=_number((row or {}).get("condition_max")), step=1.0); has_max=c2.checkbox("Van maximum", value=_clean((row or {}).get("condition_max")) is not None)
        m1,m2,m3=st.columns(3); company=m1.number_input("JITT összege (Ft)", min_value=0, value=_int((row or {}).get("company_amount_huf")), step=100); courier=m2.number_input("Futár összege (Ft)", min_value=0, value=_int((row or {}).get("courier_amount_huf")), step=100); unit=m3.selectbox("Elszámolási egység",units,index=_index(units,(row or {}).get("calculation_unit") or "per_route"),format_func=UNIT_LABELS.get)
        valid_from,valid_to,has_end,priority,is_active,note=_common_period(row or {},"periodic")
        saved=st.form_submit_button("Módosítás mentése" if row else "Időszakos díj mentése",type="primary")
    if saved:
        try:
            save_item(client, PERIODIC_FEE_TABLE, validate_periodic_fee({"fee_name":fee_name,"day_type":day_type,"route_type":route_type,"warehouse_code":warehouse,"condition_metric":condition,"condition_min":condition_min if condition != "none" else None,"condition_max":condition_max if condition != "none" and has_max else None,"company_amount_huf":company,"courier_amount_huf":courier,"calculation_unit":unit,"valid_from":valid_from,"valid_to":valid_to if has_end else None,"priority":priority,"is_active":is_active,"note":note}),_actor(),_text((row or {}).get("id")) or None)
            _mark_parameters_changed(client)
            st.success("Az időszakos díj mentve. A Paraméterértékek ablak nyitva marad.")
        except Exception as exc: st.error(f"Nem menthető: {exc}")
    _delete_control(client, PERIODIC_FEE_TABLE, row, "periodic")


def _show_reserve_insurance(client: Any) -> None:
    st.caption("Itt verziózottan állítható a biztosítás díja, az alap biztosítási végösszeg és a levonás százaléka.")
    data = read_items(client, RESERVE_INSURANCE_TABLE)
    if not data.empty:
        view = data.copy()
        view["Biztosítás díja"] = view["insurance_fee_huf"].map(_money)
        view["Alap biztosítás"] = view["base_insurance_total_huf"].map(_money)
        if "reserve_target_huf" not in view.columns:
            view["reserve_target_huf"] = 50_000
        view["Céltartalék maximum"] = view["reserve_target_huf"].map(_money)
        view["Levonás"] = view["deduction_percent"].map(lambda value: f"{_number(value):g}%")
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["Biztosítás díja", "Alap biztosítás", "Céltartalék maximum", "Levonás", "valid_from", "Vége", "note"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, "reserve_insurance", "valid_from")
    with st.form(f"reserve_insurance_form_{_text((row or {}).get('id')) or 'new'}"):
        left, right, target_col, third = st.columns(4)
        insurance_fee = left.number_input("Biztosítás díja (Ft)", min_value=0, value=_int((row or {}).get("insurance_fee_huf")), step=100)
        base_total = right.number_input("Alap biztosítási végösszeg (Ft)", min_value=0, value=_int((row or {}).get("base_insurance_total_huf")), step=100)
        reserve_target = target_col.number_input("Céltartalék maximum (Ft)", min_value=0, value=_int((row or {}).get("reserve_target_huf"), 50_000), step=1000)
        deduction = third.number_input("Levonás (%)", min_value=0.0, max_value=100.0, value=_number((row or {}).get("deduction_percent")), step=0.1)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "reserve_insurance")
        saved = st.form_submit_button("Módosítás mentése" if row else "Biztosítási szabály mentése", type="primary")
    if saved:
        try:
            save_item(client, RESERVE_INSURANCE_TABLE, validate_reserve_insurance_rule({"insurance_fee_huf": insurance_fee, "base_insurance_total_huf": base_total, "reserve_target_huf": reserve_target, "deduction_percent": deduction, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            st.success("A Céltartalék / Biztosítás szabály mentve.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, RESERVE_INSURANCE_TABLE, row, "reserve_insurance")


def _show_loyalty_bonus(client: Any) -> None:
    st.caption("A lojalitási bónusz a futár munkakezdése alapján, hónapszámhoz kötve számolható túrára vagy címre.")
    data = read_items(client, LOYALTY_BONUS_TABLE)
    if not data.empty:
        view = data.copy()
        view["Hónapok"] = pd.to_numeric(view.get("loyalty_months_required", 0), errors="coerce").fillna(0).astype(int)
        view["Előző havi normál min."] = pd.to_numeric(view.get("previous_normal_routes_min", 0), errors="coerce").fillna(0).astype(int)
        view["Túratípus"] = view.get("route_type", pd.Series("normal", index=view.index)).fillna("normal").map(ROUTE_LABELS)
        view["Egység"] = view.get("calculation_unit", pd.Series("per_route", index=view.index)).fillna("per_route").map(UNIT_LABELS)
        view["Összeg"] = view["bonus_amount_huf"].map(_money)
        view["Előfoglalás kell"] = view.get("require_advance_booking", pd.Series(True, index=view.index)).fillna(True).astype(bool)
        view["Aktív jogviszony kell"] = view.get("require_active_relationship", pd.Series(True, index=view.index)).fillna(True).astype(bool)
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["Hónapok", "Előző havi normál min.", "Túratípus", "Egység", "Összeg", "Előfoglalás kell", "Aktív jogviszony kell", "valid_from", "Vége", "note"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, "loyalty", "valid_from")
    with st.form(f"loyalty_form_{_text((row or {}).get('id')) or 'new'}"):
        left, middle, right = st.columns(3)
        required_months = left.number_input("Lojális bónusz hónapok száma", min_value=0, value=_int((row or {}).get("loyalty_months_required")), step=1)
        previous_normal_routes_min = left.number_input("Előző havi normál kör minimum", min_value=0, value=_int((row or {}).get("previous_normal_routes_min")), step=1)
        routes = ["normal", "express", "regional", "any"]
        route_type = middle.selectbox("Túratípus", routes, index=_index(routes, (row or {}).get("route_type") or "normal"), format_func=ROUTE_LABELS.get)
        units = ["per_route", "per_order"]
        unit = right.selectbox("Elszámolási egység", units, index=_index(units, (row or {}).get("calculation_unit") or "per_route"), format_func=UNIT_LABELS.get)
        require_advance_booking = middle.checkbox("Előfoglalás szükséges", value=bool((row or {}).get("require_advance_booking", True)))
        require_active_relationship = right.checkbox("Aktív jogviszony szükséges", value=bool((row or {}).get("require_active_relationship", True)))
        amount = st.number_input("Lojalitási bónusz összege (Ft)", min_value=0, value=_int((row or {}).get("bonus_amount_huf")), step=100)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "loyalty")
        saved = st.form_submit_button("Módosítás mentése" if row else "Lojalitási bónusz mentése", type="primary")
    if saved:
        try:
            save_item(client, LOYALTY_BONUS_TABLE, validate_loyalty_bonus_rule({"loyalty_months_required": required_months, "previous_normal_routes_min": previous_normal_routes_min, "require_acceptance": False, "require_advance_booking": require_advance_booking, "require_active_relationship": require_active_relationship, "route_type": route_type, "calculation_unit": unit, "bonus_amount_huf": amount, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            st.success("A lojalitási bónusz mentve.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, LOYALTY_BONUS_TABLE, row, "loyalty")


def _show_efo_assignments(client: Any) -> None:
    st.caption("EFO-s kollégák időszakos nyilvántartása. Itt tartható karban, mettől meddig volt bejelentve és mennyi a napi díj levonása.")
    data = read_items(client, EFO_ASSIGNMENT_TABLE)
    if data.attrs.get("missing_table"):
        st.info("Az EFO nyilvántartási tábla nincs telepítve. A havi számlázás kihagyását most a futár Dokumentumok menüjében, kézzel lehet kapcsolni.")
        return
    if not data.empty:
        view = data.copy()
        view["Napi levonás"] = view["daily_deduction_huf"].map(_money)
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        view["Státusz"] = [parameter_status(a, b, c) for a, b, c in zip(view["valid_from"], view["valid_to"], view["is_active"])]
        st.dataframe(
            view[["courier_id", "courier_name", "valid_from", "Vége", "Napi levonás", "Státusz", "note"]],
            use_container_width=True,
            hide_index=True,
        )
    row = _editor_row(data, "efo", "courier_id")
    with st.form(f"efo_form_{_text((row or {}).get('id')) or 'new'}"):
        left, middle, right = st.columns(3)
        courier_id = left.text_input("Futár azonosító", value=_text((row or {}).get("courier_id")))
        courier_name = middle.text_input("Futár neve", value=_text((row or {}).get("courier_name")))
        daily_deduction = right.number_input("Napi díj levonása (Ft)", min_value=0, value=_int((row or {}).get("daily_deduction_huf")), step=100)

        row_key = f"efo_{_text((row or {}).get('id')) or 'new'}"
        period_cols = st.columns(3)
        valid_from = period_cols[0].date_input("Bejelentve ettől", value=_date((row or {}).get("valid_from")), key=f"{row_key}_from")
        has_end = period_cols[1].checkbox("Van záródátum", value=_clean((row or {}).get("valid_to")) is not None, key=f"{row_key}_has_end")
        valid_to = period_cols[1].date_input("Bejelentve eddig", value=_date((row or {}).get("valid_to")), key=f"{row_key}_to")
        is_active = period_cols[2].checkbox("Aktív", value=bool((row or {}).get("is_active", True)), key=f"{row_key}_active")
        note = st.text_area("Megjegyzés", value=_text((row or {}).get("note")), height=70, key=f"{row_key}_note")
        saved = st.form_submit_button("Módosítás mentése" if row else "EFO időszak mentése", type="primary")
    if saved:
        try:
            save_item(
                client,
                EFO_ASSIGNMENT_TABLE,
                validate_efo_assignment(
                    {
                        "courier_id": courier_id,
                        "courier_name": courier_name,
                        "valid_from": valid_from,
                        "valid_to": valid_to if has_end else None,
                        "daily_deduction_huf": daily_deduction,
                        "is_active": is_active,
                        "note": note,
                    }
                ),
                _actor(),
                _text((row or {}).get("id")) or None,
            )
            st.success("Az EFO időszak mentve.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, EFO_ASSIGNMENT_TABLE, row, "efo")


def _show_life_insurance(client: Any) -> None:
    st.caption("Életbiztosítási összeg verziózott érvényességi idővel.")
    data = read_items(client, LIFE_INSURANCE_TABLE)
    if not data.empty:
        view = data.copy(); view["Életbiztosítás összege"] = view["life_insurance_amount_huf"].map(_money); view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["Életbiztosítás összege", "valid_from", "Vége", "note"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, "life_insurance", "valid_from")
    with st.form(f"life_insurance_form_{_text((row or {}).get('id')) or 'new'}"):
        amount = st.number_input("Életbiztosítás összege (Ft)", min_value=0, value=_int((row or {}).get("life_insurance_amount_huf")), step=100)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "life_insurance")
        saved = st.form_submit_button("Módosítás mentése" if row else "Életbiztosítás mentése", type="primary")
    if saved:
        try:
            save_item(client, LIFE_INSURANCE_TABLE, validate_life_insurance_rule({"life_insurance_amount_huf": amount, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            st.success("Az életbiztosítási szabály mentve.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, LIFE_INSURANCE_TABLE, row, "life_insurance")


def _show_customer_rating(client: Any) -> None:
    st.caption("Ügyfélértékelési bónusz 1-5 értékelési sávval, futárösszeggel és verziózott érvényességgel.")
    data = read_items(client, CUSTOMER_RATING_TABLE)
    if st.button("Alap ügyfélértékelési sávok feltöltése 2026-05-01-től", key="customer_rating_seed_defaults"):
        try:
            existing = {
                (_text(row.get("level_code")), _text(row.get("route_type") or "normal"), _text(row.get("valid_from")))
                for row in data.to_dict("records")
            } if not data.empty else set()
            inserted = 0
            for rule in CUSTOMER_RATING_DEFAULT_RULES:
                marker = (_text(rule["level_code"]), _text(rule["route_type"]), rule["valid_from"].isoformat())
                if marker in existing:
                    continue
                save_item(client, CUSTOMER_RATING_TABLE, validate_customer_rating_rule(rule), _actor())
                inserted += 1
            if inserted:
                _mark_parameters_changed(client)
                data = read_items(client, CUSTOMER_RATING_TABLE)
                st.success(f"{inserted} ügyfélértékelési szabály feltöltve.")
            else:
                st.info("Az alap ügyfélértékelési sávok már szerepelnek a Paraméterértékekben.")
        except Exception as exc:
            st.error(f"Az alap ügyfélértékelési sávok nem tölthetők fel: {exc}")
    if not data.empty:
        view = data.copy()
        view["Túratípus"] = view.get("route_type", pd.Series("normal", index=view.index)).fillna("normal").map(ROUTE_LABELS)
        view["Értékelési sáv"] = [_range(a, b) for a, b in zip(view["rating_min_percent"], view["rating_max_percent"])]
        view["Futár összege"] = view["courier_amount_huf"].map(_money)
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        st.dataframe(view[["level_code", "Túratípus", "Értékelési sáv", "Futár összege", "valid_from", "Vége", "note"]], use_container_width=True, hide_index=True)
    row = _editor_row(data, "customer_rating", "level_code")
    with st.form(f"customer_rating_form_{_text((row or {}).get('id')) or 'new'}"):
        left, middle, right = st.columns(3)
        level = left.text_input("Megnevezés", value=_text((row or {}).get("level_code")) or "Ügyfélértékelés")
        routes = ["normal", "express"]
        route_type = middle.selectbox("Túratípus", routes, index=_index(routes, (row or {}).get("route_type") or "normal"), format_func=ROUTE_LABELS.get)
        courier_amount = right.number_input("Futár összege (Ft)", min_value=0, value=_int((row or {}).get("courier_amount_huf")), step=100)
        rating_cols = st.columns(2)
        rating_min = rating_cols[0].number_input("Minimum értékelés", min_value=0.0, max_value=5.0, value=_number((row or {}).get("rating_min_percent")), step=0.01, help="Az Excelben szereplő 1-5 skálás átlagértékelés alsó határa.")
        rating_max = rating_cols[1].number_input("Maximum értékelés", min_value=0.0, max_value=5.0, value=_number((row or {}).get("rating_max_percent")), step=0.01, help="Az Excelben szereplő 1-5 skálás átlagértékelés felső határa.")
        bounds = st.columns(2)
        has_min = bounds[0].checkbox("Van minimum", value=_clean((row or {}).get("rating_min_percent")) is not None)
        has_max = bounds[1].checkbox("Van maximum", value=_clean((row or {}).get("rating_max_percent")) is not None)
        valid_from, valid_to, has_end, priority, is_active, note = _common_period(row or {}, "customer_rating")
        saved = st.form_submit_button("Módosítás mentése" if row else "Ügyfélértékelés mentése", type="primary")
    if saved:
        try:
            save_item(client, CUSTOMER_RATING_TABLE, validate_customer_rating_rule({"level_code": level, "route_type": route_type, "rating_min": rating_min if has_min else None, "rating_max": rating_max if has_max else None, "courier_amount_huf": courier_amount, "valid_from": valid_from, "valid_to": valid_to if has_end else None, "priority": priority, "is_active": is_active, "note": note}), _actor(), _text((row or {}).get("id")) or None)
            st.success("Az ügyfélértékelési szabály mentve.")
        except Exception as exc:
            st.error(f"Nem menthető: {exc}")
    _delete_control(client, CUSTOMER_RATING_TABLE, row, "customer_rating")


def render_parameter_catalog(client: Any) -> None:
    st.subheader("Paraméterértékek")
    st.caption("Minden szabály külön menüpontban kezelhető. A dátum nélküli zárás folyamatos érvényességet jelent.")
    try:
        tabs = st.tabs(["Kiemelt / Normál napok", "Alap díjak", "Delay bónusz", "Compliance bónusz", "Időszakos díjak", "Céltartalék / Biztosítás", "Lojalitási bónusz", "EFO", "Életbiztosítás", "Ügyfélértékelés"])
        with tabs[0]: _show_days(client)
        with tabs[1]: _show_base_rates(client)
        with tabs[2]: _show_performance(client, DELAY_TABLE, "Delay bónusz", "delay")
        with tabs[3]: _show_performance(client, COMPLIANCE_TABLE, "Compliance bónusz", "compliance")
        with tabs[4]: _show_periodic(client)
        with tabs[5]: _show_reserve_insurance(client)
        with tabs[6]: _show_loyalty_bonus(client)
        with tabs[7]: _show_efo_assignments(client)
        with tabs[8]: _show_life_insurance(client)
        with tabs[9]: _show_customer_rating(client)
    except ValueError as exc:
        st.error(f"A paraméter értéke hibás: {exc}")
    except Exception as exc:
        st.error("A settlement paramétertáblák nem olvashatók. Ha most telepíted először, futtasd a `sql/settlement_parameterized_base_rate.sql` fájlt a Supabase SQL Editorban. Részlet: " + str(exc))
