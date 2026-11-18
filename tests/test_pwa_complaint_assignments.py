import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assignment_mail', ROOT / 'resources/complaint_assignment_notifications.py')
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)
tree = ast.parse((ROOT / 'resources/complaint_assignments.py').read_text(encoding='utf-8'))
tree.body = [node for node in tree.body if not (isinstance(node, ast.ImportFrom) and node.module == 'resources.complaint_assignment_notifications')]
namespace = {'PREFIX': mail.PREFIX, 'assignment_value': mail.assignment_value}
exec(compile(tree, 'resources/complaint_assignments.py', 'exec'), namespace)
workspace = SimpleNamespace(**namespace)


class ProfileAssignmentsTest(unittest.TestCase):
    def setUp(self):
        self.id = '00000000-0000-0000-0000-000000000001'
        self.first = '10000000-0000-4000-8000-000000000001'
        self.second = '20000000-0000-4000-8000-000000000001'
        self.admin = {'username': 'Admin', 'courierId': '0'}
        self.bagoly = {'username': 'Bagoly Zoltán', 'courierId': 12345, 'active': True}
        self.employee = {'username': 'Munkatárs', 'courierId': '77', 'active': True}
        self.users = [{'username': 'Gurzó Balázs', 'courier_id': 7644, 'active': True, 'email': 'gurzo@example.test'},
                      {**self.employee, 'courier_id': 77, 'email': 'employee@example.test'}]
        self.case = {'id': self.id, 'courier_id': '8764', 'courier_name': 'Teszt Futár', 'document_month': '2026-10-01',
                     'document_type': 'settlement', 'message': 'Hiányzó bónusz', 'status': 'new', 'created_at': '2026-11-01T12:00:00Z'}
        self.record = None
        self.race = False
        self.writes = []

    def rest(self, method, table, params=None, payload=None, **_kwargs):
        self.assertIn(table, {'pwa_users', 'peopleforce_complaints', 'peopleforce_card_statuses'})
        if table == 'pwa_users':
            self.assertNotIn('password', params['select'])
            return copy.deepcopy([row for row in self.users if not params.get('username') or row['username'] == params['username'][3:]])
        if method == 'GET' and table == 'peopleforce_complaints':
            if self.case['status'] == 'deleted':
                return []
            identifier = params.get('id', '')
            if identifier.startswith('eq.') and identifier[3:] != self.id or identifier.startswith('in.') and self.id not in identifier:
                return []
            return [copy.deepcopy(self.case)]
        if method == 'GET':
            return [copy.deepcopy(self.record)] if self.record else []
        self.writes.append((table, copy.deepcopy(payload)))
        if self.race:
            return []
        if table == 'peopleforce_complaints':
            self.assertEqual(set(payload), {'status'})
            self.case.update(payload)
            return [copy.deepcopy(self.case)]
        if method == 'PATCH':
            self.assertEqual(params['updated_at'], 'eq.' + self.record['updated_at'])
        self.record = {**payload, 'id': 'record-1'}
        return [copy.deepcopy(self.record)]

    def assign(self, **extra):
        return workspace.assign_case(self.rest, self.admin, self.id, extra.pop('profile_key', 'pwa:Bagoly Zoltán'),
                                     legacy_users=[self.bagoly], operation_id=extra.pop('operation_id', self.first), **extra)

    def test_active_database_and_legacy_profiles_and_bagoly_email(self):
        rows = workspace.load_profiles(self.rest, [self.bagoly])
        self.assertEqual(len(rows), 3)
        self.assertEqual(next(row for row in rows if row['username'] == 'Bagoly Zoltán')['email'], 'zoltan.bagoly@jitt.hu')

    def test_disabled_db_profile_cannot_reappear_via_legacy(self):
        self.users.append({'username': 'Bagoly Zoltán', 'courier_id': 12345, 'active': False})
        self.assertFalse(any(row['username'] == 'Bagoly Zoltán' for row in workspace.load_profiles(self.rest, [self.bagoly])))
        with self.assertRaises(workspace.AssignmentError):
            self.assign()

    def test_assignment_saves_shared_note_and_pwa_link(self):
        result = self.assign(note='Kérlek, ellenőrizd a három műszakot.')
        self.assertEqual(result['assignee']['username'], 'Bagoly Zoltán')
        self.assertEqual(result['notes'][0]['author'], 'Admin')
        value = json.loads(self.record['status_note'])
        self.assertIn('https://futar.jitt.hu/?complaintTask=', value['hubUrl'])
        self.assertIn('Kérlek, ellenőrizd', mail.notification_message(value)[1])
        self.assertEqual(mail.verified_recipient(self.rest, value, [self.bagoly]), 'zoltan.bagoly@jitt.hu')

    def test_assignment_repeat_is_idempotent(self):
        self.assign()
        writes = len(self.writes)
        self.assign()
        self.assertEqual(len(self.writes), writes)

    def test_zero_profile_id_remains_assignable_and_verifiable(self):
        self.users.append({'username': 'Admin', 'courier_id': 0, 'active': True, 'email': 'admin@example.test'})
        self.assign(profile_key='pwa:Admin')
        value = json.loads(self.record['status_note'])
        self.assertEqual(value['assignee']['courierId'], '0')
        self.assertEqual(mail.verified_recipient(self.rest, value, []), 'admin@example.test')

    def test_only_assigned_profile_sees_case_and_notes(self):
        self.assign(note='Közös megjegyzés')
        mine = workspace.list_cases(self.rest, self.bagoly)
        self.assertEqual(mine['items'][0]['assignment']['notes'][0]['text'], 'Közös megjegyzés')
        self.assertEqual(workspace.list_cases(self.rest, self.employee)['items'], [])
        with self.assertRaises(workspace.AssignmentError) as caught:
            workspace.list_cases(self.rest, self.employee, complaint_id=self.id)
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(workspace.AssignmentError):
            workspace.list_cases(self.rest, self.bagoly, scope='all')

    def test_new_assignee_takes_access_and_retains_notes(self):
        self.assign(note='Eredeti feladat')
        self.assign(profile_key='pwa:Munkatárs', operation_id=self.second, expected_assignment_id=self.first)
        self.assertEqual(workspace.list_cases(self.rest, self.bagoly)['items'], [])
        self.assertEqual(workspace.list_cases(self.rest, self.employee)['items'][0]['assignment']['notes'][0]['text'], 'Eredeti feladat')
        self.assertEqual(mail.verified_recipient(self.rest, json.loads(self.record['status_note']), [self.bagoly]), 'employee@example.test')

    def test_assignee_can_add_note_but_other_profile_cannot(self):
        self.assign()
        result = workspace.add_note(self.rest, self.bagoly, self.id, 'Megnéztem a műszakot.', operation_id=self.second,
                                    expected_assignment_id=self.first, expected_notes_revision=self.first)
        self.assertEqual(result['notes'][-1]['author'], 'Bagoly Zoltán')
        writes = len(self.writes)
        workspace.add_note(self.rest, self.bagoly, self.id, 'Megnéztem a műszakot.', operation_id=self.second,
                           expected_assignment_id=self.first, expected_notes_revision=self.first)
        self.assertEqual(len(self.writes), writes)
        with self.assertRaises(workspace.AssignmentError) as caught:
            workspace.add_note(self.rest, self.employee, self.id, 'Másik ügy', operation_id=self.second,
                               expected_assignment_id=self.first)
        self.assertEqual(caught.exception.status, 403)

    def test_concurrent_notes_and_assignment_are_guarded(self):
        self.assign()
        with self.assertRaises(workspace.AssignmentError):
            workspace.add_note(self.rest, self.bagoly, self.id, 'Elavult', operation_id=self.second,
                               expected_assignment_id=self.first, expected_notes_revision='stale')
        self.race = True
        with self.assertRaises(workspace.AssignmentError):
            self.assign(profile_key='pwa:Munkatárs', operation_id=self.second, expected_assignment_id=self.first)

    def test_starting_investigation_is_not_an_answer_or_payment(self):
        self.assign()
        with self.assertRaises(workspace.AssignmentError):
            workspace.start_case(self.rest, self.employee, self.id)
        result = workspace.start_case(self.rest, self.bagoly, self.id)
        self.assertEqual(result['status'], 'in_progress')
        self.assertNotIn('responded_at', self.case)
        self.assertTrue(all(table in {'peopleforce_complaints', 'peopleforce_card_statuses'} for table, _payload in self.writes))

    def test_unknown_profile_and_invalid_month_are_rejected(self):
        with self.assertRaises(workspace.AssignmentError):
            self.assign(profile_key='pwa:unknown')
        with self.assertRaises(workspace.AssignmentError):
            workspace.list_cases(self.rest, self.admin, month='2026-99', admin=True, scope='all')


if __name__ == '__main__':
    unittest.main()
