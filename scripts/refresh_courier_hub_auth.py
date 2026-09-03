#!/usr/bin/env python3
"""Refresh Courier Hub auth headers with a browser login.

The script prints a single JSON object to stdout so it can be used as
COURIER_HUB_AUTH_REFRESH_COMMAND by the API importers. Diagnostics go to stderr
and never include the token value.
"""

from __future__ import annotations

import argparse
from http.cookies import SimpleCookie
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests
from selenium import webdriver
from selenium.common.exceptions import JavascriptException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_BASE_URL = "https://courier-hub.kifli.hu/"
DEFAULT_PROBE_PATH = (
    "/services/courier-hub-service/external/warehouses/2/"
    "live-monitoring-dashboard?dspId=8"
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


def save_debug_artifacts(driver: webdriver.Chrome, debug_dir: str, label: str) -> None:
    if not debug_dir:
        return
    output_dir = Path(debug_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in label)
    try:
        driver.save_screenshot(str(output_dir / f"{safe_label}.png"))
    except Exception as exc:
        debug(f"COURIER_HUB_AUTH_DEBUG_SCREENSHOT_ERROR={type(exc).__name__}")
    try:
        (output_dir / f"{safe_label}.html").write_text(driver.page_source, encoding="utf-8")
    except Exception as exc:
        debug(f"COURIER_HUB_AUTH_DEBUG_HTML_ERROR={type(exc).__name__}")
    debug(f"COURIER_HUB_AUTH_DEBUG_ARTIFACTS={output_dir / safe_label}")


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


def tokens_from_indexeddb(driver: webdriver.Chrome) -> list[str]:
    try:
        values = driver.execute_async_script(
            """
const done = arguments[arguments.length - 1];
(async () => {
  if (!window.indexedDB || !indexedDB.databases) return [];
  const result = [];
  const databases = await indexedDB.databases();
  for (const databaseInfo of databases) {
    if (!databaseInfo.name) continue;
    await new Promise((resolve) => {
      const openRequest = indexedDB.open(databaseInfo.name);
      openRequest.onerror = () => resolve();
      openRequest.onsuccess = () => {
        const db = openRequest.result;
        const storeNames = Array.from(db.objectStoreNames || []);
        if (!storeNames.length) {
          db.close();
          resolve();
          return;
        }
        const transaction = db.transaction(storeNames, "readonly");
        transaction.oncomplete = () => {
          db.close();
          resolve();
        };
        transaction.onerror = () => {
          db.close();
          resolve();
        };
        for (const storeName of storeNames) {
          const store = transaction.objectStore(storeName);
          const getRequest = store.getAll();
          getRequest.onsuccess = () => {
            for (const item of getRequest.result || []) {
              try {
                result.push(JSON.stringify(item));
              } catch (_) {
                result.push(String(item));
              }
            }
          };
        }
      };
    });
  }
  return result;
})()
  .then(done)
  .catch((error) => done({error: String(error)}));
"""
        )
    except JavascriptException:
        return []

    tokens: list[str] = []
    if not isinstance(values, list):
        return tokens
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            tokens.extend(flatten_json_tokens(json.loads(text)))
        except Exception:
            if text_is_token(text):
                tokens.append(text)
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


def seed_browser_cookies(driver: webdriver.Chrome, base_url: str) -> int:
    cookie_text = setting("COURIER_HUB_COOKIE", "KIFLI_COURIER_HUB_COOKIE")
    if not cookie_text:
        return 0

    parsed = SimpleCookie()
    try:
        parsed.load(cookie_text)
    except Exception:
        return 0

    driver.get(base_url)
    added = 0
    for morsel in parsed.values():
        name = str(morsel.key or "").strip()
        value = str(morsel.value or "").strip()
        if not name or not value:
            continue
        cookie = {
            "name": name,
            "value": value,
            "path": "/",
            "secure": True,
            "sameSite": "Lax",
        }
        try:
            driver.add_cookie(cookie)
            added += 1
        except Exception:
            continue
    if added:
        driver.get(base_url)
        time.sleep(2)
    return added


def find_first(driver: webdriver.Chrome, selectors: list[str]):
    for selector in selectors:
        matches = driver.find_elements(By.CSS_SELECTOR, selector)
        visible = [item for item in matches if item.is_displayed() and item.is_enabled()]
        if visible:
            return visible[0]
    return None


def click_rohlik_login_if_present(driver: webdriver.Chrome, wait_seconds: int) -> bool:
    try:
        button = driver.execute_script(
            """
const candidates = Array.from(document.querySelectorAll('a, button'));
return candidates.find((element) => {
  const text = (element.innerText || element.textContent || '').toLowerCase();
  return text.includes('rohlik') || text.includes('bejelentkez');
}) || null;
"""
        )
    except JavascriptException:
        button = None

    if not button:
        return False

    try:
        button.click()
        WebDriverWait(driver, wait_seconds).until(
            lambda current_driver: (
                current_driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                or current_driver.find_elements(By.CSS_SELECTOR, "input[name='username']")
                or current_driver.find_elements(By.CSS_SELECTOR, "input#username")
            )
        )
        time.sleep(1)
        return True
    except Exception as exc:
        debug(f"COURIER_HUB_AUTH_ROHLIK_LOGIN_CLICK_FAILED={type(exc).__name__}")
        return False


def login_if_needed(driver: webdriver.Chrome, username: str, password: str, wait_seconds: int) -> None:
    wait = WebDriverWait(driver, wait_seconds)
    password_input = find_first(driver, ["input[type='password']", "input[name*='password' i]"])
    if not password_input and click_rohlik_login_if_present(driver, wait_seconds):
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


def probe_api_with_headers(base_url: str, probe_path: str, headers: dict[str, str]) -> dict[str, Any]:
    today = date.today().isoformat()
    path = probe_path.format(today=today)
    url = path if path.startswith("http") else base_url.rstrip("/") + "/" + path.lstrip("/")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        return {"status": response.status_code}
    except requests.RequestException as exc:
        return {"error": str(exc)}


def refresh_session(driver: webdriver.Chrome, base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/auth/session"
    try:
        result = driver.execute_async_script(
            """
const url = arguments[0];
const done = arguments[arguments.length - 1];
fetch(url, {
  credentials: 'include',
  headers: {'Accept': 'application/json'},
})
  .then(async (response) => done({
    status: response.status,
    ok: response.ok,
  }))
  .catch(error => done({error: String(error)}));
""",
            url,
        )
        return result if isinstance(result, dict) else {}
    except JavascriptException as exc:
        debug(f"COURIER_HUB_AUTH_SESSION_REFRESH_ERROR={type(exc).__name__}")
        return {}


def auth_payload_from_driver(driver: webdriver.Chrome) -> dict[str, Any]:
    authorization = authorization_from_performance_logs(driver)
    if not authorization:
        tokens = tokens_from_storage(driver)
        authorization = normalize_authorization(tokens[0]) if tokens else ""
    if not authorization:
        tokens = tokens_from_indexeddb(driver)
        authorization = normalize_authorization(tokens[0]) if tokens else ""
    cookie = cookie_header(driver)
    return {
        "headers": {
            **({"Authorization": authorization} if authorization else {}),
            **({"Cookie": cookie} if cookie else {}),
        }
    }


def probe_auth_payload(driver: webdriver.Chrome, base_url: str, probe_path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    header_probe_result = probe_api_with_headers(
        base_url,
        probe_path,
        payload.get("headers") or {},
    )
    if header_probe_result.get("status") == 200:
        return header_probe_result, {}
    browser_probe_result = probe_api(driver, base_url, probe_path)
    return header_probe_result, browser_probe_result


def write_cache_file(payload: dict[str, Any], cache_file: str) -> None:
    if not cache_file:
        return
    cache_path = Path(cache_file)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    debug(f"COURIER_HUB_AUTH_CACHE_WRITE={cache_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=setting("COURIER_HUB_LOGIN_URL", "KIFLI_COURIER_HUB_LOGIN_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--probe-path", default=setting("COURIER_HUB_AUTH_PROBE_PATH", "KIFLI_COURIER_HUB_AUTH_PROBE_PATH") or DEFAULT_PROBE_PATH)
    parser.add_argument("--wait", type=int, default=int(setting("COURIER_HUB_AUTH_WAIT_SECONDS", "KIFLI_COURIER_HUB_AUTH_WAIT_SECONDS") or "45"))
    parser.add_argument("--debug-dir", default=setting("COURIER_HUB_AUTH_DEBUG_DIR", "KIFLI_COURIER_HUB_AUTH_DEBUG_DIR"))
    parser.add_argument("--cache-file", default=setting("COURIER_HUB_AUTH_CACHE_FILE", "KIFLI_COURIER_HUB_AUTH_CACHE_FILE"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    username = setting("COURIER_HUB_USERNAME", "KIFLI_COURIER_HUB_USERNAME")
    password = setting("COURIER_HUB_PASSWORD", "KIFLI_COURIER_HUB_PASSWORD")
    configured_cookie = setting("COURIER_HUB_COOKIE", "KIFLI_COURIER_HUB_COOKIE")
    configured_authorization = setting("COURIER_HUB_AUTHORIZATION", "KIFLI_COURIER_HUB_AUTHORIZATION")
    if not ((username and password) or configured_cookie or configured_authorization):
        raise RuntimeError("Missing Courier Hub auth secrets.")

    driver = webdriver.Chrome(options=chrome_options(args.headed))
    try:
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass
        driver.get(args.url)
        time.sleep(3)
        seeded_cookies = seed_browser_cookies(driver, args.url)
        debug(f"COURIER_HUB_AUTH_COOKIE_SEED={seeded_cookies}")

        session_result = refresh_session(driver, args.url)
        debug(
            "COURIER_HUB_AUTH_SESSION_REFRESH="
            f"{session_result.get('status') or session_result.get('error') or '-'}"
        )
        payload = auth_payload_from_driver(driver)
        if configured_authorization:
            payload.setdefault("headers", {})["Authorization"] = normalize_authorization(configured_authorization)
        header_probe_result, browser_probe_result = probe_auth_payload(
            driver,
            args.url,
            args.probe_path,
            payload,
        )
        header_probe_status = header_probe_result.get("status")
        browser_probe_status = browser_probe_result.get("status")
        if header_probe_status == 200 or browser_probe_status == 200:
            debug(
                "COURIER_HUB_AUTH_REFRESH=OK "
                f"authorization={'yes' if payload.get('headers', {}).get('Authorization') else 'no'} "
                f"cookies={'yes' if payload.get('headers', {}).get('Cookie') else 'no'} "
                f"probe_status={header_probe_status or browser_probe_status or '-'} "
                f"header_probe_status={header_probe_status or '-'} "
                f"browser_probe_status={browser_probe_status or '-'} "
                "source=seeded_session"
            )
            write_cache_file(payload, args.cache_file)
            print(json.dumps(payload, ensure_ascii=False))
            return 0

        if not (username and password):
            save_debug_artifacts(driver, args.debug_dir, "auth_probe_failed")
            raise RuntimeError(
                "Courier Hub auth refresh did not pass API probe and login secrets are missing. "
                f"Header probe status={header_probe_status or header_probe_result.get('error') or '-'}, "
                f"browser probe status={browser_probe_status or browser_probe_result.get('error') or '-'}, "
                f"authorization={'yes' if payload.get('headers', {}).get('Authorization') else 'no'}, "
                f"cookies={'yes' if payload.get('headers', {}).get('Cookie') else 'no'}."
            )

        login_if_needed(driver, username, password, args.wait)
        session_result = refresh_session(driver, args.url)
        debug(
            "COURIER_HUB_AUTH_SESSION_REFRESH="
            f"{session_result.get('status') or session_result.get('error') or '-'}"
        )
        browser_probe_result = probe_api(driver, args.url, args.probe_path)
        time.sleep(2)

        payload = auth_payload_from_driver(driver)
        header_probe_result = probe_api_with_headers(
            args.url,
            args.probe_path,
            payload["headers"],
        )
        browser_probe_status = browser_probe_result.get("status")
        header_probe_status = header_probe_result.get("status")
        probe_status = header_probe_status or browser_probe_status
        if header_probe_status != 200 and browser_probe_status != 200:
            save_debug_artifacts(driver, args.debug_dir, "auth_probe_failed")
            raise RuntimeError(
                "Courier Hub auth refresh did not pass API probe. "
                f"Header probe status={header_probe_status or header_probe_result.get('error') or '-'}, "
                f"browser probe status={browser_probe_status or browser_probe_result.get('error') or '-'}, "
                f"authorization={'yes' if payload.get('headers', {}).get('Authorization') else 'no'}, "
                f"cookies={'yes' if payload.get('headers', {}).get('Cookie') else 'no'}."
            )

        debug(
            "COURIER_HUB_AUTH_REFRESH=OK "
            f"authorization={'yes' if payload.get('headers', {}).get('Authorization') else 'no'} "
            f"cookies={'yes' if payload.get('headers', {}).get('Cookie') else 'no'} "
            f"probe_status={probe_status or '-'} "
            f"header_probe_status={header_probe_status or '-'} "
            f"browser_probe_status={browser_probe_status or '-'} "
            "source=login"
        )
        write_cache_file(payload, args.cache_file)

        print(
            json.dumps(payload, ensure_ascii=False)
        )
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
