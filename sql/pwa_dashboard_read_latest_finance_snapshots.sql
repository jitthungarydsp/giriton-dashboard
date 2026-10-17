-- Additive dashboard read model. Does not modify settlement rows or amounts.
-- The separate schema need not be exposed through the Supabase Data API.
begin;

create schema if not exists pwa_dashboard_read;

create or replace view pwa_dashboard_read.latest_finance_snapshots as
select distinct on (period_start, courier_id)
    id, period_start, courier_id, courier_name, warehouse_label,
    version, metadata, created_at
from settlement.courier_finance_snapshot
order by period_start, courier_id, version desc, created_at desc, id desc;

comment on view pwa_dashboard_read.latest_finance_snapshots is
    'Read-only dashboard projection: latest saved finance version per courier/month; no recalculation.';

revoke all on schema pwa_dashboard_read from public, anon, authenticated;
revoke all on pwa_dashboard_read.latest_finance_snapshots from public, anon, authenticated;
grant usage on schema pwa_dashboard_read to service_role;
grant select on pwa_dashboard_read.latest_finance_snapshots to service_role;

-- A read-only bridge in the already exposed settlement schema avoids exposing
-- the new schema or copying any financial data. Invoker permissions apply.
create or replace function settlement.pwa_dashboard_latest_finance_snapshots(p_period_start date)
returns setof pwa_dashboard_read.latest_finance_snapshots
language sql stable security invoker
set search_path = pg_catalog
as $$
    select *
    from pwa_dashboard_read.latest_finance_snapshots
    where period_start = p_period_start
    order by courier_id;
$$;

revoke all on function settlement.pwa_dashboard_latest_finance_snapshots(date)
    from public, anon, authenticated;
grant execute on function settlement.pwa_dashboard_latest_finance_snapshots(date)
    to service_role;

notify pgrst, 'reload schema';
commit;
