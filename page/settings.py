import streamlit as st

from resources.app_settings import (
    DEFAULT_SETTINGS,
    load_app_settings,
    save_app_settings,
)
from resources.discord_notifier import read_discord_status


def show_settings_page():
    user = st.session_state.get("user", {})

    st.title("Beállítások")

    if user.get("role") != "admin":
        st.error("Ezt az oldalt csak admin kezelheti.")
        return

    settings = load_app_settings()
    discord_status = read_discord_status()

    st.subheader("Kifli kártya")

    route_card_hidden = st.toggle(
        "Útvonal elrejtése a Kifli kártyán",
        value=settings.get("route_card_hidden", False),
        help="Ha be van kapcsolva, a futár nem látja az aktuális címet és útvonal részleteket.",
    )
    waze_button_hidden = st.toggle(
        "Waze gomb elrejtése",
        value=settings.get("waze_button_hidden", False),
        help="Ha be van kapcsolva, az Irány a cím Waze gomb nem jelenik meg.",
    )

    courier_card_snapshot_enabled = st.toggle(
        "Kifli kartya gyors snapshot hasznalata",
        value=settings.get("courier_card_snapshot_enabled", False),
        help="Most maradjon kikapcsolva: igy a Kifli kartya az osszes futart a DB-bol epiti fel.",
    )

    st.subheader("Discord")

    discord_notifications_enabled = st.toggle(
        "Discord route értesítés engedélyezése",
        value=settings.get("discord_notifications_enabled", True),
        help="Ha be van kapcsolva, új route esetén Discord webhook értesítés mehet.",
    )
    discord_notify_courier_ids = st.text_input(
        "Discord értesítés futár ID szűrés",
        value=str(settings.get("discord_notify_courier_ids") or "7644"),
        help="Vesszővel elválasztott futár ID-k. Üresen hagyva minden futár engedélyezett.",
    )

    st.caption(
        f"Webhook állapot: {'beállítva' if discord_status['webhook_configured'] else 'nincs beállítva'}"
    )

    allowed_ids = discord_status.get("allowed_courier_ids", [])
    if allowed_ids:
        st.caption(
            "Teszt futár ID szűrés: "
            + ", ".join(allowed_ids)
        )
    else:
        st.caption(
            "Teszt futár ID szűrés: nincs megadva, webhook mellett minden futár engedélyezett."
        )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Beállítások mentése", type="primary", use_container_width=True):
            save_app_settings(
                {
                    "route_card_hidden": route_card_hidden,
                    "waze_button_hidden": waze_button_hidden,
                    "courier_card_snapshot_enabled": courier_card_snapshot_enabled,
                    "discord_notifications_enabled": discord_notifications_enabled,
                    "discord_notify_courier_ids": discord_notify_courier_ids,
                }
            )
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("Beállítások mentve.")
            st.rerun()

    with col2:
        if st.button("Alapértelmezett visszaállítása", use_container_width=True):
            save_app_settings(DEFAULT_SETTINGS)
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("Alapértelmezett beállítások visszaállítva.")
            st.rerun()
