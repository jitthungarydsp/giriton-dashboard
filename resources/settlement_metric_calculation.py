"""Pure, auditable courier/month metrics; never changes operational finance rows."""
from datetime import datetime, timezone
from statistics import mean, median

VERSION = '2026-11-16-v2-all-courier-months'
FINANCIAL_TYPES = {'settlement', 'tig', 'invoice', 'invoice_submit', 'invoice_check'}

def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None

def hours(start, end):
    return (end-start).total_seconds()/3600 if start and end and end >= start else None

def duration(values):
    return {'count':len(values), 'average_hours':mean(values) if values else 0,
            'median_hours':median(values) if values else 0}

def calculate(period, statuses, acceptances, documents, closures, complaints, finances, roster):
    sources = (statuses, acceptances, documents, closures, complaints, finances, roster)
    ids = sorted({str(r.get('courier_id') or '').strip() for rows in sources for r in rows} - {''})
    details, all_response_hours = [], []
    for cid in ids:
        select = lambda rows: [r for r in rows if str(r.get('courier_id') or '').strip() == cid]
        states = {r['action_key']:r for r in select(statuses) if not str(r.get('action_key','')).startswith('process:')}
        accepted = [r for r in select(acceptances) if not str(r.get('process_id') or '').strip()]
        docs = [r for r in select(documents) if not str(r.get('document_type','')).startswith('process:')]
        def first(rows, column):
            times = [timestamp(r.get(column)) for r in rows]
            return min((t for t in times if t), default=None)
        def event(action):
            # Signed acceptance is stronger evidence than a mutable workflow row.
            value = first([r for r in accepted if r.get('action_key') == action], 'accepted_at')
            state = states.get(action, {})
            if value is None and str(state.get('status','')).strip().lower() == 'done':
                value = timestamp(state.get('updated_at'))
            return value
        opening_state = states.get('individual_monthly_billing', {})
        # created_at is the first recorded opening row, not its last update.
        opened = timestamp(opening_state.get('created_at'))
        settlement, tig = event('settlement'), event('tig')
        invoice = first([r for r in docs if r.get('document_type') == 'invoice'], 'uploaded_at')
        if invoice is None:
            invoice = event('invoice_submit')
        paid = event('invoice_payment')
        closed = [r for r in select(closures) if r.get('status') == 'done']
        if paid is None:
            paid = first(closed, 'closed_at')
        finance = max(select(finances), key=lambda r:(r.get('version') or 0, r.get('created_at') or '', r.get('id') or ''), default={})
        items = {r['item_key']:float(r.get('amount_value') or 0) for r in finance.get('items', [])
                 if r.get('section') == 'finance' and r.get('amount_kind') == 'huf'}
        meta = finance.get('metadata') or {}
        def amount(key, default=0):
            return items[key] if key in items else float(default or 0)
        malus = sum(abs(min(amount(net, amount(component)),0)) for component,net in
                    [('monthly_malus','kiflis_bonus_malus'),('manual_malus','bonus_malus')])
        correction = abs(min(amount('correction_deduction', amount('correction',meta.get('correction_total'))),0))
        deduction_net = amount('deductions',meta.get('deduction_total'))
        deduction_credits = sum(max(amount(k),0) for k in ('atm_effect','reserve','insurance_fee','salary_advance','other_expense'))
        deduction = abs(min(deduction_net - deduction_credits,0)) + correction
        # The aggregate is authoritative. Missing finance remains explicitly flagged.
        other = max(deduction - malus, 0)
        complaint_rows = [r for r in select(complaints) if str(r.get('status','')).strip().lower() != 'deleted'
                          and str(r.get('document_type','')).strip().lower() in FINANCIAL_TYPES]
        answered = [r for r in complaint_rows if str(r.get('status','')).strip().lower() in {'closed','resolved'}
                    or timestamp(r.get('responded_at')) or str(r.get('admin_response') or '').strip()]
        response_times = [h for r in answered if (h:=hours(timestamp(r.get('created_at')), timestamp(r.get('responded_at')))) is not None]
        all_response_hours.extend(response_times)
        times = {'settlement_opened_at':opened,'settlement_accepted_at':settlement,'tig_accepted_at':tig,
                 'invoice_uploaded_at':invoice,'paid_at':paid}
        stages = {'opening_to_settlement_hours':hours(opened,settlement), 'settlement_to_tig_hours':hours(settlement,tig),
                  'tig_to_invoice_hours':hours(tig,invoice), 'invoice_to_paid_hours':hours(invoice,paid),
                  'opening_to_paid_hours':hours(opened,paid)}
        complete = all(t is not None for t in times.values()) and all(h is not None for h in stages.values())
        evidence = {'definition_version':VERSION,'complete_timeline':complete,
                    'opening_source':'peopleforce_card_statuses.created_at' if opened else None,
                    'finance_snapshot_id':finance.get('id'),'finance_version':finance.get('version'),
                    'finance_available':bool(finance),'response_timed_count':len(response_times),
                    'deduction_net_huf':deduction_net,'deduction_credits_huf':deduction_credits,
                    'complaint_ids':[r['id'] for r in complaint_rows],
                    'missing_events':[k for k,t in times.items() if t is None],
                    'invalid_stage_order':[k for k,h in stages.items() if h is None and all(times.values())],
                    'workflow_statuses':{k:v.get('status') for k,v in states.items()}}
        name = next((r.get('courier_name') or r.get('driver_name') for rows in (select(roster), select(finances), select(statuses), select(complaints)) for r in rows if r.get('courier_name') or r.get('driver_name')), '')
        details.append({'period_start':period,'courier_id':cid,'courier_name':name,
                        **{k:t.isoformat() if t else None for k,t in times.items()},**stages,
                        'financial_complaint_count':len(complaint_rows),'responded_complaint_count':len(answered),
                        'response_average_hours':mean(response_times) if response_times else 0,
                        'malus_huf':malus,'other_deductions_huf':other,'deductions_huf':deduction,
                        'closure_snapshot':evidence,
                        'source_updated_at':max((t for t in times.values() if t),default=None).isoformat() if any(times.values()) else None})
    count = len(details)
    total = lambda field: sum(r[field] for r in details)
    summary = {'period_start':period,'completed_flow_count':sum(r['closure_snapshot']['complete_timeline'] for r in details),
               'complaint_flow_count':sum(r['financial_complaint_count']>0 for r in details),
               'complaint_total':total('financial_complaint_count'),'complaints_average':total('financial_complaint_count')/count if count else 0,
               'response_count':total('responded_complaint_count'),**{'response_'+k:v for k,v in duration(all_response_hours).items() if k != 'count'},
               'deductions_total_huf':total('deductions_huf'),'malus_total_huf':total('malus_huf'),
               'other_deductions_total_huf':total('other_deductions_huf'),'deductions_average_huf':total('deductions_huf')/count if count else 0,
               'source_updated_at':max((r['source_updated_at'] for r in details if r['source_updated_at']),default=None),
               'source_counts':{'courier_month_count':count,'financial_complaints':total('financial_complaint_count'),
                                'response_timed_count':len(all_response_hours),'finance_covered_couriers':sum(r['closure_snapshot']['finance_available'] for r in details),
                                'population':'all couriers with source records in the document month',
                                'opening_definition':'first recorded billing status creation; unknown stays null',
                                'deduction_definition':'latest PWA snapshot gross negative deductions plus negative corrections; positive offsets separately recorded',
                                'excluded_complaints':len(complaints)-total('financial_complaint_count')}}
    for stage in ('opening_to_settlement','settlement_to_tig','tig_to_invoice','invoice_to_paid','opening_to_paid'):
        summary[stage] = duration([r[stage+'_hours'] for r in details if r[stage+'_hours'] is not None])
    for prefix,has_complaint in [('with_complaint',True),('without_complaint',False)]:
        group = [r for r in details if bool(r['financial_complaint_count']) == has_complaint]
        value = sum(r['deductions_huf'] for r in group)
        summary[prefix+'_flow_count'] = len(group)
        summary[prefix+'_deductions_huf'] = value
        summary[prefix+'_deductions_average_huf'] = value/len(group) if group else 0
    return summary, details
