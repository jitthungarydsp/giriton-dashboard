import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gate_opening", ROOT / "resources/gate_opening.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def service(self):
        self.time = 100
        self.cfg = {"TWILIO_ACCOUNT_SID": "AC" + "a" * 32, "TWILIO_AUTH_TOKEN": "secret"}
        self.client = Mock()
        self.client.calls.create.return_value = SimpleNamespace(sid="CA123", status="queued")
        self.factory = Mock(return_value=self.client)
        return gate.GateOpeningService(lambda key: self.cfg.get(key, ""), self.factory, lambda: self.time)

    def test_call_uses_only_server_settings_and_replay_does_not_call_twice(self):
        svc = self.service()
        first = svc.open("request", "admin")
        self.assertEqual(svc.open("request", "admin"), first)
        self.client.calls.create.assert_called_once_with(
            to="+36501213800", from_="+4915888623971", timeout=20,
            url="https://webhooks.twilio.com/v1/Voice/Template/voice_speech_recognition")
        self.assertNotIn("secret", str(first) + str(svc.configuration()))

    def test_cooldown_is_shared_between_admins(self):
        svc = self.service()
        svc.open("first", "admin1")
        with self.assertRaises(gate.GateOpeningError) as error:
            svc.open("second", "admin2")
        self.assertEqual(error.exception.status_code, 429)
        self.time += 61
        svc.open("second", "admin2")
        self.assertEqual(self.client.calls.create.call_count, 2)

    def test_unknown_network_outcome_is_never_retried_with_same_id(self):
        svc = self.service()
        self.client.calls.create.side_effect = TimeoutError("secret must not leak")
        with self.assertRaises(gate.GateOpeningError) as error:
            svc.open("first", "admin")
        self.assertNotIn("secret", error.exception.message)
        self.time += 61
        with self.assertRaises(gate.GateOpeningError):
            svc.open("first", "admin")
        self.assertEqual(self.client.calls.create.call_count, 1)

    def test_unconfigured_disabled_and_no_call(self):
        svc = self.service()
        self.cfg.clear()
        self.assertFalse(svc.configuration()["configured"])
        with self.assertRaises(gate.GateOpeningError):
            svc.open("first", "admin")
        self.factory.assert_not_called()

    def test_inflight_request_does_not_duplicate(self):
        svc = self.service()
        def inside(**kwargs):
            with self.assertRaises(gate.GateOpeningError):
                svc.open("first", "admin")
            return SimpleNamespace(sid="CA123", status="queued")
        self.client.calls.create.side_effect = inside
        svc.open("first", "admin")
        self.client.calls.create.assert_called_once()

    def test_failed_twilio_status_is_not_success(self):
        svc = self.service()
        self.client.calls.create.return_value.status = "failed"
        with self.assertRaises(gate.GateOpeningError):
            svc.open("first", "admin")

    def test_api_guard_rejects_courier_coordinator_and_username_admin(self):
        names = {"require_gate_admin", "gate_configuration", "gate_open"}
        nodes = [n for n in ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8")).body
                 if isinstance(n, ast.FunctionDef) and n.name in names]
        for n in nodes:
            n.decorator_list = []
        class HTTPError(Exception):
            def __init__(self, status_code, detail): self.status_code = status_code
        svc = Mock()
        ns = dict(Any=object, GateOpeningRequest=object, Cookie=lambda **kw: None,
                  HTTPException=HTTPError, require_user=lambda user: user,
                  gate_opening_service=svc, GateOpeningError=gate.GateOpeningError)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "gate_api", "exec"), ns)
        for role in ("courier", "coordinator", "hr", ""):
            for endpoint in (lambda: ns["gate_configuration"]({"role": role, "username": "admin"}),
                             lambda: ns["gate_open"](SimpleNamespace(request_id="id"), {"role": role})):
                with self.assertRaises(HTTPError) as error: endpoint()
                self.assertEqual(error.exception.status_code, 403)
        svc.open.assert_not_called()
        for role in ("admin", "superadmin"):
            ns["gate_open"](SimpleNamespace(request_id="id"), {"role": role, "id": role})
        self.assertEqual(svc.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
