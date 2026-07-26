from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


DAY_TABLE = "cfg_jitt_day_definitions"
BASE_RATE_TABLE = "cfg_jitt_base_rates"
DELAY_TABLE = "cfg_jitt_delay_bonus_rules"
COMPLIANCE_TABLE = "cfg_jitt_compliance_bonus_rules"
PERIODIC_FEE_TABLE = "cfg_jitt_periodic_fees"

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
}


def _table(client: Any, name: str) -> Any:
    return client.schema("public").table(name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    value = _text(value)
    return value or None


def _date(value: Any, label: str) -> date:
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
    return {
        "fee_name": fee_name,
        "day_type": _choice(payload.get("day_type"), DAY_TYPES, "naptípus"),
        "route_type": _choice(payload.get("route_type"), ROUTE_TYPES, "túratípus"),
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "condition_metric": condition,
        "condition_min": condition_min,
        "condition_max": condition_max,
        "company_amount_huf": _amount(payload.get("company_amount_huf"), "JITT-összeg"),
        "courier_amount_huf": _amount(payload.get("courier_amount_huf"), "futárösszeg"),
        "calculation_unit": _choice(payload.get("calculation_unit"), CALCULATION_UNITS, "elszámolási egység"),
        **_common(payload),
    }


def parameter_status(valid_from: Any, valid_to: Any, is_active: bool, today: date | None = None) -> str:
    if not is_active:
        return "Inaktív"
    today = today or date.today()
    if today < _date(valid_from, "kezdő"):
        return "Jövőbeni"
    if valid_to not in (None, "") and today > _date(valid_to, "záró"):
        return "Lejárt"
    return "Aktív"


def read_items(client: Any, table_name: str) -> pd.DataFrame:
    response = (
        _table(client, table_name)
        .select("*")
        .is_("deleted_at", "null")
        .order("is_active", desc=True)
        .order("valid_from", desc=True)
        .execute()
    )
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
