"""Refresh the saved quality cases and optionally send one daily message per courier."""

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOPICS = {
    "lateShift": "Műszakkésés",
    "uncleanedTimeWindowLate": "Nem mentesített címkésés",
    "noShow": "No-show",
}


def read_pages(rest, table, params):
    result = []
    for offset in range(0, 50000, 500):
        rows = rest("GET", table, params={**params, "offset": offset, "limit": 500})
        result.extend(rows)
        if len(rows) < 500:
            return result
    raise RuntimeError(f"Page limit exceeded: {table}")


def courier_addresses(master, identities):
    owners = defaultdict(set)
    choices = {}
    hub = defaultdict(set)
    for row in identities:
        address = str(row.get("email") or "").strip().casefold()
        if address:
            cid = str(row["courier_id"])
            owners[address].add(cid)
            hub[cid].add(address)
    for row in master:
        cid = str(row["courier_id"])
        addresses = [str(row.get(key) or "").strip().casefold() for key in ("email", "billing_email")]
        for address in filter(None, addresses):
            owners[address].add(cid)
        choices[cid] = next(filter(None, addresses), "")
    for cid, addresses in hub.items():
        if not choices.get(cid) and len(addresses) == 1:
            choices[cid] = next(iter(addresses))
    return {cid: address for cid, address in choices.items()
            if owners[address] == {cid} and re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", address)}


def email_body(name, items, portal):
    lines = []
    for item in items:
        reference = item["reference"]
        if item["topic"] == "uncleanedTimeWindowLate":
            reference = f"Route ID {reference} · {item['item_count']} érintett cím"
        lines.append(f"- {item['work_date']} · {TOPICS[item['topic']]} · {reference}")
    return (
        f"Szia {name}!\n\n"
        "Az alábbi minőségi jelzésekhez még nincs rögzített reklamáció:\n"
        + "\n".join(lines)
        + f"\n\nHa valamelyik jelzéssel nem értesz egyet, kérjük, reklamáld meg a JittFutár alkalmazásban: {portal}\n"
        "A Statisztika menüben válaszd ki az érintett hónapot és jelzést, majd írd le röviden, mi történt.\n\n"
        "Köszönjük!\nJittFutár csapat"
    )


def deliver(rest, send, portal, month, today):
    items = read_pages(rest, "pwa_quality_outreach_overview", {
        "select": "id,courier_id,courier_name,work_date,topic,reference,item_count", "state": "eq.not_complained",
        "tracked": "eq.true",
        "and": f"(work_date.gte.{month.isoformat()},work_date.lte.{today.isoformat()})", "order": "work_date.asc,id.asc",
    })
    master = read_pages(rest, "courier_master", {
        "select": "courier_id,email,billing_email", "order": "courier_id.asc",
    })
    identities = read_pages(rest, "courier_hub_courier_identity_raw", {
        "select": "courier_id,email", "dsp_id": "eq.8", "order": "id.asc",
    })
    recipients = courier_addresses(master, identities)
    groups = defaultdict(list)
    stats = {"sent": 0, "already_claimed": 0, "unaddressable": 0, "uncertain": 0}
    for item in items:
        groups[item["courier_id"]].append(item)
    for cid, cases in groups.items():
        if cid not in recipients:
            stats["unaddressable"] += 1
            continue
        claims = rest("POST", "rpc/pwa_claim_quality_outreach_email",
                      payload={"p_courier": cid, "p_cases": [r["id"] for r in cases]},
                      prefer="return=representation")
        if not claims:
            stats["already_claimed"] += 1
            continue
        filters = {"id": f"eq.{claims[0]['id']}", "state": "eq.sending"}
        claimed_ids = set(claims[0]["case_ids"])
        cases = [item for item in cases if item["id"] in claimed_ids]
        try:
            send(recipients[cid], "Minőségi jelzések a JittFutárban", email_body(cases[0]["courier_name"], cases, portal))
        except Exception as exc:
            rest("PATCH", "pwa_quality_outreach_emails", params=filters, payload={"state": "uncertain"})
            print("Quality email result uncertain:", type(exc).__name__, flush=True)
            stats["uncertain"] += 1
            continue
        saved = rest("PATCH", "pwa_quality_outreach_emails", params=filters,
                     payload={"state": "sent", "sent_at": datetime.now(timezone.utc).isoformat()},
                     prefer="return=representation")
        if len(saved) != 1:
            raise RuntimeError("Quality email receipt could not be saved")
        stats["sent"] += 1
    return stats


def main():
    import requests
    from resources.supabase_raw import get_supabase_config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, type=lambda value: date.fromisoformat(value + "-01"))
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    today = datetime.now(ZoneInfo("Europe/Budapest")).date()
    stop = date(args.month.year + (args.month.month == 12), args.month.month % 12 + 1, 1)
    if args.month > today:
        parser.error("A hónap még nem kezdődött el.")
    through = min(today, date.fromordinal(stop.toordinal() - 1))
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("Missing Supabase configuration")
    with requests.Session() as session:
        session.headers.update({"apikey": key, "Authorization": f"Bearer {key}"})

        def rest(method, table, params=None, payload=None, prefer="return=minimal"):
            response = session.request(method, f"{url}/rest/v1/{table}", params=params, json=payload,
                                       headers={"Prefer": prefer}, timeout=30)
            if not response.ok:
                raise RuntimeError(f"{method} {table}: HTTP {response.status_code}")
            return response.json() if response.content else []

        rest("POST", "rpc/pwa_refresh_quality_outreach",
             payload={"p_month": args.month.isoformat(), "p_through": through.isoformat()})
        print("Quality outreach snapshot refreshed.", flush=True)
        if args.send:
            from resources.email_sender import app_login_url, send_custom_email, smtp_config
            smtp_config()
            stats = deliver(rest, send_custom_email, app_login_url(), args.month, through)
            print(stats, flush=True)
            return int(bool(stats["uncertain"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
