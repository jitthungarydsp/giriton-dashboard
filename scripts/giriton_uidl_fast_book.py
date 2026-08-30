from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROBOT_FILE = PROJECT_ROOT / "giriton_auto_booking_github.robot"


def clean(value: object) -> str:
    return str(value or "").strip()


def robot_variable(name: str, value: object) -> list[str]:
    return ["--variable", f"{name}:{clean(value)}"]


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gyors Giriton foglalasi proba. Jelenleg a mar bizonyitott robot folyamatot "
            "inditja kezi jelolttel es UIDL trace mentessel."
        )
    )
    parser.add_argument("--date", required=True, help="Foglalando nap YYYY-MM-DD formatumban.")
    parser.add_argument("--warehouse", required=True, help="Raktar, peldaul BUD1 vagy BUD2.")
    parser.add_argument("--shift-start", required=True, help="Muszak kezdes, peldaul 09:30.")
    parser.add_argument("--courier-id", default="", help="Futar ID.")
    parser.add_argument("--courier-name", default="", help="Futar neve.")
    parser.add_argument("--email", default="", help="Futar email cime, ha ismert.")
    parser.add_argument("--serial", default="", help="Opcionális teljes serial. Ha nincs megadva, a robot generalja.")
    parser.add_argument(
        "--trace-dir",
        default="uidl_booking_trace",
        help="UIDL trace mentese ide. Alap: uidl_booking_trace.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Robot output mappa. Ha ures, a robot alapertelmezett helyre ir.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Csak ellenorzes, nem foglal.")
    mode.add_argument("--live", action="store_true", help="Eles foglalas.")
    args = parser.parse_args()

    if not ROBOT_FILE.exists():
        raise FileNotFoundError(f"Nem talalom a robot fajlt: {ROBOT_FILE}")

    courier_id = clean(args.courier_id) or courier_id_from_serial(args.serial)
    courier_name = clean(args.courier_name)
    email = clean(args.email)
    if not courier_id:
        raise RuntimeError("Hiányzik a futár ID. Add meg --courier-id opcióval, vagy adj meg ID-t tartalmazó --serial értéket.")
    if not courier_name and not email:
        raise RuntimeError("Hiányzik a futár azonosító. Add meg --courier-name vagy --email opcióval.")

    dry_run = "false" if args.live else "true"

    command = [
        sys.executable,
        "-m",
        "robot",
    ]
    if clean(args.output_dir):
        command.extend(["--outputdir", clean(args.output_dir)])
    command.extend([
        *robot_variable("AUTO_BOOK_START_DATE", args.date),
        *robot_variable("AUTO_BOOK_END_DATE", args.date),
        *robot_variable("AUTO_BOOK_DRY_RUN", dry_run),
        *robot_variable("AUTO_BOOK_MANUAL_CANDIDATE", "true"),
        *robot_variable("AUTO_BOOK_COURIER_ID", courier_id),
        *robot_variable("AUTO_BOOK_COURIER_NAME", courier_name),
        *robot_variable("AUTO_BOOK_EMAIL", email),
        *robot_variable("AUTO_BOOK_SERIAL", args.serial),
        *robot_variable("AUTO_BOOK_WAREHOUSE", args.warehouse),
        *robot_variable("AUTO_BOOK_SHIFT_START", args.shift_start),
        *robot_variable("AUTO_BOOK_UIDL_TRACE", "true"),
        *robot_variable("AUTO_BOOK_UIDL_TRACE_DIR", args.trace_dir),
        str(ROBOT_FILE),
    ])

    print(
        "GIRITON_UIDL_FAST_BOOK "
        f"mode={'LIVE' if args.live else 'DRY_RUN'} "
        f"date={args.date} warehouse={args.warehouse} shift_start={args.shift_start} "
        f"courier_id={courier_id} courier_name={courier_name or '-'} email={email or '-'}"
    )
    if not clean(os.getenv("GIRITON_USER")):
        print("FIGYELEM: nincs GIRITON_USER kornyezeti valtozo beallitva.", file=sys.stderr)
    if not clean(os.getenv("GIRITON_PASSWORD")):
        print("FIGYELEM: nincs GIRITON_PASSWORD kornyezeti valtozo beallitva.", file=sys.stderr)

    return subprocess.call(command, cwd=PROJECT_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
