"""Rebuild only derived metrics. Dry-run by default; --write backs up and verifies DB rows."""
import argparse
import json
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

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

def upsert(table, payload, conflict, *, return_rows=True):
    request = Request(CONFIG['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table+'?'+urlencode({'on_conflict':conflict}),
        data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),method='POST',headers={
            'apikey':CONFIG['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
            'Accept-Profile':'settlement','Content-Profile':'settlement','Content-Type':'application/json',
            'Prefer':'resolution=merge-duplicates,return='+('representation' if return_rows else 'minimal')})
    for attempt in range(3):
        try:
            with urlopen(request,timeout=90) as response:
                return json.load(response) if return_rows else None
        except (HTTPError, URLError, TimeoutError) as error:
            if attempt == 2 or isinstance(error, HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                raise
            sleep(2 ** attempt)

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


def recent_months(today, count):
    month = today.replace(day=1)
    for _ in range(count):
        yield month.isoformat()
        month = (month - timedelta(days=1)).replace(day=1)


def publish(summary, details, previous_summary, previous_details):
    period = summary['period_start']
    expected_ids = {r['courier_id'] for r in details}
    if {r['courier_id'] for r in previous_details} - expected_ids:
        raise RuntimeError(f'{period}: some existing courier metrics are missing from the source; summary left intact')
    if not previous_summary:
        # The child rows need an existing parent for a newly available month.
        # Its primary key is stable even if the request needs to be retried.
        first = {'period_start': period, 'source_counts': {'refresh_pending': True}}
        summary['summary_id'] = upsert('monthly_process_metric_summary', first, 'period_start')[0]['summary_id']
    for row in details:
        row.update(summary_id=summary['summary_id'], calculated_at=summary['calculated_at'],
                   calculated_by=summary['calculated_by'])
    # The detailed replacement is a single atomic request. Publish the new
    # headline only after every detail was written for this generation.
    upsert('courier_monthly_process_metric', details, 'period_start,courier_id', return_rows=False)
    actual_details = read('courier_monthly_process_metric', 'settlement', period_start='eq.'+period)
    validate(summary, actual_details)
    assert {r['courier_id'] for r in actual_details} == expected_ids
    assert all(datetime.fromisoformat(row['calculated_at']) == datetime.fromisoformat(summary['calculated_at'])
               for row in actual_details)
    saved = upsert('monthly_process_metric_summary', summary, 'period_start')[0]
    assert datetime.fromisoformat(saved['calculated_at']) == datetime.fromisoformat(summary['calculated_at'])
    validate(saved, actual_details)

def rebuild_month(month, now, folder, write):
    previous_summary=read('monthly_process_metric_summary','settlement',period_start='eq.'+month)
    previous_details=read('courier_monthly_process_metric','settlement',period_start='eq.'+month)
    (folder/(month+'_before.json')).write_text(json.dumps({'summary':previous_summary,'details':previous_details},ensure_ascii=False),encoding='utf-8')
    summary,details=load_bundle(month,source_read)
    validate(summary,details)
    if not details:
        if previous_summary:
            raise RuntimeError(f'{month}: sources returned no courier rows; saved metrics left intact')
        print(f'{month}: no settlement data yet', flush=True)
        return None
    summary.update(definition_version=VERSION,calculated_at=now.isoformat(),calculated_by='verified-metric-rebuild')
    if previous_summary:
        summary['summary_id']=previous_summary[0]['summary_id']
    (folder/(month+'_calculated.json')).write_text(json.dumps({'summary':summary,'details':details},ensure_ascii=False),encoding='utf-8')
    if write:
        publish(summary, details, previous_summary, previous_details)
    line={'month':month,'couriers':len(details),'complete':summary['completed_flow_count'],'complaints':summary['complaint_total'],
          'answered':summary['response_count'],'timed_responses':summary['source_counts']['response_timed_count'],
          'deductions':summary['deductions_total_huf'],'finance_coverage':summary['source_counts']['finance_covered_couriers'],'written':write}
    return line


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    month_selection = parser.add_mutually_exclusive_group()
    month_selection.add_argument('--months', nargs='+')
    month_selection.add_argument('--recent-months', type=int)
    args=parser.parse_args()
    if any(not CONFIG.get(key) for key in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY')):
        parser.error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required')
    if args.recent_months is not None and not 1 <= args.recent_months <= 12:
        parser.error('--recent-months must be between 1 and 12')
    months = set()
    for value in args.months or []:
        try:
            month = date.fromisoformat(value + '-01' if len(value) == 7 else value)
            if month.day != 1:
                raise ValueError()
            months.add(month.isoformat())
        except ValueError:
            parser.error(f'invalid month: {value!r}')
    if args.recent_months is not None:
        months.update(recent_months(datetime.now(ZoneInfo('Europe/Budapest')).date(), args.recent_months))
    if not months:
        for table,schema,column in [('monthly_process_metric_summary','settlement','period_start'),('peopleforce_card_statuses','public','document_month'),('peopleforce_complaints','public','document_month')]:
            months.update(r[column] for r in read(table,schema,select=column) if r.get(column))
    now=datetime.now(timezone.utc)
    folder=ROOT/'outputs'/('verified_metrics_'+now.strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir(parents=True,exist_ok=True)
    report=[]
    failed = False
    for month in sorted(months, reverse=True):
        try:
            line = rebuild_month(month, now, folder, args.write)
        except Exception as error:
            print(f'{month}: refresh failed: {error}', file=sys.stderr, flush=True)
            failed = True
            continue
        if line is not None:
            report.append(line)
            print(json.dumps(line), flush=True)
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('BACKUP_AND_REPORT',folder,flush=True)
    if failed:
        raise SystemExit(1)

if __name__=='__main__': main()
