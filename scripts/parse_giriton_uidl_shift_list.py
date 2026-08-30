from __future__ import annotations

import argparse
import csv
from html import unescape
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any

import requests


DEFAULT_UIDL_URL = "https://kiflihu.giriton.com/?v-r=uidl&v-uiId=1"


def clean(value: Any) -> str:
    return str(value or "").strip()


def strip_html(value: str) -> str:
    text = unescape(clean(value))
    text = re.sub(r"</br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li\s*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_curl_command(path: Path) -> tuple[str, str, Any]:
    command = read_text(path).replace("`", "\\")
    command = re.sub(r"\\\s*\r?\n", " ", command)
    parts = shlex.split(command, posix=True)

    url = ""
    cookie = ""
    data = ""
    index = 0
    while index < len(parts):
        part = parts[index]
        if part.startswith("http"):
            url = part
        elif part in {"-H", "--header"} and index + 1 < len(parts):
            header = parts[index + 1]
            if header.casefold().startswith("cookie:"):
                cookie = header.split(":", 1)[1].strip()
            index += 1
        elif part in {"--data-raw", "--data", "--data-binary", "-d"} and index + 1 < len(parts):
            data = parts[index + 1]
            index += 1
        index += 1

    if not url:
        url = DEFAULT_UIDL_URL
    if not data:
        raise RuntimeError("A cURL fajlban nem talaltam UIDL JSON bodyt (--data-raw vagy -d).")

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"A cURL body nem ervenyes JSON: {error}") from error

    return url, cookie, payload


def cookie_value(cookie: str, cookie_file: str) -> str:
    if clean(cookie):
        return clean(cookie)
    if clean(cookie_file):
        return Path(cookie_file).read_text(encoding="utf-8").strip()
    return clean(os.getenv("GIRITON_UIDL_COOKIE") or os.getenv("GIRITON_COOKIE"))


def fetch_uidl_payload(
    *,
    url: str,
    request_payload: Any,
    cookie: str,
    timeout: int,
) -> Any:
    if not clean(cookie):
        raise RuntimeError(
            "Hiányzik a Giriton session cookie. Add meg --cookie-file opcióval, "
            "--cookie opcióval, vagy GIRITON_UIDL_COOKIE környezeti változóban."
        )

    response = requests.post(
        url,
        headers={
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
        },
        json=request_payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def raise_for_uidl_app_error(payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return

    if meta.get("sessionExpired"):
        raise RuntimeError(
            "A Giriton session lejárt. Friss cookie kell, és általában friss UIDL request body is "
            "ugyanabból a böngészős munkamenetből."
        )

    app_error = meta.get("appError")
    if isinstance(app_error, dict):
        message = clean(app_error.get("message"))
        details = clean(app_error.get("details"))
        caption = clean(app_error.get("caption"))
        error_text = " | ".join(part for part in [caption, message, details] if part)
        if error_text:
            raise RuntimeError(f"Giriton UIDL app error: {error_text}")


def maybe_parse_embedded_json(value: str) -> Any | None:
    text = clean(value)
    if '"state"' not in text and '"hierarchy"' not in text:
        return None
    candidates = [text]
    if not text.lstrip().startswith("{"):
        candidates.append("{" + text + "}")
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)
    elif isinstance(value, str):
        parsed = maybe_parse_embedded_json(value)
        if parsed is not None:
            yield from walk_json(parsed)


def merged_uidl_state(payload: Any) -> tuple[dict[str, dict], dict[str, list[str]]]:
    state: dict[str, dict] = {}
    hierarchy: dict[str, list[str]] = {}
    for item in walk_json(payload):
        if not isinstance(item, dict):
            continue
        item_state = item.get("state")
        if isinstance(item_state, dict):
            for key, value in item_state.items():
                if isinstance(value, dict):
                    state[str(key)] = value
        item_hierarchy = item.get("hierarchy")
        if isinstance(item_hierarchy, dict):
            for key, value in item_hierarchy.items():
                if isinstance(value, list):
                    hierarchy[str(key)] = [str(child) for child in value]
    return state, hierarchy


def descendants(node_id: str, hierarchy: dict[str, list[str]]) -> list[str]:
    result: list[str] = []
    stack = list(hierarchy.get(node_id, []))
    seen = set()
    while stack:
        child = stack.pop(0)
        if child in seen:
            continue
        seen.add(child)
        result.append(child)
        stack.extend(hierarchy.get(child, []))
    return result


def text_for_node(node_id: str, state: dict[str, dict]) -> str:
    node = state.get(str(node_id), {})
    return strip_html(clean(node.get("text") or node.get("description")))


def parse_title(title: str) -> dict[str, str]:
    text = clean(title)
    start = ""
    end = ""
    match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$", text)
    if match:
        start = normalize_time(match.group(1))
        end = normalize_time(match.group(2))
    return {
        "title": text,
        "start_time": start,
        "end_time": end,
    }


def normalize_time(value: str) -> str:
    text = clean(value)
    match = re.match(r"^(\d{1,2}):(\d{2})", text)
    if not match:
        return text
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"


def parse_description(description: str) -> dict[str, Any]:
    text = strip_html(description)
    warehouse = ""
    department = ""
    occupancy = ""
    booked = None
    maximum = None
    subscribed_users = ""

    department_match = re.search(r"Department\s*\n([^\n]+)", text, flags=re.IGNORECASE)
    if department_match:
        department = clean(department_match.group(1))
        warehouse_match = re.search(r"\b(BUD\d+)\b", department.upper())
        if warehouse_match:
            warehouse = warehouse_match.group(1)

    status_match = re.search(r"Status\s*\n([0-9]+\s*/\s*[0-9]+)", text, flags=re.IGNORECASE)
    if status_match:
        occupancy = re.sub(r"\s+", " ", status_match.group(1)).strip()
        numbers = re.findall(r"\d+", occupancy)
        if len(numbers) >= 2:
            booked = int(numbers[0])
            maximum = int(numbers[1])

    users_match = re.search(r"Subscribed users\s*\n?(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
    if users_match:
        subscribed_users = users_match.group(1).replace("- ", "").strip()
    if subscribed_users.casefold() in {"(none)", "none"}:
        subscribed_users = ""

    return {
        "warehouse": warehouse,
        "department": department,
        "occupancy": occupancy,
        "booked": booked,
        "maximum": maximum,
        "free_slots": None if booked is None or maximum is None else max(maximum - booked, 0),
        "subscribed_users": subscribed_users,
    }


def shift_cards_from_uidl(payload: Any) -> list[dict[str, Any]]:
    state, hierarchy = merged_uidl_state(payload)
    cards: list[dict[str, Any]] = []

    for node_id, node in state.items():
        styles = node.get("styles") or []
        description = clean(node.get("description"))
        if "shift-subscription-preview-panel" not in styles and "Subscribed users" not in description:
            continue

        title = ""
        for child_id in descendants(node_id, hierarchy):
            child = state.get(child_id, {})
            child_styles = child.get("styles") or []
            if "panel-title" in child_styles:
                title = text_for_node(child_id, state)
                break

        parsed_title = parse_title(title)
        parsed_description = parse_description(description)
        cards.append(
            {
                "node_id": node_id,
                **parsed_title,
                **parsed_description,
                "is_open": (
                    parsed_description["free_slots"] is not None
                    and parsed_description["free_slots"] > 0
                ),
            }
        )

    cards.sort(key=lambda row: (row.get("start_time") or "", row.get("warehouse") or "", row.get("node_id") or ""))
    return cards


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "node_id",
        "warehouse",
        "start_time",
        "end_time",
        "occupancy",
        "booked",
        "maximum",
        "free_slots",
        "subscribed_users",
        "title",
        "department",
        "is_open",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def print_table(rows: list[dict[str, Any]], only_open: bool) -> None:
    visible = [row for row in rows if row.get("is_open")] if only_open else rows
    print(f"GIRITON_UIDL_SHIFTS total={len(rows)} visible={len(visible)} only_open={only_open}")
    for row in visible:
        users = clean(row.get("subscribed_users")) or "-"
        print(
            " | ".join(
                [
                    clean(row.get("warehouse")) or "-",
                    clean(row.get("start_time")) or "-",
                    clean(row.get("end_time")) or "-",
                    clean(row.get("occupancy")) or "-",
                    f"szabad={row.get('free_slots') if row.get('free_slots') is not None else '-'}",
                    f"foglalt={users}",
                    clean(row.get("title")) or "-",
                ]
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Giriton Vaadin UIDL JSON-ból vagy éles UIDL POST-ból műszakkártya lista kinyerése."
    )
    parser.add_argument("--input", default="", help="DevToolsból mentett UIDL request vagy response JSON fájl.")
    parser.add_argument("--curl-file", default="", help="DevTools Copy as cURL fájl. Ebből kiveszi az URL-t, cookie-t és UIDL bodyt.")
    parser.add_argument("--live", action="store_true", help="Az input JSON-t POSTolja a Giriton UIDL URL-re, majd a választ dolgozza fel.")
    parser.add_argument("--url", default=DEFAULT_UIDL_URL, help="UIDL endpoint. Alap: kiflihu.giriton.com v-uiId=1.")
    parser.add_argument("--cookie", default="", help="Friss Giriton Cookie header érték. Inkább --cookie-file vagy env ajánlott.")
    parser.add_argument("--cookie-file", default="", help="Fájl, amelyben a friss Cookie header érték van.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--save-response", default="", help="Éles hívás válaszának mentése JSON fájlba.")
    parser.add_argument("--only-open", action="store_true", help="Csak a szabad hellyel rendelkező műszakokat írja ki.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="JSON listát ír ki.")
    parser.add_argument("--csv", default="", help="Opcionális CSV kimeneti fájl.")
    args = parser.parse_args()

    curl_cookie = ""
    if args.curl_file:
        curl_url, curl_cookie, payload = parse_curl_command(Path(args.curl_file))
        args.url = curl_url or args.url
        args.live = True
    elif args.input:
        payload = read_json(Path(args.input))
    else:
        raise RuntimeError("Add meg az --input vagy --curl-file opciot.")

    if args.live:
        payload = fetch_uidl_payload(
            url=args.url,
            request_payload=payload,
            cookie=cookie_value(args.cookie or curl_cookie, args.cookie_file),
            timeout=args.timeout,
        )
        if args.save_response:
            Path(args.save_response).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"GIRITON_UIDL_RESPONSE={args.save_response}")

    raise_for_uidl_app_error(payload)
    rows = shift_cards_from_uidl(payload)

    if args.csv:
        write_csv(rows, Path(args.csv))
        print(f"GIRITON_UIDL_CSV={args.csv}")

    if args.json_output:
        visible = [row for row in rows if row.get("is_open")] if args.only_open else rows
        print(json.dumps(visible, ensure_ascii=False, indent=2))
    else:
        print_table(rows, args.only_open)


if __name__ == "__main__":
    main()
