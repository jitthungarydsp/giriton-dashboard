import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


DEFAULT_OWNER = "jitthungarydsp"
DEFAULT_REPO = "giriton-dashboard"
DEFAULT_WORKFLOW = "giriton-robots.yml"
DEFAULT_REF = "main"
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


class GitHubActionsError(Exception):
    pass


def _secret(name, default=""):
    value = os.getenv(name)
    if value:
        return value

    if st is None:
        return default

    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_config():
    return {
        "owner": _secret("GITHUB_OWNER", DEFAULT_OWNER),
        "repo": _secret("GITHUB_REPO", DEFAULT_REPO),
        "workflow": _secret("GITHUB_WORKFLOW", DEFAULT_WORKFLOW),
        "ref": _secret("GITHUB_REF", DEFAULT_REF),
        "token": _secret("GITHUB_ACTIONS_TOKEN", ""),
    }


def get_actions_url():
    config = get_config()
    return f"https://github.com/{config['owner']}/{config['repo']}/actions/workflows/{config['workflow']}"


def _headers(config):
    token = config.get("token")
    if not token:
        raise GitHubActionsError(
            "Hiányzik a GITHUB_ACTIONS_TOKEN secret. Streamlit Cloudban add hozzá a Secrets részhez."
        )

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def dispatch_robot(run_folgaltsag=False, run_girition=False, run_dsp=False):
    config = get_config()
    url = (
        f"https://api.github.com/repos/{config['owner']}/{config['repo']}"
        f"/actions/workflows/{config['workflow']}/dispatches"
    )
    payload = {
        "ref": config["ref"],
        "inputs": {
            "run_folgaltsag": "true" if run_folgaltsag else "false",
            "run_girition": "true" if run_girition else "false",
            "run_dsp": "true" if run_dsp else "false",
        },
    }

    response = requests.post(
        url,
        headers=_headers(config),
        json=payload,
        timeout=20,
    )

    if response.status_code != 204:
        raise GitHubActionsError(
            f"GitHub Actions indítás sikertelen: HTTP {response.status_code} - {response.text[:500]}"
        )

    return {
        "workflow": config["workflow"],
        "ref": config["ref"],
        "triggered_at": datetime.now(BUDAPEST_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_latest_runs(limit=8):
    config = get_config()
    url = (
        f"https://api.github.com/repos/{config['owner']}/{config['repo']}"
        f"/actions/workflows/{config['workflow']}/runs"
    )
    response = requests.get(
        url,
        headers=_headers(config),
        params={"per_page": limit},
        timeout=20,
    )

    if response.status_code != 200:
        raise GitHubActionsError(
            f"GitHub Actions állapot lekérés sikertelen: HTTP {response.status_code} - {response.text[:500]}"
        )

    return response.json().get("workflow_runs", [])
