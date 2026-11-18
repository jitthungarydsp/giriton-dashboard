import copy
import ast
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('assignment_notifications', Path(__file__).resolve().parents[1] / 'resources/complaint_assignment_notifications.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PREFIX, process_pending_assignments = module.PREFIX, module.process_pending_assignments


class ComplaintNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        self.value = {"schemaVersion": 1, "complaintId": "case-1", "courierId": "1234", "month": "2026-10", "assignmentId": "revision-1",
                      "assignee": {"key": "bagoly_zoltan", "name": "Bagoly Zoltán", "email": "zoltan.bagoly@jitt.hu"},
                      "courierName": "Teszt Futár", "complaintMessage": "Bónusz eltérés", "assignedBy": "Admin",
                      "hubUrl": "https://jitthub.jitthub.workers.dev/?complaint=case-1", "notification": {"status": "pending"}}
        self.row = {"id": "record-1", "courier_id": "1234", "document_month": "2026-10-01", "action_key": PREFIX + "case-1",
                    "status": "open", "status_note": json.dumps(self.value), "updated_at": (self.now - timedelta(minutes=1)).isoformat()}
        self.send = Mock()
        self.race = False
        self.fail_final = False

    def rest(self, method, table, params=None, payload=None, **kwargs):
        if table == "pwa_users":
            return [{"role": "admin", "email": "gurzo@example.test"}]
        self.assertEqual(table, "peopleforce_card_statuses")
        if method == "GET":
            self.assertEqual(params["action_key"], "like." + PREFIX + "*")
            return [copy.deepcopy(self.row)] if self.row["status"] == "open" else []
        self.assertEqual(params["updated_at"], "eq." + self.row["updated_at"])
        if self.race or self.fail_final and payload["status"] == "done":
            return []
        self.row.update(payload)
        return [copy.deepcopy(self.row)]

    def process(self, **kwargs):
        return process_pending_assignments(self.rest, self.send, now=self.now, **kwargs)

    def test_sends_once_with_context_and_link(self):
        self.assertEqual(self.process(), 1)
        self.assertEqual(self.process(), 0)
        self.send.assert_called_once()
        recipient, subject, body = self.send.call_args.args
        self.assertEqual(recipient, "zoltan.bagoly@jitt.hu")
        self.assertIn("Teszt Futár", subject)
        self.assertIn("2026-10", body)
        self.assertIn(self.value["hubUrl"], body)
        self.assertEqual(json.loads(self.row["status_note"])["notification"]["status"], "sent")

    def test_gurzo_address_is_verified_at_delivery(self):
        self.value["assignee"] = {"key": "gurzo_balazs", "name": "Gurzó Balázs", "email": "gurzo@example.test"}
        self.row["status_note"] = json.dumps(self.value)
        self.process()
        self.assertEqual(self.send.call_args.args[0], "gurzo@example.test")

    def test_unverified_address_never_sends(self):
        self.value["assignee"]["email"] = "other@example.test"
        self.row["status_note"] = json.dumps(self.value)
        self.process()
        self.send.assert_not_called()
        self.assertEqual(json.loads(self.row["status_note"])["notification"]["status"], "failed")

    def test_concurrent_worker_does_not_send(self):
        self.race = True
        self.process()
        self.send.assert_not_called()

    def test_failed_configuration_is_visible(self):
        self.process(validate_config=Mock(side_effect=RuntimeError("unconfigured")))
        self.send.assert_not_called()
        self.assertEqual(json.loads(self.row["status_note"])["notification"]["status"], "failed")

    def test_uncertain_delivery_is_not_retried_automatically(self):
        self.send.side_effect = TimeoutError()
        self.process()
        self.process()
        self.send.assert_called_once()
        self.assertEqual(json.loads(self.row["status_note"])["notification"]["status"], "uncertain")

    def test_crashed_worker_recovery_does_not_duplicate_email(self):
        self.value["notification"] = {"status": "sending", "startedAt": (self.now - timedelta(minutes=16)).isoformat()}
        self.row["status_note"] = json.dumps(self.value)
        self.process()
        self.send.assert_not_called()
        self.assertEqual(json.loads(self.row["status_note"])["notification"]["status"], "uncertain")

    def test_result_save_failure_cannot_resend(self):
        self.fail_final = True
        self.process()
        self.process()
        self.send.assert_called_once()

    def test_pwa_startup_and_shutdown_manage_notification_worker(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'pwa_api.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'pwa_lifespan')
        stop, rest = Mock(), Mock()
        start = Mock(return_value=stop)
        namespace = {'asynccontextmanager': asynccontextmanager, 'start_assignment_notifier': start, 'supabase_rest': rest}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'pwa_api.py', 'exec'), namespace)

        async def lifecycle():
            async with namespace['pwa_lifespan'](None):
                start.assert_called_once_with(rest)
                stop.set.assert_not_called()
            stop.set.assert_called_once()

        asyncio.run(lifecycle())

if __name__ == "__main__":
    unittest.main()
