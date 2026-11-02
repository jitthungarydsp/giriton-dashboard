import ast
import asyncio
from datetime import date, datetime
from io import BytesIO
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from uuid import UUID, uuid4
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("invoice_raw", ROOT / "resources/pwa_invoice_raw.py")
raw = importlib.util.module_from_spec(spec); spec.loader.exec_module(raw)


def workbook():
    """Small OOXML test fixture, not an authored user workbook."""
    stream = BytesIO()
    files = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Adatok-JITT" sheetId="1" r:id="rId1"/><sheet name="Üres-KIFLI" sheetId="2" r:id="rId2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:F3"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Azonosító</t></is></c><c r="C1" t="n"><v>0</v></c></row><row r="3"><c r="A3"><f>1+1</f><v>2</v></c><c r="B3" t="b"><v>0</v></c><c r="F3" t="inlineStr"><is><t>001</t></is></c></row></sheetData></worksheet>',
        'xl/worksheets/sheet2.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>',
    }
    with ZipFile(stream, 'w') as archive:
        for name, content in files.items(): archive.writestr(name, content)
    return stream.getvalue()


class FakeClient:
    def __init__(self):
        self.rows = {}; self.objects = {}; self.tables = []; self.uploads = 0; self.saves = 0
        self.missing = False; self.lose_commit_response = False; self.private = True
        self.storage = SimpleNamespace(get_bucket=lambda _: {'public': not self.private}, from_=lambda _: self)
    def schema(self, schema):
        assert schema == 'public'; return self
    def table(self, table):
        assert table == raw.TABLE; self.tables.append(table); self.id = None; return self
    def select(self, fields):
        assert 'raw_data' not in fields; return self
    def eq(self, field, value):
        if field == 'id': self.id = value
        return self
    def limit(self, _): return self
    def order(self, *args, **kwargs): return self
    def range(self, *args): return self
    def execute(self):
        if self.missing: raise RuntimeError('PGRST205')
        return SimpleNamespace(data=[self.rows[self.id]] if self.id in self.rows else [])
    def upload(self, path, content, file_options):
        if path in self.objects: raise RuntimeError('exists')
        assert file_options['upsert'] == 'false'
        self.objects[path] = content; self.uploads += 1
    def download(self, path): return self.objects[path]
    def rpc(self, name, payload):
        assert name == 'pwa_invoice_raw_save'; self.saves += 1
        row = dict(id=payload['p_id'], settlement_month=payload['p_month'], source_file_name=payload['p_file_name'],
                   file_sha256=payload['p_sha256'], file_size_bytes=payload['p_byte_size'], status='saved',
                   session_id='JITT_2026_09_123456', sheet_count=len(payload['p_raw_data']['sheets']),
                   raw_row_count=sum(len(sheet['rows']) for sheet in payload['p_raw_data']['sheets']))
        self.rows[row['id']] = row
        if self.lose_commit_response:
            self.lose_commit_response = False; raise TimeoutError('lost response after commit')
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=row))


class RawTest(unittest.TestCase):
    def test_sheets_coordinates_types_and_formulas_preserved(self):
        result = raw.read_workbook(workbook(), '.xlsx')
        self.assertEqual([sheet['name'] for sheet in result['sheets']], ['Adatok-JITT','Üres-KIFLI'])
        self.assertEqual(result['sheets'][1]['rows'], [])
        rows = result['sheets'][0]['rows']; self.assertEqual([r['sourceRowNo'] for r in rows], [1,3])
        self.assertEqual(rows[0]['cells'][1]['column'], 3); self.assertEqual(rows[0]['cells'][1]['value'], 0)
        self.assertEqual(rows[1]['cells'][0], dict(column=1,type='f',value='=1+1',cachedValue=2))
        self.assertIs(rows[1]['cells'][1]['value'], False); self.assertEqual(rows[1]['cells'][2]['value'], '001')
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])
        self.assertEqual(raw.cell_value(datetime(2026,9,1)), '2026-09-01T00:00:00')

    def test_same_request_retry_is_idempotent_but_new_upload_is_separate(self):
        client = FakeClient(); id = uuid4(); content = workbook()
        first = raw.save_workbook(client,content,'test.xlsx','2026-09',id,'Admin')
        second = raw.save_workbook(client,content,'test.xlsx','2026-09',id,'Admin')
        self.assertEqual(first, second); self.assertEqual((client.uploads,client.saves),(1,1))
        raw.save_workbook(client,content,'test.xlsx','2026-09',uuid4(),'Admin')
        self.assertEqual(len(client.rows),2)  # No business deduplication in Phase 1.
        with self.assertRaises(raw.RawImportError) as error:
            raw.save_workbook(client,content,'test.xlsx','2026-10',id,'Admin')
        self.assertEqual(error.exception.status,409)
        self.assertTrue(all(table == raw.TABLE for table in client.tables))

    def test_commit_response_loss_is_confirmed_without_deleting_original(self):
        client = FakeClient(); client.lose_commit_response = True
        result = raw.save_workbook(client,workbook(),'test.xlsx','2026-09',uuid4(),'Admin')
        self.assertEqual(result['status'],'saved'); self.assertEqual(len(client.objects),1)

    def test_missing_migration_and_public_storage_never_save(self):
        client = FakeClient(); client.missing = True
        with self.assertRaises(raw.RawImportError) as error:
            raw.save_workbook(client,workbook(),'test.xlsx','2026-09',uuid4(),'Admin')
        self.assertEqual(error.exception.status,503); self.assertEqual(client.uploads,0)
        client = FakeClient(); client.private = False
        with self.assertRaises(raw.RawImportError): raw.save_workbook(client,workbook(),'test.xlsx','2026-09',uuid4(),'Admin')
        self.assertEqual((client.uploads,client.saves),(0,0))

    def test_invalid_workbook_never_claims_success(self):
        client=FakeClient()
        with self.assertRaises(raw.RawImportError): raw.save_workbook(client,b'bad','test.xlsx','2026-09',uuid4(),'Admin')
        self.assertEqual(client.uploads,0); self.assertFalse(client.rows)


class ApiError(Exception):
    def __init__(self,status_code,detail): self.status_code=status_code


class EndpointTest(unittest.TestCase):
    def test_unauthorized_requests_stop_before_reading_files_or_database(self):
        tree=ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {'admin_list_invoice_raw','admin_upload_invoice_raw'}]
        for node in nodes: node.decorator_list=[]
        def reject(user): raise ApiError(403,'Admin required')
        ns=dict(UUID=UUID,Query=lambda **k:0,Cookie=lambda **k:None,Form=lambda *a:None,File=lambda *a:None,UploadFile=object,
                require_user=lambda _: {},require_settlement_dashboard_admin=reject,HTTPException=ApiError,RawImportError=raw.RawImportError)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'raw_api','exec'),ns)
        with self.assertRaises(ApiError): ns['admin_list_invoice_raw']('2026-09',0,50)
        with self.assertRaises(ApiError): asyncio.run(ns['admin_upload_invoice_raw']('2026-09',uuid4(),None))


if __name__=='__main__': unittest.main()
