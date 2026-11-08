"""Run independently of devtest: --once for cron or --watch for a background worker."""
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from resources.account_automation import enabled, rpc, process_one
    from resources.email_sender import get_setting, send_custom_email
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--once', action='store_true')
    modes.add_argument('--watch', action='store_true')
    parser.add_argument('--enqueue-existing', action='store_true', help='Legfeljebb 100 korábbi nyitott kérelem típusként, ugyanazzal a szigorú ellenőrzéssel.')
    args = parser.parse_args()
    if not enabled():
        raise RuntimeError('PWA_ACCOUNT_AUTOMATION_ENABLED=true szükséges.')
    if args.enqueue_existing:
        from resources.pwa_users_db import _request
        from resources.account_automation import enqueue
        for kind, table in [('reset', 'pwa_password_reset_requests'), ('registration', 'pwa_registration_requests')]:
            for row in _request('GET', table, params={'select': 'id', 'status': 'eq.new', 'order': 'created_at.asc', 'limit': '100'}) or []:
                enqueue(kind, row['id'], 'automatic')
    while True:
        # Bound the work per tick; no whole-user or whole-master synchronization.
        for _ in range(10):
            state = process_one(rpc, send_custom_email, get_setting('PWA_PUBLIC_URL', 'https://futar.jitt.hu'))
            if state == 'idle':
                break
            print('Account job:', state, flush=True)
        if args.once:
            return
        time.sleep(15)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never log SMTP responses, emails, passwords, reset links or request bodies.
        print('Account worker stopped:', type(exc).__name__, file=sys.stderr)
        sys.exit(1)
