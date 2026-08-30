import os
from pathlib import Path

from selenium.webdriver import ChromeOptions


def _remove_path_chromedrivers():
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


def create_github_chrome_options():
    _remove_path_chromedrivers()
    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    return options
