import ast
import hashlib
import io
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote
from uuid import UUID
from PIL import Image


class ApiError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


def functions(db):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'pwa_api.py').read_text(encoding='utf-8'))
    names = {'quality_complaint_manager', 'quality_photo_mime', 'read_accessible_quality_complaint',
             'upload_quality_complaint_photo', 'download_quality_complaint_photo'}
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    ns = dict(Any=Any, UUID=UUID, UploadFile=Any, File=lambda *a: None, Cookie=lambda **k: None,
              io=io, hashlib=hashlib, datetime=datetime, timezone=timezone, quote=quote,
              HTTPException=ApiError, supabase_rest=db,
              require_user=lambda _: {'role': 'courier', 'courierId': '6498'},
              courier_identity=lambda user: ('6498', 'Futár'),
              pwa_attachment_bucket=lambda: 'pwa-attachments',
              load_setting=lambda name: 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'secret',
              supabase_key_headers=lambda key: {}, storage_file_name=lambda name, fallback: name or fallback)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'photos', 'exec'), ns)
    return ns


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4)).save(buffer, format='PNG')
    return buffer.getvalue()


class PhotoTest(unittest.IsolatedAsyncioTestCase):
    def test_validates_real_content_and_size(self):
        fn = functions(None)['quality_photo_mime']
        self.assertEqual(fn(png()), 'image/png')
        for content in [b'<svg>not an image</svg>', b'', b'x' * (8 * 1024 * 1024 + 1)]:
            with self.assertRaises(ApiError):
                fn(content)

    def test_owner_filter_and_no_unauthorized_download(self):
        calls = []
        def db(*args, **kwargs):
            calls.append(kwargs)
            return []
        ns = functions(db)
        with self.assertRaises(ApiError) as error:
            ns['download_quality_complaint_photo']('id', 'hash')
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(calls[0]['params']['courier_id'], 'eq.6498')

    async def test_bytes_go_to_storage_only_and_retry_deduplicates(self):
        data = png()
        saved = []
        uploads = []
        def db(method, table, **kwargs):
            if method == 'GET':
                return [{'id': 'id', 'status': 'open', 'attachments': saved.copy()}]
            self.assertEqual(table, 'rpc/pwa_attach_quality_complaint_photo')
            metadata = kwargs['payload']['p_photo']
            self.assertNotIn('file_content_base64', metadata)
            self.assertEqual(metadata['file_size'], len(data))
            saved.append(metadata)
            return [{'attachments': saved.copy()}]
        ns = functions(db)
        ns['requests'] = SimpleNamespace(post=lambda url, **kwargs: uploads.append(kwargs) or SimpleNamespace(ok=True))
        async def read(size):
            return data
        photo = SimpleNamespace(filename='kep.png', read=read)
        for _ in range(2):
            self.assertTrue((await ns['upload_quality_complaint_photo']('id', photo))['ok'])
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]['data'], data)
        self.assertEqual(len(saved), 1)

    async def test_database_rejection_cleans_unreferenced_storage_object(self):
        def db(method, table, **kwargs):
            if method == 'GET':
                return [{'id': 'id', 'status': 'open', 'attachments': []}]
            raise ApiError(502, 'Migration missing')
        ns = functions(db)
        deleted = []
        ns['requests'] = SimpleNamespace(
            post=lambda *a, **k: SimpleNamespace(ok=True),
            delete=lambda *a, **k: deleted.append(k['json']), RequestException=Exception)
        async def read(size):
            return png()
        with self.assertRaises(ApiError):
            await ns['upload_quality_complaint_photo']('id', SimpleNamespace(filename='kep.png', read=read))
        self.assertEqual(len(deleted), 1)
        self.assertTrue(deleted[0]['prefixes'][0].startswith('quality-complaints/id/'))


if __name__ == '__main__':
    unittest.main()
