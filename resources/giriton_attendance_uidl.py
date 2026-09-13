from __future__ import annotations

import html
import json
import re
from typing import Any


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_html(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>|</li>|</h3>|</b>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return clean(text)


def normalize_time(value: Any) -> str:
    text = clean(value)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return ""
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def parse_giriton_date(value: Any) -> str:
    text = clean(value)
    match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if not match:
        return ""
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return f"{year:04d}-{month:02d}-{day:02d}"


def maybe_embedded_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if '"rpc"' not in text and '"state"' not in text and '"hierarchy"' not in text:
        return {}
    for candidate in (text, "{" + text + "}"):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def walk_payloads(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_payloads(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_payloads(child)
    elif isinstance(value, str):
        parsed = maybe_embedded_payload(value)
        if parsed:
            yield from walk_payloads(parsed)


def extract_grid_row_dicts(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def walk(child: Any) -> None:
        if isinstance(child, dict):
            if isinstance(child.get("d"), dict) and isinstance(child.get("cd"), dict):
                rows.append(child)
            for nested in child.values():
                walk(nested)
        elif isinstance(child, list):
            for nested in child:
                walk(nested)

    for payload in walk_payloads(value):
        if not isinstance(payload, dict):
            continue
        rpc_items = payload.get("rpc")
        if not isinstance(rpc_items, list):
            continue
        for rpc in rpc_items:
            if not isinstance(rpc, list) or len(rpc) < 4:
                continue
            if clean(rpc[1]) != "com.vaadin.shared.data.DataCommunicatorClientRpc":
                continue
            if clean(rpc[2]) not in {"setData", "updateData"}:
                continue
            walk(rpc[3])

    return rows


def split_courier_text(value: Any) -> dict[str, str]:
    text = strip_html(value)
    match = re.search(r"\bD(\d{3,6})\b", text)
    if not match:
        return {"courier_name": text, "courier_code": "", "courier_id": ""}
    name = clean(text[: match.start()])
    return {
        "courier_name": name,
        "courier_code": f"D{match.group(1)}",
        "courier_id": match.group(1),
    }


def parse_detail_html(value: Any) -> dict[str, Any]:
    raw_html = str(value or "")
    text = html.unescape(raw_html)
    work_date = parse_giriton_date(text)

    activity_entries = []
    for match in re.finditer(
        r"<li>\s*([^<\s]+)\s*-\s*([^<\s]+)\s*\[([^\]]*)\]\s*:\s*([^<]+)</li>",
        text,
        flags=re.I,
    ):
        start_raw = clean(match.group(1))
        end_raw = clean(match.group(2))
        activity_entries.append(
            {
                "start": normalize_time(start_raw),
                "end": normalize_time(end_raw),
                "duration": clean(match.group(3)),
                "activity": strip_html(match.group(4)),
                "raw_start": start_raw,
                "raw_end": end_raw,
            }
        )

    calculated_activity = {}
    for label, amount in re.findall(r"<li>\s*([^:<]+?)\s*:\s*([^<]+)</li>", text, flags=re.I):
        label_text = clean(label)
        if label_text and label_text.lower() not in {"work", "left", "absent", "didn't come"}:
            calculated_activity[label_text] = clean(amount)

    planned_shifts = []
    shift_sections = re.findall(
        r"<b>\s*Shift\s*</b>\s*</br>\s*<ul>(.*?)</ul>",
        text,
        flags=re.I | re.S,
    )
    shift_html = "\n".join(shift_sections)
    for match in re.finditer(
        r"<li>\s*(.+?)\s*:\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*,\s*([^<]+)</li>",
        shift_html,
        flags=re.I,
    ):
        planned_shifts.append(
            {
                "label": clean(match.group(1)),
                "start": normalize_time(match.group(2)),
                "end": normalize_time(match.group(3)),
                "duration": clean(match.group(4)),
            }
        )

    starts = [entry["start"] for entry in activity_entries if entry.get("start")]
    ends = [entry["end"] for entry in activity_entries if entry.get("end")]
    activity_values = [
        entry["activity"]
        for entry in activity_entries
        if clean(entry.get("activity"))
    ]

    return {
        "work_date": work_date,
        "checkin_start": starts[0] if starts else "",
        "checkin_end": ends[-1] if ends else "",
        "activity_status": activity_values[-1] if activity_values else "",
        "activity_entries": activity_entries,
        "calculated_activity": calculated_activity,
        "planned_shifts": planned_shifts,
        "raw_details": strip_html(raw_html),
        "raw_detail_html": raw_html,
    }


def parse_attendance_uidl_rows(payload: Any, default_work_date: str = "") -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []

    for item in extract_grid_row_dicts(payload):
        data = item.get("d") if isinstance(item.get("d"), dict) else {}
        component_data = item.get("cd") if isinstance(item.get("cd"), dict) else {}
        courier = split_courier_text(data.get("1229", ""))
        detail = parse_detail_html(component_data.get("1235", ""))
        activity = strip_html(data.get("1406", "")) or detail.get("activity_status") or "Didn't come"
        planned_shifts = detail.get("planned_shifts") or []
        shift_text = ", ".join(
            clean(shift.get("label"))
            for shift in planned_shifts
            if clean(shift.get("label"))
        )

        if not courier.get("courier_name"):
            continue

        parsed_rows.append(
            {
                "work_date": detail.get("work_date") or default_work_date,
                "courier_name": courier.get("courier_name", ""),
                "courier_code": courier.get("courier_code", ""),
                "courier_id": courier.get("courier_id", ""),
                "shift_text": shift_text,
                "activity_status": activity,
                "checkin_start": detail.get("checkin_start", ""),
                "checkin_end": detail.get("checkin_end", ""),
                "raw_details": detail.get("raw_details", ""),
                "response_json": {
                    "source": "giriton_attendance_uidl",
                    "grid_key": clean(item.get("k")),
                    "courier_text": strip_html(data.get("1229", "")),
                    "courier": courier,
                    "activity_entries": detail.get("activity_entries", []),
                    "calculated_activity": detail.get("calculated_activity", {}),
                    "planned_shifts": planned_shifts,
                    "raw_detail_html": detail.get("raw_detail_html", ""),
                },
            }
        )

    return parsed_rows
