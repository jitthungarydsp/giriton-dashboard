from __future__ import annotations

import json
import tomllib
import unicodedata
from datetime import datetime, date, time, timedelta
from pathlib import Path

import requests

ROOT = Path(r"C:\Giriton\giriton-dashboard")
SECRETS = ROOT / ".streamlit" / "secrets.toml"
OUT = ROOT / "tmp" / "giriton-september-work-time.json"


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(text.split())


def fetch(url: str, key: str, table: str, select: str, params: dict[str, str]) -> list[dict]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows: list[dict] = []
    offset = 0
    while True:
        query = {**params, "select": select, "limit": "1000", "offset": str(offset)}
        response = requests.get(f"{url}/rest/v1/{table}", headers=headers, params=query, timeout=60)
        response.raise_for_status()
        page = response.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    return rows


def parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_time(value: object) -> time | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return time.fromisoformat(text[:8])
    except ValueError:
        return None


def main() -> None:
    with SECRETS.open("rb") as handle:
        secrets = tomllib.load(handle)
    url = str(secrets["SUPABASE_URL"]).rstrip("/")
    key = str(secrets["SUPABASE_SERVICE_ROLE_KEY"])
    start, end = "2026-09-01", "2026-09-30"
    attendance = fetch(
        url, key, "giriton_attendance_raw",
        "work_date,courier_name,shift_text,activity_status,checkin_start,checkin_end,raw_details",
        {"work_date": f"gte.{start}", "and": f"(work_date.lte.{end})", "order": "work_date.asc,courier_name.asc"},
    )
    route_rows = fetch(
        url, key, "courier_hub_route_statistics",
        "work_date,courier_name,returned_at",
        {"work_date": f"gte.{start}", "and": f"(work_date.lte.{end})", "returned_at": "not.is.null", "order": "work_date.asc,courier_name.asc,returned_at.asc"},
    )
    returns: dict[tuple[str, str], datetime] = {}
    for row in route_rows:
        day = str(row.get("work_date") or "")[:10]
        name_key = norm(row.get("courier_name"))
        returned = parse_dt(row.get("returned_at"))
        if day and name_key and returned and returned > returns.get((day, name_key), datetime.min.replace(tzinfo=returned.tzinfo)):
            returns[(day, name_key)] = returned

    detail: list[dict] = []
    for row in attendance:
        day = str(row.get("work_date") or "")[:10]
        name = str(row.get("courier_name") or "").strip()
        start_time = parse_time(row.get("checkin_start"))
        end_time = parse_time(row.get("checkin_end"))
        start_dt = datetime.combine(date.fromisoformat(day), start_time) if day and start_time else None
        end_source = "Giriton kijelentkezés" if end_time else ""
        end_dt = datetime.combine(date.fromisoformat(day), end_time) if day and end_time else None
        if end_dt and start_dt and end_dt < start_dt:
            end_dt += timedelta(days=1)
        if start_dt and end_dt is None:
            fallback = returns.get((day, norm(name)))
            if fallback:
                end_dt = fallback.replace(tzinfo=None)
                end_source = "Raktári visszaérkezés"
        minutes = int((end_dt - start_dt).total_seconds() // 60) if start_dt and end_dt and end_dt >= start_dt else None
        detail.append({
            "date": day,
            "courier": name,
            "status": str(row.get("activity_status") or ""),
            "shift": str(row.get("shift_text") or ""),
            "start": start_dt.strftime("%H:%M:%S") if start_dt else "",
            "end": end_dt.strftime("%H:%M:%S") if end_dt else "",
            "end_source": end_source or ("Hiányzik" if start_dt else "Nincs kezdés"),
            "worked_minutes": minutes,
        })

    grouped: dict[str, dict] = {}
    for row in detail:
        name = row["courier"] or "Ismeretlen futár"
        item = grouped.setdefault(name, {"courier": name, "days": 0, "worked_days": 0, "total_minutes": 0, "fallback_days": 0, "missing_end_days": 0, "no_show_days": 0})
        item["days"] += 1
        if row["worked_minutes"] is not None:
            item["worked_days"] += 1
            item["total_minutes"] += row["worked_minutes"]
        if row["end_source"] == "Raktári visszaérkezés":
            item["fallback_days"] += 1
        if row["end_source"] == "Hiányzik":
            item["missing_end_days"] += 1
        if row["status"].casefold() == "didn't come":
            item["no_show_days"] += 1
    for item in grouped.values():
        item["total_hours"] = round(item["total_minutes"] / 60, 2)
        item["average_minutes"] = round(item["total_minutes"] / item["worked_days"], 1) if item["worked_days"] else None
    payload = {"period": "2026-09", "attendance_rows": len(attendance), "route_return_rows": len(route_rows), "summary": sorted(grouped.values(), key=lambda x: norm(x["courier"])), "detail": detail}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"attendance_rows": len(attendance), "route_return_rows": len(route_rows), "couriers": len(grouped), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
