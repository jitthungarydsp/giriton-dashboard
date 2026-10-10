begin;

-- Fast monthly admin dashboard source for the PWA and the Streamlit admin page.
-- The UI should not rebuild this state from documents/statuses/complaints on
-- every load; this view returns one compact row per courier/month.
create or replace view settlement.vw_admin_settlement_dashboard_fast as
with config as (
    select
        period_start::date,
        session_id::text,
        calculation_mode,
        warehouse_label,
        visibility_mode,
        updated_at as config_updated_at
    from settlement.mobile_settlement_period_config
),
latest_snapshots as (
    select distinct on (period_start::date, courier_id::text)
        id,
        period_start::date,
        courier_id::text,
        courier_name::text,
        session_id::text,
        calculation_mode,
        warehouse_label,
        metadata,
        created_at
    from settlement.courier_finance_snapshot
    where period_start is not null
      and nullif(courier_id::text, '') is not null
    order by period_start::date, courier_id::text, version desc, created_at desc
),
snapshot_amounts as (
    select
        snapshot_id,
        max(amount_value) filter (where section = 'finance' and item_key = 'payable') as payable_huf,
        max(amount_value) filter (where section = 'finance' and item_key = 'base') as courier_base_rate_huf,
        max(amount_value) filter (where section = 'finance' and item_key in ('route_bonus_total', 'bonus_total')) as route_bonus_total_huf,
        max(amount_value) filter (where section = 'finance' and item_key = 'tip') as tip_huf
    from settlement.courier_finance_snapshot_item
    group by snapshot_id
),
summary_rows as (
    select
        c.period_start,
        c.session_id,
        c.calculation_mode,
        c.warehouse_label,
        c.visibility_mode,
        s.courier_id::text as courier_id,
        s.driver_name as courier_name,
        coalesce(cm.warehouse_name, '') as warehouse,
        coalesce(s.company_base_rate_huf, 0) as company_base_rate_huf,
        coalesce(s.courier_base_rate_huf, 0) as courier_base_rate_huf,
        coalesce(s.tip_huf, 0) as tip_huf,
        coalesce(s.route_bonus_total_huf, 0) as route_bonus_total_huf,
        coalesce(s.payable_huf, 0) as payable_huf,
        s.calculated_at,
        c.config_updated_at
    from config c
    join settlement.courier_settlement_summary s
        on s.session_id::text = c.session_id
    left join public.courier_master cm
        on cm.courier_id::text = s.courier_id::text
),
snapshot_candidates as (
    select
        period_start,
        courier_id,
        courier_name,
        'snapshot'::text as source
    from latest_snapshots
),
workflow_candidates as (
    select distinct
        document_month::date as period_start,
        courier_id::text,
        null::text as courier_name,
        'document'::text as source
    from public.peopleforce_documents
    where document_month is not null
      and nullif(courier_id::text, '') is not null
    union
    select distinct
        document_month::date as period_start,
        courier_id::text,
        null::text as courier_name,
        'status'::text as source
    from public.peopleforce_card_statuses
    where document_month is not null
      and nullif(courier_id::text, '') is not null
    union
    select distinct
        document_month::date as period_start,
        courier_id::text,
        null::text as courier_name,
        'complaint'::text as source
    from public.peopleforce_complaints
    where document_month is not null
      and nullif(courier_id::text, '') is not null
),
all_candidates as (
    select period_start, courier_id, courier_name, source from snapshot_candidates
    union all
    select period_start, courier_id, courier_name, source from workflow_candidates
    union all
    select period_start, courier_id, courier_name, 'summary'::text as source from summary_rows
),
candidate_rows as (
    select
        c.period_start,
        c.courier_id,
        coalesce(
            max(nullif(c.courier_name, '')),
            max(nullif(cm.courier_name, '')),
            'Futár ' || c.courier_id
        ) as courier_name,
        coalesce(max(nullif(cm.warehouse_name, '')), '') as warehouse,
        array_agg(distinct c.source order by c.source) as sources
    from all_candidates c
    left join public.courier_master cm
        on cm.courier_id::text = c.courier_id
    group by c.period_start, c.courier_id
),
documents as (
    select
        courier_id::text,
        document_month::date as period_start,
        bool_or(lower(split_part(document_type, ':', 1)) = 'settlement') as has_settlement_document,
        bool_or(lower(split_part(document_type, ':', 1)) = 'tig') as has_tig_document,
        max(uploaded_at) as last_document_at
    from public.peopleforce_documents
    where document_month is not null
    group by courier_id::text, document_month::date
),
latest_statuses as (
    select distinct on (courier_id::text, document_month::date, action_key)
        courier_id::text,
        document_month::date as period_start,
        lower(action_key) as action_key,
        lower(coalesce(status, '')) as status,
        updated_at
    from public.peopleforce_card_statuses
    where document_month is not null
      and coalesce(action_key, '') !~* '^process:[a-z0-9_-]+:'
    order by courier_id::text, document_month::date, action_key, updated_at desc nulls last
),
status_pivot as (
    select
        courier_id,
        period_start,
        bool_or(action_key = 'settlement' and status in ('open', 'done')) as settlement_started,
        bool_or(action_key = 'settlement' and status = 'done') as settlement_done,
        bool_or(action_key = 'tig' and status in ('open', 'done')) as tig_started,
        bool_or(action_key = 'tig' and status = 'done') as tig_done,
        bool_or(action_key = 'invoice_submit' and status = 'open') as invoice_submit_open,
        bool_or(action_key = 'invoice_submit' and status = 'done') as invoice_submit_done,
        bool_or(action_key = 'invoice_check' and status = 'open') as invoice_check_open,
        bool_or(action_key = 'invoice_check' and status = 'done') as invoice_check_done,
        bool_or(action_key = 'invoice_payment' and status = 'done') as invoice_payment_done,
        max(updated_at) as last_status_at
    from latest_statuses
    group by courier_id, period_start
),
complaints as (
    select
        courier_id::text,
        document_month::date as period_start,
        count(*) filter (
            where lower(coalesce(status, '')) not in ('resolved', 'closed', 'deleted')
              and coalesce(admin_response, '') = ''
              and responded_at is null
              and coalesce(document_type, '') !~* '^process:[a-z0-9_-]+:'
        )::integer as open_complaints,
        max(coalesce(updated_at, created_at)) as last_complaint_at
    from public.peopleforce_complaints
    where document_month is not null
    group by courier_id::text, document_month::date
),
dashboard_rows as (
    select
        cr.period_start,
        coalesce(ls.session_id, sr.session_id, cfg.session_id) as session_id,
        coalesce(ls.calculation_mode, sr.calculation_mode, cfg.calculation_mode) as calculation_mode,
        coalesce(ls.warehouse_label, sr.warehouse_label, cfg.warehouse_label) as warehouse_label,
        coalesce(sr.visibility_mode, cfg.visibility_mode) as visibility_mode,
        cr.courier_id,
        coalesce(nullif(ls.courier_name, ''), nullif(sr.courier_name, ''), cr.courier_name) as courier_name,
        coalesce(nullif(sr.warehouse, ''), nullif(cr.warehouse, ''), '') as warehouse,
        cr.sources,
        coalesce(sr.company_base_rate_huf, 0) as company_base_rate_huf,
        coalesce(sa.courier_base_rate_huf, sr.courier_base_rate_huf, 0) as courier_base_rate_huf,
        coalesce(sa.tip_huf, sr.tip_huf, 0) as tip_huf,
        coalesce(sa.route_bonus_total_huf, sr.route_bonus_total_huf, 0) as route_bonus_total_huf,
        coalesce(
            sa.payable_huf,
            nullif(replace(regexp_replace(coalesce(ls.metadata ->> 'payable_total', ''), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric,
            sr.payable_huf,
            0
        ) as payable_huf,
        sr.calculated_at,
        coalesce(d.has_settlement_document, false) as has_settlement_document,
        coalesce(d.has_tig_document, false) as has_tig_document,
        coalesce(sp.settlement_started, false) as settlement_started,
        coalesce(sp.settlement_done, false) as settlement_done,
        coalesce(sp.tig_started, false) as tig_started,
        coalesce(sp.tig_done, false) as tig_done,
        coalesce(sp.invoice_submit_open, false) as invoice_submit_open,
        coalesce(sp.invoice_submit_done, false) as invoice_submit_done,
        coalesce(sp.invoice_check_open, false) as invoice_check_open,
        coalesce(sp.invoice_check_done, false) as invoice_check_done,
        coalesce(sp.invoice_payment_done, false) as invoice_payment_done,
        coalesce(cp.open_complaints, 0) as open_complaints,
        greatest(
            coalesce(sr.calculated_at, '-infinity'::timestamptz),
            coalesce(ls.created_at, '-infinity'::timestamptz),
            coalesce(d.last_document_at, '-infinity'::timestamptz),
            coalesce(sp.last_status_at, '-infinity'::timestamptz),
            coalesce(cp.last_complaint_at, '-infinity'::timestamptz),
            coalesce(cfg.config_updated_at, '-infinity'::timestamptz)
        ) as updated_at
    from candidate_rows cr
    left join config cfg
        on cfg.period_start = cr.period_start
    left join latest_snapshots ls
        on ls.period_start = cr.period_start
       and ls.courier_id = cr.courier_id
    left join snapshot_amounts sa
        on sa.snapshot_id = ls.id
    left join summary_rows sr
        on sr.period_start = cr.period_start
       and sr.courier_id = cr.courier_id
    left join documents d
        on d.period_start = cr.period_start
       and d.courier_id = cr.courier_id
    left join status_pivot sp
        on sp.period_start = cr.period_start
       and sp.courier_id = cr.courier_id
    left join complaints cp
        on cp.period_start = cr.period_start
       and cp.courier_id = cr.courier_id
)
select
    *,
    case
        when open_complaints > 0 then 'Reklamáció'
        when invoice_payment_done then 'Kifizetve'
        when invoice_check_open or (invoice_submit_done and not invoice_check_done) then 'Számla ellenőrzésre vár'
        when invoice_submit_open or (tig_done and not invoice_submit_done) then 'Számlafeltöltésre vár'
        when (has_tig_document or tig_started or settlement_done) and not tig_done then 'TIG elfogadásra vár'
        when (has_settlement_document or settlement_started or session_id is not null) and not settlement_done then 'Elszámolás elfogadásra vár'
        when has_settlement_document or settlement_started or session_id is not null then 'Elszámolás'
        else 'Elszámolás készül'
    end as dashboard_status_label,
    case
        when open_complaints > 0 then open_complaints::text || ' nyitott reklamáció'
        when invoice_payment_done then 'Folyamat lezárva'
        when invoice_check_open or (invoice_submit_done and not invoice_check_done) then 'Számla beérkezett'
        when invoice_submit_open or (tig_done and not invoice_submit_done) then 'Futár teendő'
        when (has_tig_document or tig_started or settlement_done) and not tig_done then 'Futár teendő'
        when (has_settlement_document or settlement_started or session_id is not null) and not settlement_done then 'Futár teendő'
        when has_settlement_document or settlement_started or session_id is not null then 'Folyamatban'
        else 'Várakozás'
    end as dashboard_status_detail,
    case
        when open_complaints > 0 then 'attention'
        when invoice_payment_done then 'done'
        when invoice_check_open or (invoice_submit_done and not invoice_check_done) then 'warning'
        when invoice_submit_open or (tig_done and not invoice_submit_done) then 'waiting'
        when (has_tig_document or tig_started or settlement_done) and not tig_done then 'waiting'
        when (has_settlement_document or settlement_started or session_id is not null) and not settlement_done then 'waiting'
        when has_settlement_document or settlement_started or session_id is not null then 'active'
        else 'muted'
    end as dashboard_status_tone,
    case
        when open_complaints > 0 then 20
        when invoice_payment_done then 90
        when invoice_check_open or (invoice_submit_done and not invoice_check_done) then 70
        when invoice_submit_open or (tig_done and not invoice_submit_done) then 60
        when (has_tig_document or tig_started or settlement_done) and not tig_done then 50
        when (has_settlement_document or settlement_started or session_id is not null) and not settlement_done then 40
        when has_settlement_document or settlement_started or session_id is not null then 30
        else 10
    end as dashboard_status_sort
from dashboard_rows;

grant select on settlement.vw_admin_settlement_dashboard_fast to service_role;

notify pgrst, 'reload schema';

commit;
