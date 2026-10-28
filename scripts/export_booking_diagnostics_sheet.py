import collections
import json
import re
import argparse
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from resources.supabase_raw import get_supabase_config
from resources.google_sheets_values import replace_sheet_values_by_id, sheets_session, spreadsheet_url, raise_for_google_response
SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
WORKSHEET_GID = 1640110205


def read(table, params, schema='public'):
    url, secret = get_supabase_config()
    if not url or not secret:
        raise RuntimeError("Missing Supabase configuration")
    config = {"SUPABASE_URL": url, "SUPABASE_SERVICE_ROLE_KEY": secret}
    rows = []
    for offset in range(0, 100000, 1000):
        query = params | {'limit': '1000', 'offset': str(offset)}
        request = urllib.request.Request(config['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + table + '?' + urllib.parse.urlencode(query), headers={
            'apikey': config['SUPABASE_SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + config['SUPABASE_SERVICE_ROLE_KEY'], 'Accept-Profile': schema})
        with urllib.request.urlopen(request, timeout=30) as response:
            page = json.load(response)
        rows.extend(page)
        if len(page) < 1000:
            return rows
    raise RuntimeError('Pagination limit reached')


def clock(value):
    match = re.search(r'(\d{1,2}):(\d{2})', str(value or ''))
    return f'{int(match[1]):02}:{match[2]}' if match else ''


def stamp(value):
    if not value:
        return ''
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Europe/Budapest')).strftime('%Y-%m-%d %H:%M:%S')


def identity(row):
    return str(row.get('courier_id') or row.get('email') or '')


def key(row, shift):
    return row['work_date'], row.get('warehouse') or row.get('warehouse_code'), identity(row), clock(shift)


def build_diagnostics(start_date, end_date):
    period = {'work_date': 'gte.' + start_date.isoformat(), 'and': '(work_date.lte.' + end_date.isoformat() + ')'}
    mp = read('bookings', period | {'select': 'work_date,courier_id,courier_name,email,warehouse,shift_text,status,cancelled_at,source_row,booking_code,updated_at', 'order': 'work_date.asc,courier_id.asc,shift_text.asc'}, 'muszakpro')
    mp = [r for r in mp if not r.get('cancelled_at') and str(r.get('status') or '').lower() not in {'cancelled', 'canceled', 'deleted', 'inactive', 'torolve', 'törölve', 'torolt', 'törölt'}]
    hub = read('courier_hub_shift_bookings_raw', period | {'select': 'work_date,courier_id,courier_name,warehouse_code,slot_from,status,active,updated_at', 'active': 'eq.true', 'order': 'work_date.asc,courier_id.asc,slot_from.asc'})
    failures = read('hub_autobooking_failures', period | {'select': 'work_date,warehouse,courier_id,email,muszakpro_shift_start,reason,run_at', 'order': 'run_at.asc'})
    logs = read('ops_giriton_auto_booking_log', period | {'select': 'work_date,warehouse,courier_id,email,shift_start,status,message,created_at', 'order': 'created_at.asc'})
    failure_by_key = {}
    for row in failures:
        failure_by_key[key(row, row.get('muszakpro_shift_start'))] = row
    log_by_key = {}
    for row in logs:
        status = str(row.get('status') or '')
        if not (status in {'COURIER_ADDED', 'ALREADY_BOOKED', 'COURIER_DELETED', 'GIRITON_FAILED', 'GIRITON_COMPLETED'} or status.startswith('HUB_API_REJECTED_') or status.endswith('_ERROR')):
            continue
        log_by_key[key(row, row.get('shift_start'))] = row
    hub_by_key = {key(r, r['slot_from']): r for r in hub}
    mp_keys = {key(r, r['shift_text']) for r in mp if r.get('courier_id')}
    hub_times = collections.defaultdict(set)
    for row in hub:
        hub_times[key(row, row['slot_from'])[:3]].add(clock(row['slot_from']))


    def explain(reason, shift):
        if reason.startswith('giriton_failed:'):
            return 'A Giriton-ág hibával zárult', reason.split(':', 1)[1].strip(), 'A konkrét Giriton-hiba javítása és az aktuális foglalás ellenőrzése szükséges.'
        if 'Couriers are not on the roster of this DSP' in reason:
            return 'A futár nincs a DSP névsorában', 'A Hub HTTP 400 választ adott: a futár nincs az adott DSP névsorában.', 'A futár DSP-/raktár-hozzárendelését kell ellenőrizni a Hubban.'
        if 'already_assigned' in reason.lower():
            return 'A Hub szerint már hozzárendelve', 'A Hub ALREADY_ASSIGNED választ adott; ez nem új sikeres foglalás.', 'Hub-adatfrissítés és a meglévő hozzárendelés időpontjának ellenőrzése.'
        if 'overlap' in reason.lower():
            return 'Átfedés – Hub elutasította', 'A Hub üzleti válasza OVERLAP; a HTTP 200 nem jelent sikeres foglalást.', 'A meglévő műszakokkal való ütközést kell rendezni; ne kerüljön sikeres ROBOTLOG-ba.'
        if reason.startswith('no_free_slot'):
            match = re.search(r':(\d{2}:\d{2}):\d+$', reason)
            blocking = match[1] if match else ''
            if blocking and blocking != shift:
                return 'Napi foglalás másik műszakon elakadt', f'A napi csoport {blocking}-as műszakjára nem volt szabad hely; ez nem bizonyítja, hogy a {shift} is megtelt.', f'A {blocking}-as műszak kapacitását és a napi csoport szabályát kell ellenőrizni.'
            return 'Nincs szabad hely a futáskor', 'A robot a kiválasztott műszakhoz nem talált szabad kapacitást.', 'Kapacitás ellenőrzése ugyanarra a kezdésre; eltérő időpontot nem foglalunk.'
        if reason.startswith('min_gap_not_met'):
            return 'Műszakok túl közel vannak', 'A napi műszakkezdések között nincs meg a robot által előírt minimális időköz.', 'Az MP napi foglalásait és a minimum időköz szabályát kell egyeztetni.'
        if reason.startswith('missing_exact_hub_block'):
            return 'Nincs megfelelő Hub-műszak', 'A robot nem talált pontosan ehhez a kezdéshez Hub-blokkot.', 'Az azonos kezdésű Hub-műszakot kell ellenőrizni; nincs alternatív foglalás.'
        if reason.startswith('single_shift_day'):
            return 'Egyműszakos nap kihagyva', 'A teljes napi foglaló ág legalább két MP-műszakot vár.', 'Ellenőrizni kell, hogy az egyedi foglaló ág megpróbálta-e.'
        if reason.startswith('max_courier_days_reached'):
            return 'Futási darabkorlát', 'A robot elérte a futáronkénti napok futási limitjét.', 'Következő futás vagy a futási limit felülvizsgálata.'
        if reason:
            return 'Robot kihagyta / elutasítás', 'A nyers robotindok az erre szolgáló oszlopban olvasható.', 'A nyers indok alapján célzott ellenőrzés szükséges.'
        return 'Nincs igazolt robotindok', 'Nem találtam ehhez a futárhoz, naphoz és kezdéshez kapcsolható döntést.', 'A forrássort és az érintett robotfutás jelöltlistáját kell ellenőrizni.'


    checked = datetime.now(ZoneInfo('Europe/Budapest')).strftime('%Y-%m-%d %H:%M:%S')
    headers = ['Ellenőrizve', 'Dátum', 'Raktár', 'Futár ID', 'Futár / MP e-mail', 'MP kezdés', 'Aktív Hub-kezdések', 'Mi a probléma?', 'Bizonyított ok / korlát', 'Teendő', 'Utolsó robotdöntés ideje', 'Robot státusz', 'Nyers robotindok', 'MP forrássor', 'Foglaláskód', 'MP-adat frissítése', 'Hub-adat frissítése']
    result = []
    for row in mp:
        k = key(row, row['shift_text'])
        if row.get('courier_id') and k in hub_by_key:
            continue
        log = log_by_key.get(k) or {}
        failure = failure_by_key.get(k) or {}
        reason = failure.get('reason') or ''
        evidence_time = failure.get('run_at') or ''
        status = 'KIHAGYVA'
        if log and (not evidence_time or log['created_at'] > evidence_time):
            evidence_time = log['created_at']
            status = log['status']
            reason = log.get('message') or log['status']
        if not row.get('courier_id'):
            problem, explanation, action = 'MP-futárazonosító hiányzik', 'Az MP-sorban nincs courier ID; ebből nem állapítható meg biztosan a Hub-egyezés.', 'A futár ID / e-mail összerendelés javítása szükséges.'
        elif status == 'GIRITON_COMPLETED':
            problem, explanation, action = 'Giriton lefutott, Hub-pár még hiányzik', 'A Giriton-folyamat lefutott, de a jelenlegi Hub-adatban még nincs pontos pár.', 'A frissítési időket és a tényleges Giriton-/Hub-foglalást kell ellenőrizni.'
        elif status in {'COURIER_ADDED', 'ALREADY_BOOKED'}:
            problem, explanation, action = 'Korábbi siker, most nincs pontos pár', 'A robot korábban sikert jelzett, de a jelenlegi aktív Hub-adatban nincs pontos egyezés.', 'Utóellenőrzés: valóban létrejött-e, később törölték-e vagy változott az időpont.'
        else:
            problem, explanation, action = explain(reason, k[3])
        times = ', '.join(sorted(hub_times.get(k[:3], set()))) or 'Nincs azonosított Hub-foglalás'
        relevant_hub = [r for r in hub if key(r, r['slot_from'])[:3] == k[:3]]
        hub_updated = max((r.get('updated_at') or '' for r in relevant_hub), default='')
        result.append([checked, row['work_date'], row['warehouse'], str(row.get('courier_id') or ''), row.get('courier_name') or row.get('email') or 'Azonosítatlan', k[3], times, problem, explanation, action, stamp(evidence_time), status if evidence_time else 'Nincs kapcsolt döntés', reason, row.get('source_row') or '', row.get('booking_code') or '', stamp(row.get('updated_at')), stamp(hub_updated)])
    for row in hub:
        k = key(row, row['slot_from'])
        if k in mp_keys:
            continue
        log = log_by_key.get(k) or {}
        result.append([checked, row['work_date'], row['warehouse_code'], str(row['courier_id']), row.get('courier_name') or '', 'Nincs pontos MP-pár', k[3], 'Csak Hubon szereplő kezdés', 'A jelenlegi aktív MP-adatokban nincs azonos futár / nap / raktár / kezdés.', 'Az MP-forrást, az időpontváltozást és a kézi / robot eredetet kell ellenőrizni.', stamp(log.get('created_at')), log.get('status') or 'Nincs kapcsolt döntés', log.get('message') or '', '', '', '', stamp(row.get('updated_at'))])
    result.sort(key=lambda row: (row[1], row[2], row[4], row[5]))
    payload = {'checked_at': checked, 'headers': headers, 'rows': result, 'counts': dict(collections.Counter(r[7] for r in result))}
    return payload


def sheet_values(payload, start_date, end_date):
    width = len(payload['headers']) - 1
    def note(text):
        return [text] + [''] * (width - 1)
    values = [
        note(f"Foglalási hibák | {start_date} – {end_date}"),
        note(f"Ellenőrizve: {payload['checked_at']}"),
        note("Csak hibák. OVERLAP nem sikeres foglalás."),
        payload['headers'][1:], *[row[1:] for row in payload['rows']],
    ]
    values[1][6] = "Az ok az utolsó kapcsolt robotdöntésre vonatkozik; nem bizonyítja a jelenlegi kapacitást."
    values[2][6] = "Hiányzó futár ID: azonosítási hiba, nem bizonyított Hub-hiány. A források frissítési ideje külön látszik."
    if not payload['rows']:
        values.append(note('Nincs eltérés a vizsgált időszakban.'))
    return values


def format_requests(row_count):
    sid = WORKSHEET_GID
    grid = {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': row_count, 'startColumnIndex': 0, 'endColumnIndex': 16}
    requests = [
        {'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 4, 'frozenColumnCount': 4}}, 'fields': 'gridProperties(frozenRowCount,frozenColumnCount)'}},
        {'setBasicFilter': {'filter': {'range': grid | {'startRowIndex': 3}}}},
        {'repeatCell': {'range': grid, 'cell': {'userEnteredFormat': {'textFormat': {'fontFamily': 'Arial', 'fontSize': 10}, 'verticalAlignment': 'MIDDLE'}}, 'fields': 'userEnteredFormat'}},
        {'repeatCell': {'range': grid | {'startRowIndex': 3, 'endRowIndex': 4}, 'cell': {'userEnteredFormat': {'backgroundColor': {'red': .9, 'green': .9, 'blue': .9}, 'textFormat': {'bold': True}, 'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat(backgroundColor,textFormat.bold,wrapStrategy)'}},
        {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'ROWS', 'startIndex': 3, 'endIndex': row_count}, 'properties': {'pixelSize': 64}, 'fields': 'pixelSize'}},
    ]
    for i, width in enumerate([110, 70, 85, 200, 110, 200, 245, 350, 350, 165, 230, 330, 100, 190, 165, 165]):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i + 1}, 'properties': {'pixelSize': width}, 'fields': 'pixelSize'}})
    if row_count > 4:
        requests.append({'repeatCell': {'range': grid | {'startRowIndex': 4}, 'cell': {'userEnteredFormat': {'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat.wrapStrategy'}})
        for column, kind, pattern in [(0, 'DATE', 'yyyy-mm-dd'), (4, 'TIME', 'hh:mm'), (9, 'DATE_TIME', 'yyyy-mm-dd hh:mm:ss'), (14, 'DATE_TIME', 'yyyy-mm-dd hh:mm:ss'), (15, 'DATE_TIME', 'yyyy-mm-dd hh:mm:ss')]:
            requests.append({'repeatCell': {'range': grid | {'startRowIndex': 4, 'startColumnIndex': column, 'endColumnIndex': column + 1}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': kind, 'pattern': pattern}}}, 'fields': 'userEnteredFormat.numberFormat'}})
    return requests


def main():
    parser = argparse.ArgumentParser(description="MűszakPro–Hub eltérések konkrét robotindokokkal.")
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start_date).date()
    end = datetime.fromisoformat(args.end_date).date()
    if end < start:
        raise ValueError('End date precedes start date')
    payload = build_diagnostics(start, end)
    if not args.dry_run:
        values = sheet_values(payload, start, end)
        replace_sheet_values_by_id(SPREADSHEET_ID, WORKSHEET_GID, values)
        response = sheets_session().post(spreadsheet_url(SPREADSHEET_ID, ':batchUpdate'), json={'requests': format_requests(len(values))}, timeout=60)
        raise_for_google_response(response, 'Booking diagnostics formatting')
    print(json.dumps({'rows': len(payload['rows']), 'counts': payload['counts'], 'dry_run': args.dry_run}, ensure_ascii=False))


if __name__ == '__main__':
    main()
