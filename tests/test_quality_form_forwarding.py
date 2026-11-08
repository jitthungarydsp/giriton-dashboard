import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
forward=load('forward','resources/quality_form_forwarding.py')
worker=load('worker','scripts/run_quality_form_worker.py')


class PayloadTest(unittest.TestCase):
 def complaint(self):
  return dict(id='abc',courier_id='7644',courier_name='Futár',topic='uncleanedTimeWindowLate',message='Indoklás',
   affected_items=[dict(date='2026-10-31',routeId='1590606',label='Route 1590606',note='4 cím')])
 def test_all_category_specific_required_fields(self):
  for category in forward.CATEGORIES:
   payload=forward.build_payload(self.complaint(),category,license_plate='abc123')
   label,fields=forward.answers(payload)
   self.assertTrue(label);self.assertIn('abc',payload['description'])
   self.assertEqual(len(fields),2 if category=='Jármű' else 4 if category=='Túra alatti késés' else 3)
 def test_missing_route_or_plate_blocks_approval(self):
  row=self.complaint();row['affected_items'][0]['routeId']=''
  with self.assertRaises(ValueError):forward.build_payload(row,'Túra alatti késés')
  with self.assertRaises(ValueError):forward.build_payload(row,'Jármű')
 def test_one_day_only_and_invalid_category(self):
  row=self.complaint();row['affected_items'].append(dict(date='2026-11-01'))
  with self.assertRaises(ValueError):forward.build_payload(row)
  with self.assertRaises(ValueError):forward.build_payload(self.complaint(),'invalid')
 def test_identity_cannot_come_from_courier_free_text(self):
  row=self.complaint();payload=forward.build_payload(row)
  _,fields=forward.answers(payload)
  self.assertEqual(fields[238065601],'7644')
 def test_legacy_shift_default(self):
  row=self.complaint();row['topic']='noShow'
  self.assertEqual(forward.build_payload(row)['category'],'Műszak')


class WorkerTest(unittest.TestCase):
 def run_job(self,fill_error=None,start_rows=True,finish_error=False):
  events=[]
  class DB:
   def rpc(self,name,payload):
    events.append((name,payload.copy()))
    if name=='pwa_start_quality_submission':return [{}] if start_rows else []
    if finish_error:raise OSError('Lost acknowledgement')
    return [{}]
  class Page:
   def fill(self,payload):
    events.append(('fill',payload))
    if fill_error:raise fill_error
    return SimpleNamespace(click=lambda:events.append(('click',None)))
   def confirm(self):
    raise AssertionError('Fill-only worker must not confirm a submission')
  job=dict(complaint_id='abc',lease_token='lease',payload={})
  return worker.process_job(DB(),job,Page),events
 def test_fill_only_never_clicks_or_marks_forwarded(self):
  state,events=self.run_job()
  self.assertEqual(state,'prepared')
  self.assertEqual([name for name,_ in events],['pwa_start_quality_submission','fill','pwa_finish_quality_delivery'])
  self.assertEqual(events[-1][1]['p_confirmation'],'')
 def test_login_never_clicks(self):
  state,events=self.run_job(fill_error=worker.LoginRequired())
  self.assertEqual(state,'login_required');self.assertNotIn('click',[x[0] for x in events])
 def test_exposed_form_failure_never_reopens_automatically(self):
  state,events=self.run_job(fill_error=ValueError())
  self.assertEqual(state,'uncertain');self.assertNotIn('click',[x[0] for x in events])
 def test_unconfirmed_journal_never_exposes_form(self):
  state,events=self.run_job(start_rows=False)
  self.assertEqual(state,'failed');self.assertNotIn('fill',[x[0] for x in events])
 def test_lost_final_db_ack_is_not_retried(self):
  with self.assertRaises(OSError):self.run_job(finish_error=True)
 def test_browser_profile_must_stay_outside_repo(self):
  with self.assertRaises(ValueError):worker.profile_path(str(ROOT/'tmp/private-profile'))
 def test_manual_window_stays_until_closed(self):
  class Driver:
   reads=0
   @property
   def window_handles(self):
    self.reads+=1
    return ['window'] if self.reads==1 else []
  driver=Driver();original=worker.time.sleep
  worker.time.sleep=lambda _:None
  try:worker.wait_for_manual_close(driver)
  finally:worker.time.sleep=original
  self.assertEqual(driver.reads,2)

if __name__=='__main__':unittest.main()
