"""Profile-scoped internal assignment workspace; no financial writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from uuid import UUID

from resources.complaint_assignment_notifications import PREFIX, assignment_value


class AssignmentError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def profile_identity(user):
    courier_id = user.get('courier_id') if user.get('courier_id') is not None else user.get('courierId')
    return str(user.get('username') or '').strip(), str(courier_id if courier_id is not None else '').strip()


def profile_option(user):
    username, courier_id = profile_identity(user)
    if not username or not courier_id or not user.get('active', True):
        return None
    key = 'pwa:' + username
    email = str(user.get('email') or '').strip()
    if username == 'Bagoly Zoltán' and courier_id == '12345':
        email = email or 'zoltan.bagoly@jitt.hu'
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        email = ''
    return {'key': key, 'profileKey': key, 'username': username, 'name': username,
            'courierId': courier_id, 'email': email or None}


def load_profiles(rest, legacy_users=()):
    rows = []
    for offset in range(0, 10000, 500):
        batch = rest('GET', 'pwa_users', params={'select': 'courier_id,username,email,role,active', 'order': 'courier_id.asc', 'limit': '500', 'offset': str(offset)}) or []
        rows.extend(batch)
        if len(batch) < 500:
            break
    known = {str(row.get('username') or '').strip().casefold() for row in rows}
    rows += [row for row in legacy_users if str(row.get('username') or '').strip().casefold() not in known]
    return sorted([value for row in rows if (value := profile_option(row))], key=lambda row: row['name'].casefold())


def assigned_to(value, user):
    person = value.get('assignee') or {}
    username, courier_id = profile_identity(user)
    if person.get('profileKey') or person.get('username'):
        return person.get('username') == username and str(person.get('courierId')) == courier_id
    # Compatibility with assignments already saved by the Hub.
    return (person.get('key'), username, courier_id) in {
        ('bagoly_zoltan', 'Bagoly Zoltán', '12345'), ('gurzo_balazs', 'Gurzó Balázs', '7644')}


def read_records(rest, month=''):
    result = []
    for offset in range(0, 10000, 500):
        params = {'select': 'id,courier_id,document_month,action_key,status,status_note,updated_at',
                  'action_key': f'like.{PREFIX}*', 'order': 'updated_at.desc,id.desc', 'limit': '500', 'offset': str(offset)}
        if month:
            params['document_month'] = 'eq.' + month + '-01'
        batch = rest('GET', 'peopleforce_card_statuses', params=params) or []
        result.extend(batch)
        if len(batch) < 500:
            break
    return result


def read_case(rest, complaint_id):
    rows = rest('GET', 'peopleforce_complaints', params={'id': f'eq.{UUID(str(complaint_id))}', 'select': 'id,courier_id,courier_name,document_month,document_type,message,status,created_at,admin_response,responded_at', 'status': 'neq.deleted', 'limit': '1'}) or []
    if not rows:
        raise AssignmentError('A reklamáció nem található.', 404)
    return rows[0]


def record_for(rest, case):
    rows = rest('GET', 'peopleforce_card_statuses', params={
        'courier_id': 'eq.' + str(case['courier_id']), 'document_month': 'eq.' + str(case['document_month'])[:10],
        'action_key': 'eq.' + PREFIX + str(case['id']), 'select': 'id,courier_id,document_month,action_key,status,status_note,updated_at', 'limit': '1'}) or []
    row = rows[0] if rows else None
    value = assignment_value(row) if row else None
    if row and not value:
        raise AssignmentError('A kijelölés adatai nem értelmezhetők. Frissítsd az ügyet.')
    return row, value


def assignment_view(value):
    if not value:
        return None
    return {key: value.get(key) for key in ['assignmentId', 'assignee', 'assignedAt', 'assignedBy', 'notification', 'notes', 'notesRevision']}


def list_cases(rest, user, *, admin=False, scope='mine', month='', complaint_id='', offset=0, limit=50):
    if scope not in {'mine', 'all'} or scope == 'all' and not admin:
        raise AssignmentError('Más munkatárs ügyeit csak adminisztrátor nézheti meg.', 403)
    if month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise AssignmentError('Érvénytelen hónap.', 422)
    records = read_records(rest, month)
    values = {value['complaintId']: value for row in records if (value := assignment_value(row))}
    accessible = {key: value for key, value in values.items() if scope == 'all' or assigned_to(value, user)}
    if complaint_id:
        complaint_id = str(UUID(str(complaint_id)))
        if scope == 'mine' and complaint_id not in accessible:
            raise AssignmentError('Ez a reklamáció nincs a profilodhoz rendelve.', 403)
    if scope == 'mine' and not accessible:
        return {'items': [], 'hasMore': False, 'canManage': admin}
    params = {'select': 'id,courier_id,courier_name,document_month,document_type,message,status,created_at,admin_response,responded_at',
              'status': 'neq.deleted', 'order': 'created_at.desc,id.desc', 'offset': str(offset), 'limit': str(limit + 1)}
    if month:
        params['document_month'] = f'eq.{month}-01'
    if complaint_id:
        params['id'] = 'eq.' + complaint_id
    elif scope == 'mine':
        # UUIDs only, never free-form user text in a PostgREST expression.
        identifiers = [str(UUID(key)) for key in accessible]
        params['id'] = 'in.(' + ','.join(identifiers) + ')'
    if scope == 'mine' and not complaint_id:
        rows = []
        for index in range(0, len(identifiers), 100):
            batch_params = {**params, 'id': 'in.(' + ','.join(identifiers[index:index + 100]) + ')', 'offset': '0', 'limit': '100'}
            rows.extend(rest('GET', 'peopleforce_complaints', params=batch_params) or [])
        rows.sort(key=lambda row: (str(row.get('created_at') or ''), str(row['id'])), reverse=True)
        rows = rows[offset:offset + limit + 1]
    else:
        rows = rest('GET', 'peopleforce_complaints', params=params) or []
    items = []
    for row in rows[:limit]:
        value = accessible.get(str(row['id']))
        if value and (value.get('courierId') != str(row['courier_id']) or value.get('month') != str(row['document_month'])[:7]):
            continue
        if scope == 'mine' and not value:
            continue
        items.append({**row, 'assignment': assignment_view(value)})
    return {'items': items, 'hasMore': len(rows) > limit, 'canManage': admin}


def save_record(rest, case, old, value, actor):
    now = datetime.now(timezone.utc)
    if old:
        previous = datetime.fromisoformat(old['updated_at'].replace('Z', '+00:00'))
        now = max(now, previous + timedelta(microseconds=1))
    data = {'courier_id': str(case['courier_id']), 'courier_name': case.get('courier_name'), 'document_month': str(case['document_month'])[:10],
            'action_key': PREFIX + str(case['id']), 'status': 'open' if value.get('notification', {}).get('status') == 'pending' else 'done',
            'status_note': json.dumps(value, ensure_ascii=False), 'updated_at': now.isoformat(), 'updated_by': actor}
    params = {'id': 'eq.' + str(old['id']), 'updated_at': 'eq.' + old['updated_at']} if old else {'on_conflict': 'courier_id,document_month,action_key'}
    rows = rest('PATCH' if old else 'POST', 'peopleforce_card_statuses', params=params, payload=data,
                prefer='return=representation' if old else 'resolution=ignore-duplicates,return=representation') or []
    if len(rows) != 1:
        raise AssignmentError('Az ügy időközben módosult. Frissítsd a mentés előtt.')
    return assignment_view(value)


def assign_case(rest, user, complaint_id, profile_key, *, legacy_users=(), operation_id, expected_assignment_id='', note=''):
    case = read_case(rest, complaint_id)
    old, previous = record_for(rest, case)
    operation_id = str(UUID(str(operation_id)))
    if previous and previous.get('assignmentId') == operation_id:
        return assignment_view(previous)
    if case.get('status') in {'closed', 'resolved'}:
        raise AssignmentError('Lezárt reklamációt előbb nyiss vissza.')
    if (previous or {}).get('assignmentId', '') != expected_assignment_id:
        raise AssignmentError('Időközben másik felelőst jelöltek ki. Frissítsd az ügyet.')
    if (previous or {}).get('notification', {}).get('status') == 'sending':
        raise AssignmentError('Az e-mail küldése folyamatban van. Kérlek, várj a módosítással.')
    person = next((row for row in load_profiles(rest, legacy_users) if row['key'] == profile_key), None)
    if not person:
        raise AssignmentError('Nem található aktív PWA-profil ezzel az azonosítóval.', 422)
    note = str(note or '').strip()
    if len(note) > 5000:
        raise AssignmentError('A megjegyzés legfeljebb 5000 karakter lehet.', 422)
    if previous and assigned_to(previous, person) and not note and previous.get('notification', {}).get('status') in {'pending', 'sent'}:
        return assignment_view(previous)
    now = datetime.now(timezone.utc).isoformat()
    notes = list((previous or {}).get('notes') or [])
    if note:
        if len(notes) >= 200:
            raise AssignmentError('Az ügy megjegyzésnaplója megtelt.')
        notes.append({'id': operation_id, 'text': note, 'author': user['username'], 'at': now})
    value = {'schemaVersion': 1, 'complaintId': str(case['id']), 'courierId': str(case['courier_id']), 'month': str(case['document_month'])[:7],
             'assignmentId': operation_id, 'assignee': person, 'assignedAt': now, 'assignedBy': user['username'],
             'courierName': case.get('courier_name') or str(case['courier_id']), 'complaintMessage': case.get('message') or '',
             'assignmentNote': note, 'notes': notes, 'notesRevision': operation_id,
             'hubUrl': 'https://futar.jitt.hu/?complaintTask=' + str(case['id']),
             'notification': {'status': 'pending' if person.get('email') else 'failed', 'queuedAt': now, 'sentAt': None,
                              **({} if person.get('email') else {'error': 'A kijelölt PWA-profilnak nincs e-mail-címe.'})},
             'history': [*((previous or {}).get('history') or []), *([{'assignee': previous['assignee'], 'assignedAt': previous.get('assignedAt'), 'assignedBy': previous.get('assignedBy'), 'notification': previous.get('notification')}] if previous else [])][-30:]}
    return save_record(rest, case, old, value, user['username'])


def add_note(rest, user, complaint_id, text, *, admin=False, operation_id, expected_assignment_id, expected_notes_revision=''):
    case = read_case(rest, complaint_id)
    old, value = record_for(rest, case)
    if not value or not (admin or assigned_to(value, user)):
        raise AssignmentError('Ehhez az ügyhöz nincs megjegyzési jogosultságod.', 403)
    operation_id = str(UUID(str(operation_id)))
    if any(note.get('id') == operation_id for note in value.get('notes', [])):
        return assignment_view(value)
    if value.get('assignmentId') != expected_assignment_id or value.get('notesRevision', '') != expected_notes_revision:
        raise AssignmentError('Az ügy kijelölése vagy megjegyzései időközben módosultak. Frissítsd az ügyet.')
    if value.get('notification', {}).get('status') == 'sending':
        raise AssignmentError('Az értesítés küldése folyamatban van. Kérlek, próbáld újra rövidesen.')
    text = str(text or '').strip()
    if not text or len(text) > 5000 or len(value.get('notes') or []) >= 200:
        raise AssignmentError('Adj meg 1–5000 karakteres megjegyzést; legfeljebb 200 megjegyzés rögzíthető.', 422)
    value.setdefault('notes', []).append({'id': operation_id, 'text': text, 'author': user['username'], 'at': datetime.now(timezone.utc).isoformat()})
    value['notesRevision'] = operation_id
    return save_record(rest, case, old, value, user['username'])


def start_case(rest, user, complaint_id, *, admin=False):
    case = read_case(rest, complaint_id)
    _record, value = record_for(rest, case)
    if not admin and not (value and assigned_to(value, user)):
        raise AssignmentError('Ez az ügy nincs a profilodhoz rendelve.', 403)
    if case.get('status') == 'in_progress':
        return {'ok': True, 'status': 'in_progress'}
    if case.get('status') not in {'new', 'open'}:
        raise AssignmentError('Lezárt ügy vizsgálata nem indítható el.')
    rows = rest('PATCH', 'peopleforce_complaints', params={'id': 'eq.' + str(case['id']), 'courier_id': 'eq.' + str(case['courier_id']),
                'document_month': 'eq.' + str(case['document_month'])[:10], 'status': 'eq.' + case['status']},
                payload={'status': 'in_progress'}, prefer='return=representation') or []
    if len(rows) != 1:
        raise AssignmentError('Az ügy időközben módosult. Frissítsd a vizsgálat megkezdése előtt.')
    return {'ok': True, 'status': 'in_progress'}
