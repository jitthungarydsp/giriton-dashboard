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

    order_total = _coerce_int(fallback.get("order_count"))
    route_total = _coerce_int(fallback.get("route_count"))
    return {"route_total": route_total, "order_total": order_total}
