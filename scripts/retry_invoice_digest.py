"""Retry exactly one saved morning digest after explicit operator authorization."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery-id', required=True)
    args = parser.parse_args()
    from resources.email_sender import send_custom_email, smtp_config
    from resources.invoice_admin_notifications import retry_invoice_digest
    smtp_config()  # Validate settings before claiming any delivery.
    def rest(method, table, *, schema, params=None, payload=None, prefer=None):
        headers = {'apikey': os.environ['SUPABASE_SERVICE_ROLE_KEY'],
                   'Authorization': 'Bearer ' + os.environ['SUPABASE_SERVICE_ROLE_KEY'],
                   'Accept-Profile': schema, 'Content-Profile': schema, 'Content-Type': 'application/json'}
        if prefer:
            headers['Prefer'] = prefer
        url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + table
        if params:
            url += '?' + urlencode(params)
        request = Request(url, headers=headers, method=method, data=json.dumps(payload).encode() if payload is not None else None)
        with urlopen(request, timeout=45) as response:
            return json.load(response)
    result = retry_invoice_digest(rest, send_custom_email, args.delivery_id)
    print(json.dumps(result), flush=True)
    if result['state'] != 'sent':
        raise RuntimeError('A napi riport küldése nem igazolt.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception as exc:
        # Never print provider responses, credentials, message contents or headers.
        print('Invoice digest retry stopped: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
