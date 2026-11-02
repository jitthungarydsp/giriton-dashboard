import ast
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

ROOT=Path(__file__).resolve().parents[1]

class ApiError(Exception):
    def __init__(self,status_code,detail):self.status_code=status_code

class RefreshTest(unittest.TestCase):
    def endpoints(self,allowed=(1,2)):
        tree=ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'schedule_hub_refresh','schedule_hub_refresh_status'}]
        for node in nodes:node.decorator_list=[]
        def selected(user,warehouse):
            if warehouse not in [f'BUD{i}' for i in allowed]:raise ApiError(403,'Warehouse scope')
            return [int(warehouse[-1])]
        ns=dict(ScheduleHubRefreshRequest=object,UUID=UUID,Cookie=lambda **k:None,require_user=lambda _: {},
                require_coordinator=lambda user:user,coordinator_warehouse_ids=lambda _:list(allowed),
                selected_coordinator_warehouse_ids=selected,date=date,datetime=SimpleNamespace(now=lambda _:datetime(2026,11,29)),
                LOCAL_TIMEZONE=None,timedelta=timedelta,HTTPException=ApiError)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'refresh','exec'),ns)
        gh=ModuleType('resources.github_actions');gh.dispatch_workflow=Mock();gh.get_latest_runs=Mock(return_value=[])
        return ns,gh

    def test_overview_scope_five_days_including_month_boundary(self):
        ns,gh=self.endpoints();request=SimpleNamespace(request_id=uuid4(),work_date='',warehouse='')
        with patch.dict(sys.modules,{'resources.github_actions':gh}):result=ns['schedule_hub_refresh'](request)
        self.assertEqual((result['startDate'],result['endDate']),('2026-11-29','2026-12-03'))
        gh.dispatch_workflow.assert_called_once_with('pwa-schedule-refresh.yml',inputs={'request_id':str(request.request_id),'start_date':'2026-11-29','end_date':'2026-12-03','warehouse_ids':'1,2'})

    def test_daily_scope_and_unauthorized_warehouse(self):
        ns,gh=self.endpoints((2,));request=SimpleNamespace(request_id=uuid4(),work_date='2026-11-04',warehouse='BUD2')
        with patch.dict(sys.modules,{'resources.github_actions':gh}):
            result=ns['schedule_hub_refresh'](request)
            request.warehouse='BUD1'
            with self.assertRaises(ApiError) as error:ns['schedule_hub_refresh'](request)
        self.assertEqual(result['startDate'],result['endDate']);self.assertEqual(error.exception.status_code,403)
        self.assertEqual(gh.dispatch_workflow.call_count,1)

    def test_status_only_matches_exact_uuid_not_another_successful_run(self):
        ns,gh=self.endpoints();id=uuid4()
        gh.get_latest_runs.return_value=[{'event':'workflow_dispatch','display_title':f'PWA Hub refresh {uuid4()}','status':'completed','conclusion':'success'}]
        with patch.dict(sys.modules,{'resources.github_actions':gh}):
            self.assertEqual(ns['schedule_hub_refresh_status'](id)['found'],False)
            gh.get_latest_runs.return_value.append({'event':'workflow_dispatch','display_title':f'PWA Hub refresh {id}','status':'completed','conclusion':'failure'})
            result=ns['schedule_hub_refresh_status'](id)
        self.assertEqual(result['conclusion'],'failure')

if __name__=='__main__':unittest.main()
