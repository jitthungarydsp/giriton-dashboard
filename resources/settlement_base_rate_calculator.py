"""Safe, Excel-only calculation of the courier part of JITT base rates.

This module deliberately does not calculate bonuses, deductions or the JITT
company amount.  It is kept independent from Streamlit so its rules can be
tested before they are shown on the settlement page.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

import pandas as pd


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", normalized.lower())


def _value(record: dict[str, Any], *names: str) -> Any:
    lookup = {_key(key): value for key, value in record.items()}
    for name in names:
        if _key(name) in lookup:
            return lookup[_key(name)]
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _as_number(value: Any) -> float:
    if isinstance(value, str):
        value = value.replace(" ", "").replace(",", ".")
    parsed = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(parsed) else float(parsed)


def _route_type(value: Any) -> str | None:
    route = _key(value)
    if "express" in route:
        return "express"
    if "region" in route:
        return "regional"
    if route in {"normal", "standard", "varosi", "city", "urban"} or "normal" in route:
        return "normal"
    return None


def _is_live(rule: dict[str, Any], route_date: date) -> bool:
    if not bool(rule.get("is_active", True)) or rule.get("deleted_at"):
        return False
    valid_from = _as_date(rule.get("valid_from"))
    valid_to = _as_date(rule.get("valid_to"))
    return bool(valid_from and valid_from <= route_date and (not valid_to or route_date <= valid_to))


def _day_type(route_date: date, day_rules: list[dict[str, Any]]) -> str | None:
    candidates = []
    for rule in day_rules:
        if not _is_live(rule, route_date):
            continue
        weekdays = rule.get("weekdays") or []
        if route_date.isoweekday() in {int(day) for day in weekdays}:
            candidates.append(rule)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (int(item.get("priority") or 100), str(item.get("id") or "")))
    return _text(candidates[0].get("day_type")).lower() or None


def _matching_rate(
    route_date: date,
    day_type: str,
    route_type: str,
    warehouse: str,
    rate_rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for rule in rate_rules:
        if not _is_live(rule, route_date):
            continue
        if _text(rule.get("day_type")).lower() not in {day_type, "any"}:
            continue
        if _text(rule.get("route_type")).lower() not in {route_type, "any"}:
            continue
        rule_warehouse = _text(rule.get("warehouse_code"))
        if rule_warehouse and _key(rule_warehouse) != _key(warehouse):
            continue
        candidates.append(rule)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 100),
            0 if _text(item.get("warehouse_code")) else 1,
            0 if _text(item.get("day_type")).lower() == day_type else 1,
            0 if _text(item.get("route_type")).lower() == route_type else 1,
            str(item.get("id") or ""),
        )
    )
    return candidates[0]


def calculate_excel_courier_base_rates(
    rows: list[dict[str, Any]],
    day_rules: list[dict[str, Any]],
    rate_rules: list[dict[str, Any]],
) -> pd.DataFrame:
    """Return base-pay totals by Excel driver name.

    Only ``per_route`` and ``per_order`` base-rate rules are evaluated.  A
    fixed or hourly rule is intentionally skipped: without an agreed period or
    duration source, applying it would risk paying an incorrect amount.
    """
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = row.get("normalized_data", row)
        if not isinstance(record, dict):
            continue
        driver = _text(_value(record, "Driver", "Futár", "Courier", "Driver Name"))
        route_date = _as_date(_value(record, "Date", "Dátum", "Route Date"))
        route_type = _route_type(_value(record, "Route Type", "Túra típusa", "Tour Type"))
        warehouse = _text(_value(record, "Location", "Warehouse", "Raktár"))
        if not driver:
            continue
        item = totals.setdefault(
            driver,
            {"Futár": driver, "Nettó bevétel": 0.0, "Számolt túrák": 0, "Nem számolt túrák": 0},
        )
        if not route_date or not route_type:
            item["Nem számolt túrák"] += 1
            continue
        resolved_day_type = _day_type(route_date, day_rules)
        if not resolved_day_type:
            item["Nem számolt túrák"] += 1
            continue
        rate = _matching_rate(route_date, resolved_day_type, route_type, warehouse, rate_rules)
        if not rate:
            item["Nem számolt túrák"] += 1
            continue
        unit = _text(rate.get("calculation_unit")).lower()
        amount = _as_number(rate.get("courier_amount_huf"))
        if unit == "per_route":
            calculated = amount
        elif unit == "per_order":
            calculated = amount * _as_number(_value(record, "Orders", "Rendelések", "Order Count"))
        else:
            item["Nem számolt túrák"] += 1
            continue
        item["Nettó bevétel"] += calculated
        item["Számolt túrák"] += 1
    return pd.DataFrame(totals.values(), columns=["Futár", "Nettó bevétel", "Számolt túrák", "Nem számolt túrák"])
