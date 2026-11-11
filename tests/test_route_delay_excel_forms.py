import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('excel_form_drafts', ROOT/'scripts/prepare_route_delay_forms.py')
drafts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drafts)
server_spec=importlib.util.spec_from_file_location('excel_form_server',ROOT/'scripts/serve_route_delay_excel_forms.py')
server=importlib.util.module_from_spec(server_spec)
server_spec.loader.exec_module(server)


class RouteDelayDraftTest(unittest.TestCase):
    def row(self):
        return {'Dátum':'2026-10-01','Futár ID':'6498','Futár':'Árvíz & Teszt',
                'Raktár':'BUD1','Túra ID':'1557743','Javasolt kategória száma':4,
                'Kategóriajavaslat':'Optimalizálatlan túra','Besorolás megbízhatósága':'Okság nem bizonyított',
                'Adat / megfontolás':'4 cím 15 perc alatt','Forrásegyezés':'Eltérés'}

    def test_correct_prefill_fields_and_no_submission(self):
        draft = drafts.prepare_row(self.row(), 2)
        url = urlparse(draft['prefill_url']); fields = parse_qs(url.query)
        self.assertTrue(url.path.endswith('/viewform'))
        self.assertEqual(fields['entry.1629541155'], ['6498'])
        self.assertEqual(fields['entry.139333198'], ['Árvíz & Teszt'])
        self.assertEqual(fields['entry.584723978'], ['1557743'])
        self.assertEqual(draft['state'],'draft')
        self.assertEqual(len(draft['warnings']),3)
        description=fields['entry.1757898114'][0]
        self.assertEqual(description, 'Tisztelt Megbízó!\n\nÁrvíz & Teszt kolléga jelezte, hogy a '
                         '1557743 azonosítójú túrán az alábbi ok miatt késett: Optimalizálatlan túra.\n\n'
                         'Kérem szépen a reklamáció feldolgozását.')
        for internal in ['JITT reklamáció:', 'ELLENŐRZENDŐ', 'Okság nem bizonyított', 'Végleges reklamációindoklás hiányzik']:
            self.assertNotIn(internal,description)
        self.assertIn('Végleges reklamációindoklás hiányzik',draft['warnings'])
        self.assertNotIn('\n · ',draft['payload']['description'])

    def test_saved_final_reason_is_kept_in_the_letter(self):
        row=self.row();row['Reklamáció indoklása']='A diszpécserrel egyeztetett részletes indoklás.'
        draft=drafts.prepare_row(row,2)
        description=draft['payload']['description']
        self.assertIn('\n\nA diszpécserrel egyeztetett részletes indoklás.\n\n',description)
        self.assertEqual(draft['evidence'],'4 cím 15 perc alatt')

    def test_missing_identity_and_invalid_category_block_draft(self):
        for key,value in [('Futár ID',''),('Túra ID',''),('Javasolt kategória száma',9)]:
            row=self.row();row[key]=value
            with self.assertRaises(ValueError):drafts.prepare_row(row,2)

    def test_review_is_escaped_and_never_claims_submission(self):
        row=self.row();row['Futár']='<script>alert(1)</script>'
        draft=drafts.prepare_row(row,2)
        with tempfile.TemporaryDirectory() as tmp:
            drafts.write_review([draft],Path(tmp),'source.xlsx')
            page=(Path(tmp)/'urlapok.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',page)
            self.assertIn('Beküldés nem történt',page)
            self.assertNotIn('formResponse',page)
            saved=json.loads((Path(tmp)/'urlaptervezetek.json').read_text(encoding='utf-8'))
            self.assertEqual(saved[0]['state'],'draft')

    def test_running_helper_reads_current_template_each_time(self):
        book=MagicMock()
        book.__getitem__.return_value.iter_rows.side_effect=lambda **kwargs:iter([
            ['Dátum','Futár ID','Forrássor'],['2026-10-01','6498',2]])
        versions=iter(['old','new'])
        def load_template(module):
            version=next(versions)
            module.prepare_row=lambda row,key:{'version':version}
        with patch('openpyxl.load_workbook',return_value=book),patch.object(server.spec.loader,'exec_module',side_effect=load_template):
            self.assertEqual(server.load_draft('unused.xlsx','2')['version'],'old')
            self.assertEqual(server.load_draft('unused.xlsx','2')['version'],'new')

    def test_second_helper_cannot_listen_on_same_port(self):
        first=server.LocalFormServer(('127.0.0.1',0),server.handler_for('unused.xlsx','token'))
        try:
            with self.assertRaises(OSError):
                server.LocalFormServer(first.server_address,server.handler_for('unused.xlsx','token'))
        finally:
            first.server_close()


if __name__=='__main__':unittest.main()
