import ast
import copy
from datetime import date
import importlib.util
import logging
from pathlib import Path
import unittest
from unittest.mock import Mock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('partner_decisions', ROOT / 'resources/quality_complaint_decisions.py')
decisions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decisions)
CASE = '1b17cc0d-746e-4c2f-99b4-9d21f5eb0ae8'
OTHER = '22222222-2222-4222-8222-222222222222'


def email(outcome='Elfogadva', case=CASE, at='2026-11-19T18:11:24+00:00', cid='8530'):
    return {'sender': 'Kifli Last Mile <noreply@appsheet.com>',
            'subject': 'Panasz elbírálva: P-261112-999 - György Roland (Túra alatti késés) - ' + outcome,
            'body_text': f'Panasz azonosító: P-261112-999\nFutár: György Roland ({cid})\nJITT reklamáció: {case}\nDöntés: {outcome}\nIndoklás: {outcome}\nKérjük, hivatkozzatok az azonosítóra.\nBelső lábléc.',
            'courier_id': cid, 'received_at': at}


def complaint():
    return {'id': CASE, 'courier_id': '8530', 'created_at': '2026-11-10T10:50:56+00:00',
            'status': 'closed', 'admin_response': 'Duplikáció'}


class PartnerDecisionTest(unittest.TestCase):
    def attach(self, mails, item=None):
        cases = [copy.deepcopy(item or complaint())]
        calls = []
        def rest(method, table, params):
            self.assertEqual(method, 'GET')
            self.assertEqual(table, 'complaint_email_responses')
            calls.append(params)
            return copy.deepcopy(mails)
        decisions.attach_partner_decisions(rest, cases)
        return cases[0], calls

    def test_exact_case_accepted_even_if_previously_closed_duplicate(self):
        item, calls = self.attach([email()])
        result = item['partnerDecision']
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['reason'], 'Elfogadva')
        self.assertNotIn('Belső', str(result))
        self.assertEqual((item['status'], item['admin_response']), ('closed', 'Duplikáció'))
        self.assertEqual(calls[0]['courier_id'], 'eq.8530')
        self.assertIn(CASE, calls[0]['or'])
        self.assertEqual(set(result), {'status', 'reason', 'respondedAt', 'reference'})

    def test_name_day_or_route_without_exact_case_never_assigns_a_decision(self):
        unrelated = email(case=OTHER)
        self.assertNotIn('partnerDecision', self.attach([unrelated])[0])
        unrelated['body_text'] = unrelated['body_text'].replace(OTHER, 'György Roland · 2026-11-10 · Route 1600493')
        self.assertNotIn('partnerDecision', self.attach([unrelated])[0])

    def test_exact_external_reference_is_allowed_but_conflicting_explicit_case_is_not(self):
        item = {**complaint(), 'forwarding_reference': 'P-261112-999'}
        row = email()
        row['body_text'] = row['body_text'].replace('JITT reklamáció: ' + CASE, '')
        self.assertEqual(self.attach([row], item)[0]['partnerDecision']['status'], 'accepted')
        self.assertNotIn('partnerDecision', self.attach([email(case=OTHER)], item)[0])

    def test_latest_decision_wins_and_mailbox_copies_do_not_create_duplicates(self):
        rejected = email('Elutasítva', at='2026-11-19T17:00:00Z')
        item, _ = self.attach([email(), rejected, email()])
        self.assertEqual(item['partnerDecision']['status'], 'accepted')
        newer = email('Elutasítva', at='2026-11-20T17:00:00Z')
        self.assertEqual(self.attach([email(), newer])[0]['partnerDecision']['status'], 'rejected')

    def test_ambiguous_decisions_same_time_and_conflicting_body_are_not_guessed(self):
        item, _ = self.attach([email(), email('Elutasítva')])
        self.assertNotIn('partnerDecision', item)
        self.assertIn('partnerDecisionWarning', item)
        row = email()
        row['body_text'] += '\nDöntés: Elutasítva'
        self.assertIsNone(decisions.parse_decision(row))
        row = email('Elutasítva')
        row['subject'] = email()['subject']
        self.assertIsNone(decisions.parse_decision(row))

    def test_wrong_courier_sender_old_date_and_invalid_timestamp_are_ignored(self):
        for row in [{**email(), 'courier_id': '6498'},
                    {**email(), 'body_text': email(cid='6498')['body_text']},
                    {**email(), 'sender': 'other@example.test'},
                    email(at='2026-11-01T12:00:00Z'), email(at='invalid')]:
            with self.subTest(row=row):
                self.assertNotIn('partnerDecision', self.attach([row])[0])

    def test_partial_acceptance_and_multiline_reason_do_not_include_footer(self):
        row = email('Részben elfogadva')
        row['body_text'] = row['body_text'].replace('Indoklás: Részben elfogadva', 'Indoklás: Egy cím elfogadva.\nA másik cím elutasítva.')
        value = decisions.parse_decision(row)
        self.assertEqual(value['status'], 'partially_accepted')
        self.assertEqual(value['reason'], 'Egy cím elfogadva.\nA másik cím elutasítva.')

    def test_duplicate_external_reference_cannot_be_guessed_between_two_cases(self):
        items = [{**complaint(), 'forwarding_reference':'P-261112-999'},
                 {**complaint(), 'id':OTHER, 'forwarding_reference':'P-261112-999'}]
        row = email()
        row['body_text'] = row['body_text'].replace('JITT reklamáció: '+CASE, '')
        decisions.attach_partner_decisions(lambda *a,**kw:[row],items)
        self.assertTrue(all('partnerDecision' not in item for item in items))

    def test_many_couriers_are_batched_and_results_cannot_cross_owners(self):
        items = [{**complaint(), 'courier_id':str(8530+i),'id':str(UUID(int=i+1))} for i in range(30)]
        calls=[]
        def rest(method,table,params):
            calls.append(params)
            return [email(case=items[1]['id'],cid='8530')]
        decisions.attach_partner_decisions(rest,items)
        self.assertEqual(len(calls),2)
        self.assertTrue(all('partnerDecision' not in item for item in items))

    def test_own_api_uses_session_courier_and_handles_archive_failure(self):
        node = next(n for n in ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf8')).body if isinstance(n,ast.FunctionDef) and n.name=='own_quality_complaints')
        node.decorator_list = []
        node.body = [n for n in node.body if not (isinstance(n,ast.ImportFrom) and n.module=='resources.quality_complaint_decisions')]
        calls = []
        def rest(method, table, params):
            calls.append((table, params))
            if table == 'pwa_quality_complaints':
                return [{key:value for key,value in complaint().items() if key!='courier_id'}]
            return [email()]
        ns = {'Query':lambda *args,**kw:kw.get('default'), 'Cookie':lambda **kw:None,
              'require_user':lambda _: {'courierId':'8530'}, 'workflow_view_user':lambda u,c:(u,False),
              'courier_identity':lambda u:(u['courierId'],'György Roland'),
              'parse_month':lambda value:date.fromisoformat(value+'-01'), 'supabase_rest':rest,
              'attach_partner_decisions':decisions.attach_partner_decisions,'logging':logging}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'own-decisions','exec'),ns)
        result = ns['own_quality_complaints']('2026-11', '', None)
        self.assertEqual(result['items'][0]['partnerDecision']['status'], 'accepted')
        self.assertTrue(result['partnerDecisionsAvailable'])
        self.assertTrue(all(params['courier_id']=='eq.8530' for _,params in calls))
        ns['attach_partner_decisions'] = Mock(side_effect=RuntimeError('unavailable'))
        with self.assertLogs(level='WARNING'):
            result = ns['own_quality_complaints']('2026-11','',None)
        self.assertFalse(result['partnerDecisionsAvailable'])
        self.assertEqual(result['items'][0]['id'], CASE)


if __name__ == '__main__':
    unittest.main()
