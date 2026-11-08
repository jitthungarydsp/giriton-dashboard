import ast,importlib.util,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('evidence',ROOT/'resources/complaint_evidence.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class EvidenceTests(unittest.TestCase):
 def test_prefill_only_uses_affected_shift_and_its_plate(self):
  complaint=self.complaint()
  result=module.form_defaults(complaint,[{'route_id':1,'shift_name':'08:00','vehicle_plate':'OTHER'},
      {'route_id':1569692,'shift_name':'19:00'}],
      [{'route_id':1569692,'response_json':{'shift':{'vehiclePlate':'SHF512'}}}])
  self.assertEqual(result['routeId'],'1569692');self.assertEqual(result['licensePlate'],'SHF512')
 def test_explicit_route_takes_precedence_over_shift_label(self):
  complaint=self.complaint();complaint['affected_items'][0]['routeId']='2'
  result=module.form_defaults(complaint,[{'route_id':1,'shift_name':'19:00','vehicle_plate':'WRONG'},
      {'route_id':2,'shift_name':'08:00','vehicle_plate':'RIGHT'}],[])
  self.assertEqual(result['routeId'],'2');self.assertEqual(result['licensePlate'],'RIGHT')
 def test_ambiguous_plates_are_not_guessed(self):
  result=module.form_defaults(self.complaint(),[{'route_id':1,'shift_name':'19:00','vehicle_plate':'AAA123'},
      {'route_id':2,'shift_name':'19:00','vehicle_plate':'BBB123'}],[])
  self.assertEqual(result['routeId'],'1, 2');self.assertEqual(result['licensePlate'],'')
  self.assertTrue(any('Több rendszám' in text for text in result['notes']))
 def test_unmatched_shift_does_not_pick_another_tour(self):
  result=module.form_defaults(self.complaint(),[{'route_id':1,'shift_name':'08:00','vehicle_plate':'AAA123'}],[])
  self.assertEqual(result['routeId'],'');self.assertEqual(result['licensePlate'],'');self.assertTrue(result['notes'])
 def complaint(self):return {'courier_id':'7018','courier_name':'Mocsáry Attila','affected_items':[{'date':'2026-10-12','label':'19:00-23:30','giritonLoginAt':'18:30'}]}
 def test_conflicts_and_missing_raw_queue_are_visible_without_invented_event(self):
  calls=[]
  def read(table,params):
   calls.append((table,params))
   return {
    'giriton_attendance_raw':[{'checkin_start':'18:30:00'}],
    'courier_shift_overview':[{'warehouse_id':1,'raw_shift':{'evaluation':'LATE','actualStart':'2026-10-12T19:53:15'}}],
    'courier_hub_route_statistics':[{'route_id':1569692,'queue_started_at':'2026-10-12T17:53:15Z'}],
    'pwa_courier_route_quality_report':[{'route_id':1569692,'queued_on_time':True,'late_start_minutes':0}],
    'courier_route_performance_detail_raw':[{'route_id':1569692,'response_json':{'log':[{'type':'ROUTE_ASSIGNED','occurredAt':'2026-10-12T18:40:02Z'}]}}]
   }.get(table,[])
  result=module.complaint_evidence(self.complaint(),read)
  self.assertTrue(any('Eltérő' in x for x in result['warnings']))
  self.assertTrue(any('nincs külön' in x for x in result['warnings']))
  self.assertTrue(any(r['value']=='2026-10-12 20:40:02' for s in result['sections'] for r in s['rows']))
  for table,params in calls:
   if table!='giriton_attendance_raw':self.assertEqual(params['courier_id'],'eq.7018')
   self.assertEqual(params.get('work_date','eq.2026-10-12'),'eq.2026-10-12')
  self.assertEqual(calls[-1][1]['route_id'],'in.(1569692)')
 def test_failed_source_does_not_hide_other_evidence(self):
  def read(table,params):
   if table=='giriton_attendance_raw':raise TimeoutError()
   return []
  result=module.complaint_evidence(self.complaint(),read)
  self.assertTrue(any('nem olvasható' in x for x in result['warnings']))
  self.assertEqual(result['sections'][0]['title'],'A reklamációhoz mentett adatok')
 def test_multiple_days_do_not_trigger_broad_scan(self):
  row=self.complaint();row['affected_items'].append({'date':'2026-10-13'})
  result=module.complaint_evidence(row,lambda *a:self.fail('Unexpected database access'))
  self.assertFalse(result['sections']);self.assertTrue(result['warnings'])
 def test_timezone_is_explicit_including_naive_hub_time(self):
  self.assertEqual(module.display_time('2026-10-12T19:53:15'),'2026-10-12 19:53:15')
  self.assertEqual(module.display_time('2026-10-12T17:53:15Z'),'2026-10-12 19:53:15')
  self.assertEqual(module.display_time(None),'Nincs adat')
 def test_non_admin_cannot_query_evidence(self):
  node=next(n for n in ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='quality_complaint_evidence');node.decorator_list=[]
  class Denied(Exception):
   def __init__(self,status_code,detail):self.status_code=status_code
  ns={'UUID':str,'Cookie':lambda **k:None,'require_user':lambda _: {},'quality_complaint_manager':lambda _:False,'HTTPException':Denied,'supabase_rest':lambda *a,**k:self.fail('Unauthorized query')}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'endpoint','exec'),ns)
  with self.assertRaises(Denied) as error:ns['quality_complaint_evidence']('id')
  self.assertEqual(error.exception.status_code,403)
if __name__=='__main__':unittest.main()
