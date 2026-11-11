import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('excel_form_drafts', ROOT/'scripts/prepare_route_delay_forms.py')
drafts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drafts)


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
        self.assertIn('Okság nem bizonyított',fields['entry.1757898114'][0])
        self.assertNotIn('\n · ',draft['payload']['description'])

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


if __name__=='__main__':unittest.main()
