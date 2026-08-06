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
