import importlib.util,json
from pathlib import Path
from supabase import create_client
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('worker',ROOT/'scripts/run_quality_form_worker.py');w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
g=w.settings();db=create_client(str(g('SUPABASE_URL')),str(g('SUPABASE_SERVICE_ROLE_KEY')))
try:
 for label,query in [('detail',db.table('courier_route_performance_detail_raw').select('response_json').eq('year',2026).eq('month',10).eq('status_code',200).limit(1)),('shift',db.table('courier_shift_overview').select('*').gte('work_date','2026-10-01').lt('work_date','2026-11-01').limit(1))]:
  rows=query.execute().data
  print(label,'keys',list(rows[0]) if rows else [])
  if label=='detail' and rows:
   p=rows[0]['response_json'];print('payload keys',list(p));print('shift',json.dumps(p.get('shift'),ensure_ascii=True))
   for k,v in p.items():
    if isinstance(v,list) and k!='stops':print(k,'sample',json.dumps(v[:1],ensure_ascii=True))
except Exception as e:
 print(type(e).__name__)
 if hasattr(e,'message'):print(e.message)
