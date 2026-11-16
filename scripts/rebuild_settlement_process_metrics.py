r"""Rebuild the persisted settlement-process metrics from immutable PWA events.

Usage (from the repository root):
    .\.venv\Scripts\python.exe scripts\rebuild_settlement_process_metrics.py
    .\.venv\Scripts\python.exe scripts\rebuild_settlement_process_metrics.py --months 2026-07 2026-08 2026-09 2026-10

The command updates both linked tables for every selected month:
``settlement.monthly_process_metric_summary`` and
``settlement.courier_monthly_process_metric``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # The production environment already provides variables.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

from page.settlement_process_metrics import (  # noqa: E402
    _available_months,
    recalculate_and_save_monthly_process_metrics,
)


def _parse_month(value: str) -> date:
    try:
        return date.fromisoformat(f"{value.strip()}-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("A hónap formátuma ÉÉÉÉ-HH, például 2026-09.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Havi és futár-hónap elszámolási mutatók újraépítése.")
    parser.add_argument("--months", nargs="+", type=_parse_month, help="Csak ezek a hónapok épüljenek újra.")
    parser.add_argument("--actor", default="metric-rebuild", help="A mentés naplójában megjelenő végrehajtó.")
    args = parser.parse_args()

    months = args.months or _available_months()
    if not months:
        print("Nincs újraépíthető hónap.")
        return 0

    for month in sorted(set(months)):
        summary = recalculate_and_save_monthly_process_metrics(month, args.actor)
        print(
            f"{month:%Y-%m}: {summary.get('completed_flow_count', 0)} lezárt folyamat, "
            f"{summary.get('complaint_total', 0)} reklamáció, "
            f"{summary.get('response_count', 0)} megválaszolt/lezárt"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
