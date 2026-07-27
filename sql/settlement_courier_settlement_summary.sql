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
    source.session_id,
    master.courier_id::text,
    source.driver_name,
    min(source.route_date),
    max(source.route_date),
    count(*) filter (where source.is_route_primary),
    sum(case when source.is_route_primary then coalesce(source.orders, 0) else 0 end),
    sum(source.company_base_rate_huf),
    sum(source.courier_base_rate_huf),
    sum(source.courier_tip_huf),
    sum(source.courier_delay_bonus_huf),
    sum(source.courier_compliance_bonus_huf),
    sum(source.courier_other_bonus_huf),
    sum(source.courier_bonus_total_huf),
    sum(source.courier_base_rate_huf + source.courier_tip_huf + source.courier_bonus_total_huf),
    now()
from (
    select
        j.session_id,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        j.route_date, j.is_route_primary, j.company_base_rate_huf, j.courier_base_rate_huf,
        j.courier_tip_huf, j.courier_delay_bonus_huf, j.courier_compliance_bonus_huf,
        j.courier_other_bonus_huf, j.courier_bonus_total_huf,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders
    from settlement.jit_row j
    where j.session_id = p_session_id
) source
left join public.courier_master master
    on lower(trim(master.courier_name)) = lower(trim(source.driver_name))
group by source.session_id, source.driver_name, master.courier_id;
$$;

grant select, insert, update, delete on settlement.courier_settlement_summary to service_role;
grant execute on function settlement.refresh_courier_settlement_summary(uuid) to service_role;

select settlement.refresh_courier_settlement_summary(session_id)
from (select distinct session_id from settlement.jit_row) sessions;

commit;
