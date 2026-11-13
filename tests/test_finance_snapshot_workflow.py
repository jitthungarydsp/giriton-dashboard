import ast
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def load_workflow_module():
    path = ROOT / "resources" / "finance_snapshot_workflow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.Assign))]
    requests = Mock()
    get_response = Mock()
    get_response.json.return_value = [
        {
            "id": "old-auto-tig",
            "uploaded_by": "PWA automata",
            "note": "Automatikus Teljesítés-összesítő generálás elszámolás elfogadása után.",
        },
        {"id": "manual-tig", "uploaded_by": "admin", "note": "Kézzel feltöltött TIG"},
    ]
    requests.get.return_value = get_response
    ns = {
        "Any": Any,
        "date": date,
        "datetime": datetime,
        "timezone": timezone,
        "requests": requests,
        "get_supabase_config": lambda: ("https://example.invalid", "service-key"),
        "raise_for_supabase_error": lambda response: None,
        "courier_email_from_profile": Mock(return_value="futar@example.com"),
        "send_custom_email": Mock(return_value={"ok": True}),
        "log_email_event": Mock(),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


class FinanceSnapshotWorkflowTest(unittest.TestCase):
    def test_new_snapshot_reopens_all_steps_deletes_only_automatic_tig_and_notifies(self):
        ns = load_workflow_module()
        result = ns["reset_workflow_for_finance_snapshot"](
            courier_id="9070",
            courier_name="Piszker Klaudia",
            period_start=date(2026, 10, 1),
            snapshot_id="new-snapshot",
            previous_snapshot_id="",
            snapshot_source="test",
        )
        self.assertTrue(result["reset"])
        self.assertTrue(result["emailSent"])
        self.assertEqual(result["removedAutomaticTigCount"], 1)
        self.assertEqual(ns["requests"].post.call_count, 5)
        action_keys = [call.kwargs["json"]["action_key"] for call in ns["requests"].post.call_args_list]
        self.assertEqual(action_keys, list(ns["WORKFLOW_ACTIONS"]))
        self.assertEqual(ns["requests"].delete.call_count, 1)
        self.assertEqual(ns["requests"].delete.call_args.kwargs["params"], {"id": "eq.old-auto-tig"})
        ns["send_custom_email"].assert_called_once_with(
            "futar@example.com", "Elszámolás frissült – 2026-10", ns["EMAIL_BODY"]
        )


if __name__ == "__main__":
    unittest.main()
