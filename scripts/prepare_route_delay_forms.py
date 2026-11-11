"""Create one reviewable Google Form draft per route in a category workbook.

Creates local files and prefill links only. Never submits a form or modifies DB.
"""
import argparse
from collections import Counter
from datetime import date, datetime
import html
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('route_delay_form', ROOT / 'resources/quality_form_forwarding.py')
form = importlib.util.module_from_spec(spec)
spec.loader.exec_module(form)

REQUIRED = ['Dátum', 'Futár ID', 'Futár', 'Raktár', 'Túra ID', 'Javasolt kategória száma',
            'Kategóriajavaslat', 'Besorolás megbízhatósága', 'Adat / megfontolás']


def text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def prepare_row(row, source_row):
    raw_date = row.get('Dátum')
    day = raw_date.date() if isinstance(raw_date, datetime) else raw_date
    if not isinstance(day, date):
        day = date.fromisoformat(text(day))
    courier_id, name, route_id = (text(row.get(key)) for key in ['Futár ID', 'Futár', 'Túra ID'])
    if not all([courier_id, name, route_id]):
        raise ValueError(f'Hiányos futár/túra adat a {source_row}. sorban.')
    category = int(row['Javasolt kategória száma'])
    if category not in range(1, 9):
        raise ValueError(f'Érvénytelen kategória a {source_row}. sorban.')
    proposal = text(row.get('Kategóriajavaslat'))
    final_reason = text(row.get('Reklamáció indoklása'))
    agreed = text(row.get('Kategória futárral egyeztetve'))
    agreement_confirmed = agreed.casefold() in {'igen', 'i', 'yes', 'true', '1'}
    match = text(row.get('Forrásegyezés'))
    checked = text(row.get('Forráseltérés ellenőrizve')).casefold() in {'igen', 'i', 'yes', 'true', '1'}
    warnings = []
    if not agreement_confirmed:
        warnings.append('Kategória futárral még nincs igazoltan egyeztetve')
    if not final_reason:
        warnings.append('Végleges reklamációindoklás hiányzik')
    if match == 'Eltérés' and not checked:
        warnings.append('Forráseltérés ellenőrizendő')
    lines = ['ELLENŐRZENDŐ ŰRLAPTERVEZET – beküldés előtt ellenőrizendő.',
             f"Raktár: {text(row.get('Raktár'))}", f'Túra: {route_id}',
             f'Kategóriajavaslat: {category}. {proposal}',
             f"A besorolás alapja: {text(row.get('Besorolás megbízhatósága'))}",
             '', f"Forrásadat / megfontolás: {text(row.get('Adat / megfontolás'))}"]
    if final_reason:
        lines.extend(['', 'Rögzített reklamációindoklás:', final_reason])
    if match:
        lines.append(f'Összesítő és részletforrás egyezése: {match}')
    if warnings:
        lines.extend(['', 'Beküldés előtti ellenőrzések:', *warnings])
    identity = f'route-delay-{day.isoformat()}-{courier_id}-{route_id}'
    complaint = dict(id=identity, courier_id=courier_id, courier_name=name,
                     message='\n'.join(lines), affected_items=[dict(date=day.isoformat(), routeId=route_id)])
    payload = form.build_payload(complaint, category='Túra alatti késés', route_id=route_id)
    payload['description'] = payload['description'].removesuffix('\n · ')
    fields = {'usp': 'pp_url', 'entry.493012323': 'Just in Time Kft.',
              'entry.608543996': 'Túra alatti késés / Route delay',
              'entry.1629541155': courier_id, 'entry.139333198': name,
              'entry.584723978': route_id, 'entry.1757898114': payload['description']}
    return dict(source_row=source_row, date=day.isoformat(), courier_id=courier_id,
                courier_name=name, route_id=route_id, warehouse=text(row.get('Raktár')),
                suggested_category=category, category_label=proposal, warnings=warnings,
                state='draft', payload=payload, prefill_url=form.FORM_URL + '?' + urlencode(fields))


def prepare_workbook(path):
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook['Reklamációs túrák']
        rows = sheet.iter_rows(values_only=True)
        headers = [text(v) for v in next(rows)]
        missing = set(REQUIRED) - set(headers)
        if missing:
            raise ValueError('Hiányzó oszlopok: ' + ', '.join(sorted(missing)))
        drafts, seen = [], set()
        for number, values in enumerate(rows, 2):
            if not any(v is not None for v in values):
                continue
            row = dict(zip(headers, values))
            draft = prepare_row(row, number)
            key = (draft['date'], draft['courier_id'], draft['route_id'])
            if key in seen:
                raise ValueError(f'Ismételt futár/nap/túra a {number}. sorban; nincs automatikus duplázás.')
            seen.add(key)
            drafts.append(draft)
        return drafts
    finally:
        workbook.close()


def write_review(drafts, output, source_name):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'urlaptervezetek.json').write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding='utf-8')
    esc = lambda v: html.escape(str(v), quote=True)
    rows = []
    for draft in drafts:
        cells = [str(draft['source_row']), draft['date'], draft['courier_name'], draft['courier_id'],
                 draft['route_id'], str(draft['suggested_category'])+'. '+draft['category_label'],
                 '; '.join(draft['warnings']) or 'Ellenőrzésre előkészítve']
        rows.append('<tr>' + ''.join('<td>'+esc(c)+'</td>' for c in cells) +
                    '<td><a target="_blank" rel="noopener noreferrer" href="'+esc(draft['prefill_url'])+'">Űrlap előkitöltése</a></td></tr>')
    page = '''<!doctype html><html lang="hu"><meta charset="utf-8"><title>Októberi űrlaptervezetek</title>
<style>body{font:15px Arial,sans-serif;margin:28px;color:#243244}h1{font-size:25px}input{padding:12px;width:420px;max-width:90%}table{border-collapse:collapse;width:100%;margin-top:20px}th{background:#274660;color:white;position:sticky;top:0}th,td{text-align:left;padding:12px;border-bottom:1px solid #dbe2ea}td{vertical-align:top}tr:nth-child(even){background:#f4f7fa}a{color:#1753a0}small{color:#546477}</style>
<h1>Októberi űrlaptervezetek</h1><p>COUNT túra, túránként külön előkitöltött Google-űrlap. Beküldés nem történt.</p>
<p>Az „Űrlap előkitöltése” link után ellenőrizd a Google-fiókot, majd a partner és a „Túra alatti késés” választást.
A Következő gomb után látható a futár, a túraszám és a leírás. A Küldés gombot csak a végleges ellenőrzés után használd.
Az azonos űrlap nyitott lapjai közös Google-piszkozatot használhatnak: egyszerre egy ügyet kezelj, és minden megnyitáskor ellenőrizd a túraszámot.</p>
<p><small>Forrás: SOURCE. A kategóriák javaslatok; a hiányzó egyeztetés és forráseltérés a leírásban is szerepel.</small></p>
<label>Keresés futárra, dátumra vagy túraszámra: <input id="search" type="search"></label>
<table><thead><tr><th>Excel-sor</th><th>Dátum</th><th>Futár</th><th>ID</th><th>Túra</th><th>Javaslat</th><th>Ellenőrzés</th><th>Űrlap</th></tr></thead><tbody>ROWS</tbody></table>
<script>document.getElementById('search').addEventListener('input',function(){const s=this.value.toLocaleLowerCase('hu');for(const row of document.querySelectorAll('tbody tr'))row.hidden=!row.textContent.toLocaleLowerCase('hu').includes(s)});</script></html>'''
    page = page.replace('COUNT', str(len(drafts))).replace('SOURCE', esc(source_name)).replace('ROWS', '\n'.join(rows))
    (output / 'urlapok.html').write_text(page, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    drafts = prepare_workbook(args.workbook)
    write_review(drafts, args.output, args.workbook.name)
    print(json.dumps(dict(drafts=len(drafts), categories=dict(Counter(d['suggested_category'] for d in drafts)),
                         need_review=sum(bool(d['warnings']) for d in drafts), output=str(args.output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
