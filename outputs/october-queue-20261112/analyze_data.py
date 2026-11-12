import json,re,unicodedata
from collections import defaultdict,Counter
from datetime import datetime,date,time
from zoneinfo import ZoneInfo
from pathlib import Path
BASE=Path(__file__).parent;data=json.loads((BASE/'raw.json').read_text(encoding='utf-8'));TZ=ZoneInfo('Europe/Budapest')
def stamp(value):
 if not value:return None
 dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
def namekey(value):
 text=''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c))
 return ' '.join(re.sub(r'(?<!\d)\d{3,10}(?!\d)',' ',text).split())
attendance=defaultdict(list)
attendance_ids=defaultdict(list)
for a in data['attendance']:
 attendance[(a['work_date'],namekey(a['courier_name']))].append(a)
 for cid in re.findall(r'(?<!\d)\d{3,10}(?!\d)',str(a['courier_name'])):
  attendance_ids[(a['work_date'],cid)].append(a)
stats={(str(r['courier_id']),str(r['route_id']),int(r['warehouse_code'].replace('BUD',''))):r for r in data['routes']}
names=defaultdict(set)
for r in data['routes']:names[namekey(r['courier_name'])].add(str(r['courier_id']))
rows=[]
for d in data['details']:
 key=(str(d['courier_id']),str(d['route_id']),d['warehouse_id'])
 s=stats.get(key,{})
 shift=d.get('shift')or{}
 planned=stamp(shift.get('plannedStartAt'))
 if not planned or planned.year!=2026 or planned.month!=10:continue
 actual=stamp(s.get('actual_shift_start_at'))
 # Use only explicit availability log events, never synthesized queue values.
 assigned=sorted({stamp(e.get('occurredAt')) for e in d.get('log')or[] if e.get('type')=='ROUTE_ASSIGNED' and e.get('occurredAt')})
 available=sorted({stamp(e.get('occurredAt')) for e in d.get('log')or[] if e.get('type')=='SHIFT_AVAILABLE' and e.get('occurredAt')})
 notes=[]
 if len(assigned)!=1:
  queue=None;notes.append('Nem egyértelmű túrakiosztás')
 else:
  preceding=[v for v in available if v<=assigned[0] and v.date()==planned.date()]
  queue=preceding[-1] if preceding else None
  if not queue:notes.append('Nincs túrakiosztás előtti SHIFT_AVAILABLE esemény')
 if not actual:notes.append('Hiányzó tényleges műszakkezdés')
 day=planned.date().isoformat();name=s.get('courier_name')or''
 matches=attendance_ids.get((day,str(d['courier_id'])),[])
 match_source='Futár ID és dátum'
 if not matches:
  matches=attendance.get((day,namekey(name)),[])
  match_source='Név és dátum'
 login=None;login_status=''
 if match_source=='Név és dátum' and len(names[namekey(name)])>1:login_status='Több futárhoz tartozó név; Giriton-egyeztetés szükséges'
 elif len(matches)>1:login_status='Több Giriton-sor; egyeztetés szükséges'
 elif len(matches)==1:
  a=matches[0]
  value=a.get('checkin_start')
  if value:
   login=datetime.combine(date.fromisoformat(day),time.fromisoformat(value),tzinfo=TZ)
   login_status=match_source+' alapján egyeztetve'
  else:login_status='Giriton-bejelentkezés nincs rögzítve'
 else:login_status='Nincs név és dátum szerint egyező Giriton-sor'
 delta=(queue-actual).total_seconds()/60 if queue and actual else None
 rows.append({'date':day,'courier_id':str(d['courier_id']),'name':' '.join(re.sub(r'(?<!\d)\d{3,10}(?!\d)',' ',name).split()),'route_id':str(d['route_id']),
  'warehouse':s.get('warehouse_code')or f"BUD{d['warehouse_id']}",'planned':planned.isoformat(),
  'actual':actual.isoformat() if actual else None,'queue':queue.isoformat() if queue else None,
  'login':login.isoformat() if login else None,'login_status':login_status,'delta_minutes':delta,
  'queue_vs_planned':(queue-planned).total_seconds()/60 if queue else None,
  'notes':'; '.join(notes),'assigned':assigned[0].isoformat() if len(assigned)==1 else None})
assert len(rows)==len({(r['date'],r['courier_id'],r['route_id'],r['warehouse']) for r in rows})
late=[r for r in rows if r['delta_minutes'] is not None and r['delta_minutes']>0]
unknown=[r for r in rows if r['delta_minutes'] is None]
late.sort(key=lambda r:(r['date'],r['name'],r['queue'],r['route_id']))
unknown.sort(key=lambda r:(r['date'],r['name'],r['route_id']))
summary={'total_routes':len(rows),'late_routes':len(late),'late_couriers':len({r['courier_id'] for r in late}),
 'unknown':len(unknown),'late_missing_login':sum(not r['login'] for r in late),
 'actual_equals_queue':sum(r['delta_minutes']==0 for r in rows),'actual_after_queue':sum(r['delta_minutes'] is not None and r['delta_minutes']<0 for r in rows),
 'late_vs_planned':sum(r['queue_vs_planned'] is not None and r['queue_vs_planned']>0 for r in rows),
 'days_without_routes':[f'2026-10-{i:02d}' for i in range(1,32) if f'2026-10-{i:02d}' not in {r['date'] for r in rows}],
 'unknown_reasons':dict(Counter(r['notes'] for r in unknown))}
(BASE/'analysis.json').write_text(json.dumps({'summary':summary,'late':late,'unknown':unknown,'all':rows},ensure_ascii=False),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True))
print('late samples',json.dumps(late[:3],ensure_ascii=True))
