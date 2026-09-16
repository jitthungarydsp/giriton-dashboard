from __future__ import annotations

import argparse
import copy
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.giriton_attendance_db import upsert_giriton_attendance_rows  # noqa: E402
from resources.giriton_attendance_uidl import parse_attendance_uidl_rows  # noqa: E402


DEFAULT_UIDL_URL = "https://kiflihu.giriton.com/?v-r=uidl&v-uiId=0"
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def clean(value: Any) -> str:
    return str(value or "").strip()


def env_first(*names: str) -> str:
    for name in names:
        value = clean(os.getenv(name))
        if value:
            return value
    return ""


def read_request_source(cli_request_file: str = "") -> Any:
    if cli_request_file:
        return json.loads(Path(cli_request_file).read_text(encoding="utf-8-sig"))

    sequence_inline = env_first(
        "GIRITON_ATTENDANCE_UIDL_SEQUENCE_JSON",
        "GIRITON_UIDL_SEQUENCE_JSON",
    )
    if sequence_inline:
        return json.loads(sequence_inline)

    inline = env_first(
        "GIRITON_ATTENDANCE_UIDL_REQUEST_JSON",
        "GIRITON_UIDL_REQUEST_JSON",
    )
    if inline:
        return json.loads(inline)

    path = env_first(
        "GIRITON_ATTENDANCE_UIDL_REQUEST_FILE",
        "GIRITON_UIDL_REQUEST_FILE",
    )
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    return None


def looks_like_uidl_request(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if "execute" in value:
        return False
    return (
        isinstance(value.get("syncId"), int)
        and isinstance(value.get("clientId"), int)
        and (
            isinstance(value.get("rpc"), list)
            or isinstance(value.get("csrfToken"), str)
        )
    )


def normalize_request_templates(source: Any) -> list[dict[str, Any]]:
    if source is None:
        return []

    if isinstance(source, dict) and isinstance(source.get("events"), list):
        source = source["events"]

    if isinstance(source, dict) and isinstance(source.get("request_json"), dict):
        source = [source]

    if looks_like_uidl_request(source):
        return [{"url": uidl_url(), "request_json": source}]

    if isinstance(source, list):
        templates = []
        for item in source:
            if isinstance(item, dict) and isinstance(item.get("request_json"), dict):
                request_json = item["request_json"]
                if not looks_like_uidl_request(request_json):
                    continue
                templates.append(
                    {
                        "url": clean(item.get("url")) or uidl_url(),
                        "request_json": request_json,
                    }
                )
            elif looks_like_uidl_request(item):
                templates.append({"url": uidl_url(), "request_json": item})
        return templates

    return []


def adjust_uidl_counter_values(value: Any, *, sync_delta: int, client_delta: int) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key == "syncId" and isinstance(child, int):
                value[key] = child + sync_delta
            elif key == "clientId" and isinstance(child, int):
                value[key] = child + client_delta
            elif key == "promise" and isinstance(child, int):
                value[key] = child + client_delta
            else:
                adjust_uidl_counter_values(
                    child,
                    sync_delta=sync_delta,
                    client_delta=client_delta,
                )
    elif isinstance(value, list):
        for child in value:
            adjust_uidl_counter_values(
                child,
                sync_delta=sync_delta,
                client_delta=client_delta,
            )


def uidl_cookie() -> str:
    return env_first(
        "GIRITON_ATTENDANCE_UIDL_COOKIE",
        "GIRITON_UIDL_COOKIE",
        "GIRITON_COOKIE",
    )


def uidl_url() -> str:
    return env_first("GIRITON_ATTENDANCE_UIDL_URL", "GIRITON_UIDL_URL") or DEFAULT_UIDL_URL


def replace_attendance_date(value: Any, work_date: date) -> None:
    giriton_date = work_date.strftime("%d/%m/%Y")
    iso_date = work_date.isoformat()

    if isinstance(value, dict):
        for key, child in list(value.items()):
            key_text = str(key).casefold()
            if isinstance(child, str):
                if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", child.strip()):
                    value[key] = giriton_date
                elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.strip()):
                    value[key] = iso_date
            elif key_text == "year" and isinstance(child, int):
                value[key] = work_date.year
            elif key_text == "month" and isinstance(child, int):
                value[key] = work_date.month
            elif key_text == "day" and isinstance(child, int):
                value[key] = work_date.day
            else:
                replace_attendance_date(child, work_date)
    elif isinstance(value, list):
        if (
            len(value) >= 4
            and isinstance(value[2], str)
            and value[2] in {"update", "updateValueWithDelay"}
            and isinstance(value[3], list)
            and len(value[3]) >= 2
            and isinstance(value[3][1], dict)
        ):
            value[3][0] = giriton_date
            value[3][1]["YEAR"] = work_date.year
            value[3][1]["MONTH"] = work_date.month
            value[3][1]["DAY"] = work_date.day
        for child in value:
            replace_attendance_date(child, work_date)


def uidl_headers(cookie: str) -> dict[str, str]:
    return {
        "accept": "*/*",
        "accept-language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json; charset=UTF-8",
        "origin": "https://kiflihu.giriton.com",
        "pragma": "no-cache",
        "referer": "https://kiflihu.giriton.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "cookie": cookie,
    }


def raise_for_uidl_problem(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return
    if meta.get("sessionExpired"):
        raise RuntimeError("A Giriton UIDL session lejart.")
    app_error = meta.get("appError")
    if isinstance(app_error, dict):
        message = " | ".join(
            part
            for part in (
                clean(app_error.get("caption")),
                clean(app_error.get("message")),
                clean(app_error.get("details")),
            )
            if part
        )
        if message:
            raise RuntimeError(f"Giriton UIDL app error: {message}")


def fetch_attendance_uidl_payloads(
    work_date: date,
    *,
    request_file: str = "",
    timeout: int = 60,
) -> list[Any] | None:
    templates = normalize_request_templates(read_request_source(request_file))
    cookie = uidl_cookie()
    if not templates or not cookie:
        return None

    template_base_sync = templates[0]["request_json"].get("syncId")
    template_base_client = templates[0]["request_json"].get("clientId")
    if not isinstance(template_base_sync, int) or not isinstance(template_base_client, int):
        raise RuntimeError("Az Attendance UIDL request mintában nincs syncId/clientId.")

    session = requests.Session()
    payloads: list[Any] = []
    for template in templates:
        request_payload = copy.deepcopy(template["request_json"])
        adjust_uidl_counter_values(
            request_payload,
            sync_delta=0,
            client_delta=0,
        )
        replace_attendance_date(request_payload, work_date)
        response = session.post(
            clean(template.get("url")) or uidl_url(),
            headers=uidl_headers(cookie),
            json=request_payload,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        raise_for_uidl_problem(payload)
        payloads.append(payload)
    return payloads


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = []
    seen = set()
    for row in rows:
        response_json = row.get("response_json") if isinstance(row.get("response_json"), dict) else {}
        key = (
            clean(row.get("work_date")),
            clean(row.get("courier_id")),
            clean(row.get("courier_name")),
            clean(row.get("checkin_start")),
            clean(row.get("checkin_end")),
            clean(row.get("raw_details")),
            clean(response_json.get("grid_key")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def sync_giriton_attendance_uidl_direct(
    work_date: date | None = None,
    *,
    dry_run: bool = False,
    request_file: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    target_date = work_date or datetime.now(BUDAPEST_TZ).date()
    payloads = fetch_attendance_uidl_payloads(
        target_date,
        request_file=request_file,
        timeout=timeout,
    )
    if payloads is None:
        return {
            "status": "skipped",
            "reason": "missing_uidl_cookie_or_attendance_request_sequence",
            "work_date": target_date.isoformat(),
            "rows": 0,
        }

    rows = dedupe_rows(
        [
            row
            for payload in payloads
            for row in parse_attendance_uidl_rows(
                payload,
                default_work_date=target_date.isoformat(),
            )
        ]
    )
    if dry_run:
        return {
            "status": "dry_run",
            "work_date": target_date.isoformat(),
            "payloads": len(payloads),
            "rows": len(rows),
        }

    result = upsert_giriton_attendance_rows(rows)
    return {
        "status": result.get("status", "ok"),
        "work_date": target_date.isoformat(),
        "payloads": len(payloads),
        "rows": result.get("rows", len(rows)),
        "stored_rows": result.get("stored_rows"),
    }


def parse_date(value: str) -> date:
    text = clean(value)
    if not text:
        return datetime.now(BUDAPEST_TZ).date()
    return datetime.strptime(text, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Giriton Attendance direkt UIDL POST szinkron.")
    parser.add_argument("--date", default="", help="Nap YYYY-MM-DD. Üresen ma.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--request-file",
        default="",
        help="DevToolsból mentett UIDL request vagy request-sorozat JSON.",
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    result = sync_giriton_attendance_uidl_direct(
        parse_date(args.date),
        dry_run=args.dry_run,
        request_file=args.request_file,
        timeout=args.timeout,
    )
    print("GIRITON_ATTENDANCE_UIDL_SYNC=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
