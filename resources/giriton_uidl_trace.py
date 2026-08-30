from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from robot.libraries.BuiltIn import BuiltIn


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_label(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean(value)).strip("._")
    return text or "uidl_trace"


def _driver():
    selenium = BuiltIn().get_library_instance("SeleniumLibrary")
    return selenium.driver


def _uidl_events_from_logs(driver) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        logs = driver.get_log("performance")
    except Exception:
        return events

    for item in logs:
        try:
            message = json.loads(item.get("message") or "{}").get("message") or {}
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        params = message.get("params") or {}
        request_id = params.get("requestId")
        post_data = ""
        if method == "Network.requestWillBeSent":
            request = params.get("request") or {}
            url = _clean(request.get("url"))
            post_data = _clean(request.get("postData"))
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            url = _clean(response.get("url"))
        else:
            continue

        if "v-r=uidl" not in url:
            continue

        event: dict[str, Any] = {
            "method": method,
            "request_id": request_id,
            "url": url,
        }
        if post_data:
            try:
                event["request_json"] = json.loads(post_data)
            except json.JSONDecodeError:
                event["request_text"] = post_data

        if method == "Network.responseReceived" and request_id:
            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                )
                response_text = body.get("body") or ""
                event["response_json"] = json.loads(response_text)
            except Exception as error:
                event["response_error"] = str(error)

        events.append(event)

    return events


def start_giriton_uidl_trace() -> str:
    driver = _driver()
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    try:
        driver.get_log("performance")
    except Exception:
        pass
    return "OK"


def save_giriton_uidl_trace(label: str, output_dir: str = "results/giriton-uidl-booking") -> str:
    driver = _driver()
    events = _uidl_events_from_logs(driver)
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.utcnow():%Y%m%d%H%M%S}_{_safe_label(label)}.json"
    output_path = path / filename
    output_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return f"{output_path.as_posix()} events={len(events)}"
