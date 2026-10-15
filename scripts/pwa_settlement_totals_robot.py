"""Export all PWA settlement totals for one month.

The robot authenticates against the PWA API and reads the same admin list
that the settlement dashboard displays. It deliberately does not scrape
screen coordinates or rendered text, so the output remains stable when the
frontend layout changes.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests


BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_month(value: str | None) -> str:
    month = clean(value)
    if not month:
        return datetime.now(BUDAPEST_TZ).strftime("%Y-%m")
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("A hónap formátuma YYYY-MM legyen, például 2026-09.") from exc


def money(value: object) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def format_huf(value: object) -> str:
    return f"{money(value):,}".replace(",", " ") + " Ft"


def require_response(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    body = response.text[:1000].strip()
    raise RuntimeError(f"{label}: HTTP {response.status_code}: {body}")


def login(session: requests.Session, base_url: str, username: str, password: str) -> dict:
    response = session.post(
        f"{base_url}/api/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    require_response(response, "PWA bejelentkezés")
    payload = response.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict):
        raise RuntimeError("A PWA bejelentkezési válasza nem tartalmaz felhasználót.")
    if not bool(user.get("canViewSettlementDashboard")):
        raise PermissionError("A robot felhasználójának admin elszámolási jogosultság kell.")
    return user


def fetch_totals(session: requests.Session, base_url: str, month: str) -> list[dict[str, object]]:
    query = urlencode({"month": month})
    response = session.get(
        f"{base_url}/api/admin/settlement-totals?{query}",
        timeout=120,
    )
    if response.status_code == 404:
        # Backward compatibility while an older deployment is still running.
        response = session.get(
            f"{base_url}/api/admin/settlement-dashboard?{query}",
            timeout=120,
        )
    require_response(response, "Devtest végösszegek lekérése")
    payload = response.json()
    raw_rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        raise RuntimeError("A PWA válasza nem tartalmaz futárlistát.")

    rows: list[dict[str, object]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "month": month,
                "courier_id": clean(row.get("courierId")),
                "courier_name": clean(row.get("courierName")),
                "warehouse": clean(row.get("warehouse")),
                "total_payable_huf": money(row.get("totalPayableHuf")),
                "total_payable": format_huf(row.get("totalPayableHuf")),
                "status": clean((row.get("status") or {}).get("label"))
                if isinstance(row.get("status"), dict)
                else "",
                "updated_at": clean(row.get("updatedAt")),
            }
        )
    rows.sort(key=lambda row: (clean(row["courier_name"]).casefold(), clean(row["courier_id"])))
    return rows


def write_csv(rows: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "month",
        "courier_id",
        "courier_name",
        "warehouse",
        "total_payable_huf",
        "total_payable",
        "status",
        "updated_at",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    today = datetime.now(BUDAPEST_TZ).date()
    parser = argparse.ArgumentParser(
        description="PWA admin elszámolási végösszegek exportálása minden futárhoz."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("PWA_BASE_URL", "https://giriton-courier-pwa.onrender.com"),
        help="PWA címe. Alapértelmezett: PWA_BASE_URL vagy a produkciós PWA.",
    )
    parser.add_argument(
        "--month",
        default=today.strftime("%Y-%m"),
        help="Elszámolási hónap YYYY-MM formátumban. Alapértelmezett: aktuális hónap.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("PWA_ROBOT_USERNAME", ""),
        help="Admin PWA-felhasználó vagy PWA_ROBOT_USERNAME.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="CSV célfájl. Alapértelmezett: results/pwa-settlement-totals-YYYY-MM.csv",
    )
    args = parser.parse_args()

    base_url = clean(args.base_url).rstrip("/")
    month = parse_month(args.month)
    username = clean(args.username) or input("PWA admin felhasználónév: ").strip()
    password = os.getenv("PWA_ROBOT_PASSWORD") or getpass.getpass("PWA admin jelszó: ")
    if not username or not password:
        raise ValueError("A PWA admin felhasználónév és jelszó kötelező.")

    output = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"pwa-settlement-totals-{month}.csv"
    if not output.is_absolute():
        output = PROJECT_ROOT / output

    with requests.Session() as session:
        user = login(session, base_url, username, password)
        rows = fetch_totals(session, base_url, month)

    if not rows:
        raise RuntimeError(
            f"A bejelentkezés sikerült, de a {month} hónapra 0 futár érkezett "
            f"a(z) {base_url} címről. Ellenőrizd a PWA címet és azt, hogy a hónap "
            "adatai a produkciós adatbázisban vannak-e."
        )

    write_csv(rows, output)
    total = sum(money(row["total_payable_huf"]) for row in rows)
    print(f"PWA_SETTLEMENT_TOTALS month={month} couriers={len(rows)} total={format_huf(total)}")
    print(f"PWA_SETTLEMENT_TOTALS_OUTPUT={output}")
    print(f"PWA_SETTLEMENT_TOTALS_USER={clean(user.get('username'))}")
    for row in rows:
        print(f"{row['courier_id']}\t{row['courier_name']}\t{row['total_payable']}")


if __name__ == "__main__":
    main()
