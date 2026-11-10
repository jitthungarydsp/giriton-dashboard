import ast
import base64
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import unittest
from uuid import UUID
from zoneinfo import ZoneInfo


class HttpError(Exception):
    def __init__(self, status_code, detail):self.status_code=status_code


def load_functions(rest):
    tree=ast.parse((Path(__file__).resolve().parents[1]/'pwa_api.py').read_text(encoding='utf8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'own_route_signals','own_route_signal_photo','admin_route_signals','route_signal_to_complaint'}]
    for n in nodes:n.decorator_list=[]
    ns=dict(Query=lambda *a,**k:None,Cookie=lambda *a,**k:None,date=date,datetime=datetime,timedelta=timedelta,
            LOCAL_TIMEZONE=ZoneInfo('Europe/Budapest'),UUID=UUID,re=re,base64=base64,hashlib=hashlib,
            require_user=lambda _: {'courierId':'42'},workflow_view_user=lambda u,c:(u,False),
            courier_identity=lambda u:('42','Futár'),parse_month=lambda s:date.fromisoformat(s+'-01'),
            supabase_rest=rest,HTTPException=HttpError,Response=lambda **k:k,
            quality_complaint_manager=lambda u:False,
            download_pwa_attachment=lambda b,p:b'image')
    future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future,*nodes],type_ignores=[])),'pwa_api.py','exec'),ns)
    return ns


class RouteSignalTests(unittest.TestCase):
    def test_signal_conversion_is_idempotent_and_uses_existing_complaint_flow(self):
        stored=[];calls=[]
        def rest(method,table,params=None,payload=None,prefer=None):
            calls.append((method,table))
            if table=='pwa_quality_complaints':
                if method=='GET':return stored
                stored.append({'id':'complaint-id',**payload});return stored
            if table=='courier_route_alerts':return [{'id':'123','courier_id':42,'courier_name':'Futár','alert_type':'delay','route_id':'1600493','message':'Baleset miatt késtem','created_at':'2026-10-31T23:30:00Z'}]
            return []
        ns=load_functions(rest);ns['quality_complaint_manager']=lambda u:True
        one=ns['route_signal_to_complaint']('route','123',None)
        two=ns['route_signal_to_complaint']('route','123',None)
        self.assertEqual(one['item']['id'],two['item']['id'])
        self.assertEqual(len(stored),1)
        self.assertEqual(stored[0]['status'],'open')
        self.assertEqual(stored[0]['work_month'],'2026-11-01')
        self.assertEqual(stored[0]['affected_items'][0]['routeId'],'1600493')
        self.assertEqual(stored[0]['affected_items'][0]['signalId'],'123')
        self.assertFalse(any('delivery' in table for _,table in calls))

    def test_non_manager_cannot_convert_signal(self):
        ns=load_functions(lambda *a,**k:self.fail('DB must not be queried'))
        with self.assertRaises(HttpError) as caught:ns['route_signal_to_complaint']('route','123',None)
        self.assertEqual(caught.exception.status_code,403)

    def test_admin_list_requires_management_permission(self):
        ns=load_functions(lambda *a,**k:self.fail('Must reject before reading data'))
        with self.assertRaises(HttpError) as caught:ns['admin_route_signals'](0,None)
        self.assertEqual(caught.exception.status_code,403)

    def test_admin_list_includes_all_couriers_and_attaches_owned_photos(self):
        calls=[]
        def rest(method,table,params):
            calls.append((table,params))
            if table=='courier_route_alerts':return [{'id':'a','courier_id':42},{'id':'b','courier_id':43}]
            if table=='courier_route_alert_photos':return [{'id':'photo','alert_id':'b'}]
            return []
        ns=load_functions(rest);ns['quality_complaint_manager']=lambda u:True
        result=ns['admin_route_signals'](50,None)
        self.assertEqual(result['alerts'][0]['photos'],[])
        self.assertEqual(result['alerts'][1]['photos'],['photo'])
        self.assertNotIn('courier_id',calls[0][1])
        self.assertEqual(calls[0][1]['offset'],'50')
        self.assertEqual(calls[1][1]['event_type'],'in.(shift_late,coordinator_shift_late)')

    def test_queries_are_scoped_to_courier_month_and_relevant_types(self):
        calls=[]
        def rest(method,table,params):
            calls.append((table,params))
            return [{'id':12}] if table=='courier_route_alerts' else []
        result=load_functions(rest)['own_route_signals']('2026-10','',None)
        self.assertEqual(result['alerts'][0]['photos'],[])
        self.assertEqual(calls[0][1]['courier_id'],'eq.42')
        self.assertEqual(calls[0][1]['created_at'],'gte.2026-10-01T00:00:00+02:00')
        self.assertEqual(calls[0][1]['and'],'(created_at.lt.2026-11-01T00:00:00+01:00)')
        self.assertEqual(calls[1][1]['event_type'],'in.(shift_late,coordinator_shift_late)')

    def test_photo_owner_checked_before_photo_access(self):
        calls=[]
        def rest(method,table,params):calls.append((table,params));return []
        with self.assertRaises(HttpError) as caught:
            load_functions(rest)['own_route_signal_photo']('12',UUID(int=1),'',None)
        self.assertEqual(caught.exception.status_code,404)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1]['courier_id'],'eq.42')

    def test_photo_filters_cannot_be_injected(self):
        with self.assertRaises(HttpError) as caught:
            load_functions(lambda *a,**k:self.fail('DB must not be queried'))['own_route_signal_photo']('12,13',UUID(int=1),'',None)
        self.assertEqual(caught.exception.status_code,422)


if __name__=='__main__':unittest.main()
