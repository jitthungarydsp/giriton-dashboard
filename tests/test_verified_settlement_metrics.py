import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('metric_core',Path(__file__).resolve().parents[1]/'resources/settlement_metric_calculation.py')
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class MetricTests(unittest.TestCase):
    def test_all_couriers_all_complaints_and_missing_times(self):
        summary,rows=core.calculate('2026-09-01',[],[],[],[],[
            {'id':'a','courier_id':'1','document_type':'settlement','status':'resolved\r\n','created_at':'2026-10-01T00:00:00Z'},
            {'id':'b','courier_id':'1','document_type':'tig','status':'new'},
            {'id':'c','courier_id':'1','document_type':'tig','status':'deleted'}],[],[{'courier_id':'2'}])
        self.assertEqual(len(rows),2)
        self.assertEqual(summary['complaint_total'],2)
        self.assertEqual(summary['response_count'],1)
        self.assertEqual(summary['source_counts']['response_timed_count'],0)
        self.assertIsNone(rows[0]['opening_to_settlement_hours'])
        self.assertEqual(summary['completed_flow_count'],0)

    def test_created_opening_and_signed_events_preserve_fractions(self):
        statuses=[{'courier_id':'1','action_key':'individual_monthly_billing','status':'done','created_at':'2026-10-01T00:00:00Z','updated_at':'2026-10-20T00:00:00Z'}]
        accepted=[{'courier_id':'1','action_key':key,'process_id':'','accepted_at':value} for key,value in
                  [('settlement','2026-10-02T00:00:00Z'),('tig','2026-10-02T00:01:12Z')]]
        summary,rows=core.calculate('2026-09-01',statuses,accepted,[],[],[],[],[])
        self.assertEqual(rows[0]['opening_to_settlement_hours'],24)
        self.assertAlmostEqual(rows[0]['settlement_to_tig_hours'],0.02)
        self.assertEqual(summary['settlement_to_tig']['count'],1)
        self.assertEqual(summary['completed_flow_count'],0)

    def test_financial_corrections_once_and_zero_is_authoritative(self):
        finance={'courier_id':'1','id':'f','version':2,'items':[
            {'section':'finance','item_key':k,'amount_value':v,'amount_kind':'huf'} for k,v in
            [('monthly_malus',0),('manual_malus',-75000),('deductions',-75000),('correction',-974900)]]}
        summary,rows=core.calculate('2026-09-01',[],[],[],[],[],[finance],[])
        self.assertEqual(summary['malus_total_huf'],75000)
        self.assertEqual(summary['other_deductions_total_huf'],974900)
        self.assertEqual(summary['deductions_total_huf'],1049900)

    def test_positive_atm_is_credit_not_deduction(self):
        finance={'courier_id':'1','id':'f','items':[
            {'section':'finance','item_key':k,'amount_value':v,'amount_kind':'huf'} for k,v in
            [('manual_malus',-113850),('bonus_malus',-113850),('atm_effect',237),('deductions',-113613)]]}
        summary,_=core.calculate('2026-09-01',[],[],[],[],[],[finance],[])
        self.assertEqual(summary['deductions_total_huf'],113850)
        self.assertEqual(summary['other_deductions_total_huf'],0)

if __name__=='__main__':unittest.main()
