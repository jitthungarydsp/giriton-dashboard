"""Read-only, day-scoped evidence for an administrator reviewing a complaint."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo('Europe/Budapest')


def form_defaults(complaint, routes, raw_rows):
    """Only suggest routes tied to the affected item, never an arbitrary daily tour."""
    import re
    items = complaint.get('affected_items') or []
    ids = {str(x.get('routeId')) for x in items if x.get('routeId')}
    clocks = {m.group() for x in items for m in [re.search(r'\b\d{1,2}:\d{2}', str(x.get('label') or ''))] if m}
    def clock(text):
        m = re.search(r'\b\d{1,2}:\d{2}', str(text or ''))
        return m.group().zfill(5) if m else ''
    matching = [r for r in routes if str(r['route_id']) in ids] if ids else [
        r for r in routes if clock(r.get('shift_name')) in {c.zfill(5) for c in clocks}]
    if not ids and not clocks and len(routes) == 1:
        matching = routes
    matched_ids = {str(r['route_id']) for r in matching}
    plates = {str(r.get('vehicle_plate') or '').strip().upper() for r in matching if r.get('vehicle_plate')}
    for raw in raw_rows:
        if str(raw['route_id']) in matched_ids:
            plate = (raw.get('response_json') or {}).get('shift', {}).get('vehiclePlate')
            if plate:
                plates.add(str(plate).strip().upper())
    notes = []
    if not matching and not ids:
        notes.append('Az érintett műszakhoz nem találtunk egyértelmű túrát. Add meg kézzel, vagy ellenőrizd a részletes adatokat.')
    if len(plates) > 1:
        notes.append('Több rendszám tartozik az érintett túrákhoz: ' + ', '.join(sorted(plates)) + '. Válassz kézzel.')
    return {'routeId': ', '.join(sorted(ids or matched_ids)),
            'licensePlate': next(iter(plates)) if len(plates) == 1 else '', 'notes': notes}


def display_time(value):
    text = str(value or '')
    if not text:
        return 'Nincs adat'
    if len(text) <= 8 and ':' in text:
        return text
    try:
        stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=LOCAL)
        return stamp.astimezone(LOCAL).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return 'Nincs adat'


def complaint_evidence(complaint, read):
    """Never persist or reclassify anything. A failed source is not missing data."""
    days = sorted({str(x.get('date') or '') for x in complaint.get('affected_items') or []})
    sections, warnings = [], []
    if len(days) != 1:
        return {'sections': [], 'warnings': ['A reklamációhoz nem tartozik egyetlen egyértelmű nap.']}
    from datetime import date
    day = date.fromisoformat(days[0]).isoformat()
    cid = str(int(complaint['courier_id']))
    scoped = {'courier_id': 'eq.' + cid, 'work_date': 'eq.' + day, 'limit': '100'}
    queries = {
        'giriton_attendance_raw': {'select': 'work_date,courier_name,shift_text,checkin_start,checkin_end,activity_status,updated_at',
            'work_date': 'eq.' + day, 'courier_name': 'eq.' + str(complaint.get('courier_name') or ''), 'limit': '20'},
        'courier_shift_overview': {**scoped, 'select': 'warehouse_id,raw_shift,updated_at'},
        'courier_hub_route_statistics': {**scoped, 'select': 'route_id,warehouse_code,shift_name,vehicle_plate,queue_started_at,actual_shift_start_at,route_assigned_at,departed_at,returned_at,updated_at'},
        'pwa_courier_route_quality_report': {**scoped, 'select': 'route_id,shift_start_at,queue_started_at,queued_on_time,late_start_minutes,quality_ok,updated_at'},
    }
    data = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(read, name, params) for name, params in queries.items()}
        for name, future in futures.items():
            try:
                data[name] = future.result()
                if len(data[name]) >= int(queries[name]['limit']):
                    warnings.append(name + ': a megjelenítési korlátot elértük, az adatok nem feltétlenül teljesek.')
            except Exception:
                data[name] = []
                warnings.append(name + ': a forrás most nem olvasható; ez nem jelenti, hogy nincs adat.')

    def section(title, source, updated, rows):
        sections.append({'title': title, 'source': source, 'updatedAt': updated or '', 'rows': rows})

    section('A reklamációhoz mentett adatok', 'pwa_quality_complaints', complaint.get('created_at'), [
        {'label': label, 'value': value} for item in complaint.get('affected_items') or []
        for label, value in [('Műszak / érintett túra', item.get('label') or 'Nincs adat'),
                             ('Eredeti jelzés', item.get('note') or 'Nincs adat'),
                             ('Giriton-bejelentkezés', display_time(item.get('giritonLoginAt'))),
                             ('Sorba állás', display_time(item.get('queueStartedAt')))]])
    for row in data['giriton_attendance_raw']:
        section('Giriton-jelenlét', 'giriton_attendance_raw', row.get('updated_at'), [
            {'label': 'Műszak', 'value': row.get('shift_text') or 'Nincs adat'},
            {'label': 'Bejelentkezés', 'value': display_time(row.get('checkin_start'))},
            {'label': 'Kijelentkezés (forrásérték)', 'value': display_time(row.get('checkin_end'))}])
    for row in data['courier_shift_overview']:
        raw = row.get('raw_shift') or {}
        section('Hub műszakösszesítő', 'courier_shift_overview', row.get('updated_at'), [
            {'label': 'Raktár', 'value': 'BUD' + str(row.get('warehouse_id') or '?')},
            {'label': 'Műszak', 'value': f"{raw.get('plannedStart') or '?'} – {raw.get('plannedEnd') or '?'}"},
            {'label': 'Rögzített kezdés', 'value': display_time(raw.get('actualStart'))},
            {'label': 'Hub minősítés', 'value': str(raw.get('evaluation') or 'Nincs adat')}])
    routes = data['courier_hub_route_statistics']
    for row in routes:
        section('Hub túra · #' + str(row['route_id']), 'courier_hub_route_statistics', row.get('updated_at'), [
            {'label': 'Raktár / műszak', 'value': f"{row.get('warehouse_code') or '?'} · {row.get('shift_name') or '?'}"},
            *[{'label': label, 'value': display_time(row.get(key))} for key, label in [
                ('queue_started_at', 'Tárolt sorba állás'), ('actual_shift_start_at', 'Tárolt műszakkezdés'),
                ('route_assigned_at', 'Túra kiosztása'), ('departed_at', 'Indulás'), ('returned_at', 'Visszaérkezés')]]])
    for row in data['pwa_courier_route_quality_report']:
        section('PWA minősítés · #' + str(row['route_id']), 'pwa_courier_route_quality_report', row.get('updated_at'), [
            {'label': 'Műszakkezdés', 'value': display_time(row.get('shift_start_at'))},
            {'label': 'Sorba állás', 'value': display_time(row.get('queue_started_at'))},
            {'label': 'Időben sorba állt', 'value': {True: 'Igen', False: 'Nem'}.get(row.get('queued_on_time'), 'Nincs adat')},
            {'label': 'Számított műszakkésés', 'value': str(row['late_start_minutes']) + ' perc' if row.get('late_start_minutes') is not None else 'Nincs adat'}])
    late = any((r.get('raw_shift') or {}).get('evaluation') == 'LATE' for r in data['courier_shift_overview'])
    if late and any(r.get('queued_on_time') is True for r in data['pwa_courier_route_quality_report']):
        warnings.append('Eltérő napi minősítések: a Hub késést, a PWA legalább egy túrán időben történő sorba állást jelez. Kézi ellenőrzés szükséges.')
    ids = sorted({str(int(r['route_id'])) for r in routes})
    raw_rows = []
    if ids:
        try:
            raw_rows = read('courier_route_performance_detail_raw', {'select': 'route_id,response_json,fetched_at',
                'courier_id': 'eq.' + cid, 'route_id': 'in.(' + ','.join(ids) + ')', 'limit': '100'})
            labels = {'SHIFT_AVAILABLE': 'Sorba állás', 'SHIFT_START': 'Műszakkezdés (SHIFT_START)',
                      'ROUTE_ASSIGNED': 'Túra kiosztása', 'DEPARTED': 'Indulás', 'WAREHOUSE_ARRIVED': 'Visszaérkezés'}
            for raw in raw_rows:
                payload = raw.get('response_json') or {}
                events = payload.get('log') or []
                section('Nyers Hub-eseménynapló · #' + str(raw['route_id']), 'courier_route_performance_detail_raw', raw.get('fetched_at'), [
                    {'label': labels.get(event.get('type'), str(event.get('type') or 'Esemény')),
                     'value': display_time(event.get('occurredAt')) + ((' · ' + str(event['message'])) if event.get('message') else '')}
                    for event in sorted(events, key=lambda e: str(e.get('occurredAt') or ''))])
                if not any(e.get('type') == 'SHIFT_AVAILABLE' for e in events):
                    warnings.append('#' + str(raw['route_id']) + ': a nyers naplóban nincs külön sorbaállási esemény. A tárolt sorbaállási idő önmagában nem bizonyítja a tényleges időpontot.')
        except Exception:
            warnings.append('A nyers Hub-eseménynapló most nem olvasható.')
    if not data['giriton_attendance_raw']:
        warnings.append('Nincs pontos névegyezéssel talált Giriton-adat; a jelenlét ebből nem dönthető el.')
    return {'day': day, 'sections': sections, 'warnings': warnings,
            'formDefaults': form_defaults(complaint, routes, raw_rows)}
