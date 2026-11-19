import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


module = Path(__file__).resolve().parents[1] / "resources" / "invoice_admin_notifications.py"
spec = importlib.util.spec_from_file_location("invoice_admin_notifications", module)
notifications = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notifications)


def delivery(kind="immediate", events=None):
    return {
        "id": "test-delivery", "kind": kind, "digest_day": "2026-11-19",
        "events": events if events is not None else [{
            "courier_name": "Teszt Futár", "courier_id": "123",
            "period_start": "2026-10-01", "kind": "status:invoice_check", "detail": "open",
            "occurred_at": "2026-11-19T07:00:00+00:00", "historical": False,
        }],
    }


class InvoiceAdminNotificationsTest(unittest.TestCase):
    def test_claim_sends_to_explicit_mailbox_and_marks_sent(self):
        rest = Mock(side_effect=[[delivery()], None, []])
        send = Mock()
        self.assertEqual(notifications.send_pending_invoice_notifications(rest, send), 1)
        recipient, subject, body = send.call_args.args
        self.assertEqual(recipient, "zoltan.bagoly@jitt.hu")
        self.assertIn("Teszt Futár (2026-10)", subject)
        self.assertIn("11.19. 08:00", body)
        self.assertIn("Számlaellenőrzésre vár", body)
        self.assertEqual(rest.call_args_list[1].kwargs["payload"]["state"], "sent")

    def test_ambiguous_send_is_tracked_without_a_retry(self):
        rest = Mock(side_effect=[[delivery()], None, []])
        send = Mock(side_effect=TimeoutError)
        with self.assertLogs(notifications.logger, level="WARNING"):
            self.assertEqual(notifications.send_pending_invoice_notifications(rest, send), 0)
        send.assert_called_once()
        self.assertEqual(rest.call_args_list[1].kwargs["payload"]["state"], "uncertain")

    def test_empty_morning_and_closed_month_message(self):
        subject, body = notifications.build_invoice_admin_message(delivery("digest", []))
        self.assertIn("2026-11-19", subject)
        self.assertIn("nem érkezett", body)
        historical = delivery()
        historical["events"][0].update(historical=True, kind="document:invoice", detail="Számla TESZT-1")
        subject, body = notifications.build_invoice_admin_message(historical)
        self.assertIn("Lezárt havi esemény", subject)
        self.assertIn("Számla feltöltve (Számla TESZT-1)", body)
