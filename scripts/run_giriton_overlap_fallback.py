"""Book Hub API OVERLAP failures in Giriton, one candidate at a time."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_candidates(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"A failure fajl nem lista: {path}")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in payload:
        reason = clean(row.get("reason")).lower()
        if "overlap" not in reason:
            continue
        date = clean(row.get("work_date"))
        warehouse = clean(row.get("warehouse"))
        start = clean(row.get("muszakpro_shift_start")) or clean(row.get("hub_slot_from"))
        courier_id = clean(row.get("courier_id"))
        serial = clean(row.get("serial"))
        if not (date and warehouse and start and courier_id):
            continue
        key = serial or "|".join((date, warehouse, courier_id, start))
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "date": date,
            "warehouse": warehouse,
            "shift_start": start,
            "courier_id": courier_id,
            "courier_name": clean(row.get("courier_name")),
            "email": clean(row.get("email")),
            "serial": serial or f"{date[5:].replace('-', '/')}_{courier_id}_{warehouse}_{start[:5]}",
            "reason": clean(row.get("reason")),
        })
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="results/giriton-overlap-fallback")
    parser.add_argument("--trace-dir", default="results/giriton-overlap-fallback/uidl-trace")
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    trace_dir = Path(args.trace_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    candidates = read_candidates(Path(args.input))
    if args.max_items > 0:
        candidates = candidates[: args.max_items]

    results: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        command = [
            sys.executable,
            "scripts/giriton_uidl_fast_book.py",
            "--date", candidate["date"],
            "--warehouse", candidate["warehouse"],
            "--shift-start", candidate["shift_start"],
            "--courier-id", candidate["courier_id"],
            "--serial", candidate["serial"],
            "--courier-name", candidate["courier_name"],
            "--email", candidate["email"],
            "--trace-dir", str(trace_dir),
            "--output-dir", str(output_dir / "robot"),
            "--live" if not args.dry_run else "--dry-run",
        ]
        print(
            "GIRITON_OVERLAP_FALLBACK_START "
            f"item={index}/{len(candidates)} date={candidate['date']} "
            f"courier={candidate['courier_id']} warehouse={candidate['warehouse']} "
            f"shift_start={candidate['shift_start']} serial={candidate['serial']}",
            flush=True,
        )
        completed = subprocess.run(command, check=False)
        status = "success" if completed.returncode == 0 else "failed"
        results.append({**candidate, "status": status, "returncode": completed.returncode})
        print(
            f"GIRITON_OVERLAP_FALLBACK_{status.upper()} "
            f"date={candidate['date']} courier={candidate['courier_id']} "
            f"serial={candidate['serial']} returncode={completed.returncode}",
            flush=True,
        )

    summary = {
        "candidate_count": len(candidates),
        "success_count": sum(item["status"] == "success" for item in results),
        "failure_count": sum(item["status"] == "failed" for item in results),
        "dry_run": args.dry_run,
        "results": results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "GIRITON_OVERLAP_FALLBACK_DONE "
        f"candidates={summary['candidate_count']} success={summary['success_count']} "
        f"failed={summary['failure_count']} output={summary_path}",
        flush=True,
    )
    # Individual booking failures belong in the result list; they should not
    # hide the rest of the batch or prevent artifact upload.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
