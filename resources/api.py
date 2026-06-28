import requests
import streamlit as st

from datetime import datetime
from zoneinfo import ZoneInfo


BASE_URL = "https://uftplslamjbbhlozsygo.supabase.co/functions/v1"
ORGANIZATION_ID = "f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
DEPOT_ID = "JIT"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVmdHBsc2xhbWpiYmhsb3pzeWdvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI4MjY5NzcsImV4cCI6MjA2ODQwMjk3N30."
    "3h6l5oeMYIRuvOuNRtOKP-9v4RaHzcUImHGTdr5w2VM"
)
LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def request_json(method, url, **kwargs):
    try:
        response = requests.request(
            method,
            url,
            timeout=30,
            **kwargs
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(
            f"API hiba: {exc}"
        )
    except ValueError:
        st.error(
            "API hiba: a valasz nem ervenyes JSON."
        )

    return {}


def load_attendance():

    today = datetime.now(LOCAL_TIMEZONE).strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{BASE_URL}/"
        f"fetch-attendance/{DEPOT_ID}/{today}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    return request_json(
        "GET",
        url
    )


def load_drivers():

    url = (
        f"{BASE_URL}/"
        f"fetch-drivers"
        f"?id={DEPOT_ID}"
        f"&organizationId={ORGANIZATION_ID}"
        f"&departureDelayThreshold=10"
    )

    return request_json(
        "GET",
        url
    )
    
def load_driver_details(driver_id):

    today = datetime.now(LOCAL_TIMEZONE).strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{BASE_URL}/"
        f"fetch-drivers-detail/{driver_id}/{today}"
        f"?organizationId={ORGANIZATION_ID}"
    )

    return request_json(
        "GET",
        url
    )
    
def load_departure_dashboard():

    url = (
        f"{BASE_URL}/"
        f"departure-dashboard"
    )

    payload = {
        "id": DEPOT_ID,
        "organizationId": ORGANIZATION_ID
    }

    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY
    }

    return request_json(
        "POST",
        url,
        json=payload,
        headers=headers
    )
