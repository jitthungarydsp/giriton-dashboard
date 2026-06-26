import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from resources.api import load_drivers
from resources.users import load_users


LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def nested_get(data, path, default=""):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current in [None, ""]:
            return default

    return current


def format_local_time(value):
    if value in [None, ""]:
        return ""

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        return parsed.astimezone(
            LOCAL_TIMEZONE
        ).strftime("%H:%M")
    except ValueError:
        return str(value)


def get_visible_drivers(user, drivers):
    if user["role"] == "admin":
        return drivers

    if user["role"] == "trainer":
        users_data = load_users()
        trainer_courier_ids = {
            str(portal_user.get("courierId"))
            for portal_user in users_data["users"]
            if portal_user.get("trainer") == user["username"]
        }

        return [
            driver
            for driver in drivers
            if str(driver.get("driver_id")) in trainer_courier_ids
        ]

    return [
        driver
        for driver in drivers
        if str(driver.get("driver_id")) == str(user.get("courierId"))
    ]


def get_delay_label(delay_minutes):
    try:
        delay_minutes = int(delay_minutes)
    except (TypeError, ValueError):
        return "Nincs adat", "#111827"

    if delay_minutes <= 0:
        return "Időben", "#16a34a"

    if delay_minutes <= 15:
        return f"+{delay_minutes} perc", "#f59e0b"

    return f"+{delay_minutes} perc", "#dc2626"


def build_map_drivers(drivers):
    map_drivers = []

    for driver in drivers:
        position = nested_get(
            driver,
            ["route", "current_position"],
            {},
        )
        latitude = position.get("latitude") if isinstance(position, dict) else None
        longitude = position.get("longitude") if isinstance(position, dict) else None

        if latitude in [None, ""] or longitude in [None, ""]:
            continue

        delay_minutes = nested_get(
            driver,
            ["status", "delay_minutes"],
            0,
        )
        delay_label, color = get_delay_label(
            delay_minutes
        )
        path = nested_get(
            driver,
            ["route", "path"],
            [],
        )

        path_points = []

        if isinstance(path, list):
            for point in path:
                point_lat = point.get("latitude") if isinstance(point, dict) else None
                point_lon = point.get("longitude") if isinstance(point, dict) else None

                if point_lat not in [None, ""] and point_lon not in [None, ""]:
                    path_points.append([
                        float(point_lat),
                        float(point_lon),
                    ])

        map_drivers.append({
            "id": driver.get("driver_id"),
            "name": nested_get(
                driver,
                ["personal_info", "name"],
                "Ismeretlen futár",
            ),
            "warehouse": nested_get(
                driver,
                ["personal_info", "warehouse_name"],
                "",
            ),
            "license_plate": nested_get(
                driver,
                ["vehicle", "license_plate"],
                "",
            ),
            "temperature": nested_get(
                driver,
                ["vehicle", "temperature"],
                "",
            ),
            "last_temperature": format_local_time(
                nested_get(
                    driver,
                    ["vehicle", "last_measurement_timestamp"],
                    "",
                )
            ),
            "state": nested_get(
                driver,
                ["status", "current_state"],
                "",
            ),
            "delay": delay_label,
            "color": color,
            "next_stop": nested_get(
                driver,
                ["status", "next_stop"],
                "",
            ),
            "departure": format_local_time(
                nested_get(
                    driver,
                    ["status", "warehouse_departure_real"],
                    "",
                )
            ),
            "lat": float(latitude),
            "lon": float(longitude),
            "path": path_points,
        })

    return map_drivers


def render_leaflet_map(map_drivers):
    drivers_json = json.dumps(
        map_drivers,
        ensure_ascii=False,
    )

    map_html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <style>
        html, body, #map {{
          height: 100%;
          margin: 0;
          width: 100%;
        }}
        .courier-marker {{
          align-items: center;
          border: 2px solid white;
          border-radius: 999px;
          box-shadow: 0 2px 8px rgba(15, 23, 42, .35);
          color: white;
          display: flex;
          font-size: 15px;
          height: 30px;
          justify-content: center;
          width: 30px;
        }}
        .leaflet-popup-content {{
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          min-width: 220px;
        }}
      </style>
    </head>
    <body>
      <div id="map"></div>
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        const drivers = {drivers_json};
        const map = L.map('map');

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        const bounds = [];

        drivers.forEach((driver) => {{
          const marker = L.marker([driver.lat, driver.lon], {{
            icon: L.divIcon({{
              html: `<div class="courier-marker" style="background:${{driver.color}}">🚚</div>`,
              className: '',
              iconSize: [30, 30],
              iconAnchor: [15, 15]
            }})
          }}).addTo(map);

          marker.bindPopup(`
            <strong>${{driver.name}}</strong><br>
            ID: ${{driver.id}}<br>
            Rendszám: ${{driver.license_plate || '-'}}<br>
            Hőmérséklet: ${{driver.temperature !== '' ? driver.temperature + ' °C' : '-'}}<br>
            Státusz: ${{driver.state || '-'}}<br>
            Késés: ${{driver.delay || '-'}}<br>
            Indulás: ${{driver.departure || '-'}}<br>
            Következő cím: ${{driver.next_stop || '-'}}
          `);

          bounds.push([driver.lat, driver.lon]);

          if (driver.path && driver.path.length > 1) {{
            L.polyline(driver.path, {{
              color: driver.color,
              weight: 3,
              opacity: 0.55
            }}).addTo(map);

            driver.path.forEach((point) => bounds.push(point));
          }}
        }});

        if (bounds.length) {{
          map.fitBounds(bounds, {{ padding: [25, 25] }});
        }} else {{
          map.setView([47.4979, 19.0402], 10);
        }}
      </script>
    </body>
    </html>
    """

    components.html(
        map_html,
        height=620,
    )


def show_driver_card(driver):
    safe_name = html.escape(
        str(driver.get("name", "Ismeretlen futár"))
    )
    safe_next_stop = html.escape(
        str(driver.get("next_stop") or "Nincs következő cím")
    )

    st.markdown(
        f"""
<div style="
    border: 1px solid #e5e7eb;
    border-left: 5px solid {driver.get('color', '#111827')};
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 10px;
    background: #ffffff;">
    <div style="font-weight: 700;">{safe_name}</div>
    <div style="font-size: 12px; color: #64748b;">#{driver.get('id')} · {driver.get('warehouse')}</div>
    <div style="margin-top: 6px; font-size: 13px;">
        🚚 {driver.get('license_plate') or '-'} ·
        🌡️ {driver.get('temperature') if driver.get('temperature') != '' else '-'} °C
    </div>
    <div style="font-size: 13px;">Állapot: <b>{driver.get('state') or '-'}</b></div>
    <div style="font-size: 13px;">Késés: <b>{driver.get('delay') or '-'}</b></div>
    <div style="font-size: 12px; color: #475569;">Következő: {safe_next_stop}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def show_live_map_page():
    st.title("Live Map")

    user = st.session_state["user"]
    data = load_drivers()
    drivers = data.get(
        "drivers",
        [],
    )
    visible_drivers = get_visible_drivers(
        user,
        drivers,
    )
    map_drivers = build_map_drivers(
        visible_drivers,
    )

    active_count = len(map_drivers)

    st.caption(
        f"Élő futárpozíciók a fetch-drivers API-ból. Megjelenítve: {active_count} futár."
    )

    if not map_drivers:
        st.warning(
            "Most nincs térképen megjeleníthető futárpozíció."
        )
        return

    left, right = st.columns(
        [4, 1.25],
        gap="medium",
    )

    with left:
        render_leaflet_map(
            map_drivers
        )

    with right:
        st.subheader("Aktív futárok")
        st.caption(
            f"{active_count} futár térképen"
        )

        status_filter = st.selectbox(
            "Szűrés",
            [
                "Összes",
                "Késésben",
                "Időben",
            ],
            key="live_map_status_filter",
        )

        filtered_drivers = map_drivers

        if status_filter == "Késésben":
            filtered_drivers = [
                driver
                for driver in map_drivers
                if str(driver.get("delay", "")).startswith("+")
            ]
        elif status_filter == "Időben":
            filtered_drivers = [
                driver
                for driver in map_drivers
                if driver.get("delay") == "Időben"
            ]

        for driver in filtered_drivers:
            show_driver_card(
                driver
            )
