from __future__ import annotations

import argparse
import copy
from datetime import date, datetime
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.giriton_attendance_db import upsert_giriton_attendance_rows  # noqa: E402
from resources.giriton_attendance_uidl import (  # noqa: E402
    parse_attendance_uidl_rows,
    walk_payloads,
)
from scripts.live_giriton_shift_list import (  # noqa: E402
    create_driver,
    login,
    select_all_departments,
    set_giriton_date,
)


DEFAULT_UIDL_URL = "https://kiflihu.giriton.com/?v-r=uidl&v-uiId=0"
UIDL_SESSION_EXPIRED_ERROR = "A Giriton UIDL session lejart."
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def clean(value: Any) -> str:
    return str(value or "").strip()


def env_first(*names: str) -> str:
    for name in names:
        value = clean(os.getenv(name))
        if value:
            return value
    return ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip()


def parse_json_or_curl(text: str) -> Any:
    value = clean(text)
    if not value:
        return None
    if value[0] in "[{":
        return json.loads(value)
    return parse_curl_command(value)


def parse_uidl_json_body(data: str) -> Any:
    raw = clean(data)
    candidates: list[str] = []

    def add_candidate(value: str) -> None:
        value = clean(value)
        if value and value not in candidates:
            candidates.append(value)

    add_candidate(raw)
    add_candidate(html.unescape(raw))

    for value in list(candidates):
        normalized = value.replace("^", "").strip()
        if (
            len(normalized) >= 2
            and normalized[0] == normalized[-1]
            and normalized[0] in {"'", '"'}
        ):
            normalized = normalized[1:-1].strip()
        add_candidate(normalized)
        add_candidate(normalized.replace('""', '"'))
        add_candidate(normalized.replace('\\"', '"'))

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, str) and clean(parsed)[:1] in {"{", "["}:
                parsed = json.loads(parsed)
            return parsed
        except json.JSONDecodeError as error:
            last_error = error

    raise RuntimeError(f"A cURL body nem ervenyes JSON: {last_error}")


def parse_curl_command(command: str) -> dict[str, Any]:
    text = command.replace("`", "\\")
    text = re.sub(r"\\\s*\r?\n", " ", text)
    text = re.sub(r"\^\s*\r?\n", " ", text)

    plain_text = text.replace("^", "")
    url = ""
    for match in re.finditer(r"https://kiflihu\.giriton\.com/[^\s\]\)\"]+", plain_text):
        candidate = match.group(0).replace("\\&", "&")
        if "v-r=uidl" in candidate:
            url = candidate
            break

    cookie = ""
    cookie_match = re.search(
        r"(?:-b|--cookie)\s+\^?\"(?P<cookie>.*?)\^?\"",
        text,
        flags=re.I | re.S,
    )
    if cookie_match:
        cookie = cookie_match.group("cookie").replace("^", "").strip()
    else:
        header_cookie_match = re.search(
            r"(?:-H|--header)\s+\^?\"cookie:\s*(?P<cookie>.*?)\^?\"",
            text,
            flags=re.I | re.S,
        )
        if header_cookie_match:
            cookie = header_cookie_match.group("cookie").replace("^", "").strip()

    data_match = re.search(
        r"(?:--data-raw|--data-binary|--data|-d)\s+\^?\"(?P<data>.*)\^?\"",
        text,
        flags=re.I | re.S,
    )
    if not data_match:
        raise RuntimeError("A cURL-ben nem talaltam UIDL JSON bodyt (--data-raw vagy -d).")

    request_json = parse_uidl_json_body(data_match.group("data"))

    return {
        "url": url or uidl_url(),
        "cookie": cookie,
        "request_json": request_json,
    }


def read_request_source(cli_request_file: str = "") -> Any:
    if cli_request_file:
        return parse_json_or_curl(read_text(Path(cli_request_file)))

    curl_inline = env_first(
        "GIRITON_ATTENDANCE_UIDL_CURL",
        "GIRITON_UIDL_CURL",
    )
    if curl_inline:
        return parse_curl_command(curl_inline)

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
        return parse_json_or_curl(inline)

    path = env_first(
        "GIRITON_ATTENDANCE_UIDL_REQUEST_FILE",
        "GIRITON_UIDL_REQUEST_FILE",
    )
    if path:
        return parse_json_or_curl(read_text(Path(path)))

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

    inherited_url = ""
    inherited_cookie = ""
    if isinstance(source, dict):
        inherited_url = clean(source.get("url"))
        inherited_cookie = clean(source.get("cookie"))

    if isinstance(source, dict) and isinstance(source.get("events"), list):
        source = source["events"]

    if isinstance(source, dict) and isinstance(source.get("request_json"), dict):
        source = [source]

    if looks_like_uidl_request(source):
        return [{"url": inherited_url or uidl_url(), "cookie": inherited_cookie, "request_json": source}]

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
                        "cookie": clean(item.get("cookie")),
                        "request_json": request_json,
                    }
                )
            elif looks_like_uidl_request(item):
                templates.append({"url": inherited_url or uidl_url(), "cookie": inherited_cookie, "request_json": item})
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
        raise RuntimeError(UIDL_SESSION_EXPIRED_ERROR)
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


def attendance_uidl_missing_reason(request_file: str = "") -> str:
    templates = normalize_request_templates(read_request_source(request_file))
    if not templates:
        return "missing_uidl_request_sequence"

    template_cookie = next((clean(template.get("cookie")) for template in templates if clean(template.get("cookie"))), "")
    if not (uidl_cookie() or template_cookie):
        return "missing_uidl_cookie"

    return "missing_uidl_cookie_or_attendance_request_sequence"


def fetch_attendance_uidl_payloads(
    work_date: date,
    *,
    request_file: str = "",
    timeout: int = 60,
) -> list[Any] | None:
    templates = normalize_request_templates(read_request_source(request_file))
    template_cookie = next((clean(template.get("cookie")) for template in templates if clean(template.get("cookie"))), "")
    cookie = uidl_cookie() or template_cookie
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


def giriton_login_credentials() -> tuple[str, str]:
    return (
        env_first("GIRITON_USER", "GIRITON_USERNAME"),
        env_first("GIRITON_PASSWORD"),
    )


def has_giriton_login_credentials() -> bool:
    user, password = giriton_login_credentials()
    return bool(user and password)


def open_attendance(driver, timeout: int) -> None:
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.visibility_of_element_located((By.XPATH, '//*[@id="layMenuItems"]/div[2]/div/span')))
    driver.find_element(By.XPATH, '//*[@id="layMenuItems"]/div[2]/div/span').click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".v-grid, .v-datefield")))


def install_vaadin_response_capture(driver) -> None:
    driver.execute_script(
        r"""
window.__giritonAttendanceResponses = window.__giritonAttendanceResponses || [];

function patchResponses(root) {
  const nodes = [root, ...root.querySelectorAll('*')];
  for (const node of nodes) {
    if (!node || node.__giritonAttendancePatched || typeof node.setResponse !== 'function') {
      continue;
    }
    const original = node.setResponse;
    node.setResponse = function(response) {
      try {
        window.__giritonAttendanceResponses.push(response);
      } catch (error) {
      }
      return original.apply(this, arguments);
    };
    node.__giritonAttendancePatched = true;
  }
}

patchResponses(document);
if (!window.__giritonAttendancePatchInterval) {
  window.__giritonAttendancePatchInterval = window.setInterval(() => patchResponses(document), 500);
}
return true;
"""
    )


def captured_vaadin_responses(driver) -> list[Any]:
    return driver.execute_script(
        r"""
const responses = window.__giritonAttendanceResponses || [];
window.__giritonAttendanceResponses = [];
return responses;
"""
    ) or []


def fetch_attendance_browser_payloads(work_date: date, *, timeout: int = 60) -> list[Any] | None:
    user, password = giriton_login_credentials()
    if not user or not password:
        return None

    driver = create_driver(False, "")
    try:
        login(driver, user, password, timeout)
        install_vaadin_response_capture(driver)
        open_attendance(driver, timeout)
        time.sleep(1)
        try:
            select_all_departments(driver, timeout)
        except Exception as error:
            print(f"GIRITON_ATTENDANCE_SELECT_ALL_SKIPPED={type(error).__name__}: {error}", flush=True)
        install_vaadin_response_capture(driver)
        set_giriton_date(driver, work_date)
        time.sleep(3)
        responses = captured_vaadin_responses(driver)
        if not responses:
            time.sleep(2)
            responses = captured_vaadin_responses(driver)
        return responses
    finally:
        driver.quit()


def payload_debug_summary(payloads: list[Any]) -> list[dict[str, Any]]:
    summaries = []
    for index, payload in enumerate(payloads or []):
        payloads_seen = list(walk_payloads(payload))
        dicts = [item for item in payloads_seen if isinstance(item, dict)]
        rpc_count = sum(
            len(item.get("rpc") or [])
            for item in dicts
            if isinstance(item.get("rpc"), list)
        )
        state_count = sum(
            len(item.get("state") or {})
            for item in dicts
            if isinstance(item.get("state"), dict)
        )
        execute_count = sum(
            len(item.get("execute") or [])
            for item in dicts
            if isinstance(item.get("execute"), list)
        )
        meta_values = [
            item.get("meta")
            for item in dicts
            if isinstance(item.get("meta"), dict) and item.get("meta")
        ]
        summaries.append(
            {
                "index": index,
                "top_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
                "syncId": payload.get("syncId") if isinstance(payload, dict) else None,
                "clientId": payload.get("clientId") if isinstance(payload, dict) else None,
                "rpc_count": rpc_count,
                "state_count": state_count,
                "execute_count": execute_count,
                "meta": meta_values[:3],
            }
        )
    return summaries


def write_debug_payloads(payloads: list[Any], debug_dir: str, work_date: date) -> str:
    if not clean(debug_dir):
        return ""
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_path = path / f"giriton_attendance_uidl_{work_date.isoformat()}.json"
    output_path.write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


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


def parse_payload_rows(payloads: list[Any], target_date: date) -> list[dict[str, Any]]:
    return dedupe_rows(
        [
            row
            for payload in payloads or []
            for row in parse_attendance_uidl_rows(
                payload,
                default_work_date=target_date.isoformat(),
            )
        ]
    )


def sync_giriton_attendance_uidl_direct(
    work_date: date | None = None,
    *,
    dry_run: bool = False,
    debug_dir: str = "",
    request_file: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    target_date = work_date or datetime.now(BUDAPEST_TZ).date()
    payload_source = "uidl_request"
    try:
        payloads = fetch_attendance_uidl_payloads(
            target_date,
            request_file=request_file,
            timeout=timeout,
        )
    except RuntimeError as error:
        if UIDL_SESSION_EXPIRED_ERROR not in str(error) or not has_giriton_login_credentials():
            raise
        payload_source = "browser_login_uidl_capture"
        payloads = fetch_attendance_browser_payloads(target_date, timeout=timeout)

    if payloads is None:
        payload_source = "browser_login_uidl_capture"
        payloads = fetch_attendance_browser_payloads(target_date, timeout=timeout)

    if payloads is None:
        return {
            "status": "skipped",
            "reason": attendance_uidl_missing_reason(request_file),
            "work_date": target_date.isoformat(),
            "rows": 0,
        }

    rows = parse_payload_rows(payloads, target_date)
    if not rows and payload_source != "browser_login_uidl_capture" and has_giriton_login_credentials():
        fallback_payloads = fetch_attendance_browser_payloads(target_date, timeout=timeout)
        fallback_rows = parse_payload_rows(fallback_payloads or [], target_date)
        if fallback_payloads:
            payloads = fallback_payloads
            payload_source = "browser_login_uidl_capture"
            rows = fallback_rows

    if dry_run:
        result = {
            "status": "dry_run",
            "work_date": target_date.isoformat(),
            "source": payload_source,
            "payloads": len(payloads),
            "rows": len(rows),
        }
        if not rows:
            result["payload_summary"] = payload_debug_summary(payloads)
        debug_path = write_debug_payloads(payloads, debug_dir, target_date)
        if debug_path:
            result["debug_payloads"] = debug_path
        return result

    result = upsert_giriton_attendance_rows(rows)
    sync_result = {
        "status": result.get("status", "ok"),
        "work_date": target_date.isoformat(),
        "source": payload_source,
        "payloads": len(payloads),
        "rows": result.get("rows", len(rows)),
        "stored_rows": result.get("stored_rows"),
    }
    if not rows:
        sync_result["payload_summary"] = payload_debug_summary(payloads)
    debug_path = write_debug_payloads(payloads, debug_dir, target_date)
    if debug_path:
        sync_result["debug_payloads"] = debug_path
    return sync_result


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
        "--require-rows",
        action="store_true",
        help="Hibaval alljon meg, ha nem sikerult sort menteni.",
    )
    parser.add_argument(
        "--request-file",
        default="",
        help="DevToolsból mentett UIDL request vagy request-sorozat JSON.",
    )
    parser.add_argument("--debug-dir", default="", help="UIDL válasz mentése ide hibakereséshez.")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    result = sync_giriton_attendance_uidl_direct(
        parse_date(args.date),
        dry_run=args.dry_run,
        debug_dir=args.debug_dir,
        request_file=args.request_file,
        timeout=args.timeout,
    )
    print("GIRITON_ATTENDANCE_UIDL_SYNC=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.require_rows and (
        result.get("status") in {"skipped", "empty"}
        or int(result.get("rows") or 0) <= 0
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
