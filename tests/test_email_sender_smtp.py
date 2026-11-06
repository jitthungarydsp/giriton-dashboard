import importlib.util
import sys
import types
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "email_sender_under_test", Path(__file__).resolve().parents[1] / "resources/email_sender.py"
)
mail = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"streamlit": types.ModuleType("streamlit")}):
    spec.loader.exec_module(mail)


class SmtpDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.config = {"host": "smtp.example.test", "port": 587,
            "use_ssl": False, "use_starttls": True,
            "username": "private-user", "password": "private-password"}
        self.message = EmailMessage()
        self.message.set_content("private-body")
        self.smtp = Mock()
        self.smtp.send_message.return_value = {}
        self.api = patch.object(mail, "resend_api_key", return_value="")
        self.api.start()
        self.addCleanup(self.api.stop)

    def test_success_uses_starttls_and_sends_once(self):
        with patch.object(mail.smtplib, "SMTP", return_value=self.smtp):
            mail.send_message(self.message, self.config)
        self.assertEqual(self.smtp.ehlo.call_count, 2)
        self.smtp.starttls.assert_called_once()
        self.smtp.login.assert_called_once_with("private-user", "private-password")
        self.smtp.send_message.assert_called_once_with(self.message)
        self.smtp.quit.assert_called_once()
        self.smtp.close.assert_called_once()

    def test_failed_stage_is_reported_without_logging_private_details(self):
        for method, expected in [("starttls", "STARTTLS titkosítás"),
                                 ("login", "bejelentkezés"),
                                 ("send_message", "levél átadása")]:
            with self.subTest(method=method):
                self.smtp = Mock()
                getattr(self.smtp, method).side_effect = mail.smtplib.SMTPServerDisconnected(
                    "private-password private-user private-body")
                with patch.object(mail.smtplib, "SMTP", return_value=self.smtp), \
                     self.assertLogs(mail.logger, level="ERROR") as logs, \
                     self.assertRaisesRegex(RuntimeError, expected) as error:
                    mail.send_message(self.message, self.config)
                for private in ("private-password", "private-user", "private-body"):
                    self.assertNotIn(private, str(error.exception))
                    self.assertNotIn(private, " ".join(logs.output))
                self.smtp.close.assert_called_once()

    def test_connect_disconnect_is_reported_and_not_retried(self):
        with patch.object(mail.smtplib, "SMTP", side_effect=mail.smtplib.SMTPServerDisconnected()) as connect, \
             self.assertLogs(mail.logger, level="ERROR"), \
             self.assertRaisesRegex(RuntimeError, "kapcsolódás"):
            mail.send_message(self.message, self.config)
        connect.assert_called_once()

    def test_quit_disconnect_does_not_report_accepted_email_as_failed(self):
        self.smtp.quit.side_effect = mail.smtplib.SMTPServerDisconnected()
        with patch.object(mail.smtplib, "SMTP", return_value=self.smtp), \
             self.assertLogs(mail.logger, level="WARNING"):
            mail.send_message(self.message, self.config)
        self.smtp.send_message.assert_called_once()
        self.smtp.close.assert_called_once()

    def test_ssl_connection_does_not_also_starttls(self):
        with patch.object(mail.smtplib, "SMTP_SSL", return_value=self.smtp), \
             patch.object(mail.smtplib, "SMTP") as plaintext:
            mail.send_message(self.message, {**self.config, "port": 465, "use_ssl": True})
        plaintext.assert_not_called()
        self.smtp.starttls.assert_not_called()
        self.smtp.send_message.assert_called_once()

    def test_resend_api_path_is_unchanged(self):
        with patch.object(mail, "resend_api_key", return_value="test-api-key"), \
             patch.object(mail, "send_message_with_resend") as resend, \
             patch.object(mail.smtplib, "SMTP") as smtp:
            mail.send_message(self.message, self.config)
        resend.assert_called_once_with(self.message, self.config, "test-api-key")
        smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
