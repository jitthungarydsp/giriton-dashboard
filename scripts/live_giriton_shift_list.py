from __future__ import annotations

import argparse
import calendar
import copy
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.parse_giriton_uidl_shift_list import shift_cards_from_uidl, walk_json


GIRITON_URL = "https://kiflihu.giriton.com/"
DEFAULT_UIDL_URL = "https://kiflihu.giriton.com/?v-r=uidl&v-uiId=0"


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_time(value: str) -> str:
    text = clean(value)
    match = re.match(r"^(\d{1,2}):(\d{2})", text)
    if not match:
        return text
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"


def parse_date(value: str | None, default: date) -> date:
    text = clean(value)
    if not text:
        return default
    return datetime.strptime(text, "%Y-%m-%d").date()


def parse_month(value: str) -> tuple[date, int]:
    text = clean(value)
    if not text:
        raise ValueError("Hiányzik a hónap. Formátum: YYYY-MM, például 2026-08.")
    month_start = datetime.strptime(text, "%Y-%m").date().replace(day=1)
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start, days_in_month


def chrome_options(headed: bool) -> Options:
    options = Options()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return options


def remove_path_chromedrivers() -> None:
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    kept_parts = []
    removed_parts = []
    for part in path_parts:
        if not part:
            continue
        if (Path(part) / "chromedriver.exe").exists() or (Path(part) / "chromedriver").exists():
            removed_parts.append(part)
            continue
        kept_parts.append(part)
    if removed_parts:
        os.environ["PATH"] = os.pathsep.join(kept_parts)
        print(
            "CHROMEDRIVER_PATH_SKIPPED "
            + ", ".join(str(Path(part) / "chromedriver.exe") for part in removed_parts),
            file=sys.stderr,
        )


def create_driver(headed: bool, chromedriver: str = ""):
    options = chrome_options(headed)
    if clean(chromedriver):
        driver = webdriver.Chrome(
            service=Service(executable_path=chromedriver),
            options=options,
        )
    else:
        remove_path_chromedrivers()
        driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def collect_uidl_payloads(driver) -> list[Any]:
    return [
        event["response_json"]
        for event in collect_uidl_events(driver)
        if isinstance(event.get("response_json"), (dict, list))
    ]


def collect_uidl_events(driver) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        logs = driver.get_log("performance")
    except Exception:
        return events

    for item in logs:
        try:
            message = json.loads(item.get("message") or "{}").get("message") or {}
        except json.JSONDecodeError:
            continue

        params = message.get("params") or {}
        method = message.get("method")
        request_id = params.get("requestId")
        post_data = ""
        if method == "Network.requestWillBeSent":
            request = params.get("request") or {}
            url = clean(request.get("url"))
            post_data = clean(request.get("postData"))
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            url = clean(response.get("url"))
        else:
            continue

        if "v-r=uidl" not in url:
            continue

        event: dict[str, Any] = {
            "method": method,
            "request_id": request_id,
            "url": url,
        }
        if post_data:
            try:
                event["request_json"] = json.loads(post_data)
            except json.JSONDecodeError:
                event["request_text"] = post_data

        if method == "Network.responseReceived" and request_id:
            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                )
                text = body.get("body") or ""
                event["response_json"] = json.loads(text)
            except Exception:
                pass

        events.append(event)

    return events


def response_payloads_from_events(events: list[dict[str, Any]]) -> list[Any]:
    return [
        event["response_json"]
        for event in events
        if isinstance(event.get("response_json"), (dict, list))
    ]


def write_uidl_events(events: list[dict[str, Any]], output_dir: str, work_date: date) -> None:
    if not clean(output_dir):
        return
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_path = path / f"giriton_uidl_{work_date.isoformat()}.json"
    output_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"GIRITON_UIDL_EVENTS={output_path}", file=sys.stderr)


def request_templates_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if isinstance(event.get("request_json"), dict)
    ]


def date_request_payload(payload: Any, work_date: date) -> None:
    if isinstance(payload, dict):
        for value in payload.values():
            date_request_payload(value, work_date)
    elif isinstance(payload, list):
        if (
            len(payload) >= 4
            and isinstance(payload[2], str)
            and payload[2] in {"update", "updateValueWithDelay"}
            and isinstance(payload[3], list)
            and len(payload[3]) >= 2
            and isinstance(payload[3][1], dict)
        ):
            payload[3][0] = work_date.strftime("%d/%m/%Y")
            payload[3][1]["YEAR"] = work_date.year
            payload[3][1]["MONTH"] = work_date.month
            payload[3][1]["DAY"] = work_date.day
        for value in payload:
            date_request_payload(value, work_date)


def callback_node_from_payload(payload: Any) -> str:
    for item in walk_json(payload):
        if not isinstance(item, list) or len(item) < 4:
            continue
        if item[1] != "com.vaadin.ui.JavaScript$JavaScriptCallbackRpc":
            continue
        if item[2] != "call":
            continue
        args = item[3]
        if isinstance(args, list) and args and args[0] == "initialize":
            return clean(item[0])
    return ""


def update_callback_rpc_node(payload: Any, callback_node: str) -> None:
    if not callback_node:
        return
    if isinstance(payload, dict):
        for value in payload.values():
            update_callback_rpc_node(value, callback_node)
    elif isinstance(payload, list):
        if (
            len(payload) >= 4
            and payload[1] == "com.vaadin.ui.JavaScript$JavaScriptCallbackRpc"
            and payload[2] == "call"
        ):
            payload[0] = callback_node
        for value in payload:
            update_callback_rpc_node(value, callback_node)


def adjust_uidl_counter_values(value: Any, *, sync_delta: int, client_delta: int) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key == "syncId" and isinstance(child, int):
                value[key] = child + sync_delta
            elif key == "clientId" and isinstance(child, int):
                value[key] = child + client_delta
            elif key == "promise" and isinstance(child, int):
                value[key] = child + client_delta
            else:
                adjust_uidl_counter_values(
                    child,
                    sync_delta=sync_delta,
                    client_delta=client_delta,
                )
    elif isinstance(value, list):
        for child in value:
            adjust_uidl_counter_values(
                child,
                sync_delta=sync_delta,
                client_delta=client_delta,
            )


def browser_cookie_header(driver) -> str:
    return "; ".join(
        f"{cookie.get('name')}={cookie.get('value')}"
        for cookie in driver.get_cookies()
        if cookie.get("name") and cookie.get("value")
    )


def uidl_headers(cookie: str) -> dict[str, str]:
    return {
        "accept": "*/*",
        "accept-language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json; charset=UTF-8",
        "origin": "https://kiflihu.giriton.com",
        "pragma": "no-cache",
        "referer": "https://kiflihu.giriton.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "cookie": cookie,
    }


def max_response_sync_id(events: list[dict[str, Any]], fallback: int) -> int:
    values = [
        event.get("response_json", {}).get("syncId")
        for event in events
        if isinstance(event.get("response_json"), dict)
        and isinstance(event.get("response_json", {}).get("syncId"), int)
    ]
    return max(values) if values else fallback


def post_uidl_sequence(
    *,
    templates: list[dict[str, Any]],
    work_date: date,
    cookie: str,
    base_sync_id: int,
    base_client_id: int,
    timeout: int,
) -> tuple[list[dict[str, Any]], int, int]:
    if not templates:
        return [], base_sync_id, base_client_id

    template_base_sync = templates[0]["request_json"].get("syncId")
    template_base_client = templates[0]["request_json"].get("clientId")
    if not isinstance(template_base_sync, int) or not isinstance(template_base_client, int):
        raise RuntimeError("A UIDL request mintában nincs használható syncId/clientId.")

    session = requests.Session()
    events: list[dict[str, Any]] = []
    current_sync = base_sync_id
    callback_node = ""
    for index, template in enumerate(templates):
        request_json = copy.deepcopy(template["request_json"])
        adjust_uidl_counter_values(
            request_json,
            sync_delta=base_sync_id - template_base_sync,
            client_delta=base_client_id - template_base_client,
        )
        date_request_payload(request_json, work_date)
        if index > 0:
            update_callback_rpc_node(request_json, callback_node)
        url = clean(template.get("url")) or DEFAULT_UIDL_URL
        response = session.post(
            url,
            headers=uidl_headers(cookie),
            json=request_json,
            timeout=timeout,
        )
        response.raise_for_status()
        response_json = response.json()
        if isinstance(response_json, dict) and response_json.get("meta", {}).get("sessionExpired"):
            raise RuntimeError("A gyors UIDL kérésnél lejárt a Giriton session.")
        if isinstance(response_json, dict) and isinstance(response_json.get("syncId"), int):
            current_sync = response_json["syncId"]
        callback_node = callback_node_from_payload(response_json) or callback_node
        events.append(
            {
                "method": "Direct.uidlPost",
                "url": url,
                "request_json": request_json,
                "response_json": response_json,
            }
        )

    return events, current_sync, base_client_id + len(templates)


def extract_shift_cards_from_uidl_payloads(payloads: list[Any], work_date: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = set()
    for payload in payloads:
        for row in shift_cards_from_uidl(payload):
            key = (
                row.get("warehouse") or "",
                row.get("start_time") or "",
                row.get("end_time") or "",
                row.get("occupancy") or "",
                row.get("subscribed_users") or "",
                row.get("title") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "work_date": work_date.isoformat(),
                    "source": "uidl",
                    **row,
                }
            )
    rows.sort(key=lambda row: (row.get("start_time") or "", row.get("warehouse") or "", row.get("title") or ""))
    return rows


def login(driver, user: str, password: str, timeout: int) -> None:
    driver.get(GIRITON_URL)
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.visibility_of_element_located((By.ID, "CompanyLoginPanel-tfUserLogin")))
    driver.find_element(By.ID, "CompanyLoginPanel-tfUserLogin").send_keys(user)
    password_input = driver.find_element(By.ID, "CompanyLoginPanel-pfUserPassword")
    password_input.send_keys(password)
    password_input.send_keys(Keys.ENTER)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "layMenuItems")))
        return
    except Exception:
        driver.execute_script(
            """
            const visible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
            const buttons = [...document.querySelectorAll('.v-button, [role="button"], button, input[type="submit"]')].filter(visible);
            const loginButton = buttons.find(el => /login|log in|sign in|bejelentkez/i.test((el.innerText || el.value || '').trim())) || buttons[buttons.length - 1];
            if (!loginButton) { throw new Error('Visible login button not found'); }
            loginButton.click();
            """
        )
        wait.until(EC.presence_of_element_located((By.ID, "layMenuItems")))


def open_shift_subscriptions(driver, timeout: int) -> None:
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.visibility_of_element_located((By.XPATH, '//*[@id="layMenuItems"]/div[5]/div/span')))
    driver.find_element(By.XPATH, '//*[@id="layMenuItems"]/div[5]/div/span').click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".v-button")))


def select_all_departments(driver, timeout: int) -> None:
    wait = WebDriverWait(driver, timeout)
    wait.until(
        EC.visibility_of_element_located(
            (
                By.XPATH,
                "//span[contains(@class,'v-button-caption') and "
                "(contains(normalize-space(.),'Just in Time Kft') or "
                "contains(normalize-space(.),'multiple departm') or "
                "contains(normalize-space(.),'all departments'))]",
            )
        )
    )
    driver.execute_script(
        """
        const visible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
        const departmentButton = [...document.querySelectorAll('.v-button')].find(el => {
          const text = (el.innerText || '').trim();
          return (text.includes('Just in Time Kft') || text.includes('multiple departm') || text.includes('all departments')) && visible(el);
        });
        if (!departmentButton) { throw new Error('Visible department button not found'); }
        departmentButton.click();
        """
    )
    wait.until(lambda _driver: "Departments" in driver.find_element(By.TAG_NAME, "body").text)
    driver.execute_script(
        """
        const visible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
        const label = [...document.querySelectorAll('label')].find(el => (el.innerText || '').includes('all departments') && visible(el));
        if (!label) { throw new Error('Visible all departments label not found'); }
        label.click();
        """
    )
    time.sleep(1)
    driver.execute_script(
        """
        const visible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
        const button = [...document.querySelectorAll('.v-button')].find(el => (el.innerText || '').trim() === 'Choose' && visible(el));
        if (!button) { throw new Error('Visible Choose button not found'); }
        button.click();
        """
    )
    time.sleep(3)


def set_giriton_date(driver, work_date: date) -> None:
    expected = work_date.strftime("%d/%m/%Y")
    result = driver.execute_script(
        """
        const expected = arguments[0];
        const visible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
        const looksLikeDate = value => String(value || '').trim().includes('/') && String(value || '').trim().length >= 8;
        const inputs = [...document.querySelectorAll('input.v-datefield-textfield, input[class*="v-datefield-textfield"]')].filter(visible);
        const candidates = inputs.filter(input => looksLikeDate(input.value) || looksLikeDate(input.placeholder) || input.closest('.v-datefield'));
        const input = candidates.find(item => looksLikeDate(item.value)) || candidates[0] || inputs[0];
        if (!input) { return 'DATE_INPUT_NOT_FOUND'; }
        input.scrollIntoView({block:'center', inline:'nearest'});
        input.focus();
        input.value = expected;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        input.dispatchEvent(new Event('change', {bubbles:true}));
        input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
        input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
        input.blur();
        return input.value || '';
        """,
        expected,
    )
    if result == "DATE_INPUT_NOT_FOUND":
        raise RuntimeError("Nem találom a Giriton dátum mezőt.")
    time.sleep(4)


def wait_until_loaded(driver, timeout: int) -> None:
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".panel-title")))
    for _ in range(timeout):
        loading = driver.execute_script(
            """
            return [...document.querySelectorAll('.v-loading-indicator, .v-loading-indicator-delay, .v-loading-indicator-wait')]
              .some(el => {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
              });
            """
        )
        if not loading:
            return
        time.sleep(1)


def scroll_all_shifts(driver) -> None:
    driver.execute_script(
        """
        const els = [...document.querySelectorAll('*')];
        const scrollable = els.filter(e => e.scrollHeight > e.clientHeight);
        const biggest = scrollable.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
        if (biggest) { biggest.scrollTop = 0; }
        """
    )
    time.sleep(1)
    for _ in range(15):
        driver.execute_script(
            """
            const els = [...document.querySelectorAll('*')];
            const scrollable = els.filter(e => e.scrollHeight > e.clientHeight);
            const biggest = scrollable.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
            if (biggest) { biggest.scrollTop = biggest.scrollHeight; }
            """
        )
        time.sleep(0.4)


def extract_shift_cards(driver, work_date: date) -> list[dict[str, Any]]:
    raw_rows = driver.execute_script(
        """
        const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
        const rows = [];
        const panels = [...document.querySelectorAll('.shift-subscription-preview-panel')];
        for (const panel of panels) {
          const title = clean(panel.querySelector('.panel-title')?.innerText || '');
          const labels = [...panel.querySelectorAll('.info-label-value')].map(el => clean(el.innerText));
          const statusText = clean([...panel.querySelectorAll('.v-label, .v-widget')]
            .map(el => el.innerText || '')
            .find(text => /\\d+\\s*\\/\\s*\\d+/.test(text)) || '');
          const subscribed = clean(panel.querySelector('.subscribed-persons-label')?.innerText || '');
          rows.push({title, labels, statusText, subscribed});
        }
        return rows;
        """
    )
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        title = clean(raw.get("title"))
        labels = raw.get("labels") or []
        status_text = clean(raw.get("statusText"))
        subscribed = clean(raw.get("subscribed")).removeprefix("Subscribed users:").strip()
        if subscribed.casefold() in {"(none)", "none"}:
            subscribed = ""

        warehouse = ""
        label_text = " ".join(clean(value) for value in labels)
        warehouse_match = re.search(r"\b(BUD\d+)\b", label_text.upper() + " " + title.upper())
        if warehouse_match:
            warehouse = warehouse_match.group(1)

        times_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$", title)
        start_time = normalize_time(times_match.group(1)) if times_match else ""
        end_time = normalize_time(times_match.group(2)) if times_match else ""

        numbers = re.findall(r"\d+", status_text)
        booked = int(numbers[0]) if len(numbers) >= 2 else None
        maximum = int(numbers[1]) if len(numbers) >= 2 else None
        free_slots = None if booked is None or maximum is None else max(maximum - booked, 0)

        rows.append(
            {
                "work_date": work_date.isoformat(),
                "warehouse": warehouse,
                "start_time": start_time,
                "end_time": end_time,
                "occupancy": status_text,
                "booked": booked,
                "maximum": maximum,
                "free_slots": free_slots,
                "subscribed_users": subscribed,
                "title": title,
                "is_open": free_slots is not None and free_slots > 0,
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "work_date",
        "source",
        "warehouse",
        "start_time",
        "end_time",
        "occupancy",
        "booked",
        "maximum",
        "free_slots",
        "subscribed_users",
        "title",
        "is_open",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def print_table(rows: list[dict[str, Any]], only_open: bool) -> None:
    visible = [row for row in rows if row.get("is_open")] if only_open else rows
    print(f"GIRITON_LIVE_SHIFTS total={len(rows)} visible={len(visible)} only_open={only_open}")
    for row in visible:
        users = clean(row.get("subscribed_users")) or "-"
        print(
            " | ".join(
                [
                    clean(row.get("work_date")),
                    clean(row.get("warehouse")) or "-",
                    clean(row.get("start_time")) or "-",
                    clean(row.get("end_time")) or "-",
                    clean(row.get("occupancy")) or "-",
                    f"szabad={row.get('free_slots') if row.get('free_slots') is not None else '-'}",
                    f"foglalt={users}",
                    clean(row.get("title")) or "-",
                ]
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Élő Giriton bejelentkezés után visszaadja a műszaklistát."
    )
    parser.add_argument("--start-date", default="", help="Kezdő nap YYYY-MM-DD. Alap: ma.")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--month", default="", help="Egész hónap lekérése YYYY-MM formátumban, például 2026-08.")
    parser.add_argument("--only-open", action="store_true")
    parser.add_argument("--source", choices=["uidl", "dom"], default="uidl")
    parser.add_argument("--fast-uidl", action="store_true", help="Az első nap után UI léptetés helyett közvetlen UIDL POST-tal kérje le a napokat.")
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument("--csv", default="")
    parser.add_argument("--uidl-dir", default="", help="UIDL request/response események mentése könyvtárba.")
    parser.add_argument("--headed", action="store_true", help="Látható Chrome ablakban fusson.")
    parser.add_argument("--chromedriver", default="", help="Opcionális konkrét chromedriver útvonal.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--user", default=os.getenv("GIRITON_USER", ""))
    parser.add_argument("--password", default=os.getenv("GIRITON_PASSWORD", ""))
    args = parser.parse_args()

    user = clean(args.user)
    password = clean(args.password)
    if not user or not password:
        raise RuntimeError("Hiányzik a Giriton belépés. Add meg GIRITON_USER/GIRITON_PASSWORD env-ben vagy --user/--password opcióval.")

    if clean(args.month):
        start_date, days_to_collect = parse_month(args.month)
    else:
        start_date = parse_date(args.start_date, date.today())
        days_to_collect = max(int(args.days), 1)

    all_rows: list[dict[str, Any]] = []
    fast_templates: list[dict[str, Any]] = []
    fast_cookie = ""
    fast_sync_id = 0
    fast_client_id = 0

    driver = create_driver(args.headed, args.chromedriver)
    try:
        login(driver, user, password, args.timeout)
        open_shift_subscriptions(driver, args.timeout)
        select_all_departments(driver, args.timeout)
        collect_uidl_events(driver)
        for offset in range(days_to_collect):
            work_date = start_date + timedelta(days=offset)
            if args.fast_uidl and offset > 0 and fast_templates:
                try:
                    uidl_events, fast_sync_id, fast_client_id = post_uidl_sequence(
                        templates=fast_templates,
                        work_date=work_date,
                        cookie=fast_cookie,
                        base_sync_id=fast_sync_id,
                        base_client_id=fast_client_id,
                        timeout=args.timeout,
                    )
                    write_uidl_events(uidl_events, args.uidl_dir, work_date)
                    payloads = response_payloads_from_events(uidl_events)
                    day_rows = extract_shift_cards_from_uidl_payloads(payloads, work_date)
                    for row in day_rows:
                        row["source"] = "uidl-direct"
                    print(
                        f"GIRITON_UIDL_DIRECT_DAY date={work_date.isoformat()} events={len(uidl_events)} payloads={len(payloads)} rows={len(day_rows)}",
                        file=sys.stderr,
                    )
                    if not day_rows:
                        raise RuntimeError("A direkt UIDL kérés nem adott műszakkártyákat.")
                except Exception as error:
                    print(
                        f"GIRITON_UIDL_DIRECT_FALLBACK_UI date={work_date.isoformat()} error={error}",
                        file=sys.stderr,
                    )
                    fast_templates = []
                    set_giriton_date(driver, work_date)
                    wait_until_loaded(driver, args.timeout)
                    scroll_all_shifts(driver)
                    uidl_events = collect_uidl_events(driver)
                    write_uidl_events(uidl_events, args.uidl_dir, work_date)
                    payloads = response_payloads_from_events(uidl_events)
                    day_rows = extract_shift_cards_from_uidl_payloads(payloads, work_date)
                    if not day_rows:
                        day_rows = extract_shift_cards(driver, work_date)
                        for row in day_rows:
                            row["source"] = "dom-fallback"
            else:
                set_giriton_date(driver, work_date)
                wait_until_loaded(driver, args.timeout)
                scroll_all_shifts(driver)
                if args.source == "uidl":
                    uidl_events = collect_uidl_events(driver)
                    write_uidl_events(uidl_events, args.uidl_dir, work_date)
                    payloads = response_payloads_from_events(uidl_events)
                    day_rows = extract_shift_cards_from_uidl_payloads(payloads, work_date)
                    print(
                        f"GIRITON_UIDL_DAY date={work_date.isoformat()} events={len(uidl_events)} payloads={len(payloads)} rows={len(day_rows)}",
                        file=sys.stderr,
                    )
                    if args.fast_uidl and not fast_templates:
                        fast_templates = request_templates_from_events(uidl_events)
                        fast_cookie = browser_cookie_header(driver)
                        fast_sync_id = max_response_sync_id(
                            uidl_events,
                            fast_templates[-1]["request_json"].get("syncId", 0) if fast_templates else 0,
                        )
                        fast_client_id = (
                            max(
                                event["request_json"].get("clientId", 0)
                                for event in fast_templates
                                if isinstance(event.get("request_json"), dict)
                            )
                            + 1
                            if fast_templates
                            else 0
                        )
                        print(
                            f"GIRITON_UIDL_FAST_TEMPLATE requests={len(fast_templates)} next_sync={fast_sync_id} next_client={fast_client_id}",
                            file=sys.stderr,
                        )
                    if not day_rows:
                        print(
                            f"GIRITON_UIDL_EMPTY_FALLBACK_DOM date={work_date.isoformat()}",
                            file=sys.stderr,
                        )
                        day_rows = extract_shift_cards(driver, work_date)
                        for row in day_rows:
                            row["source"] = "dom-fallback"
                else:
                    day_rows = extract_shift_cards(driver, work_date)
                    for row in day_rows:
                        row["source"] = "dom"
            if args.source == "uidl":
                if not day_rows:
                    print(f"GIRITON_UIDL_NO_ROWS date={work_date.isoformat()}", file=sys.stderr)
            all_rows.extend(day_rows)
            print(f"GIRITON_LIVE_DAY date={work_date.isoformat()} rows={len(day_rows)}", file=sys.stderr)
    finally:
        driver.quit()

    if args.csv:
        write_csv(all_rows, Path(args.csv))
        print(f"GIRITON_LIVE_CSV={args.csv}")

    visible_rows = [row for row in all_rows if row.get("is_open")] if args.only_open else all_rows
    if args.json_output:
        print(json.dumps(visible_rows, ensure_ascii=False, indent=2))
    else:
        print_table(all_rows, args.only_open)


if __name__ == "__main__":
    main()
