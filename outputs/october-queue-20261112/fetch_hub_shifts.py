import json,importlib.util
from pathlib import Path
from supabase import create_client
BASE=Path(__file__).parent;ROOT=BASE.parents[1]
s=importlib.util.spec_from_file_location('worker',ROOT/'scripts/run_quality_form_worker.py');w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
g=w.settings();db=create_client(str(g('SUPABASE_URL')),str(g('SUPABASE_SERVICE_ROLE_KEY')))
rows=[]
try:
 for offset in range(0,10000,500):
  part=(db.table('courier_shift_overview_raw').select('courier_id,warehouse_id,dsp_id,response_json,status_code,fetched_at,updated_at')
        .eq('year',2026).eq('month',10).eq('dsp_id',8).eq('status_code',200)
        .order('courier_id,warehouse_id').range(offset,offset+499).execute().data or [])
  rows.extend(part)
  if len(part)<500:break
 (BASE/'hub_raw_shifts.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
 print('Raw monthly shift responses:',len(rows))
 p=rows[0]['response_json']
 print('payload shape',type(p).__name__,'keys',list(p) if isinstance(p,dict) else 'list')
 print('snapshot range',min(r['fetched_at'] for r in rows),max(r['fetched_at'] for r in rows))
except Exception as e:
 print(type(e).__name__)
 if hasattr(e,'message'):print(e.message)
 raise SystemExit(1)
