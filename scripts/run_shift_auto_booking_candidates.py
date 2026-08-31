from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROBOT_FILE = PROJECT_ROOT / "giriton_auto_booking_github.robot"
UIDL_FAST_BOOK_FILE = PROJECT_ROOT / "scripts" / "giriton_uidl_fast_book.py"


def clean(value) -> str:
    return str(value or "").strip()


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def load_candidates(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Nincs candidate fájl: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("A candidate fájl nem JSON lista.")
    return [dict(item or {}) for item in data]


def robot_command(candidate: dict, output_dir: Path, dry_run: bool) -> list[str]:
    return [
        "robot",
        "--outputdir",
        str(output_dir),
        "--variable",
        f"AUTO_BOOK_START_DATE:{clean(candidate.get('work_date'))}",
        "--variable",
        f"AUTO_BOOK_END_DATE:{clean(candidate.get('work_date'))}",
        "--variable",
        f"AUTO_BOOK_DRY_RUN:{'true' if dry_run else 'false'}",
        "--variable",
        f"AUTO_BOOK_SERIAL:{clean(candidate.get('serial'))}",
        "--variable",
        f"AUTO_BOOK_WAREHOUSE:{clean(candidate.get('warehouse')).upper()}",
        "--variable",
        f"AUTO_BOOK_EMAIL:{clean(candidate.get('email')).casefold()}",
        "--variable",
        f"AUTO_BOOK_SHIFT_START:{clean(candidate.get('shift_start'))}",
        str(ROBOT_FILE),
    ]


def uidl_command(candidate: dict, output_dir: Path, dry_run: bool) -> list[str]:
    courier_id = clean(candidate.get("courier_id")) or courier_id_from_serial(candidate.get("serial"))
    command = [
        sys.executable,
        str(UIDL_FAST_BOOK_FILE),
        "--date",
        clean(candidate.get("work_date")),
        "--warehouse",
        clean(candidate.get("warehouse")).upper(),
        "--shift-start",
        clean(candidate.get("shift_start")),
        "--courier-id",
        courier_id,
        "--courier-name",
        clean(candidate.get("courier_name")),
        "--email",
        clean(candidate.get("email")).casefold(),
        "--serial",
        clean(candidate.get("serial")),
        "--trace-dir",
        str(output_dir / "uidl-trace"),
        "--output-dir",
        str(output_dir / "robot"),
    ]
    command.append("--dry-run" if dry_run else "--live")
    return command


def validate_candidate(candidate: dict) -> list[str]:
    missing = []
    for key in ["work_date", "serial", "warehouse", "shift_start"]:
        if not clean(candidate.get(key)):
            missing.append(key)
    if not clean(candidate.get("courier_name")) and not clean(candidate.get("email")):
        missing.append("courier_name/email")
    if not clean(candidate.get("courier_id")) and not courier_id_from_serial(candidate.get("serial")):
        missing.append("courier_id")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A kiválasztott MűszakPro/Giriton foglalási sorokat egymás után lefoglalja."
    )
    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--output-root", default="results/shift-auto-booking")
    parser.add_argument("--phase", default="booking")
    parser.add_argument(
        "--engine",
        choices=["uidl", "robot"],
        default="uidl",
        help="uidl = uj kezi-jeloltes UIDL trace-es ut, robot = regi DB-s robot ut.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    candidates = load_candidates(Path(args.candidate_file))
    print(
        "SHIFT_AUTO_BOOK_RUN "
        f"phase={args.phase} engine={args.engine} candidates={len(candidates)} dry_run={args.dry_run}"
    )
    if not candidates:
        return

    failures = []
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    for index, candidate in enumerate(candidates, start=1):
        label = (
            f"{clean(candidate.get('work_date'))} "
            f"{clean(candidate.get('warehouse')).upper()} "
            f"{clean(candidate.get('shift_start'))} "
            f"{clean(candidate.get('courier_name'))} "
            f"serial={clean(candidate.get('serial'))}"
        )
        missing = validate_candidate(candidate)
        if missing:
            message = f"Hiányzó mezők: {', '.join(missing)}"
            print(f"SHIFT_AUTO_BOOK_SKIP {label} {message}")
            failures.append((label, message))
            if not args.continue_on_error:
                break
            continue

        output_dir = output_root / f"{args.phase}-{index:03d}"
        command = (
            uidl_command(candidate, output_dir, args.dry_run)
            if args.engine == "uidl"
            else robot_command(candidate, output_dir, args.dry_run)
        )
        print(f"SHIFT_AUTO_BOOK_ITEM_START {index}/{len(candidates)} {label}")
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            message = f"robot_exit_code={completed.returncode}"
            print(f"SHIFT_AUTO_BOOK_ITEM_FAIL {label} {message}")
            failures.append((label, message))
            if not args.continue_on_error:
                break
            continue

        print(f"SHIFT_AUTO_BOOK_ITEM_DONE {label}")

    if failures:
        print(f"SHIFT_AUTO_BOOK_FAILURES count={len(failures)}")
        for label, message in failures:
            print(f"SHIFT_AUTO_BOOK_FAILURE {label} {message}")
        if args.continue_on_error:
            print(
                f"SHIFT_AUTO_BOOK_RUN_PARTIAL phase={args.phase} "
                f"candidates={len(candidates)} failures={len(failures)}"
            )
            return
        raise SystemExit(1)

    print(f"SHIFT_AUTO_BOOK_RUN_DONE phase={args.phase} candidates={len(candidates)}")


if __name__ == "__main__":
    main()
