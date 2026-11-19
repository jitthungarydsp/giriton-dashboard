"""Import complaint decisions or coordinator shift notices from Gmail into Supabase."""

import argparse
import base64
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import json
import os
from pathlib import Path
import re
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MAILBOX = "balazs.gurzo@jitt.hu"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/"
INCOMING_FILTER = " -in:sent -in:drafts -in:spam -in:trash"
GMAIL_QUERY = '{subject:"Panasz elbírálva" subject:"Panasz elbiralva"}' + INCOMING_FILTER
COORDINATOR_SENDER = "koordinator@jitt.hu"
COORDINATOR_QUERY = f"from:{COORDINATOR_SENDER} {{subject:késés subject:távolmaradás}}" + INCOMING_FILTER
COMPLAINT_TABLE = "complaint_email_responses"
COORDINATOR_TABLE = "coordinator_shift_email_notices"
SUBJECT = re.compile(r"\bpanasz\s+elb[íi]r[áa]lva\b", re.IGNORECASE)
COORDINATOR_SUBJECT = re.compile(
    r"^JITT\s*[-–]\s*Koordin[áa]tor\s+(?P<courier>.+?)\s+[-–]\s+"
    r"(?:(?:(?P<ordinal>[1-9]\d{0,2})\.\s*)?k[ée]s[ée]s|(?P<absence>t[áa]volmarad[áa]s))"
    r"\s+[-–]\s+(?P<shift>.+)$",
    re.IGNORECASE,
)
EXCLUDED_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH"}


def request_json(service, url, *, headers=None, data=None):
    try:
        with urlopen(Request(url, headers=headers or {}, data=data), timeout=45) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as exc:
        code = ""
        if service.startswith("Supabase"):
            try:
                value = json.load(exc).get("code", "")
                if isinstance(value, str) and re.fullmatch(r"[A-Z0-9]{5,12}", value):
                    code = f" ({value})"
            except (ValueError, AttributeError):
                pass
        raise RuntimeError(f"{service}: HTTP {exc.code}{code}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"{service}: connection failed") from exc


def gmail_reader(settings):
    credentials = {key: settings[f"GMAIL_COMPLAINT_{key.upper()}"]
                   for key in ("client_id", "client_secret", "refresh_token")}
    token = request_json(
        "Google OAuth", "https://oauth2.googleapis.com/token",
        data=urlencode({**credentials, "grant_type": "refresh_token"}).encode(),
    )
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    def get(path, **params):
        return request_json("Gmail", GMAIL_URL + path + "?" + urlencode(params), headers=headers)

    if get("profile")["emailAddress"].casefold() != MAILBOX:
        raise RuntimeError(f"Google OAuth must belong to {MAILBOX}.")
    return get


def clean_text(value):
    return re.sub(r"[\x00\ud800-\udfff]", "\ufffd", value)


def coordinator_fields(subject, sender):
    if parseaddr(sender)[1].casefold() != COORDINATOR_SENDER:
        return None
    match = COORDINATOR_SUBJECT.fullmatch(" ".join(subject.split()))
    if not match:
        return None
    courier = match["courier"]
    courier_ids = re.findall(r"\b[0-9]{3,8}\b", courier)
    return {
        "event_type": "absence" if match["absence"] else "late",
        "courier_label": clean_text(courier),
        "courier_id": courier_ids[0] if len(courier_ids) == 1 else None,
        "late_occurrence": int(match["ordinal"]) if match["ordinal"] else None,
        "shift_label": clean_text(match["shift"]),
    }


def parse_message(message, *, coordinator=False):
    if EXCLUDED_LABELS.intersection(message.get("labelIds", ())):
        return None
    raw = message["raw"]
    email = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    subject = str(email.get("Subject", ""))
    sender = str(email.get("From", ""))
    extra = coordinator_fields(subject, sender) if coordinator else ({} if SUBJECT.search(subject) else None)
    if extra is None:
        return None

    def body(content_type):
        part = email.get_body(preferencelist=(content_type,))
        if part is None:
            return ""
        try:
            return clean_text(part.get_content())
        except LookupError:
            return clean_text(part.get_payload(decode=True).decode("utf-8", errors="replace"))

    return {
        "mailbox": MAILBOX,
        "gmail_id": message["id"],
        "gmail_thread_id": message["threadId"],
        "subject": clean_text(subject),
        "sender": clean_text(sender),
        "received_at": datetime.fromtimestamp(int(message["internalDate"]) / 1000, timezone.utc).isoformat(),
        "body_text": body("plain"),
        "body_html": body("html"),
        **extra,
    }


def import_messages(get, save, known_ids=lambda ids: set(), *, coordinator=False):
    matched = inserted = 0
    params = {"q": COORDINATOR_QUERY if coordinator else GMAIL_QUERY, "maxResults": 25}
    while True:
        page = get("messages", **params)
        ids = [item["id"] for item in page.get("messages", ())]
        known = known_ids(ids) if ids else set()
        rows = []
        for gmail_id in ids:
            if gmail_id in known:
                continue
            row = parse_message(get(f"messages/{gmail_id}", format="raw"), coordinator=coordinator)
            if row is not None:
                rows.append(row)
        if rows:
            matched += len(rows)
            inserted += save(rows)
        if not page.get("nextPageToken"):
            return matched, inserted
        params["pageToken"] = page["nextPageToken"]


def supabase_writer(settings, *, table=COMPLAINT_TABLE):
    key = settings["SUPABASE_SERVICE_ROLE_KEY"]
    url = settings["SUPABASE_URL"].rstrip("/") + f"/rest/v1/{table}"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    request_json("Supabase table check", url + "?select=gmail_id&limit=1", headers=headers)
    headers.update({"Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates,return=representation"})

    def save(rows):
        return len(request_json(
            "Supabase insert", url + "?on_conflict=mailbox,gmail_id&select=gmail_id", headers=headers,
            data=json.dumps(rows, ensure_ascii=True).encode(),
        ) or [])

    def known_ids(ids):
        params = urlencode({"mailbox": f"eq.{MAILBOX}", "gmail_id": f"in.({','.join(ids)})", "select": "gmail_id"})
        rows = request_json("Supabase existing-email lookup", url + "?" + params, headers=headers)
        return {row["gmail_id"] for row in rows}

    return save, known_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count matches without writing to the database.")
    parser.add_argument("--coordinator-shifts", action="store_true", help="Import coordinator late and absent shift notices.")
    args = parser.parse_args()
    secrets = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    local = tomllib.loads(secrets.read_text(encoding="utf-8")) if secrets.exists() else {}
    names = ["GMAIL_COMPLAINT_CLIENT_ID", "GMAIL_COMPLAINT_CLIENT_SECRET", "GMAIL_COMPLAINT_REFRESH_TOKEN"]
    if not args.dry_run:
        names += ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    settings = {name: (os.getenv(name) or local.get(name) or "").strip() for name in names}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        parser.exit(1, "Missing settings: " + ", ".join(missing) + "\n")

    try:
        get = gmail_reader(settings)
        if args.dry_run:
            matched, inserted = import_messages(get, lambda rows: 0, coordinator=args.coordinator_shifts)
        else:
            table = COORDINATOR_TABLE if args.coordinator_shifts else COMPLAINT_TABLE
            save, known_ids = supabase_writer(settings, table=table)
            matched, inserted = import_messages(get, save, known_ids, coordinator=args.coordinator_shifts)
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Matching emails: {matched}. New database rows: {inserted}.")


if __name__ == "__main__":
    main()
