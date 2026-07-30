import os
from pathlib import Path
import tomllib

import requests
import streamlit as st

from resources.app_settings import load_app_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_setting(name):
    try:
        if name in st.secrets:
            return st.secrets.get(name)
    except Exception:
        pass

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"

    if secrets_path.exists():
        try:
            with secrets_path.open("rb") as file:
                secrets = tomllib.load(file)

            if name in secrets:
                return secrets.get(name)

            discord = secrets.get("discord", {})
            if isinstance(discord, dict) and name in discord:
                return discord.get(name)
        except Exception:
            pass

    return os.getenv(name, "")


def _normalize_id(value):
    return "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )


def _normalize_warehouse(value):
    raw_value = str(value or "").strip().upper()
    compact_value = "".join(
        character
        for character in raw_value
        if character.isalnum()
    )

    if compact_value in {"1", "BUD1", "BUD1JIT"}:
        return "BUD1"

    if compact_value in {"2", "BUD2", "BUD2JIT"}:
        return "BUD2"

    if "BUD2" in compact_value:
        return "BUD2"

    if "BUD1" in compact_value or compact_value in {"BUD", "BUDAPEST"}:
        return "BUD1"

    return ""


def _read_webhook_url(warehouse=""):
    normalized_warehouse = _normalize_warehouse(warehouse)

    if normalized_warehouse:
        warehouse_webhook = str(
            _read_setting(f"DISCORD_WEBHOOK_URL_{normalized_warehouse}") or ""
        ).strip()
        if warehouse_webhook:
            return warehouse_webhook, normalized_warehouse

    fallback_webhook = str(_read_setting("DISCORD_WEBHOOK_URL") or "").strip()
    return fallback_webhook, normalized_warehouse


def _read_allowed_courier_ids(settings=None):
    settings = settings or {}
    setting_value = _read_setting("DISCORD_NOTIFY_COURIER_IDS")
    raw_value = str(
        setting_value
        or settings.get("discord_notify_courier_ids")
        or ""
    ).strip()

    if not raw_value:
        return set()

    return {
        _normalize_id(item)
        for item in raw_value.replace(";", ",").split(",")
        if _normalize_id(item)
    }


def read_discord_status():
    settings = load_app_settings()
    bud1_webhook = str(_read_setting("DISCORD_WEBHOOK_URL_BUD1") or "").strip()
    bud2_webhook = str(_read_setting("DISCORD_WEBHOOK_URL_BUD2") or "").strip()
    legacy_webhook = str(_read_setting("DISCORD_WEBHOOK_URL") or "").strip()

    return {
        "webhook_configured": bool(bud1_webhook or bud2_webhook or legacy_webhook),
        "bud1_webhook_configured": bool(bud1_webhook),
        "bud2_webhook_configured": bool(bud2_webhook),
        "allowed_courier_ids": sorted(_read_allowed_courier_ids(settings)),
    }


@st.cache_resource
def _sent_route_notifications():
    return set()


def _build_route_notification_lines(
    courier_id,
    courier_name,
    route_id,
    order_id="",
    address="",
    planned_departure="",
    planned_return="",
    orders_in_route="",
    licence_plate="",
    warehouse="",
    current_shift_note="",
    next_shift_note="",
    next_shift_delay_note="",
    queue_since_note="",
    queue_wait_note="",
):
    content_lines = [
        "**Uj tura erkezett**",
        "",
        f"**{courier_name}** `#{courier_id}`",
        f"**Route ID:** `{route_id}`",
    ]

    if warehouse:
        content_lines.append(f"**Raktar:** `{warehouse}`")

    if current_shift_note:
        content_lines.append(f"**Aktualis muszak:** {current_shift_note}")

    if next_shift_note:
        content_lines.append(f"**Kovetkezo muszak:** {next_shift_note}")

    if next_shift_delay_note:
        content_lines.append(f"**Kovetkezo muszak keses:** {next_shift_delay_note}")

    if queue_since_note:
        content_lines.append(f"**Sorba allt:** {queue_since_note}")

    if queue_wait_note:
        content_lines.append(f"**Varakozott:** {queue_wait_note}")

    if licence_plate:
        content_lines.append(f"**Aktualis rendszam:** {licence_plate}")

    return content_lines


def notify_route_assigned_once(
    courier_id,
    courier_name,
    route_id,
    order_id="",
    address="",
    planned_departure="",
    planned_return="",
    ignore_courier_filter=False,
    orders_in_route="",
    licence_plate="",
    warehouse="",
    current_shift_note="",
    next_shift_note="",
    next_shift_delay_note="",
    queue_since_note="",
    queue_wait_note="",
):
    settings = load_app_settings()

    if not settings.get("discord_notifications_enabled", True):
        return "disabled"

    webhook_url, normalized_warehouse = _read_webhook_url(warehouse)

    if not webhook_url or not route_id:
        return "skipped"

    allowed_courier_ids = _read_allowed_courier_ids(settings)
    normalized_courier_id = _normalize_id(courier_id)

    if (
        not ignore_courier_filter
        and allowed_courier_ids
        and normalized_courier_id not in allowed_courier_ids
    ):
        return "filtered"

    notification_key = f"{normalized_warehouse}:{courier_id}:{route_id}"
    sent_notifications = _sent_route_notifications()

    if notification_key in sent_notifications:
        return "already_sent"

    content_lines = _build_route_notification_lines(
        courier_id,
        courier_name,
        route_id,
        order_id=order_id,
        address=address,
        planned_departure=planned_departure,
        planned_return=planned_return,
        orders_in_route=orders_in_route,
        licence_plate=licence_plate,
        warehouse=normalized_warehouse or str(warehouse or "").strip(),
        current_shift_note=current_shift_note,
        next_shift_note=next_shift_note,
        next_shift_delay_note=next_shift_delay_note,
        queue_since_note=queue_since_note,
        queue_wait_note=queue_wait_note,
    )

    response = requests.post(
        webhook_url,
        json={"content": "\n".join(content_lines)},
        timeout=15,
    )
    response.raise_for_status()
    sent_notifications.add(notification_key)

    return "sent"
