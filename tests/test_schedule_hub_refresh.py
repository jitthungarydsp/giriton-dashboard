import ast
import calendar
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
        ns=dict(ScheduleHubRefreshRequest=object,BackgroundTasks=object,UUID=UUID,Cookie=lambda **k:None,require_user=lambda _: {},
                require_coordinator=lambda user:user,coordinator_warehouse_ids=lambda _:list(allowed),
                selected_coordinator_warehouse_ids=selected,date=date,datetime=SimpleNamespace(now=lambda _:datetime(2026,11,29)),
                LOCAL_TIMEZONE=None,timedelta=timedelta,HTTPException=ApiError,parse_month=lambda s:date.fromisoformat(s+'-01'),month_end=lambda d:d.replace(day=calendar.monthrange(d.year,d.month)[1]))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'refresh','exec'),ns)
        gh=ModuleType('resources.github_actions');gh.dispatch_workflow=Mock();gh.get_latest_runs=Mock(return_value=[])
        refresh=ModuleType('resources.schedule_direct_refresh')
        refresh.REFRESH_PREFIX='schedule-hub-refresh'
        refresh.refresh_from_hub=Mock()
        ns.update(settlement_supabase_client=Mock(),create_schedule_batch=Mock(),read_schedule_batch=Mock(return_value=None))
        return ns,gh,refresh

    def test_overview_scope_five_days_including_month_boundary(self):
        ns,gh,refresh=self.endpoints();request=SimpleNamespace(request_id=uuid4(),work_date='',warehouse='')
        background=Mock()
        with patch.dict(sys.modules,{'resources.github_actions':gh,'resources.schedule_direct_refresh':refresh}):
            result=ns['schedule_hub_refresh'](request,background)
        self.assertEqual((result['startDate'],result['endDate']),('2026-11-29','2026-12-03'))
        self.assertEqual(result['warehouse_ids'],[1,2])
        background.add_task.assert_called_once_with(refresh.refresh_from_hub,ns['settlement_supabase_client'].return_value,result)
        gh.dispatch_workflow.assert_not_called()

    def test_daily_scope_and_unauthorized_warehouse(self):
        ns,gh,refresh=self.endpoints((2,));request=SimpleNamespace(request_id=uuid4(),work_date='2026-11-04',warehouse='BUD2')
        background=Mock()
        with patch.dict(sys.modules,{'resources.schedule_direct_refresh':refresh}):
            result=ns['schedule_hub_refresh'](request,background)
            request.warehouse='BUD1'
            with self.assertRaises(ApiError) as error:ns['schedule_hub_refresh'](request,background)
        self.assertEqual(result['startDate'],result['endDate']);self.assertEqual(error.exception.status_code,403)
        self.assertEqual(background.add_task.call_count,1)

    def test_status_only_matches_exact_uuid_not_another_successful_run(self):
        ns,gh,refresh=self.endpoints();id=uuid4()
        gh.get_latest_runs.return_value=[{'event':'workflow_dispatch','display_title':f'PWA Hub refresh {uuid4()}','status':'completed','conclusion':'success'}]
        with patch.dict(sys.modules,{'resources.github_actions':gh,'resources.schedule_direct_refresh':refresh}):
            self.assertEqual(ns['schedule_hub_refresh_status'](id)['found'],False)
            gh.get_latest_runs.return_value.append({'event':'workflow_dispatch','display_title':f'PWA Hub refresh {id}','status':'completed','conclusion':'failure'})
            result=ns['schedule_hub_refresh_status'](id)
        self.assertEqual(result['conclusion'],'failure')

    def test_selected_month_refresh_covers_whole_month(self):
        ns,gh,refresh=self.endpoints();request=SimpleNamespace(request_id=uuid4(),work_date='',month='2026-12',warehouse='BUD1')
        with patch.dict(sys.modules,{'resources.schedule_direct_refresh':refresh}):
            result=ns['schedule_hub_refresh'](request,Mock())
        self.assertEqual((result['startDate'],result['endDate']),('2026-12-01','2026-12-31'))
        self.assertEqual(result['warehouses'],['BUD1'])

if __name__=='__main__':unittest.main()
