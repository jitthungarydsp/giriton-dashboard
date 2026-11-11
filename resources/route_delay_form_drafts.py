"""Excel complaint drafts and explicit, evidence-backed submission tracking."""
from datetime import date, datetime, timezone
from io import BytesIO
import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

spec = importlib.util.spec_from_file_location('route_delay_excel_preparation', Path(__file__).resolve().parents[1]/'scripts/prepare_route_delay_forms.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)

TABLE = 'route_delay_form_draft'
STATES = {'draft':'Tervezet', 'prepared':'Ellenőrzött', 'sent':'Beküldve'}
CATEGORY_LABELS = {1:'Vásárló feltartotta',2:'Tételes átadás történt',3:'Fizetési probléma (eszköz, térerő)',
                   4:'Optimalizálatlan túra: 3 külön cím / 15 perc',5:'Sok csomag: 4+ vízcsomag / rendelés',
                   6:'Elromlott lift',7:'Magas táskaszám: 15+ / egész túra',8:'Ügyfélszolgálati kérés, ügyintézés'}


def normalize_data(row):
    result = {str(k): (v.date().isoformat() if k=='Dátum' and isinstance(v,datetime)
                      else v.isoformat()) if isinstance(v, (date, datetime)) else v for k,v in row.items()}
    # The generated editable workbook uses shorter presentation headers.
    if 'Kategória száma' in result:
        result['Javasolt kategória száma'] = result['Kategória száma']
    if 'Végleges indoklás' in result:
        result['Reklamáció indoklása'] = result['Végleges indoklás']
    return result


def content_hash(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def make_record(data, source_row, source_filename='', actor=''):
    data = normalize_data(data)
    draft = preparation.prepare_row(data, source_row)
    identity = f"jitt-route-delay:{draft['date']}:{draft['courier_id']}:{draft['route_id']}"
    return dict(id=str(uuid5(NAMESPACE_URL, identity)), work_date=draft['date'],
                courier_id=draft['courier_id'], courier_name=draft['courier_name'], route_id=draft['route_id'],
                source_filename=Path(source_filename).name, source_row=int(source_row), data=data,
                content_hash=content_hash(data), state='draft', confirmation='', submitted_at=None,
                updated_by=actor, updated_at=datetime.now(timezone.utc).isoformat())


def read_excel(content, source_filename='', actor=''):
    import openpyxl
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        name = next((n for n in ['Reklamációs túrák', 'Űrlapok'] if n in book.sheetnames), None)
        if not name:
            raise ValueError('Reklamációs túrák vagy Űrlapok munkalap szükséges.')
        iterator = enumerate(book[name].iter_rows(values_only=True), 1)
        for _, values in iterator:
            headers = [preparation.text(v) for v in values]
            if {'Dátum','Futár ID','Futár','Túra ID'}.issubset(headers):
                break
        else:
            raise ValueError('Nem található a reklamációs táblázat fejléce.')
        result, seen = [], set()
        for number, values in iterator:
            if not any(v is not None for v in values):
                continue
            row = dict(zip(headers, values))
            source_row = int(row.get('Forrássor') or number)
            try:
                record = make_record(row, source_row, source_filename, actor)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'{number}. Excel-sor: {exc}') from exc
            if record['id'] in seen:
                raise ValueError(f'{number}. Excel-sor: ismételt futár/nap/túra.')
            seen.add(record['id'])
            result.append(record)
        return result
    finally:
        book.close()


def merge_import(current, incoming, overwrite=False):
    result = {r['id']: dict(r) for r in current}
    counts = dict(added=0, updated=0, skipped=0)
    for row in incoming:
        old = result.get(row['id'])
        if old and (old['state']=='sent' or not overwrite or old['content_hash']==row['content_hash']):
            counts['skipped'] += 1
            continue
        result[row['id']] = row
        counts['updated' if old else 'added'] += 1
    return list(result.values()), counts


def read_backup(content, actor=''):
    saved = json.loads(content)
    if not isinstance(saved,list):
        raise ValueError('Érvénytelen munkapéldány.')
    result = []
    for original in saved:
        row = make_record(original['data'],original['source_row'],original.get('source_filename',''),actor)
        row['id'] = str(UUID(original['id']))
        state = original.get('state','draft')
        if state not in STATES or row['content_hash']!=original.get('content_hash'):
            raise ValueError('A munkapéldány adatai vagy állapota módosult; nem tölthető vissza ellenőrzöttként.')
        if state in {'prepared','sent'}:
            row = prepare_record(row,actor)
        if state=='sent':
            row = confirm_record(row,original.get('confirmation',''),actor,True)
            submitted = original.get('submitted_at')
            if not submitted:
                raise ValueError('A beküldött tétel visszaigazolási időpontja hiányzik.')
            datetime.fromisoformat(submitted)
            row['submitted_at'] = submitted
        result.append(row)
    if len({r['id']for r in result})!=len(result):
        raise ValueError('Ismételt tétel a munkapéldányban.')
    assert_unique(result)
    return result


def edit_record(record, data, actor):
    if record['state']=='sent':
        raise ValueError('Igazoltan beküldött tétel nem írható felül.')
    replacement = make_record(data, record['source_row'], record.get('source_filename',''), actor)
    replacement['id'] = record['id']
    if replacement['content_hash']==record['content_hash']:
        return dict(record)
    return replacement


def prepare_record(record, actor):
    if record['state']=='sent':
        raise ValueError('Ez a reklamáció már beküldöttként szerepel.')
    draft = preparation.prepare_row(record['data'], record['source_row'])
    if draft['warnings']:
        raise ValueError('; '.join(draft['warnings']))
    return {**record,'state':'prepared','updated_by':actor,'updated_at':datetime.now(timezone.utc).isoformat()}


def confirm_record(record, confirmation, actor, acknowledged):
    if record['state']!='prepared':
        raise ValueError('Előbb mentsd és ellenőrizd az űrlap adatait.')
    if not acknowledged or len(confirmation.strip())<5:
        raise ValueError('Google-visszaigazolás és bizonyítékhivatkozás vagy azonosítható visszaigazolási megjegyzés szükséges.')
    return {**record,'state':'sent','confirmation':confirmation.strip(),
            'submitted_at':datetime.now(timezone.utc).isoformat(),'updated_by':actor,
            'updated_at':datetime.now(timezone.utc).isoformat()}


def load_records(db):
    rows, offset = [], 0
    while True:
        page = (db.schema('settlement').table(TABLE).select('*').order('work_date').order('id')
                .range(offset, offset+999).execute().data or [])
        rows.extend(page)
        if len(page)<1000:
            return rows
        offset += len(page)


def store_records(db, records):
    """Import new rows without overwriting concurrent edits or confirmations."""
    if records:
        db.schema('settlement').table(TABLE).upsert(records, on_conflict='id', ignore_duplicates=True).execute()


def store_edit(db, previous, replacement):
    # Compare-and-swap prevents another admin's submission/edit being overwritten.
    result = (db.schema('settlement').table(TABLE).update(replacement).eq('id',previous['id'])
              .eq('content_hash',previous['content_hash']).eq('state',previous['state'])
              .eq('updated_at',previous['updated_at']).execute().data or [])
    if not result:
        raise ValueError('A tételt közben más módosította. Töltsd újra a listát.')


def assert_unique(records):
    identities = [(r['work_date'], r['courier_id'], r['route_id']) for r in records]
    if len(identities)!=len(set(identities)):
        raise ValueError('A módosítás másik meglévő futár/nap/túra tétellel ütközik.')
