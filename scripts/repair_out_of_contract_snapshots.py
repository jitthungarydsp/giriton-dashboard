"""Repair the two verified October snapshot regressions; dry-run unless --apply.

Stage children under version -1, verify, then publish the next positive version.
History is retained. No emails are sent. Refuse changed source/workflow state.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from audit_settlement_metric_sources import CONFIG, ROOT, read

MONTH = '2026-10-01'
SESSION = '83cef907-5d14-44a3-887d-95257f6092b8'
TARGETS = {'7440': 31020, '6959': 93240}
ACTOR = 'out-of-contract-bonus-repair-20261117'
ITEM_FIELDS = ('section','item_key','item_label','amount_value','amount_kind','note','display_order')
SOURCE_FIELDS = ('source_key','source_table','payload','row_count')


def write(method, table, payload=None, **params):
    request = Request(CONFIG['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table+'?'+urlencode(params),
        method=method, data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode() if payload is not None else None,
        headers={'apikey':CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
                 'Authorization':'Bearer '+CONFIG['SUPABASE_SERVICE_ROLE_KEY'],
                 'Accept-Profile':'settlement','Content-Profile':'settlement',
                 'Content-Type':'application/json','Prefer':'return=representation'})
    with urlopen(request, timeout=60) as response:
        body=response.read()
        return json.loads(body) if body else []


def fingerprint(snapshot, items):
    financial = [dict(section=i['section'],item_key=i['item_key'],amount_huf=int(round(i['amount_value'])))
                 for i in items if i['amount_kind']=='huf']
    canonical = dict(format='financial-items-v2',period_start=MONTH,courier_id=snapshot['courier_id'],
                     items=sorted(financial,key=lambda i:(i['section'],i['item_key'])))
    return hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def build_repair(previous, original_items, original_sources, expected):
    items=[{k:i[k] for k in ITEM_FIELDS} for i in deepcopy(original_items)]
    sources=[{k:s[k] for k in SOURCE_FIELDS} for s in deepcopy(original_sources)]
    by_key={(i['section'],i['item_key']):i for i in items}
    assert len(by_key)==len(items), 'Duplicate financial keys'
    assert by_key['finance','address_bonus_kifli']['amount_value']==0
    delta=expected
    for key in ('address_bonus_kifli','income','payable'):
        by_key['finance',key]['amount_value']+=delta
    for key in ('tig_transfer_service','tig_final_total'):
        by_key['tig',key]['amount_value']+=delta
    source_map={s['source_key']:s for s in sources}
    assert source_map['settlement_summary']['payload']['other_route_bonus_huf']==expected
    tig=source_map['tig_breakdown']['payload']
    assert tig['taxMode']=='aam' and tig['cashGrossHuf']==0, 'Repair is limited to verified AAM/no-cash cases'
    old_payable=by_key['finance','payable']['amount_value']-delta
    assert tig['payableHuf']==tig['finalTotalHuf']==old_payable
    assert by_key['tig','tig_final_total']['amount_value']==old_payable+delta
    for key in ('payableHuf','finalTotalHuf','transferServiceHuf'):
        tig[key]+=delta
    service=next(r for r in tig['rows'] if r['key']=='transfer_service')
    assert service['vatHuf']==0
    service['netHuf']+=delta
    service['grossHuf']+=delta
    assert sum(r['grossHuf'] for r in tig['rows'])==tig['finalTotalHuf']
    working=source_map['working_row']['payload']
    working['Szerződésen kívüli bónusz']=expected
    working['Kifizetendő']=old_payable+delta
    drilldowns=source_map.get('card_drilldowns',{}).get('payload',{})
    for row in drilldowns.get('Szerződésen kívüli bónusz',[]):
        row['Összeg']=expected
    for row in drilldowns.get('Mobilon látható értékek',[]):
        if row.get('item_key') in ('address_bonus_kifli','income','payable'):
            row['amount_value']=by_key['finance',row['item_key']]['amount_value']
    metadata=deepcopy(previous['metadata'])
    for key in ('income_total','payable_total','tig_final_total'):
        metadata[key]+=delta
    metadata.update(source=ACTOR,out_of_contract_bonus_huf=expected,
                    repair_previous_snapshot_id=previous['id'])
    snapshot={k:previous[k] for k in ('period_start','courier_id','courier_name','source','calculation_mode','warehouse_label','session_id')}
    snapshot.update(id=str(uuid4()),version=previous['version']+1,metadata=metadata,
                    previous_snapshot_id=previous['id'],previous_fingerprint=previous['fingerprint'],
                    changed_from_previous=True,created_by=ACTOR)
    snapshot['fingerprint']=fingerprint(snapshot,items)
    assert by_key['finance','income']['amount_value']+by_key['finance','deductions']['amount_value']+metadata['correction_total']==old_payable+delta
    return snapshot,items,sources


def latest(cid):
    return read('courier_finance_snapshot','settlement',period_start='eq.'+MONTH,
                courier_id='eq.'+cid,order='version.desc')[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    folder=ROOT/'outputs'/'bonus_comparison_20261117'/('repair_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir(parents=True,exist_ok=True)
    plans=[]
    for cid,expected in TARGETS.items():
        previous=latest(cid)
        items=read('courier_finance_snapshot_item','settlement',snapshot_id='eq.'+previous['id'])
        current=next(i['amount_value'] for i in items if i['section']=='finance' and i['item_key']=='address_bonus_kifli')
        if current==expected:
            print(cid,'already correct')
            continue
        assert current==0 and previous['session_id']==SESSION
        summary=read('courier_settlement_summary','settlement',session_id='eq.'+SESSION,courier_id='eq.'+cid)[0]
        bonus=read('bonus_route_row','settlement',session_id='eq.'+SESSION,source_sheet='eq.Out_of_contract_Bonus Routes')
        assert sum(r['normalized_data']['Bonus'] for r in bonus if r['normalized_data']['Driver']==summary['driver_name'])==expected
        assert summary['other_route_bonus_huf']==expected
        statuses=read('peopleforce_card_statuses',courier_id='eq.'+cid,document_month='eq.'+MONTH)
        required={'settlement','tig','invoice_submit','invoice_check','invoice_payment'}
        assert {r['action_key'] for r in statuses if r['status']=='open'}>=required, 'Workflow changed; review required'
        documents=read('peopleforce_documents',courier_id='eq.'+cid,document_month='eq.'+MONTH,document_type='eq.tig')
        assert not documents, 'Existing TIG needs review before repair'
        sources=read('courier_finance_snapshot_source','settlement',snapshot_id='eq.'+previous['id'])
        snapshot,new_items,new_sources=build_repair(previous,items,sources,expected)
        backup=dict(previous=previous,items=items,sources=sources,statuses=statuses)
        (folder/(cid+'_before.json')).write_text(json.dumps(backup,ensure_ascii=False,indent=2),encoding='utf-8')
        plan=dict(snapshot=snapshot,items=new_items,sources=new_sources)
        (folder/(cid+'_plan.json')).write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        plans.append((previous,plan))
        print(cid,'bonus',current,'->',expected,'payable',previous['metadata']['payable_total'],'->',snapshot['metadata']['payable_total'],flush=True)
    if not args.apply:
        print('DRY RUN',folder)
        return
    for previous,plan in plans:
        snapshot=plan['snapshot']; cid=snapshot['courier_id']; new_id=snapshot['id']
        assert latest(cid)['id']==previous['id'], 'Concurrent financial update'
        stage=dict(snapshot,version=-1)
        write('POST','courier_finance_snapshot',stage)
        published=False
        try:
            write('POST','courier_finance_snapshot_item',[dict(snapshot_id=new_id,**i) for i in plan['items']])
            write('POST','courier_finance_snapshot_source',[dict(snapshot_id=new_id,**s) for s in plan['sources']])
            saved_items=read('courier_finance_snapshot_item','settlement',snapshot_id='eq.'+new_id)
            saved_sources=read('courier_finance_snapshot_source','settlement',snapshot_id='eq.'+new_id)
            assert len(saved_items)==len(plan['items']) and len(saved_sources)==len(plan['sources'])
            assert fingerprint(snapshot,saved_items)==snapshot['fingerprint']
            assert latest(cid)['id']==previous['id'], 'Concurrent financial update'
            changed=write('PATCH','courier_finance_snapshot',{'version':snapshot['version']},id='eq.'+new_id,version='eq.-1')
            assert len(changed)==1
            published=True
            assert latest(cid)['id']==new_id
            (folder/(cid+'_saved.json')).write_text(json.dumps(changed[0],ensure_ascii=False,indent=2),encoding='utf-8')
            print('SAVED',cid,'version',snapshot['version'],'snapshot',new_id,flush=True)
        finally:
            if not published:
                write('DELETE','courier_finance_snapshot',id='eq.'+new_id,version='eq.-1')
    print('BACKUP',folder)


if __name__=='__main__':
    main()
