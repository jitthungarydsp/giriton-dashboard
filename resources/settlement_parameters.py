from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


DAY_TABLE = "cfg_jitt_day_definitions"
BASE_RATE_TABLE = "cfg_jitt_base_rates"
DELAY_TABLE = "cfg_jitt_delay_bonus_rules"
COMPLIANCE_TABLE = "cfg_jitt_compliance_bonus_rules"
PERIODIC_FEE_TABLE = "cfg_jitt_periodic_fees"
RESERVE_INSURANCE_TABLE = "cfg_jitt_reserve_insurance_rules"
LOYALTY_BONUS_TABLE = "cfg_jitt_loyalty_bonus_rules"
LIFE_INSURANCE_TABLE = "cfg_jitt_life_insurance_rules"
CUSTOMER_RATING_TABLE = "cfg_jitt_customer_rating_rules"
EFO_ASSIGNMENT_TABLE = "courier_efo_assignment"

DAY_TYPES = {"highlighted", "normal", "any"}
ROUTE_TYPES = {"express", "normal", "regional", "any"}
CALCULATION_UNITS = {"fixed", "per_route", "per_order", "per_hour"}
CALCULATION_MODES = {"excel", "api", "custom"}
PERIODIC_CONDITIONS = {
    "none",
    "orders_per_route",
    "routes_per_day",
    "routes_in_period",
    "orders_in_period",
    "every_n_routes_per_day",
    "every_n_routes_in_period",
}


def _table(client: Any, name: str) -> Any:
    return client.schema("settlement").table(name)


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    value = _text(value)
    return value or None


def _date(value: Any, label: str) -> date:
    try:
        if pd.isna(value):
            raise ValueError(f"A(z) {label} dátuma érvénytelen.")
    except TypeError:
        pass
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value))
    except ValueError as exc:
        raise ValueError(f"A(z) {label} dátuma érvénytelen.") from exc


def _period(payload: dict[str, Any]) -> tuple[str, str | None]:
    valid_from = _date(payload.get("valid_from"), "kezdő")
    raw_to = payload.get("valid_to")
    valid_to = _date(raw_to, "záró") if raw_to not in (None, "") else None
    if valid_to and valid_to < valid_from:
        raise ValueError("A záró dátum nem lehet korábbi a kezdő dátumnál.")
    return valid_from.isoformat(), valid_to.isoformat() if valid_to else None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _range(payload: dict[str, Any], prefix: str, label: str) -> tuple[float | None, float | None]:
    minimum = _number(payload.get(f"{prefix}_min"))
    maximum = _number(payload.get(f"{prefix}_max"))
    if minimum is not None and maximum is not None and maximum < minimum:
        raise ValueError(f"A(z) {label} felső értéke nem lehet kisebb az alsónál.")
    return minimum, maximum


def _amount(value: Any, label: str) -> int:
    amount = int(value or 0)
    if amount < 0:
        raise ValueError(f"A(z) {label} nem lehet negatív.")
    return amount


def _choice(value: Any, choices: set[str], label: str) -> str:
    value = _text(value).lower()
    if value not in choices:
        raise ValueError(f"Ismeretlen {label}.")
    return value


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    valid_from, valid_to = _period(payload)
    return {
        "valid_from": valid_from,
        "valid_to": valid_to,
        "priority": int(payload.get("priority") or 100),
        "is_active": bool(payload.get("is_active", True)),
        "note": _optional_text(payload.get("note")),
    }


def validate_day_definition(payload: dict[str, Any]) -> dict[str, Any]:
    day_type = _choice(payload.get("day_type"), {"highlighted", "normal"}, "naptípus")
    weekdays = sorted({int(day) for day in (payload.get("weekdays") or [])})
    if not weekdays:
        raise ValueError("Legalább egy napot ki kell jelölni.")
    if any(day not in range(1, 8) for day in weekdays):
        raise ValueError("A hét napjai csak 1 és 7 közötti értékek lehetnek.")
    return {"day_type": day_type, "weekdays": weekdays, **_common(payload)}


def validate_base_rate(payload: dict[str, Any]) -> dict[str, Any]:
    day_type = _choice(payload.get("day_type"), DAY_TYPES, "naptípus")
    route_type = _choice(payload.get("route_type"), ROUTE_TYPES, "túratípus")
    unit = _choice(payload.get("calculation_unit"), CALCULATION_UNITS, "elszámolási egység")
    return {
        "day_type": day_type,
        "route_type": route_type,
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "company_amount_huf": _amount(payload.get("company_amount_huf"), "JITT-összeg"),
        "courier_amount_huf": _amount(payload.get("courier_amount_huf"), "futárösszeg"),
        "calculation_unit": unit,
        **_common(payload),
    }


def validate_performance_rule(payload: dict[str, Any]) -> dict[str, Any]:
    level_code = _text(payload.get("level_code"))
    if not level_code:
        raise ValueError("A szint megadása kötelező.")
    threshold_min, threshold_max = _range(payload, "threshold", "mutatósáv")
    duration_min, duration_max = _range(payload, "duration", "túrahossz")
    return {
        "level_code": level_code,
        "day_type": _choice(payload.get("day_type"), DAY_TYPES, "naptípus"),
        "route_type": _choice(payload.get("route_type"), ROUTE_TYPES, "túratípus"),
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "threshold_min": threshold_min,
        "threshold_max": threshold_max,
        "threshold_min_inclusive": bool(payload.get("threshold_min_inclusive", True)),
        "threshold_max_inclusive": bool(payload.get("threshold_max_inclusive", True)),
        "duration_min_hours": duration_min,
        "duration_max_hours": duration_max,
        "company_amount_huf": _amount(payload.get("company_amount_huf"), "JITT-összeg"),
        "courier_amount_huf": _amount(payload.get("courier_amount_huf"), "futárösszeg"),
        "calculation_unit": _choice(payload.get("calculation_unit"), CALCULATION_UNITS, "elszámolási egység"),
        "calculation_mode": _choice(payload.get("calculation_mode"), CALCULATION_MODES, "számítási mód"),
        "excel_source_field": _optional_text(payload.get("excel_source_field")),
        **_common(payload),
    }


def validate_periodic_fee(payload: dict[str, Any]) -> dict[str, Any]:
    fee_name = _text(payload.get("fee_name"))
    if not fee_name:
        raise ValueError("Az időszakos díj megnevezése kötelező.")
    condition = _choice(payload.get("condition_metric"), PERIODIC_CONDITIONS, "időszakos feltétel")
    condition_min, condition_max = _range(payload, "condition", "bónuszfeltétel")
    if condition == "none":
        condition_min, condition_max = None, None
    if condition in {"every_n_routes_per_day", "every_n_routes_in_period"}:
        if condition_min is None or condition_min < 1:
            raise ValueError("A minden N. kör után szabálynál az N értéke legalább 1 legyen.")
        condition_max = None
    weekdays = sorted({int(day) for day in (payload.get("weekdays") or [])})
    if any(day not in range(1, 8) for day in weekdays):
        raise ValueError("A hét napjai csak 1 és 7 közötti értékek lehetnek.")
    return {
        "fee_name": fee_name,
        "day_type": _choice(payload.get("day_type"), DAY_TYPES, "naptípus"),
        "route_type": _choice(payload.get("route_type"), ROUTE_TYPES, "túratípus"),
        "weekdays": weekdays,
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "condition_metric": condition,
        "condition_min": condition_min,
        "condition_max": condition_max,
        "company_amount_huf": _amount(payload.get("company_amount_huf"), "JITT-összeg"),
        "courier_amount_huf": _amount(payload.get("courier_amount_huf"), "futárösszeg"),
        "calculation_unit": _choice(payload.get("calculation_unit"), CALCULATION_UNITS, "elszámolási egység"),
        **_common(payload),
    }


def validate_reserve_insurance_rule(payload: dict[str, Any]) -> dict[str, Any]:
    deduction_percent = _number(payload.get("deduction_percent"))
    if deduction_percent is None or not 0 <= deduction_percent <= 100:
        raise ValueError("A levonási százaléknak 0 és 100 között kell lennie.")
    return {
        "insurance_fee_huf": _amount(payload.get("insurance_fee_huf"), "biztosítási díj"),
        "base_insurance_total_huf": _amount(payload.get("base_insurance_total_huf"), "alap biztosítási végösszeg"),
        "reserve_target_huf": _amount(payload.get("reserve_target_huf", 50_000), "céltartalék maximum"),
        "deduction_percent": deduction_percent,
        **_common(payload),
    }


def validate_loyalty_bonus_rule(payload: dict[str, Any]) -> dict[str, Any]:
    required_months = int(payload.get("loyalty_months_required") or 0)
    if required_months < 0:
        raise ValueError("A lojalitási hónapok száma nem lehet negatív.")
    previous_normal_routes_min = int(payload.get("previous_normal_routes_min") or 0)
    if previous_normal_routes_min < 0:
        raise ValueError("Az előre foglalt műszak minimum nem lehet negatív.")
    return {
        "loyalty_start_date": _date(payload.get("loyalty_start_date") or payload.get("valid_from"), "lojalitási kezdő").isoformat(),
        "loyalty_months_required": required_months,
        "previous_normal_routes_min": previous_normal_routes_min,
        "require_acceptance": bool(payload.get("require_acceptance", False)),
        "require_advance_booking": bool(payload.get("require_advance_booking", True)),
        "require_active_relationship": bool(payload.get("require_active_relationship", True)),
        "route_type": _choice(payload.get("route_type") or "normal", ROUTE_TYPES, "túratípus"),
        "calculation_unit": _choice(payload.get("calculation_unit") or "per_route", {"per_route", "per_order"}, "elszámolási egység"),
        "bonus_amount_huf": _amount(payload.get("bonus_amount_huf"), "lojalitási bónusz összege"),
        **_common(payload),
    }


def validate_life_insurance_rule(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "life_insurance_amount_huf": _amount(payload.get("life_insurance_amount_huf"), "életbiztosítás összege"),
        **_common(payload),
    }


def validate_customer_rating_rule(payload: dict[str, Any]) -> dict[str, Any]:
    rating_min, rating_max = _range(payload, "rating", "ügyfélértékelési sáv")
    if rating_min is None and rating_max is None:
        raise ValueError("Legalább minimum vagy maximum értékelést adj meg.")
    if rating_min is not None and not 0 <= rating_min <= 5:
        raise ValueError("Az ügyfélértékelés alsó határa 0 és 5 között lehet.")
    if rating_max is not None and not 0 <= rating_max <= 5:
        raise ValueError("Az ügyfélértékelés felső határa 0 és 5 között lehet.")
    return {
        "level_code": _optional_text(payload.get("level_code")) or "Ügyfélértékelés",
        "route_type": _choice(payload.get("route_type") or "normal", ROUTE_TYPES, "túratípus"),
        "rating_min_percent": rating_min,
        "rating_max_percent": rating_max,
        "courier_amount_huf": _amount(payload.get("courier_amount_huf"), "futárösszeg"),
        **_common(payload),
    }


def validate_efo_assignment(payload: dict[str, Any]) -> dict[str, Any]:
    courier_id = _text(payload.get("courier_id"))
    if not courier_id:
        raise ValueError("A futár azonosító megadása kötelező.")
    daily_deduction = _amount(payload.get("daily_deduction_huf"), "napi díj levonása")
    valid_from, valid_to = _period(payload)
    return {
        "courier_id": courier_id,
        "courier_name": _optional_text(payload.get("courier_name")),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "daily_deduction_huf": daily_deduction,
        "is_active": bool(payload.get("is_active", True)),
        "note": _optional_text(payload.get("note")),
    }


def parameter_status(valid_from: Any, valid_to: Any, is_active: bool, today: date | None = None) -> str:
    if not is_active:
        return "Inaktív"
    today = today or date.today()
    if today < _date(valid_from, "kezdő"):
        return "Jövőbeni"
    if _text(valid_to) and today > _date(valid_to, "záró"):
        return "Lejárt"
    return "Aktív"


def read_items(client: Any, table_name: str) -> pd.DataFrame:
    try:
        response = (
            _table(client, table_name)
            .select("*")
            .is_("deleted_at", "null")
            .order("is_active", desc=True)
            .order("valid_from", desc=True)
            .execute()
        )
    except Exception as exc:
        if table_name == EFO_ASSIGNMENT_TABLE and "PGRST205" in str(exc):
            data = pd.DataFrame()
            data.attrs["missing_table"] = True
            return data
        raise
    return pd.DataFrame(response.data or [])


def save_item(client: Any, table_name: str, payload: dict[str, Any], actor: str, item_id: str | None = None) -> None:
    audit = {
        **payload,
        "updated_by": _text(actor) or "unknown",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    query = _table(client, table_name)
    if item_id:
        query.update(audit).eq("id", item_id).execute()
    else:
        query.insert({**audit, "created_by": _text(actor) or "unknown"}).execute()


def soft_delete_item(client: Any, table_name: str, item_id: str, actor: str) -> None:
    _table(client, table_name).update(
        {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": _text(actor) or "unknown",
        }
    ).eq("id", item_id).is_("deleted_at", "null").execute()


def recalculate_excel_base_rates(client: Any, session_id: str | None = None) -> None:
    """Refresh persisted JITT calculations and the courier summary table.

    A parameter change has to affect every imported session, not only the
    Excel file that happens to be open in the current browser session.
    """
    normalized_session_id = _text(session_id)
    if normalized_session_id:
        session_ids = [normalized_session_id]
    else:
        rows = (
            client.schema("settlement").table("jit_row").select("session_id")
            .limit(10000).execute().data or []
        )
        session_ids = sorted({str(row.get("session_id")) for row in rows if row.get("session_id")})
    for current_session_id in session_ids:
        client.schema("settlement").rpc(
            "recalculate_jitt_base_rates",
            {"p_session_id": current_session_id},
        ).execute()
        client.schema("settlement").rpc(
            "refresh_courier_settlement_summary",
            {"p_session_id": current_session_id},
        ).execute()
