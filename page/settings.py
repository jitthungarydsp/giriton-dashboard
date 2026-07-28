from datetime import datetime, timezone

import streamlit as st

from resources.app_settings import (
    DEFAULT_SETTINGS,
    load_app_settings,
    save_app_settings,
)
from resources.discord_notifier import read_discord_status
from resources.pwa_push_notifications import (
    load_setting as load_push_setting,
    load_vapid_private_key,
    load_latest_delivery_message,
    send_push_to_courier,
)
from resources.users import load_users
from page.compensation_settings import (
    render_adjustment_item_settings,
    render_compensation_rule_settings,
)


def _active_courier_notification_users():
    try:
        users = load_users().get("users", [])
    except Exception:
        return []

    recipients = []
    for user in users:
        if not user.get("active", True):
            continue
        if str(user.get("role") or "").strip().lower() == "admin":
            continue
        courier_id = str(user.get("courierId") or user.get("courier_id") or "").strip()
        username = str(user.get("username") or "").strip()
        if not courier_id or not username:
            continue
        recipients.append(
            {
                "label": f"{username} #{courier_id}",
                "username": username,
                "courier_id": courier_id,
            }
        )
    return sorted(recipients, key=lambda item: item["label"].casefold())


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

    st.markdown(
        """
        <div style="padding:18px 20px;border-radius:18px;background:#e5f3e1;border:1px solid #b8d5b4;margin:18px 0 10px;">
          <div style="font-size:12px;font-weight:900;letter-spacing:.08em;color:#2e5b36;text-transform:uppercase;">PWA push</div>
          <div style="font-size:24px;font-weight:850;color:#17231c;">Push küldése</div>
          <div style="color:#315b37;margin-top:6px;">Központi üzenet azoknak a futároknak, akik az új mobil PWA-ban bekapcsolták az értesítéseket.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    vapid_private_ready = bool(load_vapid_private_key())
    vapid_public_ready = bool(load_push_setting("VAPID_PUBLIC_KEY"))
    st.caption(
        "Push konfiguráció: "
        f"privát kulcs {'rendben' if vapid_private_ready else 'hiányzik'}, "
        f"publikus kulcs {'rendben' if vapid_public_ready else 'hiányzik vagy helyi PEM-ből számolódik'}."
    )

    notification_users = _active_courier_notification_users()
    notification_labels = [item["label"] for item in notification_users]
    notification_by_label = {item["label"]: item for item in notification_users}

    with st.form("central_pwa_notification_form"):
        target_mode = st.radio(
            "Cimzettek",
            ["Minden aktiv futar", "Kivalasztott futarok"],
            horizontal=True,
        )
        selected_labels = []
        if target_mode == "Kivalasztott futarok":
            selected_labels = st.multiselect("Futarok", notification_labels)
        notification_title = st.text_input(
            "Ertesites cime",
            value="Giriton ertesites",
        )
        notification_body = st.text_area(
            "Uzenet",
            placeholder="Ide ird a kozponti uzenetet.",
            height=120,
        )
        confirm_central_notification = st.checkbox(
            "Megerősitem a kozponti ertesites kikuldeset.",
        )
        send_central_notification = st.form_submit_button(
            "Kozponti ertesites kikuldese",
            type="primary",
        )

    if send_central_notification:
        if not confirm_central_notification:
            st.error("A kikuldest jovahagyas nelkul nem inditom el.")
        elif not str(notification_title or "").strip():
            st.error("Az ertesites cime kotelezo.")
        elif not str(notification_body or "").strip():
            st.error("Az uzenet szovege kotelezo.")
        else:
            if target_mode == "Minden aktiv futar":
                recipients = notification_users
            else:
                recipients = [
                    notification_by_label[label]
                    for label in selected_labels
                    if label in notification_by_label
                ]

            if not recipients:
                st.error("Nincs kivalasztott cimzett.")
            else:
                tag = "central-message-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                results = {
                    "sent": 0,
                    "no_subscription": 0,
                    "missing_vapid": 0,
                    "failed": 0,
                    "other": 0,
                }
                failed_rows = []
                progress = st.progress(0)
                for index, recipient in enumerate(recipients, start=1):
                    try:
                        status = send_push_to_courier(
                            courier_id=recipient["courier_id"],
                            title=str(notification_title).strip(),
                            body=str(notification_body).strip(),
                            tag=f"{tag}-{recipient['courier_id']}",
                            url="/",
                            notification_type="central_message",
                            data={"section": "home", "source": "admin"},
                        )
                    except Exception as exc:
                        status = "failed"
                        failed_rows.append(
                            {
                                "Futar": recipient["label"],
                                "Hiba": str(exc),
                            }
                        )

                    if status in results:
                        results[status] += 1
                    else:
                        results["other"] += 1
                    if status in {"failed", "other"}:
                        failed_rows.append(
                            {
                                "Futar": recipient["label"],
                                "Hiba": load_latest_delivery_message(
                                    courier_id=recipient["courier_id"],
                                    notification_type="central_message",
                                ) or status,
                            }
                        )
                    progress.progress(index / len(recipients))

                st.success(
                    "Kozponti ertesites feldolgozva. "
                    f"Elkuldve: {results['sent']}, "
                    f"nincs feliratkozas: {results['no_subscription']}, "
                    f"hibas: {results['failed']}, "
                    f"VAPID hianyzik: {results['missing_vapid']}."
                )
                if results["missing_vapid"]:
                    st.error(
                        "A push kulcs nincs beallitva ezen a kornyezeten. "
                        "Renderben add meg a VAPID_PRIVATE_KEY es VAPID_SUBJECT env valtozokat. "
                        "A VAPID_PRIVATE_KEY lehet tobb soros PEM, vagy \\n jelekkel egy sorban."
                    )
                if failed_rows:
                    st.dataframe(failed_rows, use_container_width=True, hide_index=True)

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

    st.divider()
    render_adjustment_item_settings()
    render_compensation_rule_settings()
