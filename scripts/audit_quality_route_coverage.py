"""Read-only reconciliation of route signals, complaints and saved Kifli submissions."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html import escape
import json
import importlib.util
from pathlib import Path
import tomllib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quality_signal_duplicates', ROOT / 'resources/quality_signal_duplicates.py')
duplicates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(duplicates)
action_key, resolution_for = duplicates.action_key, duplicates.resolution_for


def reconcile(alerts, complaints, deliveries, resolutions, owners, month):
    """One row per exact courier/Route ID, with raw reports counted separately."""
    delivery_by_id = {str(row['complaint_id']): row for row in deliveries}
    cases = {str(row['id']): row for row in complaints}
    groups = defaultdict(lambda: {'signals': [], 'cases': []})
    unknown = []
    closed_duplicates = 0
    for row in alerts:
        marker = resolutions.get(action_key('route', row['id']))
        if marker and resolution_for(marker, 'route', row):
            closed_duplicates += 1
            continue
        route = str(row.get('route_id') or '').strip()
        if not route:
            unknown.append({'courier': row.get('courier_name'), 'courier_id': str(row['courier_id']), 'signal_id': row['id']})
            continue
        groups[(str(row['courier_id']), route)]['signals'].append(row)
    for case in complaints:
        if case.get('topic') not in {'cleanedTimeWindowLate', 'uncleanedTimeWindowLate'}:
            continue
        routes = {str(row.get('routeId') or '').strip() for row in case.get('affected_items') or []}
        delivery = delivery_by_id.get(str(case['id']), {})
        actual_route = str(delivery.get('route_id') or '').strip()
        if actual_route and not any(char.isspace() or char in ',;' for char in actual_route):
            routes.add(actual_route)
        routes.discard('')
        if not routes and str(case.get('work_month', '')).startswith(month):
            unknown.append({'courier': case.get('courier_name'), 'courier_id': str(case['courier_id']), 'complaint_id': case['id']})
        for route in routes:
            key = (str(case['courier_id']), route)
            if key in groups or str(case.get('work_month', '')).startswith(month):
                groups[key]['cases'].append(case)
    rows = []
    for (courier_id, route), group in groups.items():
        candidates = group['cases']
        owner = owners.get((courier_id, route))
        if owner:
            chosen = cases.get(str(owner['id']), owner)
        else:
            chosen = None
        delivery = delivery_by_id.get(str(chosen['id']), {}) if chosen else {}
        partner = (chosen or {}).get('partnerDecision', {})
        status = ('Továbbított' if chosen and (chosen.get('status') == 'forwarded' or delivery.get('state') == 'sent') else
                  'Lezárt' if chosen and chosen.get('status') == 'closed' else
                  'Továbbításra vár' if chosen else 'Még nincs reklamáció')
        dates = {str(item.get('date') or '') for case in candidates for item in case.get('affected_items') or [] if str(item.get('routeId') or '').strip() == route}
        dates.update(datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('Europe/Budapest')).date().isoformat() for row in group['signals'])
        name = (chosen or next(iter(group['signals']), None) or next(iter(candidates), {})).get('courier_name') or 'Ismeretlen'
        rows.append({'courier': name, 'courier_id': courier_id, 'route_id': route, 'dates': ', '.join(sorted(dates - {''})),
                     'status': status, 'signals': len(group['signals']), 'signal_ids': [str(row['id']) for row in group['signals']],
                     'complaint_id': str(chosen['id']) if chosen else '', 'delivery_state': delivery.get('state', ''),
                     'partner_decision': {'accepted': 'Elfogadva', 'rejected': 'Elutasítva', 'partially_accepted': 'Részben elfogadva'}.get(partner.get('status'), ''),
                     'historical_cases': len(candidates), 'unclaimed_historical_case': bool(candidates and not chosen)})
    rows.sort(key=lambda row: (row['status'], row['courier'].casefold(), row['route_id']))
    return {'month': month, 'checked_at': datetime.now(timezone.utc).isoformat(), 'counts': dict(Counter(row['status'] for row in rows)),
            'rows': rows, 'unknown_route': unknown, 'closed_duplicate_signals': closed_duplicates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--month', default='2026-11')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start = date.fromisoformat(args.month + '-01')
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    zone = ZoneInfo('Europe/Budapest')
    utc_start = datetime.combine(start, datetime.min.time(), zone).astimezone(timezone.utc).isoformat()
    utc_end = datetime.combine(end, datetime.min.time(), zone).astimezone(timezone.utc).isoformat()
    settings = tomllib.loads((ROOT / '.streamlit/secrets.toml').read_text(encoding='utf8'))
    headers = {'apikey': settings['SUPABASE_SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + settings['SUPABASE_SERVICE_ROLE_KEY']}
    def read(table, params=None, payload=None):
        request = Request(settings['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + table + ('?' + urlencode(params) if params else ''),
                          headers={**headers, 'Content-Type': 'application/json'}, data=json.dumps(payload).encode() if payload is not None else None)
        with urlopen(request, timeout=45) as response:
            return json.load(response)
    def pages(table, params):
        rows = []
        for offset in range(0, 100000, 500):
            page = read(table, {**params, 'limit': '500', 'offset': str(offset)})
            rows.extend(page)
            if len(page) < 500:
                return rows
        raise RuntimeError('Az összes adat nem tölthető be.')
    tasks = [
        ('courier_route_alerts', {'select': 'id,courier_id,courier_name,route_id,created_at,alert_type,status', 'and': f'(created_at.gte.{utc_start},created_at.lt.{utc_end})', 'alert_type': 'in.(delay,problem,bag_missing)', 'order': 'id.asc'}),
        ('pwa_quality_complaints', {'select': 'id,courier_id,courier_name,topic,work_month,status,created_at,affected_items', 'order': 'id.asc'}),
        ('pwa_quality_complaint_deliveries', {'select': 'complaint_id,state,route_id:payload->>route_id', 'order': 'complaint_id.asc'}),
        ('peopleforce_card_statuses', {'select': 'action_key,courier_id,status,status_note', 'document_month': 'eq.' + start.isoformat(), 'action_key': 'like.internal_complaint_assignment:duplicate-signal:route:*', 'order': 'id.asc'}),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        alerts, complaints, deliveries, markers = list(pool.map(lambda task: pages(*task), tasks))
    decision_spec = importlib.util.spec_from_file_location('quality_complaint_decisions', ROOT / 'resources/quality_complaint_decisions.py')
    decisions = importlib.util.module_from_spec(decision_spec)
    decision_spec.loader.exec_module(decisions)
    def decision_read(method, table, params):
        if method != 'GET':
            raise ValueError('Az audit kizárólag olvasást végezhet.')
        return read(table, params)
    decisions.attach_partner_decisions(decision_read, complaints)
    keys = {(str(row['courier_id']), str(row.get('route_id') or '').strip()) for row in alerts if row.get('route_id')}
    keys.update((str(case['courier_id']), str(item.get('routeId') or '').strip()) for case in complaints if str(case.get('work_month', '')).startswith(args.month)
                and case.get('topic') in {'cleanedTimeWindowLate', 'uncleanedTimeWindowLate'} for item in case.get('affected_items') or [] if item.get('routeId'))
    keys.update((str(case['courier_id']), str(delivery.get('route_id') or '').strip()) for case in complaints if str(case.get('work_month', '')).startswith(args.month)
                and case.get('topic') in {'cleanedTimeWindowLate', 'uncleanedTimeWindowLate'} for delivery in deliveries if str(delivery['complaint_id']) == str(case['id']) and delivery.get('route_id') and not any(c.isspace() or c in ',;' for c in delivery['route_id']))
    def owner(key):
        # This RPC is SQL STABLE and SELECT-only; it does not create complaints.
        result = read('rpc/pwa_find_quality_route_complaint', payload={'p_courier_id': key[0], 'p_route_id': key[1]})
        return key, result[0] if result else None
    with ThreadPoolExecutor(max_workers=6) as pool:
        owners = dict(pool.map(owner, sorted(keys)))
    report = reconcile(alerts, complaints, deliveries, {row['action_key']: row for row in markers}, owners, args.month)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'route-coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    columns = [('courier', 'Futár'), ('courier_id', 'Futár ID'), ('route_id', 'Route ID'), ('dates', 'Nap'), ('status', 'Állapot'), ('signals', 'Jelzések'), ('partner_decision', 'Kifli-döntés'), ('delivery_state', 'Beküldés állapota'), ('complaint_id', 'Reklamáció azonosító')]
    sections = []
    for status in ['Még nincs reklamáció', 'Továbbításra vár', 'Továbbított', 'Lezárt']:
        rows = [row for row in report['rows'] if row['status'] == status]
        sections.append(f'<h2>{escape(status)} · {len(rows)} túra</h2><table><thead><tr>' + ''.join(f'<th>{label}</th>' for _, label in columns) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + escape(str(row[key])) + '</td>' for key, _ in columns) + '</tr>' for row in rows) + '</tbody></table>')
    unknown = escape(json.dumps(report['unknown_route'], ensure_ascii=False, indent=2))
    document = '<!doctype html><html lang="hu"><meta charset="utf-8"><title>Reklamációk Route ID szerint</title><style>body{font:15px system-ui;margin:32px;color:#182536}table{border-collapse:collapse;width:100%;margin-bottom:32px}th,td{text-align:left;border-bottom:1px solid #ddd;padding:10px;font-size:13px}th{background:#edf4ee}h2{margin-top:36px}td:last-child{font-size:11px;overflow-wrap:anywhere}</style>'
    document += f'<h1>Reklamációk Route ID szerint · {escape(args.month)}</h1><p>Ellenőrizve: {escape(report["checked_at"])}. Egy sor egy futár és egy Route ID. A jelzés nem jelent beküldött reklamációt. Az automatikus és futárjelzések együtt szerepelnek.</p>'
    document += ''.join(sections) + f'<h2>Route ID nélkül · {len(report["unknown_route"])} rekord</h2><p>Ezeket nem párosítottuk találgatással.</p><pre>{unknown}</pre><p>Duplikációként lezárt, kihagyott jelzések: {report["closed_duplicate_signals"]}.</p></html>'
    (args.output / 'reklamaciok-route-id-szerint.html').write_text(document, encoding='utf8')
    print(json.dumps({key: report[key] for key in ['month', 'checked_at', 'counts', 'closed_duplicate_signals']}, ensure_ascii=False))
    print('Route ID nélküli rekordok:', len(report['unknown_route']))
    print('Nem rögzített túrák:', json.dumps([row for row in report['rows'] if row['status'] == 'Még nincs reklamáció'], ensure_ascii=False))


if __name__ == '__main__':
    main()
