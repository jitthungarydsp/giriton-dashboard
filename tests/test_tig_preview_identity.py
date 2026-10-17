import ast
import subprocess
import unittest
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]


class TigPreviewIdentityTest(unittest.TestCase):
    def test_archive_generated_tig_link_keeps_preview_courier(self):
        tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "read_courier_document_archive")
        expressions = [value for node in ast.walk(function) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == "downloadUrl"
                       and "tig.pdf" in ast.unparse(value)]
        self.assertEqual(len(expressions), 1)
        code = compile(ast.Expression(expressions[0]), "pwa_api.py", "eval")
        ns = {"quote": quote, "month_key": "2026-09", "courier_id": "6498",
              "user": {"_previewedBy": "admin"}}
        self.assertEqual(eval(code, ns), "/api/workflow/tig.pdf?month=2026-09&courier=6498")
        ns["user"] = {}
        self.assertEqual(eval(code, ns), "/api/workflow/tig.pdf?month=2026-09")

    def test_frontend_tig_link_uses_rendered_identity_and_preserves_bound_links(self):
        source = (ROOT / "pwa/app.js").read_text(encoding="utf-8")
        def function(name, next_name):
            return source[source.index(f"function {name}("):source.index(f"function {next_name}(")]
        script = "const assert = require('assert');\nconst window = {location:{origin:'https://example.test'}};\n"
        script += "const state = {user:{canPreviewCouriers:true}, workflowMonth:'2026-09', workflowProcess:'', workflowPreviewCourierId:'', workflow:{viewingAs:{courierId:'6498'}}};\n"
        script += function("previewCourierValue", "isAdminPreviewMode")
        script += function("withPreviewCourier", "currentSectionRefresh")
        script += function("workflowQuery", "workflowProcessQuery")
        script += function("workflowTigDownloadUrl", "renderTigBreakdown")
        script += """
let url = new URL(workflowTigDownloadUrl(), window.location.origin);
assert.equal(url.searchParams.get('courier'), '6498');
state.workflowPreviewCourierId = '8185';
url = new URL(workflowTigDownloadUrl(), window.location.origin);
assert.equal(url.searchParams.get('courier'), '6498');
const bound = '/api/workflow/tig.pdf?month=2026-09&courier=6498';
assert.equal(withPreviewCourier(bound), bound);
assert.equal(withPreviewCourier('/api/workflow/tig.pdf?month=2026-09'), '/api/workflow/tig.pdf?month=2026-09&courier=8185');
state.user.canPreviewCouriers = false;
url = new URL(workflowTigDownloadUrl(), window.location.origin);
assert.equal(url.searchParams.has('courier'), false);
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
