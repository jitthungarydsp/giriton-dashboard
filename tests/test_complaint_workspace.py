import unittest
from datetime import date
from resources.complaint_workspace import monthly_workspace,category


class ComplaintWorkspaceTests(unittest.TestCase):
    def read(self, table, params):
        if int(params.get('offset',0)):return []
        return {
            'courier_master':[{'courier_id':1,'courier_name':'Ákos'},{'courier_id':2,'courier_name':'György'}],
            'pwa_quality_complaints':[{'id':'a','courier_id':1,'topic':'noShow','status':'open','affected_items':[{'date':'2026-10-02'}]}],
            'courier_hub_route_statistics':[{'route_id':30,'courier_id':1,'work_date':'2026-10-02'}],
            'courier_route_alerts':[{'id':'b','courier_id':1,'route_id':30,'alert_type':'delay'},
                                    {'id':'undated','courier_id':1,'route_id':99,'alert_type':'delay'}],
            'courier_shift_checkins':[{'id':'c','courier_id':1,'work_date':'2026-10-03','event_type':'shift_late'}],
            'settlement.route_delay_form_draft':[{'id':'d','courier_id':1,'work_date':'2026-10-02','route_id':30,'state':'sent'},
                                                {'id':'outside','courier_id':1,'work_date':'2026-11-01','state':'sent'}]
        }.get(table,[])

    def test_complete_roster_keeps_couriers_without_cases(self):
        result=monthly_workspace(date(2026,10,1),self.read)
        self.assertEqual(len(result['couriers']),2)
        empty=next(r for r in result['couriers'] if r['courierId']=='2')
        self.assertEqual(empty['days'],[])

    def test_groups_by_work_day_and_preserves_distinct_sources(self):
        result=monthly_workspace(date(2026,10,1),self.read)
        courier=next(r for r in result['couriers'] if r['courierId']=='1')
        self.assertEqual([r['date'] for r in courier['days']],['2026-10-03','2026-10-02'])
        self.assertEqual({r['source'] for r in courier['days'][1]['items']},{'google','complaint','route'})
        self.assertEqual(len(courier['days'][1]['items']),3)

    def test_failed_source_is_exposed_instead_of_silent_empty(self):
        def read(table,params):
            if table=='pwa_quality_complaints':raise RuntimeError('offline')
            return self.read(table,params)
        result=monthly_workspace(date(2026,10,1),read)
        self.assertTrue(any('pwa_quality_complaints' in warning for warning in result['warnings']))
        self.assertEqual(category('noShow'),'noShow')
        self.assertEqual(category('shift_late'),'lateShift')

if __name__=='__main__':unittest.main()
