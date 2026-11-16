"""Shared source selection for UI and command-line metric rebuilding."""
from resources.settlement_metric_calculation import calculate

def load_bundle(period, read):
    def rows(table, schema='public', column='document_month', select='*'):
        return read(table, schema=schema, params={'select':select,column:'eq.'+period})
    statuses = rows('peopleforce_card_statuses')
    accepted = rows('pwa_workflow_acceptance_snapshots','settlement','period_start',
                    'id,courier_id,courier_name,action_key,process_id,accepted_at')
    docs = rows('peopleforce_documents',select='id,courier_id,courier_name,document_type,uploaded_at')
    closures = rows('courier_monthly_closure','settlement','period_start',
                    'id,courier_id,courier_name,status,closed_at')
    complaints = rows('peopleforce_complaints')
    finances = rows('courier_finance_snapshot','settlement','period_start',
                    'id,courier_id,courier_name,version,created_at,metadata')
    latest = {}
    for row in finances:
        cid = str(row['courier_id'])
        if cid not in latest or (row['version'],row['created_at'],row['id']) > (latest[cid]['version'],latest[cid]['created_at'],latest[cid]['id']):
            latest[cid] = row
    snapshots = list(latest.values())
    for start in range(0,len(snapshots),40):
        batch = snapshots[start:start+40]
        items = read('courier_finance_snapshot_item',schema='settlement',params={
            'select':'snapshot_id,section,item_key,amount_kind,amount_value',
            'snapshot_id':'in.('+','.join(r['id'] for r in batch)+')'})
        for row in batch:
            row['items'] = [item for item in items if item['snapshot_id'] == row['id']]
    roster = rows('vw_courier_month_profile_snapshot','settlement','period_month','courier_id,driver_name')
    return calculate(period,statuses,accepted,docs,closures,complaints,snapshots,roster)
