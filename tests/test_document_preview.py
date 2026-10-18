import ast
import base64
import subprocess
import unittest
from pathlib import Path
from urllib.parse import quote

from fastapi import Cookie, HTTPException, Query, Response


ROOT = Path(__file__).resolve().parents[1]


class DocumentPreviewTest(unittest.TestCase):
    def endpoint(self, mime="application/pdf", filename="szamla.pdf", rows=None):
        tree = ast.parse((ROOT / "pwa_api.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "download_document")
        fn.decorator_list = []
        calls = []
        row = {"file_name": filename, "mime_type": mime,
               "file_content_base64": base64.b64encode(b"%PDF-test").decode()}
        def read(method, table, **kwargs):
            calls.append((method, table, kwargs))
            return [row] if rows is None else rows
        ns = {"Query": Query, "Cookie": Cookie, "Response": Response,
              "HTTPException": HTTPException, "base64": base64, "quote": quote,
              "require_user": lambda _: {"id": "admin"},
              "workflow_view_user": lambda user, courier: ({"courier": courier}, True),
              "courier_identity": lambda user: (user["courier"], "Futár"),
              "base_action_key": lambda value: value, "supabase_rest": read}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "pwa_api.py", "exec"), ns)
        return ns["download_document"], calls

    def test_inline_pdf_and_default_download_keep_courier_scope(self):
        endpoint, calls = self.endpoint(mime="application/octet-stream")
        preview = endpoint("doc1", courier="6498", inline=True)
        self.assertTrue(preview.headers["content-disposition"].startswith("inline;"))
        self.assertEqual(preview.headers["content-type"], "application/pdf")
        self.assertEqual(preview.headers["cache-control"], "private, no-store")
        download = endpoint("doc1", courier="6498", inline=False)
        self.assertTrue(download.headers["content-disposition"].startswith("attachment;"))
        self.assertEqual(preview.body, download.body)
        self.assertTrue(all(call[0] == "GET" and call[2]["params"]["courier_id"] == "eq.6498" for call in calls))

    def test_unpreviewable_file_remains_attachment(self):
        endpoint, _ = self.endpoint(mime="text/html", filename="file.html")
        self.assertTrue(endpoint("doc1", courier="6498", inline=True).headers["content-disposition"].startswith("attachment;"))

    def test_missing_document_is_not_rendered(self):
        endpoint, _ = self.endpoint(rows=[])
        with self.assertRaises(HTTPException) as error:
            endpoint("doc1", courier="6498", inline=True)
        self.assertEqual(error.exception.status_code, 404)

    def test_list_does_not_load_files_until_selected(self):
        source = (ROOT / "pwa/app.js").read_text(encoding="utf-8")
        code = source[source.index("function documentPreviewList("):source.index("function documentArchiveQuery(")]
        script = """
const assert = require('assert');
const window = {location:{origin:'https://example.test'}};
const previewCourierValue = () => '8185';
const escapeHtml = value => String(value);
const documentList = () => '';
let click;
const document = {addEventListener: (_, handler) => click = handler,
 createElement: tag => ({tagName:tag.toUpperCase(),style:{}})};
""" + code + """
const html = documentPreviewList([{downloadUrl:'/api/documents/doc1',file_name:'test.pdf'}], '6498');
assert(!html.includes('<iframe'));
assert(!html.includes('<img'));
assert(html.includes('href="/api/documents/doc1?courier=6498"'));
assert(html.includes('data-document-preview-url="/api/documents/doc1?courier=6498&inline=true"'));
const panels = [0,1].map(() => ({firstElementChild:null,replaceChildren(){this.firstElementChild=null;},
 append(...children){this.children=children;this.firstElementChild=children[0];}}));
let list;
const buttons = panels.map((panel, index) => ({dataset:{documentPreviewUrl:'/api/documents/'+index+'?inline=true',
 documentPreviewType:'pdf'},setAttribute(){},closest: selector => selector === '.document-preview-list' ? list : {querySelector:()=>panel}}));
list = {querySelectorAll: selector => selector.includes('panel') ? panels : buttons};
click({target:{closest:()=>buttons[0]}});
assert.equal(panels[0].children[1].tagName, 'IFRAME');
assert.equal(panels[0].children[1].src, buttons[0].dataset.documentPreviewUrl);
click({target:{closest:()=>buttons[1]}});
assert.equal(panels[0].firstElementChild, null);
assert(panels[1].firstElementChild);
click({target:{closest:()=>buttons[1]}});
assert.equal(panels[1].firstElementChild, null);
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
