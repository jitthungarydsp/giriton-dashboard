from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0
    return int(numeric)


def _has_row(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, pd.Series):
        return not value.empty
    if isinstance(value, Mapping):
        return bool(value)
    return False


def resolve_profile_route_metrics(route_detail: pd.DataFrame, summary_row: dict[str, Any] | pd.Series | None, fallback_row: dict[str, Any] | pd.Series | None = None) -> dict[str, int]:
    """Return route/order metrics for the courier profile.

    Prefer the auditable route-detail rows when they are available. Only fall back
    to the persisted settlement summary when the detail rows are missing or empty.
    """
    fallback = summary_row if _has_row(summary_row) else fallback_row if _has_row(fallback_row) else {}

    if not route_detail.empty:
        order_total = 0
        if "Rendelések" in route_detail.columns:
            order_total = int(pd.to_numeric(route_detail["Rendelések"], errors="coerce").fillna(0).sum())
        route_total = int(len(route_detail))
        return {"route_total": route_total, "order_total": order_total}

    order_total = max(
        _coerce_int(fallback.get("order_count")),
        _coerce_int(fallback.get("workload_order_count")),
        _coerce_int(fallback.get("total_orders")),
        _coerce_int(fallback.get("Rendelések")),
        _coerce_int(fallback.get("Rendelés")),
    )
    route_candidates = [
        _coerce_int(fallback.get("route_count")),
        _coerce_int(fallback.get("completed_route_count")),
        _coerce_int(fallback.get("calculated_routes")),
        _coerce_int(fallback.get("total_routes")),
        _coerce_int(fallback.get("Kör")),
        _coerce_int(fallback.get("Útvonalak")),
        _coerce_int(fallback.get("Számolt túrák")),
    ]
    typed_route_total = sum(
        _coerce_int(fallback.get(column))
        for column in ("normal_route_count", "express_route_count", "regional_route_count")
    )
    route_total = max(*route_candidates, typed_route_total)
    if _has_row(fallback_row) and fallback_row is not fallback:
        route_total = max(route_total, *(
            _coerce_int(fallback_row.get(key)) for key in
            ("Kör", "Útvonalak", "Számolt túrák", "route_count", "completed_route_count")
        ))
        order_total = max(order_total, *(
            _coerce_int(fallback_row.get(key)) for key in
            ("Rendelések", "Rendelés", "order_count")
        ))
    return {"route_total": route_total, "order_total": order_total}
