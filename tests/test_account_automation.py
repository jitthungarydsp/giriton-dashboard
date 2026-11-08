import ast,hashlib,importlib.util,re,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('account',ROOT/'resources/account_automation.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class WorkerTests(unittest.TestCase):
 def test_void_finish_rpc_is_success_but_missing_prepare_is_not(self):
  import sys
  from unittest.mock import patch
  with patch.dict(sys.modules, {'resources.pwa_users_db':SimpleNamespace(_request=lambda *a,**k:None)}):
   self.assertIsNone(module.rpc('pwa_auth_finish',{'p_job':'job','p_sent':True}))
   with self.assertRaises(RuntimeError):module.rpc('pwa_auth_prepare',{})
 def run_job(self,ready=True,send_error=False,ack_error=False):
  calls=[];messages=[]
  def call(name,payload):
   calls.append((name,payload))
   if name=='pwa_auth_claim':return [{'id':'job'}]
   if name=='pwa_auth_prepare':return {'ready':ready,'username':'Courier','email':'saved@example.test'}
   if ack_error:raise TimeoutError()
   return True
  def send(*args):
   messages.append(args)
   if send_error:raise TimeoutError()
  result=module.process_one(call,send,'https://futar.jitt.hu')
  return result,calls,messages
 def test_only_hashed_secret_is_stored_and_mail_uses_trusted_destination(self):
  result,calls,messages=self.run_job();self.assertEqual(result,'sent');self.assertEqual(messages[0][0],'saved@example.test')
  token=re.search(r'#set-password=([A-Za-z0-9_-]+)',messages[0][2]).group(1)
  self.assertEqual(len(token),43);self.assertEqual(calls[1][1]['p_hash'],hashlib.sha256(token.encode()).hexdigest())
  self.assertFalse(any(token in str(payload) for _,payload in calls));self.assertEqual(calls[-1][1]['p_sent'],True)
 def test_mismatch_does_not_send(self):
  result,calls,messages=self.run_job(ready=False);self.assertEqual(result,'manual');self.assertFalse(messages);self.assertEqual(len(calls),2)
 def test_smtp_failure_is_uncertain_and_does_not_retry(self):
  result,calls,messages=self.run_job(send_error=True);self.assertEqual(result,'uncertain');self.assertEqual(len(messages),1);self.assertFalse(calls[-1][1]['p_sent'])
 def test_lost_db_ack_never_repeats_email(self):
  with self.assertRaises(TimeoutError):self.run_job(ack_error=True)
 def test_base_url_is_validated_before_claim(self):
  for url in ['http://example.test','https://user:pass@example.test','https://example.test/?token=123','https://az-alkalmazas-cime.example.com']:
   with self.assertRaises(ValueError):module.process_one(lambda *a:self.fail('Unexpected claim'),None,url)
 def test_idle_does_not_send(self):
  self.assertEqual(module.process_one(lambda *a:[],lambda *a:self.fail('Unexpected send'),'https://futar.jitt.hu'),'idle')
class ApiTests(unittest.TestCase):
 def function(self,name,ns):
  node=next(n for n in ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name==name);node.decorator_list=[]
  exec(compile(ast.Module(body=[node],type_ignores=[]),'api','exec'),ns);return ns[name]
 def test_public_registration_does_not_write_trusted_email(self):
  ns={'Any':object,'RegistrationRequest':object,'normalize_profile_courier_id':str,'normalize_email_address':str,
      'find_pwa_user_by_courier_id':lambda _:None,'save_registration_request':lambda _: {'id':1},
      'read_master_auth_row':lambda _:self.fail('Public registration must not bind master email'),
      'update_master_email_if_missing':lambda *a:self.fail('Untrusted email write')}
  result=self.function('register',ns)(SimpleNamespace(courier_id=123,email='untrusted@example.test'))
  self.assertTrue(result['ok'])
 def test_missing_recovery_email_cannot_be_added_by_request(self):
  class Denied(Exception):
   def __init__(self,**kw):self.status=kw['status_code']
  ns={'Any':object,'PasswordResetRequest':object,'normalize_profile_courier_id':str,'normalize_email_address':str,
      'find_pwa_user_by_courier_id':lambda _: {'username':'Courier'},'read_master_auth_row':lambda _: {},
      'master_email':lambda _: '', 'HTTPException':Denied}
  with self.assertRaises(Denied) as exc:self.function('save_password_reset_request',ns)(SimpleNamespace(courier_id=123,email='untrusted@example.test'))
  self.assertEqual(exc.exception.status,403)
 def test_password_change_revokes_old_session_but_allows_new_same_second(self):
  import hmac,secrets
  from datetime import datetime,timezone
  now=1900000000.8
  user={'username':'Courier','courierId':'123'}
  db_user={'username':'Courier','courier_id':123,'active':True,'password_updated_at':datetime.fromtimestamp(now-.1,timezone.utc).isoformat()}
  ns={'Any':object,'time':SimpleNamespace(time=lambda:now,time_ns=lambda:int(now*1e9)),
      'hashlib':hashlib,'hmac':hmac,'secrets':secrets,'session_secret':lambda:b'test-key','SESSION_TTL_SECONDS':1000,
      'find_pwa_user_by_login':lambda _:db_user,'public_pwa_user':lambda row:row,
      'local_datetime':lambda text:datetime.fromisoformat(text),'load_users':lambda:self.fail('Unexpected legacy fallback')}
  create=self.function('create_session',ns);read=self.function('read_session',ns)
  self.assertIsNotNone(read(create(user)))
  ns['time'].time_ns=lambda:int((now-.2)*1e9)
  self.assertIsNone(read(create(user)))
 def test_old_json_password_cannot_bypass_db_password(self):
  ns={'Any':object,'find_pwa_user_by_login':lambda _: {'active':True,'password_hash':'new'},'verify_password':lambda *a:False,
      'public_pwa_user':lambda u:u,'authenticate_legacy_json_user':lambda *a:self.fail('Legacy password bypass')}
  self.assertIsNone(self.function('authenticate',ns)('courier','old'))
 def test_database_outage_does_not_fallback_to_old_password(self):
  class Denied(Exception):
   def __init__(self,**kw):self.status=kw['status_code']
  def unavailable(_):raise TimeoutError()
  ns={'Any':object,'find_pwa_user_by_login':unavailable,'HTTPException':Denied,'authenticate_legacy_json_user':lambda *a:self.fail('Unsafe fallback')}
  with self.assertRaises(Denied) as exc:self.function('authenticate',ns)('courier','old')
  self.assertEqual(exc.exception.status,503)
 def test_redeem_api_passes_hashes_and_clears_session(self):
  calls=[];deleted=[]
  ns={'PasswordLinkRequest':object,'Response':object,'load_setting':lambda _: 'true','re':re,'hashlib':hashlib,
      'hash_password':lambda value:'HASHED_PASSWORD','supabase_rest':lambda *a,**kw:calls.append(kw) or True,'SESSION_COOKIE':'session'}
  result=self.function('complete_password_reset',ns)(SimpleNamespace(token='a'*43,password='long-password'),SimpleNamespace(headers={},delete_cookie=deleted.append))
  self.assertTrue(result['ok']);self.assertEqual(calls[0]['payload']['p_password_hash'],'HASHED_PASSWORD');self.assertNotIn('a'*43,str(calls));self.assertEqual(deleted,['session'])
if __name__=='__main__':unittest.main()
