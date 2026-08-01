#!/usr/bin/env python3
"""
Holnapi műszak push értesítések küldése.

Szükséges csomag:
    pip install pywebpush requests

Környezeti változók:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    VAPID_PRIVATE_KEY
    VAPID_SUBJECT   pl. mailto:admin@example.com

Futtatás:
    python send_tomorrow_shift_push.py
    python send_tomorrow_shift_push.py --dry-run
    python send_tomorrow_shift_push.py --date 2026-07-16
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pywebpush import WebPushException, webpush


BUDAPEST = ZoneInfo("Europe/Budapest")


def setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Hiányzó környezeti változó: {name}")
    return value


def supabase_headers(prefer: str = "") -> dict[str, str]:
    key = setting("SUPABASE_SERVICE_ROLE_KEY")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str = "",
) -> Any:
    url = setting("SUPABASE_URL").rstrip("/")
    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(prefer),
        params=params,
        json=payload,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase {table}: HTTP {response.status_code}: {response.text[:2000]}")
    if not response.content:
        return []
    return response.json()


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_time(value: Any) -> str:
    text = str(value or "").strip().replace(".", ":")
    if not text:
        return ""
    parts = text.split(":")
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]) if len(parts) > 1 else 0:02d}"
    except ValueError:
        return text[:5]


def load_tomorrow_shifts(work_date: date) -> dict[int, list[dict[str, Any]]]:
    rows = supabase_request(
        "GET",
        "vw_attendance_muszakpro_latest_comparison",
        params={
            "select": (
                "courier_id,courier_name,warehouse,shift_start,shift_end,"
                "attendance_status,muszakpro_status,muszakpro_booking_code,work_date"
            ),
            "work_date": f"eq.{work_date.isoformat()}",
            "order": "courier_id.asc,shift_start.asc",
            "limit": "5000",
        },
    )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("muszakpro_status") or "").strip().upper() != "OK":
            continue
        grouped[int(row["courier_id"])].append(row)
    return grouped


def load_subscriptions(courier_ids: list[int]) -> list[dict[str, Any]]:
    if not courier_ids:
        return []
    joined = ",".join(str(value) for value in courier_ids)
    return supabase_request(
        "GET",
        "pwa_push_subscriptions",
        params={
            "select": "id,courier_id,endpoint,p256dh,auth",
            "courier_id": f"in.({joined})",
            "active": "eq.true",
            "order": "courier_id.asc,updated_at.desc",
            "limit": "10000",
        },
    )


def already_sent(courier_id: int, work_date: date) -> bool:
    rows = supabase_request(
        "GET",
        "pwa_push_delivery_log",
        params={
            "select": "id",
            "courier_id": f"eq.{courier_id}",
            "work_date": f"eq.{work_date.isoformat()}",
            "notification_type": "eq.tomorrow_shift",
            "status": "eq.sent",
            "limit": "1",
        },
    )
    return bool(rows)


def format_shift_line(row: dict[str, Any]) -> str:
    start_text = str(row.get("shift_start") or "").strip()
    end_text = str(row.get("shift_end") or "").strip()
    start = parse_iso(start_text) if "T" in start_text else None
    end = parse_iso(end_text) if "T" in end_text else None
    local_start = start.astimezone(BUDAPEST).strftime("%H:%M") if start else normalize_time(start_text) or "?"
    local_end = end.astimezone(BUDAPEST).strftime("%H:%M") if end else normalize_time(end_text) or "?"
    warehouse = str(row.get("warehouse") or row.get("warehouse_name") or "Raktár")
    return f"{warehouse} · {local_start}–{local_end}"


def save_delivery_log(
    *,
    courier_id: int,
    work_date: date,
    status: str,
    message: str,
) -> None:
    supabase_request(
        "POST",
        "pwa_push_delivery_log",
        payload={
            "courier_id": courier_id,
            "work_date": work_date.isoformat(),
            "notification_type": "tomorrow_shift",
            "status": status,
            "message": message[:2000],
            "sent_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def deactivate_subscription(subscription_id: int) -> None:
    supabase_request(
        "PATCH",
        "pwa_push_subscriptions",
        params={"id": f"eq.{subscription_id}"},
        payload={
            "active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Célnap YYYY-MM-DD; alapértelmezett: holnap.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(BUDAPEST).date() + timedelta(days=1)
    )

    shifts_by_courier = load_tomorrow_shifts(target_date)
    subscriptions = load_subscriptions(sorted(shifts_by_courier))
    subscriptions_by_courier: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for subscription in subscriptions:
        subscriptions_by_courier[int(subscription["courier_id"])].append(subscription)

    sent = 0
    skipped = 0
    failed = 0

    for courier_id, shifts in sorted(shifts_by_courier.items()):
        if already_sent(courier_id, target_date):
            skipped += 1
            print(f"KIHAGYVA már elküldve: courier_id={courier_id}")
            continue

        courier_subscriptions = subscriptions_by_courier.get(courier_id, [])
        if not courier_subscriptions:
            skipped += 1
            print(f"KIHAGYVA nincs feliratkozás: courier_id={courier_id}")
            continue

        lines = [format_shift_line(row) for row in shifts]
        body = "\n".join(lines)
        title = "Holnapi műszakod" if len(lines) == 1 else "Holnapi műszakjaid"
        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "tag": f"tomorrow-shift-{courier_id}-{target_date.isoformat()}",
                "url": "/",
                "renotify": False,
                "data": {
                    "section": "home",
                    "workDate": target_date.isoformat(),
                },
            },
            ensure_ascii=False,
        )

        if args.dry_run:
            print(f"DRY_RUN courier_id={courier_id} title={title!r} body={body!r}")
            continue

        courier_success = False
        errors: list[str] = []

        for subscription in courier_subscriptions:
            info = {
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"],
                },
            }
            try:
                webpush(
                    subscription_info=info,
                    data=payload,
                    vapid_private_key=setting("VAPID_PRIVATE_KEY"),
                    vapid_claims={"sub": setting("VAPID_SUBJECT")},
                    ttl=12 * 60 * 60,
                )
                courier_success = True
            except WebPushException as exc:
                status_code = getattr(exc.response, "status_code", None)
                errors.append(f"subscription={subscription['id']} status={status_code} error={exc}")
                if status_code in {404, 410}:
                    deactivate_subscription(int(subscription["id"]))

        if courier_success:
            sent += 1
            save_delivery_log(
                courier_id=courier_id,
                work_date=target_date,
                status="sent",
                message=body,
            )
            print(f"ELKÜLDVE courier_id={courier_id}: {body}")
        else:
            failed += 1
            error_text = " | ".join(errors) or "Ismeretlen küldési hiba."
            save_delivery_log(
                courier_id=courier_id,
                work_date=target_date,
                status="failed",
                message=error_text,
            )
            print(f"HIBA courier_id={courier_id}: {error_text}", file=sys.stderr)

    print(f"Kész. elküldve={sent} kihagyva={skipped} hibás={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
