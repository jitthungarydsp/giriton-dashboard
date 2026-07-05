import os
from pathlib import Path
import tomllib

import requests
import streamlit as st


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


@st.cache_resource
def _sent_route_notifications():
    return set()


def notify_route_assigned_once(courier_id, courier_name, route_id, order_id="", address=""):
    webhook_url = str(_read_setting("DISCORD_WEBHOOK_URL") or "").strip()

    if not webhook_url or not route_id:
        return "skipped"

    notification_key = f"{courier_id}:{route_id}"
    sent_notifications = _sent_route_notifications()

    if notification_key in sent_notifications:
        return "already_sent"

    content_lines = [
        "Új túra érkezett a futárra.",
        f"Futár: {courier_name} #{courier_id}",
        f"Route ID: {route_id}",
    ]

    if order_id:
        content_lines.append(f"Aktuális rendelés: {order_id}")

    if address:
        content_lines.append(f"Aktuális cím: {address}")

    response = requests.post(
        webhook_url,
        json={"content": "\n".join(content_lines)},
        timeout=15,
    )
    response.raise_for_status()
    sent_notifications.add(notification_key)

    return "sent"
