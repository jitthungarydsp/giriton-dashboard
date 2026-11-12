import ast,json,importlib.util,re,unicodedata
from pathlib import Path
from datetime import date
from collections import Counter
from supabase import create_client
BASE=Path(__file__).parent;ROOT=BASE.parents[1]
s=importlib.util.spec_from_file_location('worker',ROOT/'scripts/run_quality_form_worker.py');w=importlib.util.module_from_spec(s);s.loader.exec_module(w);g=w.settings()
db=create_client(str(g('SUPABASE_URL')),str(g('SUPABASE_SERVICE_ROLE_KEY')))
ids=['6498','6959','6730','6206','8960','7244','7817','8863','8185','7842','8332']
master=db.table('courier_master').select('courier_id,courier_name,active').in_('courier_id',ids).execute().data
adjustments=db.schema('settlement').table('courier_settlement_adjustment').select('courier_id,source_key,adjustment_type,amount_huf,effective_date,note,is_active,deleted_at').in_('courier_id',ids).gte('effective_date','2026-10-01').lt('effective_date','2026-11-01').execute().data
snaps=db.schema('settlement').table('courier_finance_snapshot').select('id,courier_id,version,created_at').in_('courier_id',ids).eq('period_start','2026-10-01').order('version',desc=True).limit(500).execute().data
latest={}
for snap in snaps:latest.setdefault(str(snap['courier_id']),snap)
items=db.schema('settlement').table('courier_finance_snapshot_item').select('snapshot_id,item_key,amount_value,note').in_('snapshot_id',[r['id'] for r in latest.values()]).in_('item_key',['bonus_malus','correction_income','correction_deduction','payable']).execute().data
tree=ast.parse((ROOT/'scripts/import_google_bonus_malus_adjustments.py').read_text(encoding='utf-8'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'normalize_text','slug','source_key','adjustment_types_for_row'}]
ns={'re':re,'unicodedata':unicodedata,'SOURCE_PREFIX':'google_bonus_malus'}
future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
exec(compile(ast.fix_missing_locations(ast.Module(body=[future,*nodes],type_ignores=[])),'importer.py','exec'),ns)
sheet=json.loads((BASE/'check_bonus_sheet.json').read_text(encoding='utf-8'))
def identity(v):return ' '.join(re.sub(r'\d+',' ',ns['normalize_text'](v)).split())
results=[]
for cid in ids:
 m=next(r for r in master if str(r['courier_id'])==cid)
 matching=[]
 for source in sheet:
  vals=source['values'];embedded=re.findall(r'(?<!\d)\d{3,10}(?!\d)',vals[1])
  if cid in embedded or identity(vals[1])==identity(m['courier_name']):matching.append(source)
 expected=[]
 for r in matching:
  v=r['values']
  for kind,amount in ns['adjustment_types_for_row'](v[2],int(v[4]or 0),int(v[5]or 0)):
   payload={'row_number':r['row'],'transaction_id':v[7],'courier_name':v[1],'effective_date':date.fromisoformat(r['day']),'adjustment_type':kind,'amount_huf':amount}
   expected.append({**payload,'source_key':ns['source_key']('1G58HK2dyefsIOOBEZIlI9gDuAiFCe4zKHNgPYg3OiXM',629006360,payload)})
 actual=[r for r in adjustments if str(r['courier_id'])==cid and r.get('source_key','').startswith('google_bonus_malus:') and r['is_active'] and not r['deleted_at']]
 keys={r['source_key'] for r in actual};expkeys={r['source_key'] for r in expected}
 missing=[{'row':r['row_number'],'type':r['adjustment_type'],'amount':r['amount_huf']} for r in expected if r['source_key'] not in keys]
 extra=[r for r in actual if r['source_key'] not in expkeys]
 sums=Counter()
 for r in actual:sums[r['adjustment_type']]+=int(r['amount_huf'])
 snap=latest.get(cid);snapitems=[r for r in items if snap and r['snapshot_id']==snap['id']]
 amounts={r['item_key']:r['amount_value'] for r in snapitems}
 results.append({'id':cid,'name':m['courier_name'],'source_rows':len(expected),'db_rows':len(actual),
   'missing':missing,'extra_rows':len(extra),'db_sums':dict(sums),'db_bonus_malus':sums['bonus']-sums['malus'],
   'snapshot':snap,'snapshot_amounts':amounts,'snapshot_bonus_malus_matches':amounts.get('bonus_malus')==sums['bonus']-sums['malus']})
(BASE/'bonus_update_audit.json').write_text(json.dumps(results,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps(results,ensure_ascii=True,default=str))
