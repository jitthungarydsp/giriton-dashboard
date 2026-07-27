from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd
import streamlit as st

from resources.settlement_parameters import (
    BASE_RATE_TABLE,
    COMPLIANCE_TABLE,
    DAY_TABLE,
    DELAY_TABLE,
    PERIODIC_FEE_TABLE,
    parameter_status,
    read_items,
    recalculate_excel_base_rates,
    save_item,
    soft_delete_item,
    validate_base_rate,
    validate_day_definition,
    validate_performance_rule,
    validate_periodic_fee,
)


DAY_LABELS = {"highlighted": "Kiemelt nap", "normal": "Normál nap", "any": "Bármely nap"}
ROUTE_LABELS = {"express": "Expressz", "normal": "Normál", "regional": "Regionális", "any": "Bármely túra"}
UNIT_LABELS = {"fixed": "Fix összeg", "per_route": "Ft / túra", "per_order": "Ft / cím", "per_hour": "Ft / óra"}
CALCULATION_MODE_LABELS = {"excel": "Excel", "api": "API", "custom": "Egyéni"}
CONDITION_LABELS = {"none": "Nincs feltétel", "orders_per_route": "Címek száma túránként", "routes_per_day": "Túrák száma naponta", "routes_in_period": "Túrák száma az időszakban", "orders_in_period": "Címek száma az időszakban"}
WEEKDAY_LABELS = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}


def _actor() -> str:
    return str(st.session_state.get("user", {}).get("username") or "unknown").strip()


def _mark_parameters_changed(client: Any) -> None:
    st.session_state["settlement_parameter_revision"] = int(
        st.session_state.get("settlement_parameter_revision", 0)
    ) + 1
    try:
        recalculate_excel_base_rates(
            client,
            st.session_state.get("settlement_import_session_id"),
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
        rows = (
            client.schema("settlement")
            .table("jit_row")
            .select("normalized_data")
            .order("created_at", desc=True)
            .limit(250)
            .execute()
            .data
            or []
        )
    except Exception:
        return []
    headers: set[str] = set()
    for row in rows:
        normalized_data = row.get("normalized_data") or {}
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
    col1, col2, col3 = st.columns(3)
    valid_from = col1.date_input("Érvényes ettől", value=_date(row.get("valid_from")), key=f"{key}_from")
    has_end = col2.checkbox("Van záródátum", value=_clean(row.get("valid_to")) is not None, key=f"{key}_has_end")
    valid_to = col2.date_input("Érvényes eddig", value=_date(row.get("valid_to")), key=f"{key}_to")
    priority = col3.number_input("Prioritás", value=_int(row.get("priority"), 100), step=1, key=f"{key}_priority")
    is_active = st.checkbox("Engedélyezett", value=bool(row.get("is_active", True)), key=f"{key}_active")
    note = st.text_area("Megjegyzés", value=_text(row.get("note")), key=f"{key}_note", height=70)
    return valid_from, valid_to, has_end, priority, is_active, note


def _show_days(client: Any) -> None:
    st.caption("Itt állítható be, hogy az egyes időszakokban mely hétköznapok számítanak kiemeltnek vagy normálnak.")
    data = read_items(client, DAY_TABLE)
    if not data.empty:
        view = data.copy()
        view["Naptípus"] = view["day_type"].map(DAY_LABELS)
        view["Napok"] = view["weekdays"].apply(lambda values: ", ".join(WEEKDAY_LABELS.get(int(value), str(value)) for value in (values or [])))
        view["Vége"] = view["valid_to"].fillna("Folyamatos")
        view["Státusz"] = [parameter_status(a, b, c) for a, b, c in zip(view["valid_from"], view["valid_to"], view["is_active"])]
        st.dataframe(view[["Naptípus", "Napok", "valid_from", "Vége", "Státusz", "note"]], use_container_width=True, hide_index=True)
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
    st.caption(f"{title}: szint, százalékos sáv, tervezett túrahossz és kétoldali díjazás külön paraméterezhető.")
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
        st.markdown("##### Mutatósáv és tervezett túrahossz")
        c1,c2,c3,c4 = st.columns(4); threshold_min = c1.number_input("Mutató minimum (%)", value=_number((row or {}).get("threshold_min")), step=0.01); threshold_max = c2.number_input("Mutató maximum (%)", value=_number((row or {}).get("threshold_max")), step=0.01); duration_min = c3.number_input("Túrahossz minimum", value=_number((row or {}).get("duration_min_hours")), min_value=0.0, step=0.5); duration_max = c4.number_input("Túrahossz maximum", value=_number((row or {}).get("duration_max_hours")), min_value=0.0, step=0.5)
        bounds = st.columns(2); has_threshold_min = bounds[0].checkbox("Van alsó mutatóhatár", value=_clean((row or {}).get("threshold_min")) is not None); has_threshold_max = bounds[1].checkbox("Van felső mutatóhatár", value=_clean((row or {}).get("threshold_max")) is not None)
        durations = st.columns(2); has_duration_min = durations[0].checkbox("Van minimum túrahossz", value=_clean((row or {}).get("duration_min_hours")) is not None); has_duration_max = durations[1].checkbox("Van maximum túrahossz", value=_clean((row or {}).get("duration_max_hours")) is not None)
        m1,m2,m3,m4 = st.columns(4); company = m1.number_input("JITT összege (Ft)", min_value=0, value=_int((row or {}).get("company_amount_huf")), step=100); courier = m2.number_input("Futár összege (Ft)", min_value=0, value=_int((row or {}).get("courier_amount_huf")), step=100); unit = m3.selectbox("Elszámolási egység", units, index=_index(units, (row or {}).get("calculation_unit") or "per_route"), format_func=UNIT_LABELS.get); modes = list(CALCULATION_MODE_LABELS); calculation_mode = m4.selectbox("Számítás módja", modes, index=_index(modes, (row or {}).get("calculation_mode") or "excel"), format_func=CALCULATION_MODE_LABELS.get)
        source_headers = ["(nincs kiválasztva)"] + _excel_source_headers(client)
        stored_source = _text((row or {}).get("excel_source_field"))
        default_source = stored_source or ("Delay Bonus" if key == "delay" else "Compliance Bonus")
        if default_source not in source_headers:
            source_headers.append(default_source)
        excel_source_field = st.selectbox(
            "Excel forrásmező",
            source_headers,
            index=_index(source_headers, default_source),
            help="Az Excelben talált fejléc. Excel mód esetén ebből a mezőből olvassuk a bónusz alapértékét.",
        )
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


def render_parameter_catalog(client: Any) -> None:
    st.subheader("Paraméterértékek")
    st.caption("Minden szabály külön menüpontban kezelhető. A dátum nélküli zárás folyamatos érvényességet jelent.")
    try:
        tabs = st.tabs(["Kiemelt / Normál napok", "Alap díjak", "Delay bónusz", "Compliance bónusz", "Időszakos díjak"])
        with tabs[0]: _show_days(client)
        with tabs[1]: _show_base_rates(client)
        with tabs[2]: _show_performance(client, DELAY_TABLE, "Delay bónusz", "delay")
        with tabs[3]: _show_performance(client, COMPLIANCE_TABLE, "Compliance bónusz", "compliance")
        with tabs[4]: _show_periodic(client)
    except Exception as exc:
        st.error("A settlement paramétertáblák még nem érhetők el. Futtasd a `sql/settlement_parameterized_base_rate.sql` fájlt a Supabase SQL Editorban. Részlet: " + str(exc))
