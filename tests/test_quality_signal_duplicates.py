import copy
import importlib.util
import json
import unittest
from pathlib import Path
from test_courier_route_signals import load_functions, HttpError


class DuplicateSignalTest(unittest.TestCase):
    def setUp(self):
        self.signal = {'id': '123', 'courier_id': 9136, 'courier_name': 'Szendi Balázs',
                       'alert_type': 'problem', 'route_id': '1602226', 'message': 'Baleset miatt torlódás.', 'created_at': '2026-11-11T17:35:00Z'}
        self.records = []
        self.complaint = None
        self.day_case = None
        self.writes = []
        self.fail_save = False
        self.race = False
        self.ns = load_functions(self.rest)
        self.ns['require_user'] = lambda _: {'username': 'Teszt Admin', 'role': 'admin'}
        self.ns['quality_complaint_manager'] = lambda user: user.get('role') == 'admin'

    def rest(self, method, table, params=None, payload=None, **kwargs):
        if method != 'GET' and not table.startswith('rpc/'):
            self.writes.append((table, copy.deepcopy(payload)))
        if table in {'courier_route_alerts', 'courier_shift_checkins'}:
            return [copy.deepcopy(self.signal)] if self.signal else []
        if table == 'rpc/pwa_find_quality_route_complaint':
            return [copy.deepcopy(self.day_case)] if self.day_case and any(item.get('routeId') == payload['p_route_id'] for item in self.day_case['affected_items']) else []
        if table == 'peopleforce_card_statuses':
            if method == 'POST':
                if self.fail_save:
                    return []
                if not self.records:
                    self.records.append({'id': 'marker', **payload})
                    return copy.deepcopy(self.records)
                return []
            return copy.deepcopy(self.records)
        if table == 'pwa_quality_complaints':
            if method == 'POST':
                if self.race:
                    self.day_case = {'id': 'won-race', 'affected_items': [{'date': '2026-11-11','routeId':'1602226'}], 'status': 'open'}
                    raise HttpError(409, 'Erre a napra már van ilyen típusú reklamáció.')
                self.complaint = {'id': 'created', **payload}
                return [self.complaint]
            if 'request_id' in params:
                return [self.complaint] if self.complaint else []
            return [self.day_case] if self.day_case else []
        return []

    def close(self, kind='route', signal_id='123'):
        return self.ns['close_duplicate_quality_signal'](kind, signal_id, None)

    def test_close_audits_only_private_marker_and_retry_preserves_original_actor(self):
        result = self.close()
        self.assertTrue(result['ok'])
        self.assertEqual(result['resolution']['reason'], 'duplicate')
        self.assertEqual(result['resolution']['closedBy'], 'Teszt Admin')
        self.assertTrue(result['resolution']['closedAt'])
        self.assertEqual(self.writes[0][0], 'peopleforce_card_statuses')
        self.assertTrue(self.records[0]['action_key'].startswith('internal_complaint_assignment:duplicate-signal:route:'))
        self.ns['require_user'] = lambda _: {'username': 'Másik admin', 'role': 'admin'}
        again = self.close()
        self.assertEqual(again, result)
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.signal['message'], 'Baleset miatt torlódás.')

    def test_permissions_and_malformed_identity_rejected_before_writes(self):
        for kind, signal_id in [('route', '123,456'), ('other', '123')]:
            with self.assertRaises(HttpError) as error:
                self.close(kind, signal_id)
            self.assertEqual(error.exception.status_code, 422)
        self.ns['quality_complaint_manager'] = lambda _: False
        with self.assertRaises(HttpError) as error:
            self.close()
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.writes, [])

    def test_wrong_month_irrelevant_shift_or_linked_complaint_cannot_be_silently_closed(self):
        original = dict(self.signal)
        for change, kind, status in [({'created_at': '2026-10-11T17:35:00Z'}, 'route', 422),
                                     ({'event_type': 'queued', 'work_date': '2026-11-11'}, 'shift', 422)]:
            self.signal = {**original, **change}
            with self.assertRaises(HttpError) as error:
                self.close(kind)
            self.assertEqual(error.exception.status_code, status)
        self.signal = original
        self.complaint = {'id': 'already-created'}
        with self.assertRaises(HttpError) as error:
            self.close()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.writes, [])

    def test_shift_duplicate_and_failed_save(self):
        self.signal.update(event_type='shift_late', work_date='2026-11-11')
        self.assertTrue(self.close('shift')['ok'])
        self.assertIn(':shift:123', self.records[0]['action_key'])
        self.records.clear()
        self.fail_save = True
        with self.assertRaises(HttpError) as error:
            self.close()
        self.assertEqual(error.exception.status_code, 502)

    def test_duplicate_marker_is_attached_to_list_and_blocks_conversion(self):
        self.close()
        rows = [dict(self.signal)]
        self.ns['attach_resolutions'](self.rest, rows, [], self.ns['QUALITY_COMPLAINT_MONTH'])
        self.assertEqual(rows[0]['resolution']['reason'], 'duplicate')
        with self.assertRaises(HttpError) as error:
            self.ns['route_signal_to_complaint']('route', '123', None)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any(table == 'pwa_quality_complaints' for table, _ in self.writes))

    def test_existing_day_case_opens_without_new_complaint_or_signal_write(self):
        self.day_case = {'id': 'daily-original', 'affected_items': [{'date': '2026-11-11','routeId':'1602226'}], 'status': 'forwarded'}
        result = self.ns['route_signal_to_complaint']('route', '123', None)
        self.assertTrue(result['alreadyExists'])
        self.assertEqual(result['item']['id'], 'daily-original')
        self.assertEqual(self.writes, [])
        # The independent raw report can still be explicitly closed as a duplicate.
        self.assertTrue(self.close()['ok'])

    def test_day_claim_race_uses_existing_case_and_does_not_overwrite_it(self):
        self.race = True
        result = self.ns['route_signal_to_complaint']('route', '123', None)
        self.assertTrue(result['alreadyExists'])
        self.assertEqual(result['item']['id'], 'won-race')
        self.assertEqual(self.complaint, None)

    def test_same_day_different_route_does_not_reuse_address_delay_case(self):
        self.signal['alert_type'] = 'bag_missing'
        self.day_case = {'id': 'unrelated', 'affected_items': [{'date': '2026-11-11','routeId':'other-route'}]}
        result = self.ns['route_signal_to_complaint']('route', '123', None)
        self.assertEqual(result['item']['id'], 'created')
        self.assertFalse(result.get('alreadyExists'))

    def test_private_closure_is_not_a_complaint_assignment_email(self):
        self.close()
        spec = importlib.util.spec_from_file_location('mail_notifier', Path(__file__).resolve().parents[1] / 'resources/complaint_assignment_notifications.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIsNone(module.assignment_value(self.records[0]))

    def test_lookup_uses_authoritative_claim_with_exact_route_not_date_or_category(self):
        seen = []
        def rest(method, table, payload):
            self.assertEqual((method,table),('POST','rpc/pwa_find_quality_route_complaint'))
            seen.append(payload)
            return [{'id': 'original', 'affected_items': [{'date': '2026-11-10','routeId':'1602226','category':'Futárbüntetés'}]}]
        result = self.ns['find_existing_day_complaint'](rest, 'route', self.signal, '2026-11-11')
        self.assertEqual(result['id'], 'original')
        self.assertEqual(seen[0]['p_courier_id'], '9136')
        self.assertEqual(seen[0]['p_route_id'], '1602226')
        self.assertNotIn('work_month',seen[0])

    def test_missing_route_is_not_guessed_from_another_signal(self):
        self.signal.pop('route_id')
        with self.assertRaises(HttpError) as error:
            self.ns['route_signal_to_complaint']('route','123',None)
        self.assertEqual(error.exception.status_code,422)
        self.assertEqual(self.writes,[])


if __name__ == '__main__':
    unittest.main()
