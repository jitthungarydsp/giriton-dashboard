import sys,json,importlib.util
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from supabase import create_client
s=importlib.util.spec_from_file_location('worker',ROOT/'scripts/run_quality_form_worker.py')
w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
g=w.settings();db=create_client(str(g('SUPABASE_URL')),str(g('SUPABASE_SERVICE_ROLE_KEY')))
def fetch(table,columns,order):
    rows=[]
    for offset in range(0,50000,500):
        part=(db.table(table).select(columns).gte('work_date','2026-10-01').lt('work_date','2026-11-01')
              .order(order).range(offset,offset+499).execute().data or [])
        rows.extend(part)
        if len(part)<500: return rows
    raise ValueError('Pagination limit exceeded')
try:
    routes=fetch('courier_hub_route_statistics','work_date,courier_id,courier_name,warehouse_code,route_id,shift_name,queue_started_at,actual_shift_start_at,route_assigned_at,returned_at','route_id')
    attendance=fetch('giriton_attendance_raw','work_date,courier_name,shift_text,activity_status,checkin_start,checkin_end,updated_at','work_date,courier_name')
    shifts=fetch('courier_shift_overview','courier_id,courier_name,work_date,warehouse_id,shift_id,shift_key,shift_name,shift_start,planned_start_at,actual_start_at,raw_shift','courier_id,work_date,shift_key')
    details=[]
    for offset in range(0,50000,500):
        part=(db.table('courier_route_performance_detail_raw')
              .select('courier_id,route_id,warehouse_id,dsp_id,updated_at,shift:response_json->shift,log:response_json->log')
              .eq('year',2026).eq('month',10).eq('status_code',200)
              .order('courier_id,route_id,warehouse_id').range(offset,offset+499).execute().data or [])
        details.extend(part)
        if len(part)<500:break
    (Path(__file__).parent/'raw.json').write_text(json.dumps({'routes':routes,'attendance':attendance,'details':details,'shifts':shifts},ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'routes':len(routes),'attendance':len(attendance),'details':len(details),'shifts':len(shifts),'route_days':len({r['work_date'] for r in routes}),
      'queue_populated':sum(bool(r['queue_started_at']) for r in routes),'shift_populated':sum(bool(r['actual_shift_start_at']) for r in routes),
      'sample':[{k:r.get(k) for k in ['work_date','actual_shift_start_at','queue_started_at']} for r in routes[:2]],
      'attendance_sample':[{k:r.get(k) for k in ['work_date','checkin_start','checkin_end','shift_text']} for r in attendance[:2]]},ensure_ascii=True))
except Exception as exc:
    print('READ FAILED:',type(exc).__name__)
    if hasattr(exc,'code'): print('Code:',exc.code,'Message:',exc.message)
    raise SystemExit(1)
