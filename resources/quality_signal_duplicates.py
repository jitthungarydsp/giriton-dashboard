"""Audited closure of raw quality signals, independent of daily complaint limits."""
from datetime import datetime, timezone
import json
import re


# This private namespace is already excluded from courier settlement workflows.
PREFIX = 'internal_complaint_assignment:duplicate-signal:'
TABLE = 'peopleforce_card_statuses'


def action_key(kind, signal_id):
    if kind not in {'route', 'shift'} or not re.fullmatch(r'(?:[0-9]{1,20}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})', str(signal_id)):
        raise ValueError('Érvénytelen jelzésazonosító.')
    return PREFIX + kind + ':' + str(signal_id).lower()


def resolution_for(record, kind, signal):
    if record.get('action_key') != action_key(kind, signal['id']) or str(record.get('courier_id')) != str(signal.get('courier_id')):
        return None
    try:
        value = json.loads(record.get('status_note') or '{}')
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or value.get('recordType') != 'qualitySignalResolution' or value.get('reason') != 'duplicate' or record.get('status') != 'done':
        return None
    return {key: value.get(key) for key in ('reason', 'closedAt', 'closedBy')}


def read_resolution(rest, kind, signal, month):
    rows = rest('GET', TABLE, params={'select': 'action_key,courier_id,status,status_note',
        'courier_id': 'eq.' + str(signal['courier_id']), 'document_month': 'eq.' + str(month),
        'action_key': 'eq.' + action_key(kind, signal['id']), 'limit': '1'}) or []
    return resolution_for(rows[0], kind, signal) if rows else None


def attach_resolutions(rest, alerts, shifts, month):
    signals = [(kind, row) for kind, rows in [('route', alerts), ('shift', shifts)] for row in rows]
    for offset in range(0, len(signals), 30):
        batch = signals[offset:offset + 30]
        keys = ','.join(action_key(kind, row['id']) for kind, row in batch)
        records = rest('GET', TABLE, params={'select': 'action_key,courier_id,status,status_note',
            'document_month': 'eq.' + str(month), 'action_key': 'in.(' + keys + ')', 'limit': '100'}) or []
        by_key = {row['action_key']: row for row in records}
        for kind, signal in batch:
            record = by_key.get(action_key(kind, signal['id']))
            if record:
                signal['resolution'] = resolution_for(record, kind, signal)


def close_duplicate(rest, kind, signal, month, actor):
    current = read_resolution(rest, kind, signal, month)
    if current:
        return current
    now = datetime.now(timezone.utc).isoformat()
    value = {'schemaVersion': 2, 'recordType': 'qualitySignalResolution', 'reason': 'duplicate',
             'signalKind': kind, 'signalId': str(signal['id']), 'closedAt': now, 'closedBy': actor}
    saved = rest('POST', TABLE, params={'on_conflict': 'courier_id,document_month,action_key'}, payload={
        'courier_id': str(signal['courier_id']), 'document_month': str(month),
        'action_key': action_key(kind, signal['id']), 'status': 'done',
        'status_note': json.dumps(value, ensure_ascii=False), 'updated_at': now, 'updated_by': actor,
    }, prefer='resolution=ignore-duplicates,return=representation') or []
    confirmed = resolution_for(saved[0], kind, signal) if saved else read_resolution(rest, kind, signal, month)
    if not confirmed:
        raise RuntimeError('A duplikációs lezárás mentése nem igazolható.')
    return confirmed


def find_existing_day_complaint(rest, kind, signal, work_date):
    # Mirror the address_delay bucket in pwa_quality_complaint_daily_limit.sql.
    # Bag-missing penalties and late-shift signals do not claim that bucket.
    if kind != 'route' or signal.get('alert_type') == 'bag_missing':
        return None
    for offset in range(0, 10000, 100):
        rows = rest('GET', 'pwa_quality_complaints', params={'select': '*',
            'courier_id': 'eq.' + str(signal['courier_id']), 'work_month': 'eq.' + work_date[:7] + '-01',
            'topic': 'in.(cleanedTimeWindowLate,uncleanedTimeWindowLate)',
            'affected_items': 'cs.' + json.dumps([{'date': work_date}]),
            'order': 'created_at.asc,id.asc', 'offset': str(offset), 'limit': '100'}) or []
        for row in rows:
            if any(item.get('date') == work_date and not (item.get('signalKind') == 'route' and item.get('category') == 'Futárbüntetés') for item in row.get('affected_items') or []):
                return row
        if len(rows) < 100:
            return None
    raise RuntimeError('A meglévő napi reklamáció nem azonosítható egyértelműen.')
