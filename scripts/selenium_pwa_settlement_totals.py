"""Export visible PWA settlement totals through a real Selenium browser session.

The script intentionally uses the rendered PWA UI only. It logs in, opens the
admin settlement dashboard, selects the requested month, reads every visible
settlement row, and writes the values to CSV.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
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
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://giriton-courier-pwa.onrender.com"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "pwa-settlement-totals-{month}.csv"
HUF_RE = re.compile(r"([-+]?\s*\d[\d\s\u00a0\u202f.,]*)\s*Ft", re.IGNORECASE)

# The admin preview list is the required processing order. The PWA dropdown
# can omit couriers whose current settlement state is empty, so it cannot be
# the only source of the export population.
EXPECTED_PWA_COURIERS: tuple[tuple[str, str], ...] = (
    ("7688", "Kancsár Zoltán"), ("8185", "Komjáti 8185 Ákos"),
    ("2875", "Rácz Csaba"), ("6959", "Bárándi Bendegúz"),
    ("6909", "Bajorhegyi Ádám"), ("6596", "Nagy Kristóf"),
    ("6825", "Szolnoki Tibor"), ("7147", "Horváth István"),
    ("7486", "Papp 7486 Nikolett"), ("6956", "Árva Tamás"),
    ("8530", "György 8530 Roland"), ("7538", "Cserna Levente Zoltán"),
    ("7842", "Fabó Marcell"), ("7817", "Varecza Roland"),
    ("6206", "Hervai Olivér"), ("7725", "Nagy 7725 István"),
    ("8332", "Hegedüs 8332 Dávid"), ("6686", "Magyar Csilla"),
    ("7245", "Kiss 7245 Csaba"), ("7226", "Bubán Szimonetta"),
    ("7665", "Koncsik Zoltán"), ("7632", "Tinger József"),
    ("5836", "Pardi Ottó"), ("7767", "Kanyó Krisztián"),
    ("6730", "Jamal Nasir"), ("7829", "Hohmann András Ármin"),
    ("8001", "Lulaj 8001 Brendon"), ("7979", "Jeney 7979 Tibor"),
    ("7056", "Baranyi Szabolcs"), ("8264", "Rusvai 8264 Marcell"),
    ("5774", "Prantner Péter Ákos"), ("8223", "Takács 8223 Attila"),
    ("8267", "Laukó 8267 Buda"), ("7296", "Petrik Róbert"),
    ("7753", "Tuza Ádám"), ("6856", "Király Dániel Dávid"),
    ("8226", "Baráth 8226 Dominik"), ("7244", "Nagy 7244 Attila"),
    ("7724", "Molnár Ákos"), ("6855", "Vándor Balázs"),
    ("6544", "Kiss Koppány Zalán"), ("8054", "Szombati 8054 Márk"),
    ("7267", "Bodonyi Gellért"), ("8980", "Markgráf 8980 Zsolt"),
    ("7018", "Mocsáry Attila"), ("8976", "Varró 8976 lili"),
    ("8994", "Szentjobi 8994 Tamás Hunor"), ("8266", "Szikszai 8266 Ferenc"),
    ("7624", "Révbíró Gábor"), ("8853", "Biró 8853 József"),
    ("9089", "Galyas 9089 Patrik"), ("9065", "Blaschek 9065 Ákos Kristóf"),
    ("8532", "Nagy 8532 Norbert"), ("6498", "Abonyi György Zoltán"),
    ("12345", "Bagoly Zoltán"), ("7185", "Baranyai István"),
    ("7747", "Bari Anett"), ("6528", "Bognár András"),
    ("8031", "Boskó 8031 György"), ("8760", "Báder 8760 Gergely"),
    ("9261", "Báder Miklós"), ("6572", "Deme Tamás"),
    ("8263", "Ember 8263 Gábor"), ("7814", "FARKAS ZSOLT JÁNOS E.V."),
    ("8292", "Fekete 8292 Bálint"), ("7687", "Fábián Alexandra"),
    ("7977", "Grózner 7977 Bálint"), ("7644", "Gurzó Balázs"),
    ("7239", "GÉMES ZOLTÁN E.V."), ("7927", "Gál 7927 Dominik"),
    ("7895", "Herkovics Andrea"), ("8938", "Hohn 8938 Hunor"),
    ("7815", "Homonnai Imre"), ("7440", "Jamal Raihan"),
    ("8764", "Kispál Zsolt"), ("8945", "Kollár 8945 Benedek"),
    ("8122", "Koncsik 8122 Tamás"), ("9382", "Kovács László"),
    ("7221", "Kristóf Attila"), ("7926", "Kurucz 7926 Márton"),
    ("7746", "Kövesdi Zsolt"), ("6476", "Meleg Dominika"),
    ("8032", "Máté 8032 Dániel"), ("7956", "Nagy 7956 Gergely"),
    ("8013", "Nagy 8013 Zoltán"), ("9067", "Nagy Ákos Zoltán"),
    ("5709", "Nádasi Martin Nicolas"), ("7743", "Német Bence"),
    ("8864", "Orbán 8864 Attila"), ("5838", "Pardi Ottó"),
    ("8960", "Pehl 8960 István József"), ("7295", "Persőtzi Bence"),
    ("7901", "Pálinkás Balázs"), ("8706", "Péchy 8706 Tamás"),
    ("7150", "Rezsnyák Bence László"), ("7072", "Rábl Norbert"),
    ("7938", "Sabján 7938 Iván"), ("7843", "Siklósi Máté"),
    ("8055", "Stumpf 8055 József"), ("7103", "Stumpf András István"),
    ("9016", "Szabó 9016 Gábor Áron"), ("8944", "Szamosvári 8944 Máté"),
    ("9136", "Szendi Balázs"), ("8056", "Szinovál 8056 Szilveszter"),
    ("8265", "Szász 8265 Márk"), ("7722", "Tóth 7722 Gábor"),
    ("6801", "Vajda Erik"), ("7939", "Varga 7939 Patrik Ádám"),
    ("6403", "Varga Románó"), ("8863", "Vidák 8863 Krisztofer"),
    ("6729", "Zorányi Tamás Bence"), ("1234", "admin"),
    ("6642", "Ádám Erik"),
)


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
        wait.until(EC.visibility_of_element_located((By.ID, "nav-settlement")))
        print("SELENIUM_STEP=belépés sikeres", flush=True)
    except TimeoutException as exc:
        error = clean(driver.find_element(By.ID, "login-error").text)
        if error:
            raise RuntimeError(f"Sikertelen belépés: {error}") from exc
        raise RuntimeError(
            "A belépés sikerült vagy az oldal nem töltődött be, de az Elszámolásom menü nem látható."
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


def open_settlement_page(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    print("SELENIUM_STEP=Elszámolásom oldal megnyitása", flush=True)
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
    nav = wait.until(EC.element_to_be_clickable((By.ID, "nav-settlement")))
    driver.execute_script("arguments[0].click();", nav)
    wait.until(EC.visibility_of_element_located((By.ID, "settlement-content")))
    wait.until(EC.visibility_of_element_located((By.ID, "workflow-month")))


def read_courier_catalog(driver: webdriver.Chrome, timeout: int) -> list[dict[str, str]]:
    # Read the live dropdown when available so warehouse data stays current,
    # but use the agreed full ID list as the authoritative population.
    options = driver.find_elements(By.CSS_SELECTOR, "#courier-master-list option")
    catalog = []
    for option in options:
        courier_id = clean(option.get_attribute("value"))
        label = clean(option.get_attribute("label"))
        if not courier_id:
            continue
        name = label.split(" · #", 1)[0].strip() if " · #" in label else label
        warehouse = ""
        if " · #" in label:
            identity_tail = label.split(" · #", 1)[1]
            if " · " in identity_tail:
                warehouse = identity_tail.split(" · ", 1)[1].strip()
        catalog.append({"courier_id": courier_id, "courier_name": name or courier_id, "warehouse": warehouse})
    unique: dict[str, dict[str, str]] = {}
    for item in catalog:
        unique[item["courier_id"]] = item
    ordered = []
    expected_ids = set()
    for courier_id, courier_name in EXPECTED_PWA_COURIERS:
        expected_ids.add(courier_id)
        live = unique.get(courier_id, {})
        ordered.append({
            "courier_id": courier_id,
            "courier_name": courier_name or live.get("courier_name") or courier_id,
            "warehouse": live.get("warehouse", ""),
        })
    # Keep any newly added PWA courier after the agreed list instead of
    # silently dropping it from the export.
    ordered.extend(item for item in unique.values() if item["courier_id"] not in expected_ids)
    print(
        f"SELENIUM_STEP=futárlista összeállítva: {len(ordered)} db "
        f"(megadott lista: {len(EXPECTED_PWA_COURIERS)} db)",
        flush=True,
    )
    return ordered


def select_workflow_month(driver: webdriver.Chrome, month: str, timeout: int) -> None:
    def month_select_ready(current_driver):
        select = current_driver.find_element(By.ID, "workflow-month")
        if not select.is_displayed():
            return False
        values = [clean(option.get_attribute("value")) for option in Select(select).options]
        return select if month in values else False

    select_element = WebDriverWait(driver, timeout).until(month_select_ready)
    Select(select_element).select_by_value(month)
    WebDriverWait(driver, timeout).until(
        lambda current_driver: clean(current_driver.find_element(By.ID, "workflow-month").get_attribute("value")) == month
    )


def wait_for_workflow_idle(driver: webdriver.Chrome, timeout: int, courier_id: str) -> None:
    """Wait for the automatic load started by changing the workflow month."""
    WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, "workflow-refresh"))
    )
    started = time.monotonic()
    last_report = started
    while time.monotonic() - started < timeout:
        current = driver.find_element(By.ID, "workflow-refresh")
        label = clean(current.text)
        disabled = not current.is_enabled() or current.get_attribute("disabled") is not None
        if not disabled and label == "Frissítés":
            return
        if time.monotonic() - last_report >= 10:
            elapsed = int(time.monotonic() - started)
            print(
                f"SELENIUM_WAIT={courier_id}: hónapváltás utáni betöltésre várunk "
                f"({elapsed}/{timeout} mp)",
                flush=True,
            )
            last_report = time.monotonic()
        time.sleep(0.5)
    raise TimeoutException(f"A PWA automatikus hónapbetöltése nem fejeződött be: {courier_id}")


def wait_for_workflow_data(driver: webdriver.Chrome, courier_id: str, timeout: int) -> None:
    panel = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, "settlement-panel"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", panel)
    print(f"SELENIUM_STEP={courier_id}: pénzügyi panelre görgetés", flush=True)
    started = time.monotonic()
    last_report = started

    def rendered(current_driver):
        nonlocal last_report
        now = time.monotonic()
        if now - last_report >= 10:
            elapsed = int(now - started)
            print(
                f"SELENIUM_WAIT={courier_id}: PWA adatok betöltésére várunk "
                f"({elapsed}/{timeout} mp)",
                flush=True,
            )
            last_report = now
        status = clean(current_driver.find_element(By.ID, "admin-preview-status").text)
        if courier_id not in status:
            return False
        panel = current_driver.find_element(By.ID, "settlement-panel")
        text = clean(panel.text)
        total_elements = [
            item for item in panel.find_elements(By.CSS_SELECTOR, ".financial-total-card strong")
            if clean(item.text)
        ]
        financial_cards = [
            item for item in panel.find_elements(By.CSS_SELECTOR, ".financial-card")
            if clean(item.text)
        ]
        if not text or not (total_elements or financial_cards):
            return False
        return panel

    WebDriverWait(driver, timeout).until(rendered)


def preview_courier(driver: webdriver.Chrome, courier: dict[str, str], month: str, timeout: int) -> dict[str, Any]:
    prefix = f"{courier['courier_id']} {courier['courier_name']}"
    input_element = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, "admin-preview-courier"))
    )
    last_error = None
    # IDs are authoritative: names can be duplicated or have changed spelling.
    # Keep the name as a fallback for older PWA builds that do not match IDs.
    for query in [courier["courier_id"], courier["courier_name"]]:
        if not query:
            continue
        input_element.clear()
        input_element.send_keys(query)
        open_button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.ID, "admin-preview-open")))
        driver.execute_script("arguments[0].click();", open_button)
        try:
            print(f"SELENIUM_STEP={prefix}: futár megnyitva, adatokra várakozás", flush=True)
            wait_for_workflow_data(driver, courier["courier_id"], timeout)
            break
        except TimeoutException as exc:
            last_error = exc
    else:
        raise last_error or RuntimeError(f"Nem nyitható meg a futár: {courier['courier_name']}")
    print(f"SELENIUM_STEP={prefix}: futár adatai betöltve", flush=True)
    select_workflow_month(driver, month, timeout)
    print(f"SELENIUM_STEP={prefix}: hónap kiválasztva: {month}", flush=True)
    wait_for_workflow_idle(driver, timeout, courier["courier_id"])
    print(f"SELENIUM_STEP={prefix}: automatikus hónapbetöltés kész", flush=True)
    wait_for_workflow_data(driver, courier["courier_id"], timeout)
    print(f"SELENIUM_STEP={prefix}: frissített adatok betöltve", flush=True)
    return extract_workflow_record(driver, courier)


def extract_workflow_record(driver: webdriver.Chrome, courier: dict[str, str]) -> dict[str, Any]:
    panel = driver.find_element(By.ID, "settlement-panel")
    total_elements = panel.find_elements(By.CSS_SELECTOR, ".financial-total-card strong")
    detail_total = clean(total_elements[0].text) if total_elements else ""
    cards = []
    for card in panel.find_elements(By.CSS_SELECTOR, ".financial-card"):
        labels = card.find_elements(By.CSS_SELECTOR, ".financial-card-title > span")
        values = card.find_elements(By.CSS_SELECTOR, ".financial-card-summary-side > strong")
        if not labels or not values:
            continue
        displayed = clean(values[0].text)
        cards.append({
            "label": clean(labels[0].text),
            "displayed_value": displayed,
            "value_huf": parse_huf(displayed) if "Ft" in displayed else None,
        })
    steps = clean(driver.find_element(By.ID, "workflow-steps").text)
    message = clean(driver.find_element(By.ID, "workflow-message").text)
    error_text = ""
    if "még nem aktívak" in clean(panel.text).casefold():
        error_text = clean(panel.text)
    return {
        "courier_id": courier["courier_id"],
        "courier_name": courier["courier_name"],
        "warehouse": courier["warehouse"],
        "status": message or (steps.splitlines()[0] if steps else ""),
        "status_detail": steps,
        "flags": [],
        "highlighted": False,
        "total_payable_huf": parse_huf(detail_total) if detail_total else 0,
        "displayed_total": detail_total or "0 Ft",
        "detail_total_payable_huf": parse_huf(detail_total) if detail_total else None,
        "detail_total_payable": detail_total,
        "detail_loaded": bool(detail_total or cards),
        "detail_available": bool(detail_total or cards),
        "detail_error": error_text,
        "complaints_count": len(panel.find_elements(By.CSS_SELECTOR, ".complaint-box")),
        "documents_count": len(panel.find_elements(By.CSS_SELECTOR, ".document-card")),
        "financial_cards": cards,
    }


def collect_settlement_from_workflow(
    driver: webdriver.Chrome,
    catalog: list[dict[str, str]],
    month: str,
    timeout: int,
) -> list[dict[str, Any]]:
    exported = []
    print(f"SELENIUM_STEP=futárok végigkattintása az Elszámolás oldalon: {len(catalog)} db", flush=True)
    for index, courier in enumerate(catalog, start=1):
        try:
            record = preview_courier(driver, courier, month, timeout)
        except (TimeoutException, StaleElementReferenceException, WebDriverException, ValueError) as exc:
            record = {
                **courier,
                "status": "",
                "status_detail": "",
                "flags": [],
                "highlighted": False,
                "total_payable_huf": 0,
                "displayed_total": "0 Ft",
                "detail_total_payable_huf": None,
                "detail_total_payable": "",
                "detail_loaded": False,
                "detail_available": False,
                "detail_error": f"Elszámolás betöltési hiba: {exc.__class__.__name__}",
                "complaints_count": 0,
                "documents_count": 0,
                "financial_cards": [],
            }
            print(f"SELENIUM_WARN={index}/{len(catalog)} {courier['courier_name']} elszámolása nem töltődött be", flush=True)
        exported.append(record)
        print(
            f"SELENIUM_COURIER={index}/{len(catalog)} id={courier['courier_id']} "
            f"name={courier['courier_name']} total={record['displayed_total']}",
            flush=True,
        )
    return exported


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
    status_detail = clean(smalls[1].text) if len(smalls) > 1 else ""
    flags = [clean(flag.text) for flag in row.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-flag") if clean(flag.text)]
    classes = set(clean(row.get_attribute("class")).split())
    warehouse = identity.split("·", 1)[1].strip() if "·" in identity else ""
    return {
        "courier_id": courier_id,
        "courier_name": name,
        "warehouse": warehouse,
        "status": status,
        "status_detail": status_detail,
        "flags": flags,
        "highlighted": "highlighted" in classes,
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


def parse_detail_card(card) -> dict[str, Any]:
    summary = card.find_elements(By.TAG_NAME, "summary")
    if not summary:
        return {}
    labels = summary[0].find_elements(By.TAG_NAME, "span")
    amounts = summary[0].find_elements(By.TAG_NAME, "strong")
    label = clean(labels[0].text) if labels else ""
    displayed = clean(amounts[0].text) if amounts else ""
    return {
        "label": label,
        "displayed_value": displayed,
        "value_huf": parse_huf(displayed) if "Ft" in displayed else None,
    }


def detail_record(driver: webdriver.Chrome, expanded, record: dict[str, Any]) -> dict[str, Any]:
    """Read the important, currently rendered fields from one opened courier."""
    result = dict(record)
    total_elements = expanded.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-mini-total strong")
    detail_displayed = clean(total_elements[0].text) if total_elements else ""
    result["detail_total_payable"] = detail_displayed
    result["detail_total_payable_huf"] = parse_huf(detail_displayed) if detail_displayed else None
    result["financial_cards"] = [
        card for card in (parse_detail_card(item) for item in expanded.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-mini-card"))
        if card
    ]
    result["complaints_count"] = len(expanded.find_elements(By.CSS_SELECTOR, ".settlement-dashboard-complaint"))
    result["documents_count"] = len(expanded.find_elements(By.CSS_SELECTOR, "[data-document-id]"))
    result["detail_available"] = bool(total_elements)
    result["detail_error"] = ""
    error_elements = expanded.find_elements(By.CSS_SELECTOR, ".notice.error")
    if error_elements:
        result["detail_error"] = clean(error_elements[0].text)
    return result


def wait_for_detail(driver: webdriver.Chrome, courier_id: str, timeout: int):
    def find_ready(current_driver):
        selectors = f".settlement-dashboard-expanded[data-expanded-courier-id='{courier_id}']"
        expanded = current_driver.find_elements(By.CSS_SELECTOR, selectors)
        if not expanded:
            return False
        candidate = expanded[0]
        if "Futár részletek betöltése" in clean(candidate.text):
            return False
        return candidate

    return WebDriverWait(driver, timeout).until(find_ready)


def click_through_rows(
    driver: webdriver.Chrome,
    timeout: int,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Open every rendered courier row and wait for the full detail response."""
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
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
            driver.execute_script("arguments[0].click();", row)
            expanded = wait_for_detail(driver, courier_id, min(timeout, 90))
            record = detail_record(driver, expanded, record)
            record["detail_loaded"] = True
        except (TimeoutException, StaleElementReferenceException) as exc:
            record["detail_loaded"] = False
            record["detail_available"] = False
            record["detail_error"] = f"Részletek betöltési időtúllépése: {exc.__class__.__name__}"
            print(
                f"SELENIUM_WARN={index}/{len(rows)} {record['courier_name']} részletei nem töltődtek be",
                flush=True,
            )
        try:
            record.setdefault("detail_loaded", False)
            record.setdefault("financial_cards", [])
            record.setdefault("complaints_count", 0)
            record.setdefault("documents_count", 0)
            record.setdefault("detail_total_payable", "")
            record.setdefault("detail_total_payable_huf", None)
            record.setdefault("detail_available", False)
            record.setdefault("detail_error", "")
        except Exception:
            pass
        exported.append(record)
        print(
            f"SELENIUM_COURIER={index}/{len(rows)} id={record['courier_id']} "
            f"name={record['courier_name']} total={record['detail_total_payable'] or record['displayed_total']}",
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
        "status_detail",
        "flags",
        "highlighted",
        "total_payable_huf",
        "displayed_total",
        "detail_total_payable_huf",
        "detail_total_payable",
        "detail_loaded",
        "detail_available",
        "detail_error",
        "complaints_count",
        "documents_count",
        "financial_cards_json",
        "extracted_at",
    ]
    extracted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            exported = {field: row.get(field, "") for field in fields}
            exported.update({
                "month": month,
                "flags": ", ".join(row.get("flags", [])),
                "financial_cards_json": json.dumps(row.get("financial_cards", []), ensure_ascii=False),
                "extracted_at": extracted_at,
            })
            writer.writerow(exported)


def write_json(rows: list[dict[str, Any]], output_path: Path, month: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "month": month,
        "extracted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "couriers": rows,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_debug_artifacts(driver: webdriver.Chrome, output_path: Path) -> tuple[Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_path.with_name(output_path.stem + "-debug.png")
    html_path = output_path.with_name(output_path.stem + "-debug.html")
    driver.save_screenshot(str(screenshot_path))
    html_path.write_text(driver.page_source, encoding="utf-8")
    return screenshot_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seleniummel belép a PWA-ba, megnyitja az Elszámolásom oldalt, "
            "admin előnézetben végigmegy minden futáron, és a fontos adatokat CSV/JSON-ba menti."
        )
    )
    parser.add_argument("--month", default="2026-09", help="Elszámolási hónap, például 2026-09")
    parser.add_argument("--url", default=os.getenv("PWA_URL", DEFAULT_URL), help="PWA kezdő URL")
    parser.add_argument("--username", default=os.getenv("PWA_ROBOT_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("PWA_ROBOT_PASSWORD", ""))
    parser.add_argument("--output", default="", help="CSV kimenet; alapértelmezés: results/pwa-settlement-details-YYYY-MM.csv")
    parser.add_argument("--output-json", default="", help="JSON kimenet; alapértelmezés: a CSV neve .json kiterjesztéssel")
    parser.add_argument("--headed", action="store_true", help="Látható Chrome ablak használata")
    parser.add_argument("--chromedriver", default="", help="ChromeDriver elérési útja")
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Várakozási idő másodpercben; a PWA lassú frissítéséhez alapból 180",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    username = args.username or input("PWA felhasználónév: ").strip()
    password = args.password or getpass.getpass("PWA jelszó: ")
    output_path = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"pwa-settlement-details-{args.month}.csv"
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    json_path = Path(args.output_json) if args.output_json else output_path.with_suffix(".json")
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path

    driver = None
    started = time.time()
    try:
        driver = create_driver(args.headed, args.chromedriver)
        driver.get(args.url)
        wait = WebDriverWait(driver, args.timeout)
        login(driver, wait, username, password)
        open_settlement_page(driver, wait)
        catalog = read_courier_catalog(driver, args.timeout)
        if not catalog:
            screenshot_path, html_path = save_debug_artifacts(driver, output_path)
            panel_text = clean(driver.find_element(By.TAG_NAME, "body").text)
            raise RuntimeError(
                "A PWA admin előnézetben nem található futárlista. "
                f"Oldalszöveg: {panel_text[:240]!r}. "
                f"Diagnosztika: {screenshot_path}, {html_path}"
            )
        rows = collect_settlement_from_workflow(driver, catalog, args.month, args.timeout)
        write_csv(rows, output_path, args.month)
        write_json(rows, json_path, args.month)
        total = sum(int(row["total_payable_huf"]) for row in rows)
        loaded = sum(1 for row in rows if row.get("detail_loaded"))
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS month={args.month} couriers={len(rows)} details_loaded={loaded} total={total:,} Ft".replace(",", " "))
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS_OUTPUT={output_path.resolve()}")
        print(f"PWA_SELENIUM_SETTLEMENT_DETAILS_JSON={json_path.resolve()}")
        print(f"PWA_SELENIUM_SETTLEMENT_TOTALS_SECONDS={time.time() - started:.1f}")
    except (WebDriverException, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Selenium elszámolás export hiba: {exc}") from exc
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    main()
