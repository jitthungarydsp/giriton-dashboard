from datetime import datetime
import importlib.util
from pathlib import Path
import json
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('draft_management',ROOT/'resources/route_delay_form_drafts.py')
service=importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class DraftManagementTest(unittest.TestCase):
    def data(self):
        return {'Dátum':'2026-10-01','Futár ID':'6498','Futár':'Abonyi György','Túra ID':'1557743',
                'Raktár':'BUD1','Javasolt kategória száma':4,'Kategóriajavaslat':'Optimalizálatlan túra',
                'Adat / megfontolás':'4 külön cím 15 perc alatt','Forrásegyezés':'Egyezik',
                'Kategória futárral egyeztetve':'Igen','Reklamáció indoklása':'Ellenőrzött indoklás.'}
    def record(self):
        return service.make_record(self.data(),2,'source.xlsx','admin')
    def test_import_is_idempotent_and_sent_rows_are_not_overwritten(self):
        row=self.record()
        merged,counts=service.merge_import([row],[row])
        self.assertEqual(counts,dict(added=0,updated=0,skipped=1))
        sent=service.confirm_record(service.prepare_record(row,'admin'),'Google visszaigazolás: 123','admin',True)
        changed=service.make_record({**self.data(),'Reklamáció indoklása':'Új szöveg'},2)
        merged,counts=service.merge_import([sent],[changed],True)
        self.assertEqual(merged,[sent]);self.assertEqual(counts['updated'],0)
    def test_changed_saved_fields_change_prefill_and_reset_review(self):
        row=service.prepare_record(self.record(),'admin')
        changed={**self.data(),'Futár':'Módosított név','Túra ID':'99999','Reklamáció indoklása':'Új végleges indoklás.'}
        updated=service.edit_record(row,changed,'editor')
        self.assertEqual(updated['id'],row['id']);self.assertEqual(updated['state'],'draft')
        draft=service.preparation.prepare_row(updated['data'],updated['source_row'])
        query=parse_qs(urlparse(draft['prefill_url']).query)
        self.assertEqual(query['entry.139333198'],['Módosított név'])
        self.assertEqual(query['entry.584723978'],['99999'])
        self.assertIn('Új végleges indoklás.',query['entry.1757898114'][0])
    def test_preview_does_not_confirm_and_confirmation_requires_evidence(self):
        row=self.record()
        service.preparation.prepare_row(row['data'],2)
        self.assertEqual(row['state'],'draft')
        with self.assertRaises(ValueError):service.confirm_record(row,'proof','admin',True)
        prepared=service.prepare_record(row,'admin')
        with self.assertRaises(ValueError):service.confirm_record(prepared,'proof','admin',False)
        with self.assertRaises(ValueError):service.confirm_record(prepared,'','admin',True)
    def test_missing_checks_block_review_and_sent_edit_is_blocked(self):
        row=service.make_record({**self.data(),'Kategória futárral egyeztetve':'Nem'},2)
        with self.assertRaises(ValueError):service.prepare_record(row,'admin')
        sent=service.confirm_record(service.prepare_record(self.record(),'admin'),'Google proof','admin',True)
        with self.assertRaises(ValueError):service.edit_record(sent,self.data(),'admin')
    def test_excel_dates_and_editable_headers_are_normalized(self):
        row=self.data();row.pop('Javasolt kategória száma');row.pop('Reklamáció indoklása')
        row.update({'Dátum':datetime(2026,10,1),'Kategória száma':4,'Végleges indoklás':'Módosított Excel-indoklás'})
        record=service.make_record(row,2)
        self.assertEqual(record['work_date'],'2026-10-01')
        self.assertEqual(record['data']['Reklamáció indoklása'],'Módosított Excel-indoklás')
    def test_courier_route_collision_is_rejected(self):
        row=self.record()
        with self.assertRaises(ValueError):service.assert_unique([row,{**row,'id':'other'}])
    def test_work_copy_restores_confirmed_state_but_rejects_changed_content(self):
        sent=service.confirm_record(service.prepare_record(self.record(),'admin'),'Google proof 123','admin',True)
        restored=service.read_backup(json.dumps([sent]),'editor')[0]
        self.assertEqual(restored['state'],'sent');self.assertEqual(restored['submitted_at'],sent['submitted_at'])
        sent['data']['Futár']='Different'
        with self.assertRaises(ValueError):service.read_backup(json.dumps([sent]),'editor')
    def test_concurrent_save_requires_matching_version_and_state(self):
        db=Mock();query=db.schema.return_value.table.return_value.update.return_value
        query.eq.return_value=query;query.execute.return_value.data=[]
        row=self.record()
        with self.assertRaisesRegex(ValueError,'közben más'):service.store_edit(db,row,row)
        fields=[call.args[0]for call in query.eq.call_args_list]
        self.assertEqual(fields,['id','content_hash','state','updated_at'])


if __name__=='__main__':unittest.main()
