import json,re,unicodedata
from collections import defaultdict,Counter
from datetime import datetime,date,time
from zoneinfo import ZoneInfo
from pathlib import Path
BASE=Path(__file__).parent;data=json.loads((BASE/'raw.json').read_text(encoding='utf-8'));TZ=ZoneInfo('Europe/Budapest')
# Use the latest complete monthly Hub response; the flattened table retains
# obsolete index-based shift rows when a month's ordering changes.
monthly=json.loads((BASE/'hub_raw_shifts.json').read_text(encoding='utf-8'))
name_lookup={str(s['courier_id']):s['courier_name'] for s in data['shifts'] if s.get('courier_name')}
name_lookup.update({str(r['courier_id']):r['courier_name'] for r in data['routes'] if r.get('courier_name')})
source_shifts=[]
for record in monthly:
 for i,raw in enumerate(record['response_json'].get('shifts')or[]):
  if str(raw.get('date')or'')[:7]!='2026-10':continue
  source_shifts.append({'courier_id':record['courier_id'],'courier_name':name_lookup.get(str(record['courier_id']),''),
   'work_date':str(raw['date'])[:10],'warehouse_id':record['warehouse_id'],'shift_key':f"{record['courier_id']}:{record['warehouse_id']}:{i}",
   'raw_shift':raw})
data['shifts']=source_shifts
def stamp(value):
 if not value:return None
 dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
def namekey(value):
 text=''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c))
 return ' '.join(re.sub(r'(?<!\d)\d{3,10}(?!\d)',' ',text).split())
def cleanname(value):return ' '.join(re.sub(r'(?<!\d)\d{3,10}(?!\d)',' ',str(value or '')).split())
att_id=defaultdict(list);att_name=defaultdict(list);name_ids=defaultdict(set)
for a in data['attendance']:
 att_name[(a['work_date'],namekey(a['courier_name']))].append(a)
 for cid in re.findall(r'(?<!\d)\d{3,10}(?!\d)',str(a['courier_name'])):att_id[(a['work_date'],cid)].append(a)
for s in data['shifts']:name_ids[namekey(s['courier_name'])].add(str(s['courier_id']))
def login_for(day,cid,name):
 matches=att_id.get((day,cid),[]);source='ID és dátum'
 if not matches:
  matches=att_name.get((day,namekey(name)),[]);source='név és dátum'
  if len(name_ids[namekey(name)])>1:return None,'Nem egyértelmű névegyezés'
 if len(matches)!=1:return None,'Nincs egyértelmű Giriton-sor'
 value=matches[0].get('checkin_start')
 if not value:return None,'A Giriton-belépés nincs rögzítve'
 return datetime.combine(date.fromisoformat(day),time.fromisoformat(value),tzinfo=TZ),'Giriton-egyeztetés: '+source
grouped=defaultdict(list);missing_plan=[]
for s in data['shifts']:
 raw=s.get('raw_shift')or{};planned=raw.get('plannedStart') or raw.get('plannedStartAt') or s.get('planned_start_at') or s.get('shift_start')
 if planned and re.fullmatch(r'\d{2}:\d{2}(:\d{2})?',planned):planned=s['work_date']+'T'+planned
 parsed=stamp(planned)
 if not parsed:missing_plan.append(s);continue
 grouped[(s['work_date'],str(s['courier_id']))].append((parsed,s))
route_map=defaultdict(list)
for d in data['details']:
 planned=stamp((d.get('shift')or{}).get('plannedStartAt'))
 if planned:route_map[(planned.date().isoformat(),str(d['courier_id']),d['warehouse_id'],planned)].append(d)
first=[];ties=[]
for (day,cid),items in grouped.items():
 earliest=min(p for p,s in items);candidates=[s for p,s in items if p==earliest]
 if len(candidates)!=1:
  ties.append({'date':day,'courier_id':cid,'notes':'Több műszaksor azonos első kezdési idővel'});continue
 s=candidates[0];raw=s.get('raw_shift')or{};evaluation=raw.get('evaluation') or s.get('evaluation') or 'NINCS ÉRTÉKELÉS'
 actual=stamp(raw.get('actualStart') or raw.get('actualStartAt') or s.get('actual_start_at'))
 login,login_note=login_for(day,cid,s['courier_name'])
 linked=route_map.get((day,cid,s['warehouse_id'],earliest),[])
 route_match='Tervezett műszakkezdés egyezik'
 if not linked and actual:
  # A source route can have a different planned start, but the independently
  # stored actual shift start identifies the same shift without time guessing.
  stat_ids={str(r['route_id']) for r in data['routes'] if str(r['courier_id'])==cid
            and r['work_date']==day and r['warehouse_code']=='BUD'+str(s['warehouse_id'])
            and stamp(r.get('actual_shift_start_at'))==actual}
  linked=[d for d in data['details'] if str(d['courier_id'])==cid and d['warehouse_id']==s['warehouse_id'] and str(d['route_id']) in stat_ids]
  route_match='Tényleges műszakkezdés egyezik; eltérő route-terv'
 def assigned(d):
  return min([stamp(e['occurredAt']) for e in d.get('log')or[] if e.get('type')=='ROUTE_ASSIGNED' and e.get('occurredAt')],default=earliest.replace(hour=23,minute=59,second=59))
 linked=sorted(linked,key=lambda d:(assigned(d),str(d['route_id'])))
 route=linked[0] if linked else None
 queue=None;notes=[]
 if route:
  cutoff=assigned(route)
  events=[stamp(e['occurredAt']) for e in route.get('log')or[] if e.get('type')=='SHIFT_AVAILABLE' and e.get('occurredAt')]
  events=[v for v in events if v<=cutoff and v.date().isoformat()==day]
  queue=max(events,default=None)
  if not queue:notes.append('Nincs kiosztás előtti SHIFT_AVAILABLE esemény')
 else:notes.append('A műszakhoz nincs egyező Route ID a túraforrásban')
 first.append({'date':day,'courier_id':cid,'name':cleanname(s['courier_name']),'warehouse':'BUD'+str(s['warehouse_id']),
  'route_id':str(route['route_id']) if route else None,'other_routes':', '.join(str(d['route_id']) for d in linked[1:]),
  'planned':earliest.isoformat(),'actual':actual.isoformat() if actual else None,
  'queue':queue.isoformat() if queue else None,'login':login.isoformat() if login else None,
  'evaluation':evaluation,'login_note':login_note,'notes':'; '.join(notes),'route_match':route_match if linked else 'Nincs egyező túra',
  'delay_minutes':(actual-earliest).total_seconds()/60 if actual else None,'shift_key':s['shift_key']})
first.sort(key=lambda r:(r['date'],r['name'],r['courier_id']))
late=[r for r in first if r['evaluation']=='LATE']
summary={'period':'2026-10','first_shifts':len(first),'first_shift_statuses':dict(Counter(r['evaluation'] for r in first)),
 'late_first_shifts':len(late),'late_couriers':len({r['courier_id'] for r in late}),
 'late_missing_login':sum(not r['login'] for r in late),'late_missing_route':sum(not r['route_id'] for r in late),
 'late_missing_queue':sum(not r['queue'] for r in late),'same_start_ties':len(ties),'missing_planned_start':len(missing_plan),
 'total_late_all_shifts':sum((s.get('raw_shift')or{}).get('evaluation')=='LATE' for s in data['shifts']),
 'hub_monthly_late_count':sum((r['response_json'].get('lateLoginShifts')or 0) for r in monthly),
 'hub_snapshot_min':min(r['fetched_at'] for r in monthly),'hub_snapshot_max':max(r['fetched_at'] for r in monthly)}
print('Ordering diagnostics',json.dumps({'summary':summary,'ties':ties[:8],'missing':[{'date':s['work_date'],'id':s['courier_id'],'raw':s.get('raw_shift')} for s in missing_plan[:3]]},ensure_ascii=True))
assert not ties and not missing_plan,'Unresolved first-shift ordering'
assert len(first)==len({(r['date'],r['courier_id']) for r in first})
summary['late_nonpositive_or_missing_delta']=sum(r['delay_minutes'] is None or r['delay_minutes']<=0 for r in late)
reconcile=[]
for record in monthly:
 p=record['response_json'];count=sum(s.get('evaluation')=='LATE' for s in p.get('shifts')or[])
 if count!=p.get('lateLoginShifts'):
  reconcile.append({'courier_id':str(record['courier_id']),'name':cleanname(name_lookup.get(str(record['courier_id']),'')),
   'warehouse':'BUD'+str(record['warehouse_id']),'monthly_late':p.get('lateLoginShifts'),'daily_late':count,
   'notes':'A Hub havi lateLoginShifts értéke eltér a napi LATE soroktól; az eltéréshez nincs azonosítható dátum és Route ID.'})
(BASE/'first_shift_analysis.json').write_text(json.dumps({'summary':summary,'late':late,'first':first,'reconcile':reconcile},ensure_ascii=False),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True))
print('Sample',json.dumps(late[:2],ensure_ascii=True))
