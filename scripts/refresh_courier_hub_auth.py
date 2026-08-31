#!/usr/bin/env python3
"""Refresh Courier Hub auth headers with a browser login.

The script prints a single JSON object to stdout so it can be used as
COURIER_HUB_AUTH_REFRESH_COMMAND by the API importers. Diagnostics go to stderr
and never include the token value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import JavascriptException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/"
DEFAULT_PROBE_PATH = (
    "/services/courier-hub-service/external/performance/dsp/JIT/couriers"
    "?dateFrom={today}&dateTo={today}&dspId=8&warehouseId=1"
)
TOKEN_KEY_PARTS = ("token", "authorization", "auth", "jwt", "access")


def setting(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def debug(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def chrome_options(headed: bool) -> Options:
    options = Options()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return options


def text_is_token(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and (
        text.lower().startswith("bearer ")
        or text.count(".") >= 2
        or len(text) > 80
    )


def normalize_authorization(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith(("bearer ", "basic ", "token ")):
        return text
    return f"Bearer {text}"


def flatten_json_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key or "").lower()
            if any(part in key_text for part in TOKEN_KEY_PARTS) and text_is_token(child):
                tokens.append(str(child).strip())
            tokens.extend(flatten_json_tokens(child))
    elif isinstance(value, list):
        for child in value:
            tokens.extend(flatten_json_tokens(child))
    elif text_is_token(value):
        tokens.append(str(value).strip())
    return tokens


def storage_values(driver: webdriver.Chrome, storage_name: str) -> dict[str, str]:
    try:
        return driver.execute_script(
            """
const storage = window[arguments[0]];
const result = {};
for (let i = 0; i < storage.length; i += 1) {
  const key = storage.key(i);
  result[key] = storage.getItem(key);
}
return result;
""",
            storage_name,
        )
    except JavascriptException:
        return {}


def tokens_from_storage(driver: webdriver.Chrome) -> list[str]:
    tokens: list[str] = []
    for storage_name in ("localStorage", "sessionStorage"):
        for key, value in storage_values(driver, storage_name).items():
            key_text = str(key or "").lower()
            text = str(value or "").strip()
            if any(part in key_text for part in TOKEN_KEY_PARTS) and text_is_token(text):
                tokens.append(text)
            try:
                tokens.extend(flatten_json_tokens(json.loads(text)))
            except Exception:
                continue
    return tokens


def authorization_from_performance_logs(driver: webdriver.Chrome) -> str:
    try:
        logs = driver.get_log("performance")
    except Exception:
        return ""

    for entry in reversed(logs):
        try:
            message = json.loads(entry.get("message") or "{}").get("message") or {}
        except Exception:
            continue
        method = message.get("method")
        params = message.get("params") or {}
        request = params.get("request") or {}
        headers = params.get("headers") or request.get("headers") or {}
        if method not in {"Network.requestWillBeSent", "Network.requestWillBeSentExtraInfo"}:
            continue
        authorization = headers.get("Authorization") or headers.get("authorization")
        if authorization:
            return str(authorization).strip()
    return ""


def cookie_header(driver: webdriver.Chrome) -> str:
    pairs = []
    for cookie in driver.get_cookies():
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def find_first(driver: webdriver.Chrome, selectors: list[str]):
    for selector in selectors:
        matches = driver.find_elements(By.CSS_SELECTOR, selector)
        visible = [item for item in matches if item.is_displayed() and item.is_enabled()]
        if visible:
            return visible[0]
    return None


def login_if_needed(driver: webdriver.Chrome, username: str, password: str, wait_seconds: int) -> None:
    wait = WebDriverWait(driver, wait_seconds)
    password_input = find_first(driver, ["input[type='password']", "input[name*='password' i]"])
    if not password_input:
        debug("COURIER_HUB_AUTH_LOGIN_FORM=not_found")
        return

    user_input = find_first(
        driver,
        [
            "input[type='email']",
            "input[name*='email' i]",
            "input[name*='user' i]",
            "input[id*='email' i]",
            "input[id*='user' i]",
            "input[type='text']",
        ],
    )
    if not user_input:
        raise RuntimeError("Courier Hub login form found, but username input was not found.")

    user_input.clear()
    user_input.send_keys(username)
    password_input.clear()
    password_input.send_keys(password)
    password_input.send_keys(Keys.ENTER)

    try:
        wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    except TimeoutException:
        debug("COURIER_HUB_AUTH_LOGIN_WAIT=password_still_visible")
    time.sleep(3)


def probe_api(driver: webdriver.Chrome, base_url: str, probe_path: str) -> dict[str, Any]:
    today = date.today().isoformat()
    path = probe_path.format(today=today)
    url = path if path.startswith("http") else base_url.rstrip("/") + "/" + path.lstrip("/")
    try:
        result = driver.execute_async_script(
            """
const url = arguments[0];
const done = arguments[arguments.length - 1];
fetch(url, {credentials: 'include'})
  .then(response => done({status: response.status}))
  .catch(error => done({error: String(error)}));
""",
            url,
        )
        return result if isinstance(result, dict) else {}
    except JavascriptException as exc:
        debug(f"COURIER_HUB_AUTH_PROBE_ERROR={type(exc).__name__}")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=setting("COURIER_HUB_LOGIN_URL", "KIFLI_COURIER_HUB_LOGIN_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--probe-path", default=setting("COURIER_HUB_AUTH_PROBE_PATH", "KIFLI_COURIER_HUB_AUTH_PROBE_PATH") or DEFAULT_PROBE_PATH)
    parser.add_argument("--wait", type=int, default=int(setting("COURIER_HUB_AUTH_WAIT_SECONDS", "KIFLI_COURIER_HUB_AUTH_WAIT_SECONDS") or "45"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    username = setting("COURIER_HUB_USERNAME", "KIFLI_COURIER_HUB_USERNAME")
    password = setting("COURIER_HUB_PASSWORD", "KIFLI_COURIER_HUB_PASSWORD")
    if not username or not password:
        raise RuntimeError("Missing COURIER_HUB_USERNAME/COURIER_HUB_PASSWORD secrets.")

    driver = webdriver.Chrome(options=chrome_options(args.headed))
    try:
        driver.get(args.url)
        time.sleep(3)
        login_if_needed(driver, username, password, args.wait)
        probe_result = probe_api(driver, args.url, args.probe_path)
        time.sleep(2)

        authorization = authorization_from_performance_logs(driver)
        if not authorization:
            tokens = tokens_from_storage(driver)
            authorization = normalize_authorization(tokens[0]) if tokens else ""
        cookie = cookie_header(driver)

        probe_status = probe_result.get("status")
        if not authorization:
            raise RuntimeError(
                "Courier Hub auth refresh did not find Bearer authorization. "
                f"Browser probe status={probe_status or '-'}, cookies={'yes' if cookie else 'no'}."
            )

        debug(
            "COURIER_HUB_AUTH_REFRESH=OK "
            f"authorization={'yes' if authorization else 'no'} "
            f"cookies={'yes' if cookie else 'no'} "
            f"probe_status={probe_status or '-'}"
        )
        print(
            json.dumps(
                {
                    "headers": {
                        **({"Authorization": authorization} if authorization else {}),
                        **({"Cookie": cookie} if cookie else {}),
                    }
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
