"""Export the values shown by the Streamlit devtest settlement page.

This deliberately drives the rendered devtest UI with Selenium.  It logs in,
selects the settlement month, reads every courier row, opens each courier's
Pénzügy view, waits for the finance cards, and writes CSV plus JSON output.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from scripts.selenium_pwa_settlement_totals import HUF_RE, clean, create_driver, parse_huf
except ModuleNotFoundError:
    from selenium_pwa_settlement_totals import HUF_RE, clean, create_driver, parse_huf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://localhost:8501"
HUNGARIAN_MONTHS = {
    1: "január",
    2: "február",
    3: "március",
    4: "április",
    5: "május",
    6: "június",
    7: "július",
    8: "augusztus",
    9: "szeptember",
    10: "október",
    11: "november",
    12: "december",
}


def month_parts(month: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", clean(month))
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise ValueError("A hónap formátuma YYYY-MM legyen, például 2026-09.")
    return int(match.group(1)), int(match.group(2))


def click_text(driver, text: str, timeout: int, *, exact: bool = True) -> None:
    xpath = f'//button[normalize-space(.)="{text}"]' if exact else f'//button[contains(normalize-space(.), "{text}")]'
    button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    driver.execute_script("arguments[0].click();", button)


def set_streamlit_input(driver, element, value: str) -> None:
    """Set a React-controlled Streamlit input and fire the events it expects."""
    driver.execute_script(
        """
        const input = arguments[0];
        const value = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype,
            'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        element,
        value,
    )
    # Keep a keyboard fallback for Streamlit/React versions that do not accept
    # the native setter immediately.
    if element.get_attribute("value") != value:
        element.clear()
        element.send_keys(value)


def visible_login_error(driver) -> str:
    selectors = (
        "[data-testid='stException']",
        "[role='alert']",
        "[data-testid='stAlert']",
    )
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if element.is_displayed() and clean(element.text):
                return clean(element.text)
    body = clean(driver.find_element(By.TAG_NAME, "body").text)
    for marker in ("Hibás felhasználónév vagy jelszó", "Hibás felhasználónév", "Hibás jelszó"):
        if marker.casefold() in body.casefold():
            return marker
    return ""


def login(driver, wait: WebDriverWait, username: str, password: str) -> None:
    user_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[aria-label='Felhasználónév']")))
    password_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[aria-label='Jelszó']")))
    set_streamlit_input(driver, user_input, username)
    set_streamlit_input(driver, password_input, password)
    click_text(driver, "Belépés", wait._timeout)

    deadline = time.monotonic() + wait._timeout
    while time.monotonic() < deadline:
        error = visible_login_error(driver)
        if error:
            raise RuntimeError(f"A devtest belépés elutasítva: {error}")
        body = clean(driver.find_element(By.TAG_NAME, "body").text)
        if "Felhasználó:" in body and "Belépés" not in body:
            print("DEVTEST_SELENIUM_STEP=belépés sikeres", flush=True)
            return
        time.sleep(0.25)

    error = visible_login_error(driver)
    if error:
        raise RuntimeError(f"A devtest belépés elutasítva: {error}")
    raise RuntimeError(
        "A devtest belépés nem fejeződött be. Ellenőrizd, hogy a megadott admin jelszó "
        "a https://devtest.streamlit.app oldalon is működik-e."
    )


def selectbox_by_label(driver, label: str, option_match, timeout: int) -> None:
    def find_combo(current_driver):
        for widget in current_driver.find_elements(By.CSS_SELECTOR, "[data-testid='stSelectbox']"):
            if label not in clean(widget.text):
                continue
            combos = widget.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            if combos:
                combo = combos[0]
                current_value = clean(combo.get_attribute("aria-label")) or clean(combo.text)
                if option_match(current_value):
                    return (combo, True)
                return (combo, False)
        return False

    combo, already_selected = WebDriverWait(driver, timeout).until(find_combo)
    if already_selected:
        return
    combo.click()
    option = WebDriverWait(driver, timeout).until(
        lambda current_driver: next(
            (
                item for item in current_driver.find_elements(By.CSS_SELECTOR, "[role='option']")
                if option_match(clean(item.text))
            ),
            False,
        )
    )
    option.click()


def select_month(driver, month: str, timeout: int) -> None:
    year, month_number = month_parts(month)
    month_name = HUNGARIAN_MONTHS[month_number]

    def matches(option_text: str) -> bool:
        normalized = option_text.casefold().replace(" ", "")
        return str(year) in normalized and month_name.casefold() in normalized

    selectbox_by_label(driver, "Elszámolási hónap", matches, timeout)
    print(f"DEVTEST_SELENIUM_STEP=hónap kiválasztva: {month}", flush=True)


def open_settlement_page(driver, wait: WebDriverWait, month: str) -> None:
    # The default page is Els zamolas, but select it explicitly when the app
    # opens on another Streamlit radio option.
    radios = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stSidebar'] label")
    for radio in radios:
        if clean(radio.text).casefold() in {"elszámolás", "elszamolas"}:
            checked = radio.find_elements(By.CSS_SELECTOR, "input[type='radio']:checked")
            if not checked:
                radio.click()
            break
    print("DEVTEST_SELENIUM_STEP=elszámolás oldal aktív", flush=True)
    select_month(driver, month, wait._timeout)
    print("DEVTEST_SELENIUM_STEP=futárlista várakozás", flush=True)
    wait_for_list(driver, wait._timeout)
    print("DEVTEST_SELENIUM_STEP=elszámolási lista betöltve", flush=True)


def row_elements(driver):
    return driver.find_elements(By.CSS_SELECTOR, "div[class*='st-key-courier_row_']")


def wait_for_list(driver, timeout: int):
    def loaded(current_driver):
        rows = row_elements(current_driver)
        if rows:
            return rows
        body = clean(current_driver.find_element(By.TAG_NAME, "body").text)
        if "Nincs találat" in body or "Nincs feldolgozható futár" in body:
            return [None]
        return False

    try:
        result = WebDriverWait(driver, timeout).until(loaded)
    except TimeoutException as exc:
        body = clean(driver.find_element(By.TAG_NAME, "body").text)
        raise RuntimeError(
            "A devtest elszámolási futárlista nem jelent meg "
            f"{timeout} másodpercen belül. Az oldal jelenlegi állapota: {body[:300]}"
        ) from exc
    return [] if result == [None] else result


def list_row_record(row) -> dict[str, Any]:
    text = clean(row.text)
    buttons = [button for button in row.find_elements(By.TAG_NAME, "button") if clean(button.text)]
    identity = clean(buttons[0].text) if buttons else ""
    if "·" in identity:
        name, courier_id = [part.strip() for part in identity.rsplit("·", 1)]
    else:
        name, courier_id = identity or "Futár", ""
    amounts = HUF_RE.findall(text.replace("\u00a0", " "))
    contractor_display = f"{amounts[-2].strip()} Ft" if len(amounts) >= 2 else ""
    total_display = f"{amounts[-1].strip()} Ft" if amounts else "0 Ft"
    status_badges = [clean(item.text) for item in row.find_elements(By.CSS_SELECTOR, ".status-badge") if clean(item.text)]
    flags = [clean(item.text) for item in row.find_elements(By.CSS_SELECTOR, ".courier-flag") if clean(item.text)]
    title = clean(buttons[0].get_attribute("title")) if buttons else ""
    warehouse = title.split(":", 1)[1].strip() if ":" in title else ""
    return {
        "courier_id": courier_id,
        "courier_name": name,
        "warehouse": warehouse,
        "status": status_badges[0] if status_badges else "",
        "status_detail": " | ".join(status_badges[1:]),
        "flags": flags,
        "highlighted": any("kiemelt figyel" in flag.casefold() for flag in flags),
        "contractor_total_huf": parse_huf(contractor_display),
        "contractor_total": contractor_display,
        "total_payable_huf": parse_huf(total_display),
        "displayed_total": total_display,
    }


def read_list_rows(driver, timeout: int) -> list[dict[str, Any]]:
    rows = wait_for_list(driver, timeout)
    return [list_row_record(row) for row in rows if row is not None]


def finance_card_record(card) -> dict[str, Any]:
    label_nodes = card.find_elements(By.CSS_SELECTOR, ".finance-kpi-label")
    value_nodes = card.find_elements(By.CSS_SELECTOR, ".finance-kpi-value")
    label = clean(label_nodes[0].text) if label_nodes else ""
    displayed = clean(value_nodes[0].text) if value_nodes else ""
    amount = parse_huf(displayed) if "Ft" in displayed else None
    count = int(re.sub(r"\D", "", displayed.replace("\u00a0", "")) or 0) if amount is None else None
    return {"label": label, "displayed_value": displayed, "value_huf": amount, "value_count": count}


def read_detail(driver, record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    cards = [finance_card_record(card) for card in driver.find_elements(By.CSS_SELECTOR, ".finance-kpi")]
    result["financial_cards"] = [card for card in cards if card["label"]]
    result["detail_loaded"] = bool(result["financial_cards"])
    result["detail_error"] = ""
    payable = next(
        (card for card in result["financial_cards"] if card["label"].casefold() in {"fizetendő", "kifizetendő"}),
        None,
    )
    result["detail_total_payable"] = payable["displayed_value"] if payable else ""
    result["detail_total_payable_huf"] = payable["value_huf"] if payable else None
    result["detail_order_count"] = next((card["value_count"] for card in result["financial_cards"] if card["label"].casefold() == "rendelés"), None)
    result["detail_route_count"] = next((card["value_count"] for card in result["financial_cards"] if card["label"].casefold() == "kör"), None)
    result["complaints_count"] = clean(driver.find_element(By.TAG_NAME, "body").text).count("Bejelentések")
    return result


def open_detail_and_return(driver, original: dict[str, Any], timeout: int) -> dict[str, Any]:
    courier_id = original["courier_id"]

    def find_row(current_driver):
        for row in row_elements(current_driver):
            candidate = list_row_record(row)
            if candidate["courier_id"] == courier_id:
                return row
        return False

    row = WebDriverWait(driver, timeout).until(find_row)
    buttons = [button for button in row.find_elements(By.TAG_NAME, "button") if clean(button.text)]
    if not buttons:
        raise RuntimeError(f"Nincs megnyitható futárgomb: {courier_id}")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buttons[0])
    driver.execute_script("arguments[0].click();", buttons[0])
    WebDriverWait(driver, timeout).until(
        lambda current_driver: "Futár részletei" in clean(current_driver.find_element(By.TAG_NAME, "body").text)
    )
    if not driver.find_elements(By.CSS_SELECTOR, ".finance-kpi-grid"):
        finance_labels = [
            label for label in driver.find_elements(By.TAG_NAME, "label")
            if clean(label.text) == "Pénzügy"
        ]
        if finance_labels:
            driver.execute_script("arguments[0].click();", finance_labels[0])
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".finance-kpi-grid")))
    record = read_detail(driver, original)
    try:
        click_text(driver, "Vissza a listához", timeout)
        wait_for_list(driver, timeout)
    except TimeoutException:
        driver.back()
        wait_for_list(driver, timeout)
    return record


def write_outputs(rows: list[dict[str, Any]], csv_path: Path, json_path: Path, month: str) -> None:
    fields = [
        "month", "courier_id", "courier_name", "warehouse", "status", "status_detail",
        "flags", "highlighted", "contractor_total_huf", "contractor_total",
        "total_payable_huf", "displayed_total", "detail_total_payable_huf",
        "detail_total_payable", "detail_order_count", "detail_route_count",
        "detail_loaded", "detail_error", "complaints_count", "financial_cards_json", "extracted_at",
    ]
    extracted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            output.update({
                "month": month,
                "flags": ", ".join(row.get("flags", [])),
                "financial_cards_json": json.dumps(row.get("financial_cards", []), ensure_ascii=False),
                "extracted_at": extracted_at,
            })
            writer.writerow(output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"month": month, "extracted_at": extracted_at, "couriers": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Selenium export a devtest.py Streamlit elszámolási oldaláról.")
    parser.add_argument("--month", default="2026-09", help="Elszámolási hónap YYYY-MM formátumban")
    parser.add_argument("--url", default=os.getenv("DEVTEST_URL", DEFAULT_URL), help="A devtest.py Streamlit URL-je")
    parser.add_argument("--username", default=os.getenv("DEVTEST_ROBOT_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("DEVTEST_ROBOT_PASSWORD", ""))
    parser.add_argument("--output", default="", help="CSV kimeneti fájl")
    parser.add_argument("--output-json", default="", help="JSON kimeneti fájl")
    parser.add_argument("--headed", action="store_true", help="Látható Chrome ablak használata")
    parser.add_argument("--chromedriver", default="", help="ChromeDriver elérési útja")
    parser.add_argument("--timeout", type=int, default=90, help="Várakozási idő másodpercben")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    month_parts(args.month)
    username = args.username.strip()
    password = args.password or getpass.getpass(
        f"Devtest jelszó ({username}, a beírás nem jelenik meg): "
    )
    if not password:
        raise SystemExit(
            "Devtest Selenium export hiba: nincs jelszó. Add meg a promptnál, "
            "vagy állítsd be a DEVTEST_ROBOT_PASSWORD környezeti változót."
        )
    csv_path = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"devtest-settlement-details-{args.month}.csv"
    json_path = Path(args.output_json) if args.output_json else csv_path.with_suffix(".json")
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path

    driver = None
    started = time.time()
    try:
        driver = create_driver(args.headed, args.chromedriver)
        driver.get(args.url)
        wait = WebDriverWait(driver, args.timeout)
        login(driver, wait, username, password)
        open_settlement_page(driver, wait, args.month)
        rows = read_list_rows(driver, args.timeout)
        if not rows:
            raise RuntimeError(f"A devtest.py oldalon nem található futár a(z) {args.month} hónaphoz.")
        print(f"DEVTEST_SELENIUM_STEP=futárok végigkattintása: {len(rows)} db", flush=True)
        exported: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            try:
                record = open_detail_and_return(driver, row, args.timeout)
            except (TimeoutException, StaleElementReferenceException, WebDriverException) as exc:
                record = dict(row)
                record.update({
                    "financial_cards": [],
                    "detail_loaded": False,
                    "detail_error": f"Részletek betöltési hiba: {exc.__class__.__name__}",
                    "detail_total_payable": "",
                    "detail_total_payable_huf": None,
                    "detail_order_count": None,
                    "detail_route_count": None,
                    "complaints_count": 0,
                })
                print(f"DEVTEST_SELENIUM_WARN={index}/{len(rows)} {row['courier_name']} részletei nem töltődtek be", flush=True)
            exported.append(record)
            print(
                f"DEVTEST_SELENIUM_COURIER={index}/{len(rows)} id={row['courier_id']} "
                f"name={row['courier_name']} total={record.get('detail_total_payable') or row['displayed_total']}",
                flush=True,
            )
        write_outputs(exported, csv_path, json_path, args.month)
        print(f"DEVTEST_SELENIUM_SETTLEMENT month={args.month} couriers={len(exported)} details_loaded={sum(bool(row.get('detail_loaded')) for row in exported)}", flush=True)
        print(f"DEVTEST_SELENIUM_SETTLEMENT_OUTPUT={csv_path.resolve()}")
        print(f"DEVTEST_SELENIUM_SETTLEMENT_JSON={json_path.resolve()}")
        print(f"DEVTEST_SELENIUM_SETTLEMENT_SECONDS={time.time() - started:.1f}")
    except (WebDriverException, RuntimeError, ValueError) as exc:
        debug_path = ""
        if driver is not None:
            debug_dir = PROJECT_ROOT / "results"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "devtest-login-failure.png"
            try:
                driver.save_screenshot(str(debug_file))
                debug_path = str(debug_file.resolve())
            except WebDriverException:
                pass
        detail = f" Devtoolscreenshot: {debug_path}" if debug_path else ""
        current_url = ""
        if driver is not None:
            try:
                current_url = f" URL: {driver.current_url}"
            except WebDriverException:
                pass
        raise SystemExit(
            f"Devtest Selenium export hiba: {type(exc).__name__}: {exc!r}.{current_url}{detail}"
        ) from exc
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    main()
