import pandas as pd

from resources.profile_route_metrics import resolve_profile_route_metrics


def test_prefers_route_detail_rows_for_profile_counts() -> None:
    route_detail = pd.DataFrame(
        {
            "Rendelések": [2, 3, 4],
            "Route ID": ["r1", "r2", "r3"],
        }
    )
    summary_row = {"order_count": 200, "route_count": 19}

    metrics = resolve_profile_route_metrics(route_detail, summary_row, None)

    assert metrics["route_total"] == 3
    assert metrics["order_total"] == 9


def test_falls_back_to_summary_row_when_route_detail_empty() -> None:
    summary_row = {"order_count": 15, "route_count": 19}

    metrics = resolve_profile_route_metrics(pd.DataFrame(), summary_row, None)

    assert metrics["route_total"] == 19
    assert metrics["order_total"] == 15


def test_saved_working_row_keeps_monthly_routes_when_summary_counts_are_zero() -> None:
    metrics = resolve_profile_route_metrics(
        pd.DataFrame(), {"route_count": 0, "order_count": 0},
        {"Kör": 50, "Rendelés": 574},
    )
    assert metrics == {"route_total": 50, "order_total": 574}


def test_hungarian_route_count_fields_are_accepted_without_summary() -> None:
    metrics = resolve_profile_route_metrics(
        pd.DataFrame(), {}, {"Útvonalak": 50, "Rendelések": 574},
    )
    assert metrics == {"route_total": 50, "order_total": 574}
