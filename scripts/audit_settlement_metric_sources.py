"""Read-only source inventory for rebuilding the two derived metric tables."""
import json
import tomllib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / '.streamlit/secrets.toml').read_text(encoding='utf-8'))

def read(table, schema='public', **params):
    rows = []
    offset = 0
    while True:
        order = {'monthly_process_metric_summary':'period_start.asc','courier_monthly_process_metric':'courier_metric_id.asc','vw_courier_month_profile_snapshot':'courier_id.asc'}.get(table,'id.asc')
        query = urlencode({'order':order, **params, 'limit': 500, 'offset': offset})
        request = Request(CONFIG['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + table + '?' + query,
            headers={'apikey': CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
                     'Authorization': 'Bearer ' + CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
                     'Accept-Profile': schema})
        with urlopen(request, timeout=60) as response:
            batch = json.load(response)
        rows.extend(batch)
        if len(batch) < 500:
            return rows
        offset += len(batch)

if __name__ == '__main__':
    for table, schema, column in [
        ('monthly_process_metric_summary','settlement','period_start'),
        ('courier_monthly_process_metric','settlement','period_start'),
        ('peopleforce_card_statuses','public','document_month'),
        ('peopleforce_complaints','public','document_month'),
        ('pwa_workflow_acceptance_snapshots','settlement','period_start'),
        ('courier_finance_snapshot','settlement','period_start'),
        ('courier_monthly_closure','settlement','period_start'),
        ('peopleforce_documents','public','document_month')]:
        rows = read(table, schema, select='*', order=column + '.asc')
        counts = {}
        for row in rows:
            month = row.get(column)
            counts[month] = counts.get(month, 0) + 1
        print(table, 'columns', list(rows[0]) if rows else [], 'months', json.dumps(counts))
        if table == 'monthly_process_metric_summary':
            print(json.dumps([{k:r.get(k) for k in ('period_start','definition_version','completed_flow_count','complaint_total','source_counts')} for r in rows]))
        if table == 'peopleforce_card_statuses':
            print('actions', sorted(set(r.get('action_key','') for r in rows)))
        if table == 'peopleforce_complaints':
            print('statuses', sorted(set(r.get('status','') or '' for r in rows)))
            print('types', sorted(set(r.get('document_type','') or '' for r in rows)))
