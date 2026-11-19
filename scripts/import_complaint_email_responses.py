"""Import received complaint decisions from Gmail into Supabase."""

import argparse
import base64
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
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
GMAIL_QUERY = '{subject:"Panasz elbírálva" subject:"Panasz elbiralva"} -in:sent -in:drafts -in:spam -in:trash'
SUBJECT = re.compile(r"\bpanasz\s+elb[íi]r[áa]lva\b", re.IGNORECASE)
EXCLUDED_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH"}


def request_json(service, url, *, headers=None, data=None):
    try:
        with urlopen(Request(url, headers=headers or {}, data=data), timeout=45) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as exc:
        raise RuntimeError(f"{service}: HTTP {exc.code}") from None
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


def parse_message(message):
    if EXCLUDED_LABELS.intersection(message.get("labelIds", ())):
        return None
    raw = message["raw"]
    email = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    subject = str(email.get("Subject", ""))
    if not SUBJECT.search(subject):
        return None

    def body(content_type):
        part = email.get_body(preferencelist=(content_type,))
        if part is None:
            return ""
        try:
            return part.get_content().replace("\x00", "\ufffd")
        except LookupError:
            return part.get_payload(decode=True).decode("utf-8", errors="replace").replace("\x00", "\ufffd")

    return {
        "mailbox": MAILBOX,
        "gmail_id": message["id"],
        "gmail_thread_id": message["threadId"],
        "subject": subject.replace("\x00", "\ufffd"),
        "sender": str(email.get("From", "")).replace("\x00", "\ufffd"),
        "received_at": datetime.fromtimestamp(int(message["internalDate"]) / 1000, timezone.utc).isoformat(),
        "body_text": body("plain"),
        "body_html": body("html"),
    }


def import_messages(get, save, known_ids=lambda ids: set()):
    matched = inserted = 0
    params = {"q": GMAIL_QUERY, "maxResults": 25}
    while True:
        page = get("messages", **params)
        ids = [item["id"] for item in page.get("messages", ())]
        known = known_ids(ids) if ids else set()
        rows = []
        for gmail_id in ids:
            if gmail_id in known:
                continue
            row = parse_message(get(f"messages/{gmail_id}", format="raw"))
            if row is not None:
                rows.append(row)
        if rows:
            matched += len(rows)
            inserted += save(rows)
        if not page.get("nextPageToken"):
            return matched, inserted
        params["pageToken"] = page["nextPageToken"]


def supabase_writer(settings):
    key = settings["SUPABASE_SERVICE_ROLE_KEY"]
    url = settings["SUPABASE_URL"].rstrip("/") + "/rest/v1/complaint_email_responses"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    request_json("Supabase", url + "?select=gmail_id&limit=1", headers=headers)
    headers.update({"Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates,return=representation"})

    def save(rows):
        return len(request_json(
            "Supabase", url + "?on_conflict=mailbox,gmail_id&select=gmail_id", headers=headers,
            data=json.dumps(rows, ensure_ascii=True).encode(),
        ) or [])

    def known_ids(ids):
        params = urlencode({"mailbox": f"eq.{MAILBOX}", "gmail_id": f"in.({','.join(ids)})", "select": "gmail_id"})
        rows = request_json("Supabase", url + "?" + params, headers=headers)
        return {row["gmail_id"] for row in rows}

    return save, known_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count matches without writing to the database.")
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
            matched, inserted = import_messages(get, lambda rows: 0)
        else:
            save, known_ids = supabase_writer(settings)
            matched, inserted = import_messages(get, save, known_ids)
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Matching emails: {matched}. New database rows: {inserted}.")


if __name__ == "__main__":
    main()
