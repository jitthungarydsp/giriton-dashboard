begin;

-- One persisted settlement row per Excel session and courier.  This is the
-- authoritative route-calculation layer; the UI only reads these values.
create table if not exists settlement.courier_settlement_summary (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    courier_id text,
    driver_name text not null,
    period_start date,
    period_end date,
    route_count integer not null default 0,
    order_count numeric not null default 0,
    company_base_rate_huf numeric not null default 0,
    courier_base_rate_huf numeric not null default 0,
    tip_huf numeric not null default 0,
    delay_bonus_huf numeric not null default 0,
    compliance_bonus_huf numeric not null default 0,
    other_route_bonus_huf numeric not null default 0,
    route_bonus_total_huf numeric not null default 0,
    imported_bonus_huf numeric not null default 0,
    manual_bonus_huf numeric not null default 0,
    customer_rating_bonus_huf numeric not null default 0,
    malus_huf numeric not null default 0,
    atm_deduction_huf numeric not null default 0,
    other_expense_huf numeric not null default 0,
    payable_huf numeric not null default 0,
    calculated_at timestamptz not null default now(),
    constraint courier_settlement_summary_session_driver_unique unique (session_id, driver_name)
);

create index if not exists courier_settlement_summary_session_idx
    on settlement.courier_settlement_summary(session_id);

create or replace function settlement.refresh_courier_settlement_summary(p_session_id uuid)
returns void
language sql
security definer
set search_path = settlement, public
as $$
delete from settlement.courier_settlement_summary where session_id = p_session_id;

insert into settlement.courier_settlement_summary (
    session_id, courier_id, driver_name, period_start, period_end, route_count, order_count,
    company_base_rate_huf, courier_base_rate_huf, tip_huf, delay_bonus_huf,
    compliance_bonus_huf, other_route_bonus_huf, route_bonus_total_huf, payable_huf, calculated_at
)
select
    grouped.session_id,
    coalesce(grouped.courier_id, master.courier_id::text),
    grouped.driver_name,
    grouped.period_start,
    grouped.period_end,
    grouped.route_count,
    grouped.order_count,
    grouped.company_base_rate_huf,
    grouped.courier_base_rate_huf,
    grouped.tip_huf,
    grouped.delay_bonus_huf,
    grouped.compliance_bonus_huf,
    grouped.other_route_bonus_huf,
    grouped.route_bonus_total_huf,
    grouped.payable_huf,
    now()
from (
    select
        source.session_id,
        max(source.courier_id) filter (where source.courier_id is not null) as courier_id,
        source.driver_name,
        min(source.route_date) as period_start,
        max(source.route_date) as period_end,
        count(*) filter (where source.is_route_primary) as route_count,
        sum(case when source.is_route_primary then coalesce(source.orders, 0) else 0 end) as order_count,
        sum(source.company_base_rate_huf) as company_base_rate_huf,
        sum(source.courier_base_rate_huf) as courier_base_rate_huf,
        sum(source.courier_tip_huf) as tip_huf,
        sum(source.courier_delay_bonus_huf) as delay_bonus_huf,
        sum(source.courier_compliance_bonus_huf) as compliance_bonus_huf,
        sum(source.courier_other_bonus_huf) as other_route_bonus_huf,
        sum(source.courier_bonus_total_huf) as route_bonus_total_huf,
        sum(source.courier_base_rate_huf + source.courier_tip_huf + source.courier_bonus_total_huf) as payable_huf
    from (
        select
            j.session_id,
            nullif(coalesce(j.normalized_data ->> 'Courier ID', j.normalized_data ->> 'courier_id'), '') as courier_id,
            coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
            j.route_date, j.is_route_primary, j.company_base_rate_huf, j.courier_base_rate_huf,
            j.courier_tip_huf, j.courier_delay_bonus_huf, j.courier_compliance_bonus_huf,
            j.courier_other_bonus_huf, j.courier_bonus_total_huf,
            coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders
        from settlement.jit_row j
        where j.session_id = p_session_id
    ) source
    group by source.session_id, source.driver_name
) grouped
left join lateral (
    select cm.courier_id
    from public.courier_master cm
    where cm.courier_id::text = grouped.courier_id
       or lower(trim(cm.courier_name)) = lower(trim(grouped.driver_name))
    order by case when cm.courier_id::text = grouped.courier_id then 0 else 1 end, cm.courier_id::text
    limit 1
) master on true;
$$;

grant select, insert, update, delete on settlement.courier_settlement_summary to service_role;
grant execute on function settlement.refresh_courier_settlement_summary(uuid) to service_role;

select settlement.refresh_courier_settlement_summary(session_id)
from (select distinct session_id from settlement.jit_row) sessions;

commit;
