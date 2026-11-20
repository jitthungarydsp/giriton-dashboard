import base64
from email.message import EmailMessage
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gmail_archive_import', ROOT / 'scripts/import_complaint_email_responses.py')
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)


def message(subject='Panasz elbírálva: 8332', sender='partner@example.test'):
    email = EmailMessage()
    email['Subject'] = subject
    email['From'] = sender
    email.set_content('Ellenőrzött döntés.')
    return {'id': 'a1', 'threadId': 'b1', 'internalDate': '1795000000000', 'labelIds': ['INBOX'],
            'raw': base64.urlsafe_b64encode(email.as_bytes()).decode().rstrip('=')}


class GmailMailboxImportTest(unittest.TestCase):
    def test_old_default_and_both_mailboxes_preserve_message_parsing(self):
        self.assertEqual(mail.parse_message(message())['mailbox'], 'balazs.gurzo@jitt.hu')
        for account in mail.MAILBOXES:
            row = mail.parse_message(message(), mailbox=account)
            self.assertEqual(row['mailbox'], account)
            self.assertEqual(row['gmail_id'], 'a1')
            self.assertIn('Ellenőrzött döntés', row['body_text'])
            coordinator = mail.parse_message(message('JITT - Koordinátor Teszt 8332 Dávid - 1. késés - 06:00-14:00', 'koordinator@jitt.hu'), mailbox=account, coordinator=True)
            self.assertEqual(coordinator['mailbox'], account)
            self.assertEqual(coordinator['courier_id'], '8332')
            self.assertEqual(coordinator['late_occurrence'], 1)

    def test_oauth_verifies_selected_account_before_any_message_read(self):
        settings = {f'GMAIL_COMPLAINT_{key}': 'test-only' for key in ['CLIENT_ID', 'CLIENT_SECRET', 'REFRESH_TOKEN']}
        for account in mail.MAILBOXES:
            calls = []
            def request(service, url, **kwargs):
                calls.append(url)
                return {'access_token': 'test-only'} if service == 'Google OAuth' else {'emailAddress': account.upper()}
            with patch.object(mail, 'request_json', side_effect=request):
                mail.gmail_reader(settings, mailbox=account)
            self.assertEqual(len(calls), 2)
            self.assertIn('/profile?', calls[-1])
        with patch.object(mail, 'request_json', side_effect=[{'access_token': 'test-only'}, {'emailAddress': mail.MAILBOX}]) as request:
            with self.assertRaisesRegex(RuntimeError, 'system@jitt.hu'):
                mail.gmail_reader(settings, mailbox='system@jitt.hu')
            self.assertEqual(request.call_count, 2)

    def test_all_pages_and_coordinator_mode_pass_selected_mailbox_to_storage(self):
        for coordinator in (False, True):
            saved = []
            def get(path, **params):
                if path == 'messages':
                    return {'messages': [{'id': 'a1'}], **({'nextPageToken': 'next'} if 'pageToken' not in params else {})}
                return message('JITT - Koordinátor Teszt 8332 Dávid - távolmaradás - reggel', 'koordinator@jitt.hu') if coordinator else message()
            def save(rows):
                saved.extend(rows)
                return len(rows)
            self.assertEqual(mail.import_messages(get, save, mailbox='system@jitt.hu', coordinator=coordinator), (2, 2))
            self.assertTrue(all(row['mailbox'] == 'system@jitt.hu' for row in saved))

    def test_existing_id_lookups_are_scoped_to_mailbox_and_batch_cannot_cross_accounts(self):
        requests = []
        def request(service, url, **kwargs):
            requests.append((url, kwargs))
            if service == 'Supabase insert':
                return json.loads(kwargs['data'])
            return [{'gmail_id': 'a1'}] if service == 'Supabase existing-email lookup' else []
        settings = {'SUPABASE_URL': 'https://database.example.test', 'SUPABASE_SERVICE_ROLE_KEY': 'test-only'}
        with patch.object(mail, 'request_json', side_effect=request):
            for account in mail.MAILBOXES:
                save, known = mail.supabase_writer(settings, mailbox=account)
                self.assertEqual(known(['a1']), {'a1'})
                query = parse_qs(urlparse(requests[-1][0]).query)
                self.assertEqual(query['mailbox'], ['eq.' + account])
                self.assertEqual(save([{'gmail_id': 'a1', 'mailbox': account}]), 1)
                self.assertEqual(parse_qs(urlparse(requests[-1][0]).query)['on_conflict'], ['mailbox,gmail_id'])
                count = len(requests)
                with self.assertRaisesRegex(RuntimeError, 'different mailbox'):
                    save([{'gmail_id': 'a1', 'mailbox': 'other@example.test'}])
                self.assertEqual(len(requests), count)

    def test_dry_run_needs_no_database_credentials_and_never_opens_writer(self):
        credentials = {f'GMAIL_COMPLAINT_{key}': 'test-only' for key in ['CLIENT_ID', 'CLIENT_SECRET', 'REFRESH_TOKEN']}
        with tempfile.TemporaryDirectory() as root, patch.object(mail, '__file__', str(Path(root) / 'scripts/import.py')), \
             patch.dict('os.environ', credentials, clear=True), \
             patch('sys.argv', ['import.py', '--mailbox', 'system@jitt.hu', '--dry-run']), \
             patch.object(mail, 'gmail_reader', return_value=Mock()) as reader, \
             patch.object(mail, 'import_messages', return_value=(3, 0)) as messages, \
             patch.object(mail, 'supabase_writer') as writer, patch('sys.stdout', new_callable=io.StringIO):
            mail.main()
            reader.assert_called_once_with(credentials, mailbox='system@jitt.hu')
            self.assertEqual(messages.call_args.kwargs['mailbox'], 'system@jitt.hu')
            writer.assert_not_called()

    def test_sent_drafts_spam_and_trash_are_excluded_for_system_too(self):
        for label in mail.EXCLUDED_LABELS:
            row = message()
            row['labelIds'].append(label)
            self.assertIsNone(mail.parse_message(row, mailbox='system@jitt.hu'))

    def test_workflow_pairs_both_accounts_with_both_sources_and_separate_secrets(self):
        workflow = (ROOT / '.github/workflows/import-complaint-email-responses.yml').read_text(encoding='utf-8')
        accounts = re.findall(r'- mailbox: (\S+)\n\s+client_id_secret: (\S+)\n\s+client_secret_secret: (\S+)\n\s+refresh_token_secret: (\S+)', workflow)
        self.assertEqual({row[0] for row in accounts}, set(mail.MAILBOXES))
        self.assertEqual(set(re.findall(r'- source: (\S+)', workflow)), {'complaint-responses', 'coordinator-shifts'})
        self.assertIn(('system@jitt.hu', 'GMAIL_SYSTEM_CLIENT_ID', 'GMAIL_SYSTEM_CLIENT_SECRET', 'GMAIL_SYSTEM_REFRESH_TOKEN'), accounts)
        self.assertIn((mail.MAILBOX, 'GMAIL_COMPLAINT_CLIENT_ID', 'GMAIL_COMPLAINT_CLIENT_SECRET', 'GMAIL_COMPLAINT_REFRESH_TOKEN'), accounts)
        self.assertIn('GMAIL_COMPLAINT_CLIENT_ID: ${{ secrets[matrix.account.client_id_secret] }}', workflow)
        self.assertIn('--mailbox "$IMPORT_MAILBOX"', workflow)
        self.assertIn('--dry-run', workflow)
        self.assertIn("inputs.mailbox == matrix.account.mailbox", workflow)


if __name__ == '__main__':
    unittest.main()
