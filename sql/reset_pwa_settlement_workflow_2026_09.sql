-- Reset the September 2026 PWA workflow to its first step.
-- Keeps settlement summaries, finance snapshots and manual overrides intact.
-- Removes only workflow progress and courier-visible settlement documents.

begin;

-- Remove every completed/open workflow action for the affected couriers.
with reset_targets as (
    select distinct courier_id::text as courier_id
    from settlement.courier_settlement_summary
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
    union
    select distinct courier_id::text as courier_id
    from settlement.courier_finance_snapshot
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
)
delete from public.peopleforce_card_statuses status_row
where status_row.document_month::date = date '2026-09-01'
  and exists (
      select 1
      from reset_targets
      where reset_targets.courier_id = status_row.courier_id::text
  );

-- Remove settlement/TIG/invoice documents so they cannot reopen the workflow.
-- Complaint documents and complaints are intentionally preserved.
with reset_targets as (
    select distinct courier_id::text as courier_id
    from settlement.courier_settlement_summary
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
    union
    select distinct courier_id::text as courier_id
    from settlement.courier_finance_snapshot
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
)
delete from public.peopleforce_documents document_row
where document_row.document_month::date = date '2026-09-01'
  and lower(split_part(document_row.document_type, ':', 1)) in ('settlement', 'tig', 'invoice')
  and exists (
      select 1
      from reset_targets
      where reset_targets.courier_id = document_row.courier_id::text
  );

with reset_targets as (
    select distinct courier_id::text as courier_id
    from settlement.courier_settlement_summary
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
    union
    select distinct courier_id::text as courier_id
    from settlement.courier_finance_snapshot
    where period_start::date = date '2026-09-01'
      and nullif(courier_id::text, '') is not null
)
select
    'PWA workflow reset completed' as result,
    count(*) as affected_couriers
from reset_targets;

commit;
