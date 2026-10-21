from __future__ import annotations

import json
import tomllib
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(r"C:\Giriton\giriton-dashboard")
OUT = ROOT / "tmp" / "long-routes-aug-sep-2026.json"


def fetch(url: str, key: str) -> list[dict]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "select": "work_date,route_id,courier_id,courier_name,warehouse_code,route_type,route_type_label,departed_at,returned_at,planned_departure_at,planned_return_at,loading_minutes,actual_route_minutes,total_minutes,orders,stops",
            "work_date": "gte.2026-08-01",
            "and": "(work_date.lte.2026-09-30)",
            "order": "work_date.asc,courier_name.asc,route_id.asc",
            "limit": "1000",
            "offset": str(offset),
        }
        response = requests.get(f"{url}/rest/v1/courier_hub_route_statistics", headers=headers, params=params, timeout=60)
        response.raise_for_status()
        page = response.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    return rows


def number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def minutes(value: object) -> int | None:
    parsed = number(value)
    return round(parsed) if parsed is not None else None


def dt_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def is_regional(row: dict) -> bool:
    text = f"{row.get('route_type') or ''} {row.get('route_type_label') or ''}".casefold()
    return any(token in text for token in ("regional", "regionális", "regio", "régió"))


def main() -> None:
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as handle:
        secrets = tomllib.load(handle)
    rows = fetch(str(secrets["SUPABASE_URL"]).rstrip("/"), str(secrets["SUPABASE_SERVICE_ROLE_KEY"]))
    result: list[dict] = []
    for row in rows:
        if is_regional(row):
            continue
        total = minutes(row.get("total_minutes"))
        if total is None:
            actual = minutes(row.get("actual_route_minutes"))
            loading = minutes(row.get("loading_minutes")) or 0
            total = actual + loading if actual is not None else None
        if total is None or total <= 300 or row.get("route_id") in (None, ""):
            continue
        result.append({
            "hónap": str(row.get("work_date") or "")[:7],
            "dátum": str(row.get("work_date") or "")[:10],
            "route_id": row.get("route_id"),
            "futár_id": row.get("courier_id"),
            "futár": row.get("courier_name") or f"Futár #{row.get('courier_id') or ''}".strip(),
            "raktár": row.get("warehouse_code") or "",
            "túra_típus": row.get("route_type_label") or row.get("route_type") or "",
            "indulás": dt_text(row.get("departed_at") or row.get("planned_departure_at")),
            "visszaérkezés": dt_text(row.get("returned_at") or row.get("planned_return_at")),
            "bepakolás_perc": minutes(row.get("loading_minutes")),
            "túraidő_perc": minutes(row.get("actual_route_minutes")),
            "összes_idő_perc": total,
            "összes_idő_óra": round(total / 60, 2),
            "összes_idő_óra_perc": f"{total // 60} óra {total % 60} perc",
            "rendelések": row.get("orders"),
            "címek": row.get("stops"),
        })
    result.sort(key=lambda item: (item["dátum"], str(item["futár"]), int(item["route_id"] or 0)))
    summary: dict[str, dict] = {}
    for row in result:
        key = (row["hónap"], row["futár"])
        item = summary.setdefault(key, {"hónap": row["hónap"], "futár": row["futár"], "túrák": 0, "összes_idő_óra": 0})
        item["túrák"] += 1
        item["összes_idő_óra"] += row["összes_idő_óra"]
    for item in summary.values():
        item["összes_idő_óra"] = round(item["összes_idő_óra"], 2)
    payload = {"rows": result, "summary": sorted(summary.values(), key=lambda x: (x["hónap"], x["futár"]))}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(result), "couriers": len(summary), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
