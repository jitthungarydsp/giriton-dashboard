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


def merged_state(value: Any) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for payload in walk_payloads(value):
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
            continue
        for key, item in payload["state"].items():
            if isinstance(item, dict):
                state[str(key)] = item
    return state


def state_text(item: Any) -> str:
    if not isinstance(item, dict):
        return strip_html(item)
    return strip_html(
        item.get("text")
        or item.get("caption")
        or item.get("description")
        or ""
    )


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


def looks_like_person_name(value: Any) -> bool:
    text = state_text(value)
    if not text or "<" in str(value):
        return False
    lowered = text.casefold()
    if any(part in lowered for part in ("just in time", "work", "shift", "user number")):
        return False
    if re.search(r"\bD\d{3,6}\b", text):
        return False
    words = [word for word in text.split(" ") if word]
    return len(words) >= 2 and any(re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]", word) for word in words)


def selected_courier_from_state(state: dict[str, dict[str, Any]]) -> dict[str, str]:
    code_candidates = []
    for key, item in state.items():
        text = state_text(item)
        match = re.fullmatch(r"D(\d{3,6})", text)
        if match:
            try:
                code_candidates.append((int(key), match.group(1)))
            except ValueError:
                code_candidates.append((0, match.group(1)))

    for numeric_key, courier_id in sorted(code_candidates):
        for offset in range(-5, 1):
            candidate = state.get(str(numeric_key + offset))
            if looks_like_person_name(candidate):
                name = state_text(candidate)
                return {
                    "courier_name": name,
                    "courier_code": f"D{courier_id}",
                    "courier_id": courier_id,
                }

    for item in state.values():
        courier = split_courier_text(state_text(item))
        if courier.get("courier_id"):
            return courier

    return {"courier_name": "", "courier_code": "", "courier_id": ""}


def find_courier_text(data: dict[str, Any]) -> str:
    for value in data.values():
        text = strip_html(value)
        if re.search(r"\bD\d{3,6}\b", text):
            return text
    return strip_html(data.get("1229", ""))


def find_detail_html(component_data: dict[str, Any]) -> str:
    for value in component_data.values():
        text = str(value or "")
        if "<h3>" in text and ("<ul" in text or "Shift" in text or "Calculated activity" in text):
            return text
    for value in component_data.values():
        text = str(value or "")
        if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", text):
            return text
    return str(component_data.get("1235", "") or "")


def find_activity_status(data: dict[str, Any], detail: dict[str, Any]) -> str:
    activity_words = {
        "work",
        "left",
        "didn't come",
        "didnt come",
        "absent",
        "holiday",
        "sick",
    }
    for value in data.values():
        text = strip_html(value)
        if text.lower() in activity_words:
            return "Didn't come" if text.lower() == "didnt come" else text
    return detail.get("activity_status") or "Didn't come"


def extract_selected_entry_rows(value: Any) -> list[dict[str, str]]:
    state = merged_state(value)
    entries: list[dict[str, str]] = []

    def resolved_cell_text(cell_value: Any) -> str:
        state_item = state.get(str(cell_value))
        return state_text(state_item) or strip_html(cell_value)

    for payload in walk_payloads(value):
        if not isinstance(payload, dict) or not isinstance(payload.get("rpc"), list):
            continue
        for rpc in payload["rpc"]:
            if not isinstance(rpc, list) or len(rpc) < 4:
                continue
            if clean(rpc[1]) != "com.vaadin.shared.data.DataCommunicatorClientRpc":
                continue
            if clean(rpc[2]) not in {"setData", "updateData"}:
                continue
            for item in extract_rows_from_rpc_args(rpc[3]):
                data = item.get("d") if isinstance(item.get("d"), dict) else {}
                if not data or isinstance(item.get("cd"), dict):
                    continue
                values = [resolved_cell_text(value) for value in data.values()]
                activity = next(
                    (
                        value
                        for value in values
                        if value.casefold() in {"work", "left", "didn't come", "didnt come"}
                    ),
                    "",
                )
                time_value = next((normalize_time(value) for value in values if normalize_time(value)), "")
                if not activity or not time_value:
                    continue
                entries.append(
                    {
                        "activity": "Didn't come" if activity.casefold() == "didnt come" else activity,
                        "start": time_value,
                        "end": "",
                        "duration": "",
                        "raw_start": time_value,
                        "raw_end": "",
                    }
                )

    return entries


def extract_rows_from_rpc_args(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def walk(child: Any) -> None:
        if isinstance(child, dict):
            if isinstance(child.get("d"), dict):
                rows.append(child)
            for nested in child.values():
                walk(nested)
        elif isinstance(child, list):
            for nested in child:
                walk(nested)

    walk(value)
    return rows


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
        courier = split_courier_text(find_courier_text(data))
        detail = parse_detail_html(find_detail_html(component_data))
        activity = find_activity_status(data, detail)
        planned_shifts = detail.get("planned_shifts") or []
        shift_text = ", ".join(
            clean(shift.get("label"))
            for shift in planned_shifts
            if clean(shift.get("label"))
        )
        raw_details = detail.get("raw_details", "")
        if not clean(raw_details):
            raw_details = clean(
                " | ".join(
                    part
                    for part in (
                        f"Shift: {shift_text}" if shift_text else "",
                        f"Status: {activity}" if activity else "",
                    )
                    if part
                )
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
                "raw_details": raw_details,
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

    if not parsed_rows:
        state = merged_state(payload)
        courier = selected_courier_from_state(state)
        entries = extract_selected_entry_rows(payload)
        if courier.get("courier_name") and entries:
            starts = [entry["start"] for entry in entries if entry.get("start")]
            ends = [entry["end"] for entry in entries if entry.get("end")]
            activity_values = [entry["activity"] for entry in entries if clean(entry.get("activity"))]
            parsed_rows.append(
                {
                    "work_date": default_work_date,
                    "courier_name": courier.get("courier_name", ""),
                    "courier_code": courier.get("courier_code", ""),
                    "courier_id": courier.get("courier_id", ""),
                    "shift_text": "",
                    "activity_status": activity_values[-1] if activity_values else "Work",
                    "checkin_start": starts[0] if starts else "",
                    "checkin_end": ends[-1] if ends else "",
                    "raw_details": "; ".join(
                        clean(
                            f"{entry.get('start') or ''}"
                            + (f" - {entry.get('end')}" if entry.get("end") else "")
                            + f" : {entry.get('activity') or ''}"
                        )
                        for entry in entries
                    ),
                    "response_json": {
                        "source": "giriton_attendance_uidl_selected_entries",
                        "courier": courier,
                        "activity_entries": entries,
                    },
                }
            )

    return parsed_rows
