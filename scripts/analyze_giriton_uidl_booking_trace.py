from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def maybe_embedded_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    text = clean(value)
    if '"state"' not in text and '"hierarchy"' not in text and '"rpc"' not in text:
        return {}
    for candidate in (text, "{" + text + "}"):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)
    elif isinstance(value, str):
        parsed = maybe_embedded_payload(value)
        if parsed:
            yield from walk_json(parsed)


def inner_request_payload(request_json: dict[str, Any]) -> dict[str, Any]:
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


def request_rpcs(event: dict[str, Any]) -> list[list[Any]]:
    request_json = event.get("request_json")
    if not isinstance(request_json, dict):
        return []
    rpc = inner_request_payload(request_json).get("rpc")
    return rpc if isinstance(rpc, list) else []


def response_payloads(event: dict[str, Any]) -> list[dict[str, Any]]:
    response_json = event.get("response_json")
    if not isinstance(response_json, dict):
        return []
    return [item for item in walk_json(response_json) if isinstance(item, dict)]


def response_states(event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for payload in response_payloads(event):
        state = payload.get("state")
        if not isinstance(state, dict):
            continue
        for key, value in state.items():
            if isinstance(value, dict):
                states[str(key)] = value
    return states


def response_type_mappings(event: dict[str, Any]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for payload in response_payloads(event):
        type_mappings = payload.get("typeMappings")
        if not isinstance(type_mappings, dict):
            continue
        for class_name, type_id in type_mappings.items():
            mappings[str(type_id)] = str(class_name)
    return mappings


def event_sync_client(event: dict[str, Any]) -> tuple[Any, Any]:
    request_json = event.get("request_json")
    if not isinstance(request_json, dict):
        return "", ""
    inner = inner_request_payload(request_json)
    return inner.get("syncId"), inner.get("clientId")


def classify_rpc(rpc: list[Any]) -> str:
    if len(rpc) < 3:
        return "unknown"
    class_name = clean(rpc[1])
    method = clean(rpc[2])
    args = rpc[3] if len(rpc) > 3 else []

    if class_name.endswith("CssLayoutServerRpc") and method == "layoutClick":
        return "shift_card_click"
    if class_name.endswith("TabsheetServerRpc") and method == "setSelected":
        return "open_subscribed_users_tab"
    if class_name.endswith("ButtonServerRpc") and method == "click":
        return "button_click"
    if class_name.endswith("AbstractTextFieldServerRpc") and method == "setText":
        return "courier_search_text"
    if class_name.endswith("GridMultiSelectServerRpc") and method == "select":
        return "courier_grid_select"
    if class_name.endswith("GridMultiSelectServerRpc") and method == "deselect":
        return "courier_grid_deselect"
    if class_name.endswith("DataRequestRpc") and method == "requestRows":
        return "grid_rows_request"
    if isinstance(args, list) and args and "R" in json.dumps(args, ensure_ascii=False):
        return "maybe_courier_action"
    return "other"


def summarize_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    components: dict[str, list[dict[str, str]]] = {}

    for index, event in enumerate(events):
        sync_id, client_id = event_sync_client(event)
        for rpc in request_rpcs(event):
            if not isinstance(rpc, list) or len(rpc) < 3:
                continue
            step = {
                "event_index": index,
                "kind": classify_rpc(rpc),
                "component_id": clean(rpc[0]),
                "class": clean(rpc[1]),
                "method": clean(rpc[2]),
                "args": rpc[3] if len(rpc) > 3 else [],
                "sync_id": sync_id,
                "client_id": client_id,
            }
            steps.append(step)

        mappings = response_type_mappings(event)
        states = response_states(event)
        for component_id, state in states.items():
            type_name = mappings.get(clean(state.get("id")) or component_id, "")
            caption = clean(state.get("caption"))
            text = clean(state.get("text"))
            selected = clean(state.get("selected"))
            tabs = state.get("tabs") if isinstance(state.get("tabs"), list) else []
            if caption or text or selected or tabs:
                components.setdefault(component_id, []).append(
                    {
                        "event_index": str(index),
                        "type": type_name,
                        "caption": caption,
                        "text": text,
                        "selected": selected,
                        "tabs": ", ".join(clean(tab.get("caption")) for tab in tabs if isinstance(tab, dict)),
                    }
                )

    important = []
    seen_shift_click = False
    for step in steps:
        if step["kind"] == "shift_card_click":
            if seen_shift_click:
                continue
            seen_shift_click = True
            important.append(step)
        elif step["kind"] in {
            "open_subscribed_users_tab",
            "button_click",
            "courier_search_text",
            "courier_grid_select",
            "courier_grid_deselect",
        }:
            important.append(step)

    recipe_steps = []
    button_click_count = 0
    for step in important:
        action = step["kind"]
        if action == "button_click":
            button_click_count += 1
            action = "open_courier_picker" if button_click_count == 1 else "confirm_courier_picker"
        recipe_steps.append(
            {
                "action": action,
                "component_id": step["component_id"],
                "rpc_class": step["class"],
                "rpc_method": step["method"],
                "args": step["args"],
                "source_event_index": step["event_index"],
            }
        )

    return {
        "event_count": len(events),
        "uidl_request_count": sum(1 for event in events if event.get("request_json")),
        "important_steps": important,
        "recipe_steps": recipe_steps,
        "components": components,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(
        "GIRITON_UIDL_BOOKING_TRACE "
        f"events={summary['event_count']} requests={summary['uidl_request_count']} "
        f"recipe_steps={len(summary['recipe_steps'])}"
    )
    for step in summary["recipe_steps"]:
        args_text = json.dumps(step["args"], ensure_ascii=False)
        if len(args_text) > 220:
            args_text = args_text[:217] + "..."
        print(
            " | ".join(
                [
                    f"event={step['source_event_index']}",
                    step["action"],
                    f"component={step['component_id']}",
                    f"{step['rpc_class']}::{step['rpc_method']}",
                    f"args={args_text}",
                ]
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sikeres Giriton UIDL booking trace elemzese es visszajatszasi recept keszitese."
    )
    parser.add_argument("trace", help="UIDL booking trace JSON fajl.")
    parser.add_argument("--out", default="", help="Opcionális JSON recept kimenet.")
    args = parser.parse_args()

    events = read_json(Path(args.trace))
    if not isinstance(events, list):
        raise RuntimeError("A trace fajlnak listanak kell lennie.")

    summary = summarize_trace(events)
    print_summary(summary)

    if clean(args.out):
        Path(args.out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"GIRITON_UIDL_BOOKING_RECIPE={args.out}")


if __name__ == "__main__":
    main()
