"""Rebuild only derived metrics. Dry-run by default; --write backs up and verifies DB rows."""
import argparse
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_settlement_metric_sources import CONFIG, ROOT, read
# These pure modules need no Streamlit application bootstrap.
package=types.ModuleType('resources')
package.__path__=[str(ROOT/'resources')]
sys.modules.setdefault('resources',package)
from resources.settlement_metric_repository import load_bundle
from resources.settlement_metric_calculation import VERSION

def source_read(table, *, schema='public', params=None):
    return read(table,schema,**(params or {}))

def upsert(table, payload, conflict):
    request = Request(CONFIG['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table+'?'+urlencode({'on_conflict':conflict}),
        data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),method='POST',headers={
            'apikey':CONFIG['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
            'Accept-Profile':'settlement','Content-Profile':'settlement','Content-Type':'application/json',
            'Prefer':'resolution=merge-duplicates,return=representation'})
    with urlopen(request,timeout=90) as response:
        return json.load(response)

def validate(summary, details):
    assert len(details)==len({r['courier_id'] for r in details})
    assert summary['complaint_total']==sum(r['financial_complaint_count'] for r in details)
    assert summary['response_count']==sum(r['responded_complaint_count'] for r in details)
    assert abs(summary['deductions_total_huf']-sum(r['deductions_huf'] for r in details))<0.01
    assert summary['with_complaint_flow_count']+summary['without_complaint_flow_count']==len(details)
    assert abs(summary['malus_total_huf']+summary['other_deductions_total_huf']-summary['deductions_total_huf'])<0.01
    for row in details:
        assert row['responded_complaint_count']<=row['financial_complaint_count']
        for key,value in row.items():
            if key.endswith('_hours') and value is not None:
                assert value>=0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--months',nargs='+')
    args=parser.parse_args()
    months=set(args.months or [])
    if not months:
        for table,schema,column in [('monthly_process_metric_summary','settlement','period_start'),('peopleforce_card_statuses','public','document_month'),('peopleforce_complaints','public','document_month')]:
            months.update(r[column] for r in read(table,schema,select=column) if r.get(column))
    now=datetime.now(timezone.utc)
    folder=ROOT/'outputs'/('verified_metrics_'+now.strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir(parents=True,exist_ok=True)
    report=[]
    for month in sorted(months):
        if len(month)==7: month+='-01'
        previous_summary=read('monthly_process_metric_summary','settlement',period_start='eq.'+month)
        previous_details=read('courier_monthly_process_metric','settlement',period_start='eq.'+month)
        (folder/(month+'_before.json')).write_text(json.dumps({'summary':previous_summary,'details':previous_details},ensure_ascii=False),encoding='utf-8')
        summary,details=load_bundle(month,source_read)
        validate(summary,details)
        summary.update(definition_version=VERSION,calculated_at=now.isoformat(),calculated_by='verified-metric-rebuild')
        if previous_summary:
            summary['summary_id']=previous_summary[0]['summary_id']
        (folder/(month+'_calculated.json')).write_text(json.dumps({'summary':summary,'details':details},ensure_ascii=False),encoding='utf-8')
        if args.write:
            saved=upsert('monthly_process_metric_summary',summary,'period_start')[0]
            for row in details:
                row.update(summary_id=saved['summary_id'],calculated_at=now.isoformat(),calculated_by='verified-metric-rebuild')
            for start in range(0,len(details),100):
                upsert('courier_monthly_process_metric',details[start:start+100],'period_start,courier_id')
            actual_summary=read('monthly_process_metric_summary','settlement',period_start='eq.'+month)[0]
            actual_details=read('courier_monthly_process_metric','settlement',period_start='eq.'+month)
            validate(actual_summary,actual_details)
            assert len(actual_details)==len(details), 'Unexpected stale courier rows'
            expected={r['courier_id']:r for r in details}
            for row in actual_details:
                for field in ('financial_complaint_count','responded_complaint_count','deductions_huf','opening_to_settlement_hours','settlement_to_tig_hours','invoice_to_paid_hours'):
                    value=expected[row['courier_id']][field]
                    assert row[field] is None if value is None else abs(row[field]-value)<1e-7
        line={'month':month,'couriers':len(details),'complete':summary['completed_flow_count'],'complaints':summary['complaint_total'],
              'answered':summary['response_count'],'timed_responses':summary['source_counts']['response_timed_count'],
              'deductions':summary['deductions_total_huf'],'finance_coverage':summary['source_counts']['finance_covered_couriers'],'written':args.write}
        report.append(line)
        print(json.dumps(line),flush=True)
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('BACKUP_AND_REPORT',folder,flush=True)

if __name__=='__main__': main()
