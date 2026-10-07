from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FALLBACK_REASON_TOKEN = "missing_hub_block"


def clean(value: object) -> str:
    return str(value or "").strip()


def normalize_email(value: object) -> str:
    return clean(value).casefold()


def is_fallback_reason(reason: object) -> bool:
    return FALLBACK_REASON_TOKEN in clean(reason).casefold()


def load_failure_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"A HUB_JOB_AUTOBOOKING failure fajl nem JSON lista: {path}")
    return [dict(item or {}) for item in data]


def build_candidate(record: dict[str, Any]) -> dict[str, str]:
    return {
        "work_date": clean(record.get("work_date")),
        "warehouse": clean(record.get("warehouse")).upper(),
        "shift_start": clean(record.get("muszakpro_shift_start")),
        "serial": clean(record.get("serial")),
        "courier_id": clean(record.get("courier_id")),
        "courier_name": clean(record.get("courier_name")),
        "email": normalize_email(record.get("email")),
        "hub_failure_reason": clean(record.get("reason")),
        "source": "hub_job_autobooking_fallback",
    }


def candidate_is_valid(candidate: dict[str, str]) -> bool:
    required = ("work_date", "warehouse", "shift_start", "serial")
    if any(not candidate.get(key) for key in required):
        return False
    return bool(candidate.get("courier_name") or candidate.get("email"))


def dedupe_key(candidate: dict[str, str]) -> tuple[str, str, str, str, str]:
    person_key = candidate.get("email") or candidate.get("courier_id") or candidate.get("courier_name", "")
    return (
        candidate.get("work_date", ""),
        candidate.get("warehouse", ""),
        candidate.get("shift_start", ""),
        candidate.get("serial", ""),
        person_key,
    )


def fallback_candidates(records: list[dict[str, Any]]) -> tuple[list[dict[str, str]], int, int]:
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    skipped_reason = 0
    skipped_invalid = 0

    for record in records:
        if not is_fallback_reason(record.get("reason")):
            skipped_reason += 1
            continue

        candidate = build_candidate(record)
        if not candidate_is_valid(candidate):
            skipped_invalid += 1
            continue

        key = dedupe_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    return candidates, skipped_reason, skipped_invalid


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "A HUB_JOB_AUTOBOOKING missing_hub_block sorait atalakitja a regi "
            "Giriton foglalo robot candidate formatumara."
        )
    )
    parser.add_argument("--input", default="results/hub-job-autobooking/failures.json")
    parser.add_argument("--output", default="results/hub-job-autobooking/giriton-fallback-candidates.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records = load_failure_records(input_path)
    candidates, skipped_reason, skipped_invalid = fallback_candidates(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "HUB_JOB_AUTOBOOKING_GIRITON_FALLBACK "
        f"input={input_path} records={len(records)} candidates={len(candidates)} "
        f"skipped_reason={skipped_reason} skipped_invalid={skipped_invalid} output={output_path}"
    )


if __name__ == "__main__":
    main()
