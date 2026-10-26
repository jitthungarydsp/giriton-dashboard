"""Book Hub API OVERLAP failures in Giriton, one candidate at a time."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import get_supabase_config


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


def enrich_candidates_from_hub_identity(candidates: list[dict[str, Any]]) -> int:
    """Use the Hub roster's exact Giriton display name for each candidate.

    The overlap artifact may contain the short MuszakPro name.  The Hub
    identity table contains the name Giriton actually searches, including the
    numeric courier ID (for example ``Komjáti 8185 Ákos``).
    """
    if not candidates:
        return 0

    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        print("GIRITON_OVERLAP_IDENTITY_ENRICH_SKIPPED missing_supabase_config", flush=True)
        return 0

    courier_ids = sorted({clean(item.get("courier_id")) for item in candidates if clean(item.get("courier_id"))})
    if not courier_ids:
        return 0

    response = requests.get(
        f"{supabase_url.rstrip('/')}/rest/v1/courier_hub_courier_identity_raw",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params={
            "select": "courier_id,name_json,name_without_identifier,giriton_person_id,email",
            "dsp_id": "eq.8",
            "courier_id": f"in.({','.join(courier_ids)})",
            "limit": "1000",
        },
        timeout=60,
    )
    response.raise_for_status()
    identities = response.json()
    by_id = {
        clean(row.get("courier_id")): row
        for row in identities
        if isinstance(row, dict) and clean(row.get("courier_id"))
    }

    enriched = 0
    for candidate in candidates:
        identity = by_id.get(clean(candidate.get("courier_id")))
        if not identity:
            continue
        exact_name = clean(identity.get("name_json"))
        if exact_name and exact_name != clean(candidate.get("courier_name")):
            candidate["courier_name"] = exact_name
            enriched += 1
        if clean(identity.get("email")):
            candidate["email"] = clean(identity["email"])
        candidate["giriton_person_id"] = clean(identity.get("giriton_person_id"))

    print(
        f"GIRITON_OVERLAP_IDENTITY_ENRICH matched={len(by_id)} enriched={enriched}",
        flush=True,
    )
    return enriched


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
    try:
        enrich_candidates_from_hub_identity(candidates)
    except Exception as exc:
        # Keep the batch running with the artifact's values if the optional
        # identity lookup is temporarily unavailable.
        print(
            f"GIRITON_OVERLAP_IDENTITY_ENRICH_FAILED {type(exc).__name__}: {exc}",
            flush=True,
        )
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
