"""Export visible PWA settlement totals through a real Selenium browser session.

The script intentionally uses the rendered PWA UI only. It logs in, opens the
admin settlement dashboard, selects the requested month, reads every visible
settlement row, and writes the values to CSV.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import platform
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://giriton-courier-pwa.onrender.com"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "pwa-settlement-totals-{month}.csv"
HUF_RE = re.compile(r"([-+]?\s*\d[\d\s\u00a0\u202f.,]*)\s*Ft", re.IGNORECASE)


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_huf(value: str) -> int:
    """Parse the displayed Hungarian forint value without relying on locale."""
    text = clean(value).replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("Ft", "").replace("ft", "")
    sign = -1 if "-" in text else 1
    digits = re.sub(r"\D", "", text)
    return sign * int(digits or "0")


def displayed_amount(text: str) -> tuple[str, int]:
    matches = HUF_RE.findall(text.replace("\u00a0", " "))
    if not matches:
        raise ValueError(f"Nem található Ft összeg a futár sorában: {text!r}")
    raw = matches[-1]
    return f"{raw.strip()} Ft", parse_huf(raw)


def chrome_options(headed: bool) -> Options:
    options = Options()
    chrome_binary = clean(
        os.getenv("CHROME_BIN")
        or os.getenv("GOOGLE_CHROME_BIN")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome_binary:
        options.binary_location = chrome_binary
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options


def remove_stale_chromedriver_directories() -> None:
    """Keep old chromedriver folders out of Selenium Manager's PATH lookup."""
    if platform.system().lower() != "windows":
        return
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    kept_parts = []
    for part in path_parts:
        if not part:
            continue
        if (Path(part) / "chromedriver.exe").exists() or (Path(part) / "chromedriver").exists():
            continue
        kept_parts.append(part)
    os.environ["PATH"] = os.pathsep.join(kept_parts)


def create_driver(headed: bool, chromedriver: str = "") -> webdriver.Chrome:
    options = chrome_options(headed)
    driver_path = clean(chromedriver or os.getenv("CHROMEDRIVER") or os.getenv("CHROMEDRIVER_PATH"))
    if driver_path:
        return webdriver.Chrome(service=Service(driver_path), options=options)
    remove_stale_chromedriver_directories()
    return webdriver.Chrome(options=options)


def wait_for(driver: webdriver.Chrome, condition, timeout: int):
    return WebDriverWait(driver, timeout).until(condition)


def login(driver: webdriver.Chrome, wait: WebDriverWait, username: str, password: str) -> None:
    print("SELENIUM_STEP=belépési oldal megnyitva", flush=True)
    wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()

    try:
        wait.until(EC.visibility_of_element_located((By.ID, "nav-settlement-dashboard")))
        print("SELENIUM_STEP=belépés sikeres", flush=True)
    except TimeoutException as exc:
        error = clean(driver.find_element(By.ID, "login-error").text)
        if error:
            raise RuntimeError(f"Sikertelen belépés: {error}") from exc
        raise RuntimeError(
            "A belépés sikerült vagy az oldal nem töltődött be, de az admin elszámolási menü nem látható."
        ) from exc


def set_month(driver: webdriver.Chrome, month: str) -> None:
    month_input = driver.find_element(By.ID, "settlement-dashboard-month")
    driver.execute_script(
        """
        const input = arguments[0];
        const value = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        month_input,
        month,
    )


def open_dashboard(driver: webdriver.Chrome, wait: WebDriverWait, month: str) -> None:
    print("SELENIUM_STEP=elszámolási dashboard megnyitása", flush=True)
    # An active admin courier preview changes the rest of the UI to a single
    # courier's read-only view. Clear it before collecting the full list.
    preview_status = driver.find_elements(By.ID, "admin-preview-status")
    clear_preview = driver.find_elements(By.ID, "admin-preview-clear")
    if (
        preview_status
        and "Előnézet aktív" in clean(preview_status[0].text)
        and clear_preview
        and clear_preview[0].is_displayed()
    ):
        driver.execute_script("arguments[0].click();", clear_preview[0])
        wait.until(lambda current_driver: "Előnézet aktív" not in clean(
            current_driver.find_element(By.ID, "admin-preview-status").text
        ))
        print("SELENIUM_STEP=admin előnézet törölve", flush=True)
    nav = wait.until(EC.element_to_be_clickable((By.ID, "nav-settlement-dashboard")))
    driver.execute_script("arguments[0].click();", nav)
    wait.until(EC.visibility_of_element_located((By.ID, "settlement-dashboard-content")))
    set_month(driver, month)
    refresh = wait.until(EC.element_to_be_clickable((By.ID, "settlement-dashboard-refresh")))
    driver.execute_script("arguments[0].click();", refresh)
    print(f"SELENIUM_STEP=hónap betöltése: {month}", flush=True)


def row_record(row) -> dict[str, Any]:
    row_text = clean(row.text)
    amount_display, amount_huf = displayed_amount(row_text)
    strongs = row.find_elements(By.TAG_NAME, "strong")
    name = clean(strongs[0].text) if strongs else "Futár"
    courier_id = clean(row.get_attribute("data-courier-id"))
    smalls = row.find_elements(By.TAG_NAME, "small")
    identity = clean(smalls[0].text) if smalls else ""
    status_elements = row.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-status")
    status = clean(status_elements[0].text) if status_elements else ""
    warehouse = identity.split("·", 1)[1].strip() if "·" in identity else ""
    return {
        "courier_id": courier_id,
        "courier_name": name,
        "warehouse": warehouse,
        "status": status,
        "total_payable_huf": amount_huf,
        "displayed_total": amount_display,
    }


def read_rows(driver: webdriver.Chrome, wait: WebDriverWait, timeout: int) -> list[dict[str, Any]]:
    panel = wait.until(EC.visibility_of_element_located((By.ID, "settlement-dashboard-panel")))

    def rows_loaded(_driver):
        rows = panel.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-row")
        if rows:
            return rows
        text = clean(panel.text)
        if "Nincs futár" in text:
            return [None]
        if "betöltése" in text.lower():
            return False
        return False

    loaded = WebDriverWait(driver, timeout).until(rows_loaded)
    rows = [] if loaded == [None] else loaded
    return [row_record(row) for row in rows]


def click_through_rows(
    driver: webdriver.Chrome,
    timeout: int,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Click every rendered courier row and read its visible amount again."""
    exported: list[dict[str, Any]] = []
    print(f"SELENIUM_STEP=futárok végigkattintása: {len(rows)} db", flush=True)
    for index, original in enumerate(rows, start=1):
        courier_id = original["courier_id"]

        def find_row(current_driver):
            for candidate in current_driver.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-row"):
                if clean(candidate.get_attribute("data-courier-id")) == courier_id:
                    return candidate
            return False

        row = WebDriverWait(driver, timeout).until(find_row)
        record = row_record(row)
        driver.execute_script("arguments[0].click();", row)

        def expanded_row(current_driver):
            candidate = find_row(current_driver)
            if candidate and "active" in clean(candidate.get_attribute("class")).split():
                return candidate
            return False

        try:
            active_row = WebDriverWait(driver, min(timeout, 20)).until(expanded_row)
            record = row_record(active_row)
        except TimeoutException:
            print(
                f"SELENIUM_WARN={index}/{len(rows)} {record['courier_name']} sor nem nyílt ki, a listaösszeg kerül mentésre",
                flush=True,
            )
        exported.append(record)
        print(
            f"SELENIUM_COURIER={index}/{len(rows)} id={record['courier_id']} "
            f"name={record['courier_name']} total={record['displayed_total']}",
            flush=True,
        )
    return exported


def write_csv(rows: list[dict[str, Any]], output_path: Path, month: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "month",
        "courier_id",
        "courier_name",
        "warehouse",
        "status",
        "total_payable_huf",
        "displayed_total",
        "extracted_at",
    ]
    extracted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "month": month, "extracted_at": extracted_at})


def save_debug_artifacts(driver: webdriver.Chrome, output_path: Path) -> tuple[Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_path.with_name(output_path.stem + "-debug.png")
    html_path = output_path.with_name(output_path.stem + "-debug.html")
    driver.save_screenshot(str(screenshot_path))
    html_path.write_text(driver.page_source, encoding="utf-8")
    return screenshot_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seleniummel belép a PWA elszámolási dashboardba és CSV-be menti a futáronkénti végösszegeket."
    )
    parser.add_argument("--month", required=True, help="Elszámolási hónap, például 2026-09")
    parser.add_argument("--url", default=os.getenv("PWA_URL", DEFAULT_URL), help="PWA kezdő URL")
    parser.add_argument("--username", default=os.getenv("PWA_ROBOT_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("PWA_ROBOT_PASSWORD", ""))
    parser.add_argument("--output", default="", help="CSV kimenet; alapértelmezés: results/pwa-settlement-totals-YYYY-MM.csv")
    parser.add_argument("--headed", action="store_true", help="Látható Chrome ablak használata")
    parser.add_argument("--chromedriver", default="", help="ChromeDriver elérési útja")
    parser.add_argument("--timeout", type=int, default=60, help="Várakozási idő másodpercben")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    username = args.username or input("PWA felhasználónév: ").strip()
    password = args.password or getpass.getpass("PWA jelszó: ")
    output_path = Path(args.output) if args.output else Path(str(DEFAULT_OUTPUT).format(month=args.month))

    driver = None
    started = time.time()
    try:
        driver = create_driver(args.headed, args.chromedriver)
        driver.get(args.url)
        wait = WebDriverWait(driver, args.timeout)
        login(driver, wait, username, password)
        open_dashboard(driver, wait, args.month)
        rows = read_rows(driver, wait, args.timeout)
        if not rows:
            screenshot_path, html_path = save_debug_artifacts(driver, output_path)
            panel_text = clean(driver.find_element(By.ID, "settlement-dashboard-panel").text)
            raise RuntimeError(
                f"A dashboard nem adott vissza futársort a(z) {args.month} hónapra. "
                f"Oldalszöveg: {panel_text[:240]!r}. "
                f"Diagnosztika: {screenshot_path}, {html_path}"
            )
        rows = click_through_rows(driver, args.timeout, rows)
        write_csv(rows, output_path, args.month)
        total = sum(int(row["total_payable_huf"]) for row in rows)
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS month={args.month} couriers={len(rows)} total={total:,} Ft".replace(",", " "))
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS_OUTPUT={output_path.resolve()}")
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS_SECONDS={time.time() - started:.1f}")
    except (WebDriverException, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Selenium elszámolás export hiba: {exc}") from exc
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    main()
