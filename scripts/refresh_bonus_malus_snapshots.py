"""Drain durable changed-courier/month jobs; never run a route/session batch."""
import argparse
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from resources.supabase_raw import get_supabase_config
from resources.bonus_malus_snapshot_refresh import prepare_bonus_malus_refresh


def rest(method, table, *, params=None, payload=None, schema="settlement"):
    url, key = get_supabase_config()
    headers = {"apikey": key, "Accept-Profile": schema, "Content-Profile": schema,
               "Prefer": "return=representation"}
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = "Bearer " + key
    response = requests.request(method, url.rstrip("/") + "/rest/v1/" + table,
                                headers=headers, params=params, json=payload, timeout=60)
    if not response.ok:
        if response.status_code in (404, 406) and ("bonus_malus_refresh" in table):
            raise RuntimeError("Telepítsd a sql/bonus_malus_snapshot_refresh.sql migrációt az import előtt.")
        raise RuntimeError(f"{table}: HTTP {response.status_code}: {response.text[:1000]}")
    return response.json() if response.content else []


def require_refresh_schema():
    rest("GET", "bonus_malus_refresh_queue", params={"select": "courier_id", "limit": "1"})


def read_all(table, params):
    rows, offset = [], 0
    while True:
        page = rest("GET", table, params={**params, "limit": "1000", "offset": str(offset)})
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def refresh_one(job):
    cid, period, revision = job["courier_id"], job["period_start"], job["revision"]
    latest = rest("GET", "courier_finance_snapshot", params={"select": "*", "courier_id": "eq." + cid,
                  "period_start": "eq." + period, "order": "version.desc", "limit": "1"})
    args = {"p_courier_id": cid, "p_period_start": period, "p_revision": revision,
            "p_base_snapshot_id": latest[0]["id"] if latest else None, "p_fingerprint": None, "p_prepared": None}
    closed = rest("GET", "courier_monthly_closure", params={"select": "status", "courier_id": "eq." + cid,
                  "period_start": "eq." + period, "status": "eq.done", "limit": "1"})
    paid = rest("GET", "peopleforce_card_statuses", schema="public", params={"select": "status",
                "courier_id": "eq." + cid, "document_month": "eq." + period,
                "action_key": "eq.invoice_payment", "status": "eq.done", "limit": "1"})
    if latest and not closed and not paid:
        snapshot = latest[0]
        snapshot["items"] = read_all("courier_finance_snapshot_item", {"select": "*", "snapshot_id": "eq." + snapshot["id"], "order": "section.asc,item_key.asc"})
        snapshot["sources"] = read_all("courier_finance_snapshot_source", {"select": "*", "snapshot_id": "eq." + snapshot["id"], "order": "source_key.asc"})
        adjustments = read_all("courier_settlement_adjustment", {"select": "*", "courier_id": "eq." + cid,
                              "adjustment_type": "in.(bonus,malus)", "order": "id.asc"})
        result = prepare_bonus_malus_refresh(snapshot, adjustments)
        if result:
            args["p_fingerprint"] = result["fingerprint"]
            args["p_prepared"] = result["prepared"]
    return rest("POST", "rpc/publish_bonus_malus_refresh", payload=args)


def refresh_pending(courier_id=None, month=None, limit=200):
    params = {"select": "*", "state": "in.(pending,error)", "order": "updated_at.asc", "limit": str(limit)}
    if courier_id:
        params["courier_id"] = "eq." + str(courier_id)
    if month:
        params["period_start"] = "eq." + str(month)[:7] + "-01"
    jobs = rest("GET", "bonus_malus_refresh_queue", params=params)
    results, errors = [], []
    for job in jobs:
        try:
            result = refresh_one(job)
            results.append({"courier_id": job["courier_id"], "month": job["period_start"], **result})
        except Exception as exc:
            message = str(exc)[:1500]
            # Never acknowledge a newer revision that arrived during processing.
            rest("PATCH", "bonus_malus_refresh_queue", params={"courier_id": "eq." + job["courier_id"],
                 "period_start": "eq." + job["period_start"], "revision": "eq." + str(job["revision"])},
                 payload={"state": "error", "last_error": message})
            errors.append(f"#{job['courier_id']} / {job['period_start']}: {message}")
    if errors:
        raise RuntimeError("A pénzügyi frissítés újrapróbálásra vár: " + "; ".join(errors))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--courier-id")
    parser.add_argument("--month")
    args = parser.parse_args()
    require_refresh_schema()
    if args.apply:
        for result in refresh_pending(args.courier_id, args.month):
            print(result)
    else:
        print("DRY RUN: frissítés nem indult; használd az --apply kapcsolót.")
