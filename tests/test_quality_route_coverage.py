import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('coverage_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_quality_route_coverage.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CoverageTest(unittest.TestCase):
    def signal(self, identifier, route):
        return {'id': identifier, 'courier_id': 9460, 'courier_name': 'Juhász József', 'route_id': route,
                'created_at': '2026-11-20T11:00:00Z'}

    def case(self, identifier='case', route='1612799', status='forwarded'):
        return {'id': identifier, 'courier_id': '9460', 'courier_name': 'Juhász József',
                'topic': 'uncleanedTimeWindowLate', 'work_month': '2026-11-01', 'status': status,
                'affected_items': [{'date': '2026-11-20', 'routeId': route}]}

    def test_same_tour_signals_count_once_while_another_route_is_unrecorded(self):
        case = self.case()
        result = audit.reconcile([self.signal(111,'1612799'),self.signal(112,'1612799'),self.signal(114,'other')],
            [case], [{'complaint_id':'case','state':'sent','route_id':'1612799'}], {}, {('9460','1612799'):case}, '2026-11')
        self.assertEqual(result['counts'], {'Továbbított':1, 'Még nincs reklamáció':1})
        sent = next(row for row in result['rows'] if row['route_id']=='1612799')
        self.assertEqual(sent['signals'],2)

    def test_no_route_is_reported_as_unknown_not_guessed(self):
        result = audit.reconcile([self.signal(1,'')], [], [], {}, {}, '2026-11')
        self.assertEqual(result['rows'],[])
        self.assertEqual(len(result['unknown_route']),1)

    def test_explicit_duplicate_closure_is_excluded_without_deleting_original(self):
        signal = self.signal(1,'route')
        key = audit.action_key('route',1)
        marker = {'action_key':key,'courier_id':'9460','status':'done',
                  'status_note':json.dumps({'recordType':'qualitySignalResolution','reason':'duplicate'})}
        result = audit.reconcile([signal], [], [], {key:marker}, {}, '2026-11')
        self.assertEqual(result['closed_duplicate_signals'],1)
        self.assertEqual(result['rows'],[])
        self.assertEqual(signal['route_id'],'route')

    def test_actual_submission_and_authoritative_owner_win_over_older_duplicate(self):
        old, sent = self.case('old'), self.case('sent',status='closed')
        result = audit.reconcile([], [old,sent], [{'complaint_id':'sent','state':'sent','route_id':'other'}], {},
            {('9460','1612799'):sent,('9460','other'):sent}, '2026-11')
        self.assertEqual(result['counts'], {'Továbbított':2})
        self.assertTrue(all(row['complaint_id']=='sent' for row in result['rows']))


if __name__ == '__main__':
    unittest.main()
