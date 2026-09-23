from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clean(value) -> str:
    return str(value or "").strip()


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def run_step(label: str, command: list[str]) -> None:
    print(f"OPS_SHIFT_COMPARISON_REFRESH_STEP_START {label}", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    print(f"OPS_SHIFT_COMPARISON_REFRESH_STEP_OK {label}", flush=True)


def main() -> int:
    today = date.today()
    parser = argparse.ArgumentParser(
        description=(
            "Courier HUB adatok frissitese, majd az ops_shift_comparison "
            "ujraepitese egy lepesben."
        )
    )
    parser.add_argument("--date", default="", help="Egy nap frissitese YYYY-MM-DD.")
    parser.add_argument("--start-date", default="", help="Kezdo nap YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Zaro nap YYYY-MM-DD.")
    parser.add_argument("--days", type=int, default=1, help="Hany napot nezzen a kezdonaptol.")
    parser.add_argument(
        "--warehouse-ids",
        default=os.getenv("COURIER_HUB_WAREHOUSE_IDS") or "1,2",
        help="Courier HUB warehouse id-k vesszovel elvalasztva. BUD1=1, BUD2=2.",
    )
    parser.add_argument(
        "--dsp-id",
        type=int,
        default=int(os.getenv("COURIER_HUB_DSP_ID") or "8"),
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--source-limit", type=int, default=20000)
    parser.add_argument(
        "--output-dir",
        default="results/ops-shift-comparison-refresh",
    )
    parser.add_argument(
        "--skip-hub-sync",
        action="store_true",
        help="Csak az ops_shift_comparison ujraepitese, HUB lehuzas nelkul.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="HUB lehuzas probaja DB iras nelkul; az osszehasonlito DB iras kimarad.",
    )
    args = parser.parse_args()

    start_date = parse_date(args.start_date or args.date, today)
    if args.end_date:
        end_date = parse_date(args.end_date, start_date)
    else:
        end_date = start_date + timedelta(days=max(int(args.days), 1) - 1)

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_hub_sync:
        sync_command = [
            sys.executable,
            "scripts/sync_courier_hub_shift_blocks.py",
            "--start-date",
            start_date.isoformat(),
            "--end-date",
            end_date.isoformat(),
            "--warehouse-ids",
            clean(args.warehouse_ids),
            "--dsp-id",
            str(int(args.dsp_id)),
        ]
        if args.dry_run:
            sync_command.append("--dry-run")
        run_step("hub_shift_tables", sync_command)

    if args.dry_run:
        print(
            "OPS_SHIFT_COMPARISON_REFRESH_DRY_RUN comparison_db_write_skipped",
            flush=True,
        )
        return 0

    comparison_days = (end_date - start_date).days + 1
    for match_kind in ("exact", "alternative"):
        output_file = output_dir / f"{match_kind}-candidates.json"
        run_step(
            f"ops_shift_comparison_{match_kind}",
            [
                sys.executable,
                "scripts/select_shift_auto_booking_candidates.py",
                "--start-date",
                start_date.isoformat(),
                "--days",
                str(comparison_days),
                "--match-kind",
                match_kind,
                "--limit",
                str(max(int(args.limit), 1)),
                "--source-limit",
                str(max(int(args.source_limit), 1)),
                "--output",
                str(output_file),
            ],
        )

    print(
        "OPS_SHIFT_COMPARISON_REFRESH_DONE "
        f"start_date={start_date.isoformat()} end_date={end_date.isoformat()} "
        f"warehouse_ids={clean(args.warehouse_ids)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
