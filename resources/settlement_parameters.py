from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


RATE_TABLE = "cfg_jitt_rate_parameters"
PERIODIC_BONUS_TABLE = "cfg_jitt_periodic_bonuses"

RATE_KINDS = {
    "base_rate",
    "delay_bonus",
    "compliance_bonus",
    "customer_rating_bonus",
    "other",
}
DAY_TYPES = {"any", "highlighted", "not_highlighted"}
ROUTE_TYPES = {"any", "express", "normal", "regional"}
CALCULATION_UNITS = {
    "fixed",
    "per_route",
    "per_order",
    "per_hour",
    "percent",
}
PERIODIC_CONDITIONS = {
    "none",
    "orders_per_route",
    "routes_per_day",
    "routes_in_period",
    "orders_in_period",
}


def _table(client: Any, table_name: str) -> Any:
    return client.schema("public").table(table_name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    normalized = _text(value)
    return normalized or None


def _date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value))
    except ValueError as exc:
        raise ValueError(f"A(z) {field_name} dátuma érvénytelen.") from exc


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _nonnegative_int(value: Any, field_name: str) -> int:
    number = int(value or 0)
    if number < 0:
        raise ValueError(f"A(z) {field_name} nem lehet negatív.")
    return number


def _weekdays(values: Any) -> list[int]:
    result = sorted({int(value) for value in (values or [])})
    if any(value < 1 or value > 7 for value in result):
        raise ValueError("A hét napjai csak 1 és 7 közötti értékek lehetnek.")
    return result


def _validated_weekdays(values: Any, day_type: str) -> list[int]:
    result = _weekdays(values)
    if day_type != "any" and not result:
        raise ValueError(
            "Kiemelt vagy nem kiemelt naptípusnál legalább egy napot válassz."
        )
    return result


def _text_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = values.split(",")
    return list(dict.fromkeys(_text(value) for value in (values or []) if _text(value)))


def _validate_period(
    valid_from_value: Any,
    valid_to_value: Any,
) -> tuple[str, str | None]:
    valid_from = _date(valid_from_value, "kezdő")
    valid_to = (
        _date(valid_to_value, "záró")
        if valid_to_value not in (None, "")
        else None
    )
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("A záró dátum nem lehet korábbi a kezdő dátumnál.")
    return valid_from.isoformat(), valid_to.isoformat() if valid_to else None


def _validate_range(
    minimum: Any,
    maximum: Any,
    label: str,
) -> tuple[float | None, float | None]:
    minimum_value = _optional_number(minimum)
    maximum_value = _optional_number(maximum)
    if (
        minimum_value is not None
        and maximum_value is not None
        and maximum_value < minimum_value
    ):
        raise ValueError(f"A(z) {label} felső értéke nem lehet kisebb az alsónál.")
    return minimum_value, maximum_value


def validate_rate_parameter(payload: dict[str, Any]) -> dict[str, Any]:
    name = _text(payload.get("parameter_name"))
    if not name:
        raise ValueError("A paraméter megnevezése kötelező.")

    parameter_kind = _text(payload.get("parameter_kind")).lower()
    if parameter_kind not in RATE_KINDS:
        raise ValueError("Ismeretlen díjparaméter-típus.")

    day_type = _text(payload.get("day_type")).lower()
    if day_type not in DAY_TYPES:
        raise ValueError("Ismeretlen naptípus.")

    route_type = _text(payload.get("route_type")).lower()
    if route_type not in ROUTE_TYPES:
        raise ValueError("Ismeretlen túratípus.")

    calculation_unit = _text(payload.get("calculation_unit")).lower()
    if calculation_unit not in CALCULATION_UNITS:
        raise ValueError("Ismeretlen elszámolási egység.")

    threshold_min, threshold_max = _validate_range(
        payload.get("threshold_min"),
        payload.get("threshold_max"),
        "mutatósáv",
    )
    duration_min, duration_max = _validate_range(
        payload.get("planned_duration_min_hours"),
        payload.get("planned_duration_max_hours"),
        "túrahossz",
    )
    valid_from, valid_to = _validate_period(
        payload.get("valid_from"),
        payload.get("valid_to"),
    )

    return {
        "parameter_name": name,
        "parameter_kind": parameter_kind,
        "level_code": _optional_text(payload.get("level_code")),
        "day_type": day_type,
        "weekdays": _validated_weekdays(
            payload.get("weekdays"),
            day_type,
        ),
        "route_type": route_type,
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "threshold_min": threshold_min,
        "threshold_max": threshold_max,
        "threshold_min_inclusive": bool(
            payload.get("threshold_min_inclusive", True)
        ),
        "threshold_max_inclusive": bool(
            payload.get("threshold_max_inclusive", True)
        ),
        "planned_duration_min_hours": duration_min,
        "planned_duration_max_hours": duration_max,
        "company_amount_huf": _nonnegative_int(
            payload.get("company_amount_huf"),
            "JITT-összeg",
        ),
        "courier_amount_huf": _nonnegative_int(
            payload.get("courier_amount_huf"),
            "futárösszeg",
        ),
        "calculation_unit": calculation_unit,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "priority": int(payload.get("priority") or 100),
        "is_active": bool(payload.get("is_active", True)),
        "note": _optional_text(payload.get("note")),
    }


def validate_periodic_bonus(payload: dict[str, Any]) -> dict[str, Any]:
    name = _text(payload.get("bonus_name"))
    if not name:
        raise ValueError("A bónusz megnevezése kötelező.")

    day_type = _text(payload.get("day_type")).lower()
    if day_type not in DAY_TYPES:
        raise ValueError("Ismeretlen naptípus.")

    route_type = _text(payload.get("route_type")).lower()
    if route_type not in ROUTE_TYPES:
        raise ValueError("Ismeretlen túratípus.")

    calculation_unit = _text(payload.get("calculation_unit")).lower()
    if calculation_unit not in CALCULATION_UNITS:
        raise ValueError("Ismeretlen elszámolási egység.")

    condition_metric = _text(payload.get("condition_metric")).lower()
    if condition_metric not in PERIODIC_CONDITIONS:
        raise ValueError("Ismeretlen időszakos bónuszfeltétel.")

    condition_min, condition_max = _validate_range(
        payload.get("condition_min"),
        payload.get("condition_max"),
        "bónuszfeltétel",
    )
    if condition_metric == "none":
        condition_min = None
        condition_max = None

    valid_from, valid_to = _validate_period(
        payload.get("valid_from"),
        payload.get("valid_to"),
    )
    maximum_awards = payload.get("maximum_awards_per_courier")
    maximum_awards = (
        _nonnegative_int(maximum_awards, "maximális jóváírás")
        if maximum_awards not in (None, "")
        else None
    )
    separate_invoice_line = bool(
        payload.get("show_as_separate_invoice_line", False)
    )
    invoice_line_note = _optional_text(payload.get("invoice_line_note"))
    if separate_invoice_line and not invoice_line_note:
        raise ValueError(
            "A külön számlasorhoz számlasor-megjegyzés szükséges."
        )

    return {
        "bonus_name": name,
        "day_type": day_type,
        "weekdays": _validated_weekdays(
            payload.get("weekdays"),
            day_type,
        ),
        "route_type": route_type,
        "warehouse_code": _optional_text(payload.get("warehouse_code")),
        "courier_ids": _text_list(payload.get("courier_ids")),
        "company_names": _text_list(payload.get("company_names")),
        "condition_metric": condition_metric,
        "condition_min": condition_min,
        "condition_max": condition_max,
        "company_amount_huf": _nonnegative_int(
            payload.get("company_amount_huf"),
            "JITT-összeg",
        ),
        "courier_amount_huf": _nonnegative_int(
            payload.get("courier_amount_huf"),
            "futárösszeg",
        ),
        "calculation_unit": calculation_unit,
        "maximum_awards_per_courier": maximum_awards,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "priority": int(payload.get("priority") or 100),
        "is_active": bool(payload.get("is_active", True)),
        "show_as_separate_invoice_line": separate_invoice_line,
        "invoice_line_note": invoice_line_note,
        "note": _optional_text(payload.get("note")),
    }


def parameter_status(
    valid_from_value: Any,
    valid_to_value: Any,
    is_active: bool,
    today: date | None = None,
) -> str:
    if not is_active:
        return "Inaktív"
    current_date = today or date.today()
    valid_from = _date(valid_from_value, "kezdő")
    valid_to = (
        _date(valid_to_value, "záró")
        if valid_to_value not in (None, "")
        else None
    )
    if current_date < valid_from:
        return "Jövőbeni"
    if valid_to is not None and current_date > valid_to:
        return "Lejárt"
    return "Aktív"


def read_rate_parameters(client: Any) -> pd.DataFrame:
    response = (
        _table(client, RATE_TABLE)
        .select("*")
        .is_("deleted_at", "null")
        .order("is_active", desc=True)
        .order("valid_from", desc=True)
        .order("parameter_name")
        .execute()
    )
    return pd.DataFrame(response.data or [])


def read_periodic_bonuses(client: Any) -> pd.DataFrame:
    response = (
        _table(client, PERIODIC_BONUS_TABLE)
        .select("*")
        .is_("deleted_at", "null")
        .order("is_active", desc=True)
        .order("valid_from", desc=True)
        .order("bonus_name")
        .execute()
    )
    return pd.DataFrame(response.data or [])


def _audit_payload(payload: dict[str, Any], actor: str, *, create: bool) -> dict[str, Any]:
    result = dict(payload)
    normalized_actor = _text(actor) or "unknown"
    result["updated_by"] = normalized_actor
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    if create:
        result["created_by"] = normalized_actor
    return result


def save_rate_parameter(
    client: Any,
    payload: dict[str, Any],
    actor: str,
    parameter_id: str | None = None,
) -> dict[str, Any]:
    clean_payload = _audit_payload(
        validate_rate_parameter(payload),
        actor,
        create=not parameter_id,
    )
    query = _table(client, RATE_TABLE)
    if parameter_id:
        response = query.update(clean_payload).eq("id", parameter_id).execute()
    else:
        response = query.insert(clean_payload).execute()
    rows = response.data or []
    return rows[0] if rows else clean_payload


def save_periodic_bonus(
    client: Any,
    payload: dict[str, Any],
    actor: str,
    bonus_id: str | None = None,
) -> dict[str, Any]:
    clean_payload = _audit_payload(
        validate_periodic_bonus(payload),
        actor,
        create=not bonus_id,
    )
    query = _table(client, PERIODIC_BONUS_TABLE)
    if bonus_id:
        response = query.update(clean_payload).eq("id", bonus_id).execute()
    else:
        response = query.insert(clean_payload).execute()
    rows = response.data or []
    return rows[0] if rows else clean_payload


def delete_rate_parameter(
    client: Any,
    parameter_id: str,
    actor: str,
) -> None:
    _table(client, RATE_TABLE).update(
        {
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": _text(actor) or "unknown",
            "is_active": False,
        }
    ).eq("id", parameter_id).is_("deleted_at", "null").execute()


def delete_periodic_bonus(
    client: Any,
    bonus_id: str,
    actor: str,
) -> None:
    _table(client, PERIODIC_BONUS_TABLE).update(
        {
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": _text(actor) or "unknown",
            "is_active": False,
        }
    ).eq("id", bonus_id).is_("deleted_at", "null").execute()
