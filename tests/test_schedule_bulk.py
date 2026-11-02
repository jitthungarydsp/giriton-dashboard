import ast
import copy
from datetime import date, datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec=importlib.util.spec_from_file_location(name, ROOT/path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
bulk=module('bulk','resources/schedule_bulk.py')
runner=module('bulk_runner','scripts/run_pwa_schedule_bulk.py')

def item(**changes):
    return dict(action='delete',work_date='2026-11-04',warehouse='BUD2',shift_template_id=12,
                slot_from='05:00',courier_id=9336,courier_name='Oláh László',**changes)

class BulkTest(unittest.TestCase):
    def test_scope_duplicates_and_fingerprint(self):
        rows=bulk.normalize_batch('delete',[item()], [2])
        self.assertEqual(rows[0]['slot_from'],'05:00:00')
        self.assertEqual(bulk.fingerprint(rows),bulk.fingerprint(copy.deepcopy(rows)))
        for action,rows,allowed in [('delete',[item()], [1]),('delete',[item(),item()],[2]),
                                    ('book',[item(),item()|{'work_date':'2026-11-05'}],[2]),
                                    ('book',[item()|{'courier_id':0}],[2]),('invalid',[item()],[2]),('book',[],[2])]:
            with self.assertRaises(ValueError):bulk.normalize_batch(action,rows,allowed)
        with self.assertRaises(ValueError):bulk.object_path('../../secret')

    def test_worker_journals_before_mutation_and_does_not_retry(self):
        record={'status':'queued','items':bulk.normalize_batch('delete',[item(),item()|{'slot_from':'09:00'}],[2])}
        snapshots=[];executed=[]
        def execute(row):
            self.assertEqual(snapshots[-1]['items'][len(executed)]['status'],'running')
            executed.append(row['slot_from'])
            if len(executed)==2:raise TimeoutError()
            return 'succeeded','OK'
        runner.run_items(record,lambda row:snapshots.append(copy.deepcopy(row)),execute)
        self.assertEqual(executed,['05:00:00','09:00:00'])
        self.assertEqual([row['status'] for row in record['items']],['succeeded','uncertain'])
        self.assertEqual(record['status'],'refreshing')
        runner.run_items(record,lambda _:None,lambda _:self.fail('Interrupted batch must never replay'))

    def test_journal_failure_stops_before_external_action(self):
        record={'status':'queued','items':[item()]};execute=Mock()
        with self.assertRaises(OSError):runner.run_items(record,Mock(side_effect=OSError()),execute)
        execute.assert_not_called()

    def test_overlap_and_nonzero_are_not_success(self):
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='HUB_API_BOOK_REJECTED status=200 reason=overlap response={}')):
            status,message=runner.execute_item(item()|{'action':'book'})
            self.assertEqual(status,'failed');self.assertIn('OVERLAP',message)
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='HUB_API_BOOK_OK status=200')):
            self.assertEqual(runner.execute_item(item()|{'action':'book'})[0],'succeeded')


class ApiError(Exception):
    def __init__(self,status_code,detail):self.status_code=status_code

class EndpointTest(unittest.TestCase):
    def endpoints(self,store,dispatch,allowed=(2,)):
        tree=ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'schedule_bulk_submit','schedule_bulk_status'}]
        for node in nodes:node.decorator_list=[]
        def create(client,record):
            if record['id'] in store:raise ValueError('Already exists')
            store[record['id']]=copy.deepcopy(record)
        ns=dict(Any=Any,UUID=UUID,ScheduleBulkRequest=Any,Cookie=lambda **k:None,Query=lambda **k:False,
                HTTPException=ApiError,require_user=lambda _:{'username':'Admin'},require_coordinator=lambda user:user,
                coordinator_warehouse_ids=lambda _:list(allowed),normalize_batch=bulk.normalize_batch,
                resolve_schedule_shift_template_id=lambda payload,*a:(payload.shift_template_id,payload.slot_from),
                ScheduleHubShiftActionRequest=SimpleNamespace,date=date,datetime=datetime,timezone=timezone,
                warehouse_id_for_hub=lambda value:int(value[-1]),settlement_supabase_client=lambda:None,
                schedule_batch_fingerprint=bulk.fingerprint,create_schedule_batch=create,
                read_schedule_batch=lambda client,id:copy.deepcopy(store[id]))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'endpoints','exec'),ns)
        gh=ModuleType('resources.github_actions');gh.dispatch_workflow=dispatch
        return ns,gh

    def payload(self,request_id=None,**changes):
        data=item()|changes
        return SimpleNamespace(request_id=request_id or uuid4(),action=data['action'],items=[SimpleNamespace(**data,model_dump=lambda:data)])

    def test_idempotent_submit_and_read_scope(self):
        store={};dispatch=Mock();ns,gh=self.endpoints(store,dispatch)
        payload=self.payload()
        with patch.dict(sys.modules,{'resources.github_actions':gh}):
            first=ns['schedule_bulk_submit'](payload)
            second=ns['schedule_bulk_submit'](payload)
        dispatch.assert_called_once_with('pwa-schedule-bulk.yml',inputs={'request_id':str(payload.request_id)})
        self.assertEqual(first['id'],second['id'])
        with self.assertRaises(ApiError) as error:ns['schedule_bulk_submit'](self.payload(payload.request_id,courier_id=42))
        self.assertEqual(error.exception.status_code,409)
        ns,_=self.endpoints(store,dispatch,allowed=(1,))
        with self.assertRaises(ApiError) as error:ns['schedule_bulk_status'](payload.request_id,False)
        self.assertEqual(error.exception.status_code,403)

    def test_invalid_scope_never_persists_or_dispatches(self):
        store={};dispatch=Mock();ns,_=self.endpoints(store,dispatch,allowed=(1,))
        with self.assertRaises(ApiError):ns['schedule_bulk_submit'](self.payload())
        self.assertFalse(store);dispatch.assert_not_called()

    def test_lost_dispatch_response_retains_id_and_never_redispatches(self):
        store={};dispatch=Mock(side_effect=TimeoutError());ns,gh=self.endpoints(store,dispatch)
        payload=self.payload()
        with patch.dict(sys.modules,{'resources.github_actions':gh}):
            with self.assertRaises(ApiError):ns['schedule_bulk_submit'](payload)
            ns['schedule_bulk_submit'](payload)
        self.assertEqual(dispatch.call_count,1)
        self.assertIn(str(payload.request_id),store)


if __name__=='__main__':unittest.main()
