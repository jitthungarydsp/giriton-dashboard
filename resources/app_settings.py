import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"

DEFAULT_SETTINGS = {
    "discord_notifications_enabled": True,
    "discord_notify_courier_ids": "",
    "route_card_hidden": False,
    "waze_button_hidden": False,
    "courier_card_snapshot_enabled": False,
}

BOOLEAN_SETTINGS = {
    "discord_notifications_enabled",
    "route_card_hidden",
    "waze_button_hidden",
    "courier_card_snapshot_enabled",
}


def load_app_settings():
    if not CONFIG_PATH.exists() or CONFIG_PATH.stat().st_size == 0:
        return DEFAULT_SETTINGS.copy()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    settings = DEFAULT_SETTINGS.copy()
    for key, value in data.items():
        if key not in DEFAULT_SETTINGS:
            continue

        if key in BOOLEAN_SETTINGS:
            settings[key] = bool(value)
        else:
            settings[key] = str(value or "").strip()

    return settings


def save_app_settings(settings):
    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    clean_settings = DEFAULT_SETTINGS.copy()
    for key, value in settings.items():
        if key not in DEFAULT_SETTINGS:
            continue

        if key in BOOLEAN_SETTINGS:
            clean_settings[key] = bool(value)
        else:
            clean_settings[key] = str(value or "").strip()

    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            clean_settings,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return clean_settings
