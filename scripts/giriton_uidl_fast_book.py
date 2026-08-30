from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.live_giriton_shift_list import (  # noqa: E402
    DEFAULT_UIDL_URL,
    browser_cookie_header,
    collect_uidl_events,
    create_driver,
    login,
    max_response_sync_id,
    open_shift_subscriptions,
    select_all_departments,
    set_giriton_date,
    uidl_headers,
    wait_until_loaded,
)
from scripts.parse_giriton_uidl_shift_list import (  # noqa: E402
    merged_uidl_state,
    normalize_time,
    shift_cards_from_uidl,
    walk_json,
)


def clean(value: object) -> str:
    return str(value or "").strip()


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).casefold().strip()


def courier_id_from_serial(serial: str) -> str:
    parts = clean(serial).split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def mouse_event(event_type: int = 1) -> dict[str, Any]:
    return {
        "altKey": False,
        "button": "LEFT",
        "clientX": 0,
        "clientY": 0,
        "ctrlKey": False,
        "metaKey": False,
        "relativeX": 0,
        "relativeY": 0,
        "shiftKey": False,
        "type": event_type,
    }


def embedded_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = clean(value)
    if '"syncId"' not in text and '"state"' not in text and '"rpc"' not in text:
        return {}
    for candidate in (text, "{" + text + "}"):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def unwrap_inner_request(request_json: dict[str, Any]) -> dict[str, Any]:
    rpc = request_json.get("rpc")
    if (
        isinstance(rpc, list)
        and rpc
        and isinstance(rpc[0], dict)
        and rpc[0].get("templateEventMethodName") == "setRequest"
    ):
        args = rpc[0].get("templateEventMethodArgs") or []
        if args and isinstance(args[0], dict):
            return args[0]
    return request_json


def request_templates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    templates = []
    for event in events:
        request_json = event.get("request_json")
        if not isinstance(request_json, dict):
            continue
        inner = unwrap_inner_request(request_json)
        if isinstance(inner.get("csrfToken"), str) and isinstance(inner.get("clientId"), int):
            templates.append(event)
    return templates


def int_values(events: list[dict[str, Any]], key: str, *, inner: bool) -> list[int]:
    values: list[int] = []
    for event in events:
        request_json = event.get("request_json")
        if not isinstance(request_json, dict):
            continue
        payload = unwrap_inner_request(request_json) if inner else request_json
        value = payload.get(key)
        if isinstance(value, int):
            values.append(value)
    return values


def inner_response_payloads(payload: Any) -> list[dict[str, Any]]:
    payloads = []
    for item in walk_json(payload):
        parsed = embedded_payload(item)
        if parsed:
            payloads.append(parsed)
    return payloads


def raise_for_uidl_problem(payload: Any) -> None:
    for item in inner_response_payloads(payload):
        meta = item.get("meta")
        if not isinstance(meta, dict):
            continue
        if meta.get("sessionExpired"):
            raise RuntimeError("A Giriton session lejart az UIDL foglalas kozben.")
        app_error = meta.get("appError")
        if isinstance(app_error, dict):
            parts = [
                clean(app_error.get("caption")),
                clean(app_error.get("message")),
                clean(app_error.get("details")),
            ]
            message = " | ".join(part for part in parts if part)
            if message:
                raise RuntimeError(f"Giriton UIDL app error: {message}")


class UidlClient:
    def __init__(
        self,
        *,
        template: dict[str, Any],
        cookie: str,
        start_sync_id: int,
        start_outer_client_id: int,
        start_inner_client_id: int,
        timeout: int,
        trace_dir: Path,
    ) -> None:
        self.template = copy.deepcopy(template)
        self.cookie = cookie
        self.current_sync_id = start_sync_id
        self.outer_client_id = start_outer_client_id
        self.inner_client_id = start_inner_client_id
        self.timeout = timeout
        self.trace_dir = trace_dir
        self.events: list[dict[str, Any]] = []

    def build_request(self, rpcs: list[list[Any]]) -> dict[str, Any]:
        request_json = copy.deepcopy(self.template["request_json"])
        inner = unwrap_inner_request(request_json)
        inner["rpc"] = rpcs
        inner["syncId"] = self.current_sync_id + 1
        inner["clientId"] = self.inner_client_id
        request_json["syncId"] = self.current_sync_id
        request_json["clientId"] = self.outer_client_id

        outer_rpc = request_json.get("rpc")
        if isinstance(outer_rpc, list) and outer_rpc and isinstance(outer_rpc[0], dict):
            outer_rpc[0]["promise"] = self.inner_client_id
            outer_rpc[0]["templateEventMethodArgs"] = [inner]
        return request_json

    def post(self, label: str, rpcs: list[list[Any]]) -> Any:
        request_json = self.build_request(rpcs)
        url = clean(self.template.get("url")) or DEFAULT_UIDL_URL
        response = requests.post(
            url,
            headers=uidl_headers(self.cookie),
            json=request_json,
            timeout=self.timeout,
        )
        response.raise_for_status()
        response_json = response.json()
        raise_for_uidl_problem(response_json)

        if isinstance(response_json, dict) and isinstance(response_json.get("syncId"), int):
            self.current_sync_id = int(response_json["syncId"])
        else:
            self.current_sync_id += 1
        self.outer_client_id += 1
        self.inner_client_id += 1
        self.events.append(
            {
                "method": "Direct.uidlBookPost",
                "label": label,
                "url": url,
                "request_json": request_json,
                "response_json": response_json,
            }
        )
        print(f"GIRITON_UIDL_BOOK_STEP={label} sync={self.current_sync_id}")
        return response_json

    def write_trace(self, status: str, args: argparse.Namespace) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean(args.courier_name) or clean(args.courier_id) or "courier")
        safe_start = normalize_time(args.shift_start).replace(":", "_")
        path = self.trace_dir / (
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{args.date}_{args.warehouse.upper()}_"
            f"{safe_start}_{safe_name}_{status}.json"
        )
        path.write_text(json.dumps(self.events, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def node_sort_key(node_id: str) -> int:
    return int(node_id) if str(node_id).isdigit() else -1


def find_target_shift(initial_payloads: list[Any], warehouse: str, shift_start: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    target_warehouse = clean(warehouse).upper()
    target_start = normalize_time(shift_start)
    cards: list[dict[str, Any]] = []
    hierarchy: dict[str, list[str]] = {}
    for payload in initial_payloads:
        _, payload_hierarchy = merged_uidl_state(payload)
        hierarchy.update(payload_hierarchy)
        cards.extend(shift_cards_from_uidl(payload))

    matches = [
        card
        for card in cards
        if clean(card.get("warehouse")).upper() == target_warehouse
        and normalize_time(clean(card.get("start_time"))) == target_start
    ]
    if not matches:
        raise RuntimeError(f"Nincs ilyen Giriton muszak az UIDL listaban: {target_warehouse} {target_start}.")
    if len(matches) > 1:
        printable = ", ".join(f"{m.get('node_id')} {m.get('title')}" for m in matches)
        raise RuntimeError(f"Tobb azonos Giriton muszakot talaltam: {printable}")
    return matches[0], hierarchy


def find_subscribed_tab(payload: Any) -> str:
    state, _ = merged_uidl_state(payload)
    candidates = []
    for node_id, node in state.items():
        tabs = node.get("tabs")
        if not isinstance(tabs, list):
            continue
        captions = [clean(tab.get("caption")) for tab in tabs if isinstance(tab, dict)]
        if any("Subscribed users" in caption for caption in captions):
            candidates.append(node_id)
    if not candidates:
        raise RuntimeError("Nem talalom a Subscribed users fulet az UIDL valaszban.")
    return max(candidates, key=node_sort_key)


def find_add_button(payload: Any) -> str:
    state, _ = merged_uidl_state(payload)
    candidates = []
    for node_id, node in state.items():
        caption = clean(node.get("caption"))
        description = clean(node.get("description"))
        if caption == "Add" or description == "Add":
            candidates.append(node_id)
    if not candidates:
        raise RuntimeError("Nem talalom az Add gombot a feliratkozott futarok fulon.")
    return max(candidates, key=node_sort_key)


def find_picker_parts(payload: Any) -> tuple[str, str, str, str]:
    state, hierarchy = merged_uidl_state(payload)
    search = ""
    confirm = ""
    select = ""
    grid = ""

    for node_id, node in state.items():
        if clean(node.get("id")) == "SearchField-tfTextSearch":
            search = node_id
        if clean(node.get("id")) == "SelectionDialog-btn-confirm-selection":
            confirm = node_id
        if node.get("selectAllCheckBoxVisible") is True:
            select = node_id

    for node_id, node in state.items():
        if "header" not in node:
            continue
        children = hierarchy.get(node_id, [])
        if select in children:
            # Vaadin Grid children are data communicator, escalator, sidebar, selector.
            # The DataRequestRpc target is the first child in the successful booking trace.
            grid = children[0] if children else grid

    if not grid:
        for item in inner_response_payloads(payload):
            rpc = item.get("rpc")
            if not isinstance(rpc, list):
                continue
            for call in rpc:
                if (
                    isinstance(call, list)
                    and len(call) >= 3
                    and clean(call[1]) == "com.vaadin.shared.data.DataCommunicatorClientRpc"
                    and clean(call[2]) in {"reset", "setData"}
                ):
                    grid = clean(call[0])

    missing = [
        name
        for name, value in [("search", search), ("grid", grid), ("select", select), ("confirm", confirm)]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Nem talalom a futarvalaszto elemeit: {', '.join(missing)}")
    return search, grid, select, confirm


def row_key_matches(row: dict[str, Any], courier_id: str, courier_name: str, email: str) -> bool:
    data = row.get("d") if isinstance(row.get("d"), dict) else {}
    values = [clean(value) for value in data.values()]
    text = " ".join(values)
    folded = fold_text(text)
    if courier_id and re.search(rf"\bD?{re.escape(courier_id)}\b", text, flags=re.IGNORECASE):
        return True
    if email and fold_text(email) in folded:
        return True
    if courier_name and fold_text(courier_name) in folded:
        return True
    return False


def find_courier_row_key(payload: Any, courier_id: str, courier_name: str, email: str) -> str:
    matches = []
    for item in inner_response_payloads(payload):
        rpc = item.get("rpc")
        if not isinstance(rpc, list):
            continue
        for call in rpc:
            if not (
                isinstance(call, list)
                and len(call) >= 4
                and clean(call[1]) == "com.vaadin.shared.data.DataCommunicatorClientRpc"
                and clean(call[2]) in {"setData", "updateData"}
            ):
                continue
            args = call[3]
            row_blocks = []
            if isinstance(args, list) and len(args) >= 2 and isinstance(args[1], list):
                row_blocks = args[1]
            elif isinstance(args, list) and args and isinstance(args[0], list):
                row_blocks = args[0]
            for row in row_blocks:
                if isinstance(row, dict) and row_key_matches(row, courier_id, courier_name, email):
                    matches.append(clean(row.get("k")))

    unique = sorted({match for match in matches if match})
    if not unique:
        raise RuntimeError("A futar kereses nem adott talalatot a megadott ID/nev/email alapjan.")
    if len(unique) > 1:
        raise RuntimeError(f"Tobb futar sor illeszkedik a keresesre: {', '.join(unique)}")
    return unique[0]


def response_contains_selected(payload: Any) -> bool:
    state, _ = merged_uidl_state(payload)
    return any("Selected 1" in clean(node.get("text")) for node in state.values())


def response_mentions_courier(payload: Any, courier_id: str, courier_name: str, email: str) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    folded = fold_text(text)
    return (
        bool(courier_id and re.search(rf"\bD?{re.escape(courier_id)}\b", text, flags=re.IGNORECASE))
        or bool(email and fold_text(email) in folded)
        or bool(courier_name and fold_text(courier_name) in folded)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gyors Giriton foglalas kozvetlen Vaadin UIDL POST-okkal.")
    parser.add_argument("--date", required=True, help="Foglalando nap YYYY-MM-DD formatumban.")
    parser.add_argument("--warehouse", required=True, help="Raktar, peldaul BUD1 vagy BUD2.")
    parser.add_argument("--shift-start", required=True, help="Muszak kezdes, peldaul 09:30.")
    parser.add_argument("--courier-id", default="", help="Futar ID.")
    parser.add_argument("--courier-name", default="", help="Futar neve.")
    parser.add_argument("--email", default="", help="Futar email cime, ha ismert.")
    parser.add_argument("--serial", default="", help="Opcionális teljes serial.")
    parser.add_argument("--trace-dir", default="uidl_booking_trace", help="UIDL trace mentese ide.")
    parser.add_argument("--output-dir", default="", help="Kompatibilitasi opcio, az UIDL ut nem hasznalja.")
    parser.add_argument("--headed", action="store_true", help="Lathato Chrome ablakban fusson.")
    parser.add_argument("--chromedriver", default="", help="Opcionális konkret chromedriver utvonal.")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--user", default=os.getenv("GIRITON_USER", ""))
    parser.add_argument("--password", default=os.getenv("GIRITON_PASSWORD", ""))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Csak ellenorzes, nem foglal.")
    mode.add_argument("--live", action="store_true", help="Eles foglalas.")
    args = parser.parse_args()

    user = clean(args.user)
    password = clean(args.password)
    courier_id = clean(args.courier_id) or courier_id_from_serial(args.serial)
    courier_name = clean(args.courier_name)
    email = clean(args.email).casefold()
    work_date = datetime.strptime(clean(args.date), "%Y-%m-%d").date()
    warehouse = clean(args.warehouse).upper()
    shift_start = normalize_time(args.shift_start)

    if not user or not password:
        raise RuntimeError("Hianyzik a Giriton belepes. Add meg GIRITON_USER/GIRITON_PASSWORD env-ben.")
    if not courier_id and not courier_name and not email:
        raise RuntimeError("Hianyzik a futar azonosito. Kell --courier-id, --courier-name vagy --email.")

    print(
        "GIRITON_UIDL_FAST_BOOK "
        f"mode={'LIVE' if args.live else 'DRY_RUN'} date={work_date.isoformat()} "
        f"warehouse={warehouse} shift_start={shift_start} courier_id={courier_id or '-'} "
        f"courier_name={courier_name or '-'} email={email or '-'}"
    )

    driver = create_driver(args.headed, args.chromedriver)
    client: UidlClient | None = None
    try:
        print("AUTO_BOOK_STEP=STEP_LOGIN_START LOG=OK")
        login(driver, user, password, args.timeout)
        print("AUTO_BOOK_STEP=STEP_LOGIN_DONE LOG=OK")
        print("AUTO_BOOK_STEP=STEP_SHIFT_SUBS_OPEN_START LOG=OK")
        open_shift_subscriptions(driver, args.timeout)
        select_all_departments(driver, args.timeout)
        collect_uidl_events(driver)
        set_giriton_date(driver, work_date)
        wait_until_loaded(driver, args.timeout)
        time.sleep(1)
        initial_events = collect_uidl_events(driver)
        initial_payloads = [
            event["response_json"]
            for event in initial_events
            if isinstance(event.get("response_json"), (dict, list))
        ]
        print(f"GIRITON_UIDL_FAST_INITIAL events={len(initial_events)} payloads={len(initial_payloads)}")

        target_shift, hierarchy = find_target_shift(initial_payloads, warehouse, shift_start)
        print(
            "GIRITON_UIDL_FAST_TARGET "
            f"node={target_shift.get('node_id')} occupancy={target_shift.get('occupancy') or '-'} "
            f"free_slots={target_shift.get('free_slots')} title={target_shift.get('title') or '-'}"
        )

        templates = request_templates(initial_events)
        if not templates:
            raise RuntimeError("Nincs hasznalhato UIDL request minta a Giriton sessionbol.")
        start_sync_id = max_response_sync_id(initial_events, max(int_values(initial_events, "syncId", inner=False) or [0]))
        outer_clients = int_values(initial_events, "clientId", inner=False)
        inner_clients = int_values(initial_events, "clientId", inner=True)
        client = UidlClient(
            template=templates[-1],
            cookie=browser_cookie_header(driver),
            start_sync_id=start_sync_id,
            start_outer_client_id=(max(outer_clients) + 1) if outer_clients else 1,
            start_inner_client_id=(max(inner_clients) + 1) if inner_clients else 1,
            timeout=args.timeout,
            trace_dir=Path(args.trace_dir),
        )

        card_node = clean(target_shift.get("node_id"))
        click_node = (hierarchy.get(card_node) or [card_node])[0]
        popup = client.post(
            "shift_card_click",
            [[
                card_node,
                "com.vaadin.shared.ui.csslayout.CssLayoutServerRpc",
                "layoutClick",
                [mouse_event(8), click_node],
            ]],
        )
        tab_node = find_subscribed_tab(popup)
        subscribed = client.post(
            "open_subscribed_users_tab",
            [[tab_node, "com.vaadin.shared.ui.tabsheet.TabsheetServerRpc", "setSelected", ["2"]]],
        )
        add_button = find_add_button(subscribed)

        if args.dry_run and not args.live:
            trace_path = client.write_trace("DRY_RUN_READY", args)
            print(f"GIRITON_UIDL_FAST_BOOK_RESULT=DRY_RUN_READY trace={trace_path}")
            return 0

        picker = client.post(
            "open_courier_picker",
            [[add_button, "com.vaadin.shared.ui.button.ButtonServerRpc", "click", [mouse_event(1)]]],
        )
        search_node, grid_node, select_node, confirm_node = find_picker_parts(picker)
        search_text = courier_name or email or courier_id
        client.post(
            "courier_search_text",
            [[
                search_node,
                "com.vaadin.shared.ui.textfield.AbstractTextFieldServerRpc",
                "setText",
                [search_text, len(search_text)],
            ]],
        )
        rows_payload = client.post(
            "grid_rows_request",
            [[grid_node, "com.vaadin.shared.data.DataRequestRpc", "requestRows", [0, 10, 0, 0]]],
        )
        row_key = find_courier_row_key(rows_payload, courier_id, courier_name, email)
        print(f"GIRITON_UIDL_FAST_COURIER_ROW key={row_key}")
        selected_payload = client.post(
            "courier_grid_select",
            [[select_node, "com.vaadin.shared.data.selection.GridMultiSelectServerRpc", "select", [row_key]]],
        )
        if not response_contains_selected(selected_payload):
            print("FIGYELEM: a kivalasztas valasza nem tartalmazta a 'Selected 1' szoveget.", file=sys.stderr)
        confirm_payload = client.post(
            "confirm_courier_picker",
            [[confirm_node, "com.vaadin.shared.ui.button.ButtonServerRpc", "click", [mouse_event(1)]]],
        )
        status = "COURIER_ADDED" if response_mentions_courier(confirm_payload, courier_id, courier_name, email) else "DONE"
        trace_path = client.write_trace(status, args)
        print(f"GIRITON_UIDL_FAST_BOOK_RESULT={status} trace={trace_path}")
        return 0
    except Exception as error:
        if client is not None:
            trace_path = client.write_trace("FAILED", args)
            print(f"GIRITON_UIDL_FAST_BOOK_TRACE={trace_path}", file=sys.stderr)
        print(f"GIRITON_UIDL_FAST_BOOK_ERROR={error}", file=sys.stderr)
        return 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
