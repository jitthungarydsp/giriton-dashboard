/*
Run this file in Supabase SQL Editor.

It removes only the old public JITT parameter tables, creates their settlement
schema replacements, and writes the calculation result into existing
settlement.jit_row rows. No new route data table is created.
*/

begin;

create schema if not exists settlement;
create extension if not exists pgcrypto;

drop table if exists public.cfg_jitt_rate_parameters cascade;
drop table if exists public.cfg_jitt_periodic_bonuses cascade;
drop table if exists public.cfg_jitt_rate_parameter_names cascade;
drop table if exists public.cfg_jitt_day_definitions cascade;
drop table if exists public.cfg_jitt_base_rates cascade;
drop table if exists public.cfg_jitt_delay_bonus_rules cascade;
drop table if exists public.cfg_jitt_compliance_bonus_rules cascade;
drop table if exists public.cfg_jitt_periodic_fees cascade;

create table if not exists settlement.cfg_jitt_day_definitions (
    id uuid primary key default gen_random_uuid(),
    day_type text not null check (day_type in ('highlighted', 'normal')),
    weekdays smallint[] not null check (cardinality(weekdays) > 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists settlement.cfg_jitt_base_rates (
    id uuid primary key default gen_random_uuid(),
    day_type text not null check (day_type in ('highlighted', 'normal', 'any')),
    route_type text not null check (route_type in ('express', 'normal', 'regional', 'any')),
    warehouse_code text,
    company_amount_huf integer not null default 0 check (company_amount_huf >= 0),
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    calculation_unit text not null default 'per_route' check (calculation_unit in ('fixed', 'per_route', 'per_order', 'per_hour')),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists settlement.cfg_jitt_delay_bonus_rules (
    id uuid primary key default gen_random_uuid(),
    level_code text not null,
    day_type text not null check (day_type in ('highlighted', 'normal', 'any')),
    route_type text not null check (route_type in ('express', 'normal', 'regional', 'any')),
    warehouse_code text,
    threshold_min numeric,
    threshold_max numeric,
    threshold_min_inclusive boolean not null default true,
    threshold_max_inclusive boolean not null default true,
    duration_min_hours numeric,
    duration_max_hours numeric,
    company_amount_huf integer not null default 0 check (company_amount_huf >= 0),
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    calculation_unit text not null default 'per_route' check (calculation_unit in ('fixed', 'per_route', 'per_order', 'per_hour')),
    calculation_mode text not null default 'excel' check (calculation_mode in ('excel', 'api', 'custom')),
    excel_source_field text,
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from),
    check (threshold_max is null or threshold_min is null or threshold_max >= threshold_min),
    check (duration_max_hours is null or duration_min_hours is null or duration_max_hours >= duration_min_hours)
);

create table if not exists settlement.cfg_jitt_compliance_bonus_rules (
    like settlement.cfg_jitt_delay_bonus_rules including all
);

alter table settlement.cfg_jitt_delay_bonus_rules
    add column if not exists excel_source_field text;
alter table settlement.cfg_jitt_compliance_bonus_rules
    add column if not exists excel_source_field text;

create table if not exists settlement.cfg_jitt_periodic_fees (
    id uuid primary key default gen_random_uuid(),
    fee_name text not null,
    day_type text not null check (day_type in ('highlighted', 'normal', 'any')),
    route_type text not null check (route_type in ('express', 'normal', 'regional', 'any')),
    weekdays integer[] not null default '{}',
    warehouse_code text,
    condition_metric text not null default 'none' check (condition_metric in ('none', 'orders_per_route', 'routes_per_day', 'routes_in_period', 'orders_in_period', 'every_n_routes_per_day', 'every_n_routes_in_period')),
    condition_min numeric,
    condition_max numeric,
    company_amount_huf integer not null default 0 check (company_amount_huf >= 0),
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    calculation_unit text not null default 'per_route' check (calculation_unit in ('fixed', 'per_route', 'per_order', 'per_hour')),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from),
    check (condition_max is null or condition_min is null or condition_max >= condition_min),
    check (weekdays <@ array[1,2,3,4,5,6,7])
);

alter table settlement.cfg_jitt_periodic_fees
    add column if not exists weekdays integer[] not null default '{}';

alter table settlement.cfg_jitt_periodic_fees
    drop constraint if exists cfg_jitt_periodic_fees_condition_metric_check,
    add constraint cfg_jitt_periodic_fees_condition_metric_check
    check (condition_metric in ('none', 'orders_per_route', 'routes_per_day', 'routes_in_period', 'orders_in_period', 'every_n_routes_per_day', 'every_n_routes_in_period'));

alter table settlement.cfg_jitt_periodic_fees
    drop constraint if exists cfg_jitt_periodic_fees_weekdays_check,
    add constraint cfg_jitt_periodic_fees_weekdays_check
    check (weekdays <@ array[1,2,3,4,5,6,7]);

create table if not exists settlement.cfg_jitt_reserve_insurance_rules (
    id uuid primary key default gen_random_uuid(),
    insurance_fee_huf integer not null default 0 check (insurance_fee_huf >= 0),
    base_insurance_total_huf integer not null default 0 check (base_insurance_total_huf >= 0),
    reserve_target_huf integer not null default 50000 check (reserve_target_huf >= 0),
    deduction_percent numeric not null check (deduction_percent between 0 and 100),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists settlement.cfg_jitt_loyalty_bonus_rules (
    id uuid primary key default gen_random_uuid(),
    loyalty_start_date date not null,
    loyalty_months_required integer not null default 0 check (loyalty_months_required >= 0),
    route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    calculation_unit text not null default 'per_route' check (calculation_unit in ('per_route', 'per_order')),
    bonus_amount_huf integer not null default 0 check (bonus_amount_huf >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

alter table settlement.cfg_jitt_loyalty_bonus_rules
    add column if not exists loyalty_months_required integer not null default 0 check (loyalty_months_required >= 0),
    add column if not exists route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    add column if not exists calculation_unit text not null default 'per_route' check (calculation_unit in ('per_route', 'per_order'));

create table if not exists settlement.cfg_jitt_life_insurance_rules (
    id uuid primary key default gen_random_uuid(),
    life_insurance_amount_huf integer not null default 0 check (life_insurance_amount_huf >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists settlement.cfg_jitt_customer_rating_rules (
    id uuid primary key default gen_random_uuid(),
    level_code text not null default 'Ügyfélértékelés',
    route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    rating_min_percent numeric,
    rating_max_percent numeric,
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from),
    check (rating_max_percent is null or rating_min_percent is null or rating_max_percent >= rating_min_percent)
);

alter table settlement.cfg_jitt_customer_rating_rules
    add column if not exists route_type text not null default 'normal'
    check (route_type in ('normal', 'express', 'regional', 'any'));

alter table settlement.jit_row
    add column if not exists route_unique_id text,
    add column if not exists route_date date,
    add column if not exists weekday_iso smallint,
    add column if not exists calculated_day_type text,
    add column if not exists company_base_rate_huf numeric not null default 0,
    add column if not exists courier_base_rate_huf numeric not null default 0,
    add column if not exists courier_tip_huf numeric not null default 0,
    add column if not exists is_route_primary boolean not null default false,
    add column if not exists base_rate_status text not null default 'pending',
    add column if not exists base_rate_calculated_at timestamptz;

create or replace function settlement.recalculate_jitt_base_rates(p_session_id uuid)
returns void
language sql
security definer
set search_path = settlement, public
as $$
with raw as (
    select
        j.id,
        j.session_id,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        coalesce(nullif(j.normalized_data ->> 'Route Unique ID', ''), nullif(j.normalized_data ->> 'route_unique_id', ''), j.id::text) as route_unique_id,
        case
            when date_value.date_text ~ '^\d{4}-\d{2}-\d{2}'
                then left(date_value.date_text, 10)::date
            when date_value.date_text ~ '^\d{4}/\d{2}/\d{2}'
                then to_date(left(date_value.date_text, 10), 'YYYY/MM/DD')
            when date_value.date_text ~ '^\d{1,2}[./-]\d{1,2}[./-]\d{4}$'
                then to_date(replace(replace(date_value.date_text, '.', '/'), '-', '/'), 'DD/MM/YYYY')
            when date_value.date_text ~ '^\d{5}(\.0+)?$'
                then date '1899-12-30' + date_value.date_text::numeric::integer
        end as work_date,
        case
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%express%' then 'express'
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%region%' then 'regional'
            else 'normal'
        end as route_type,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Tip', j.normalized_data ->> 'tip_huf', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as tip_huf
    from settlement.jit_row j
    cross join lateral (
        select coalesce(
            nullif(j.normalized_data ->> 'Date', ''),
            nullif(j.normalized_data ->> 'date', ''),
            nullif(j.normalized_data ->> 'Dátum', ''),
            nullif(j.normalized_data ->> 'work_date', ''),
            (select item.value from jsonb_each_text(j.normalized_data) as item(key, value) where lower(trim(item.key)) in ('date', 'dátum', 'datum', 'work_date') limit 1),
            ''
        ) as date_text
    ) date_value
    where j.session_id = p_session_id
), ranked as (
    select raw.*, row_number() over (partition by route_unique_id order by id) as route_rank
    from raw
), resolved as (
    select
        r.*,
        coalesce(day_rule.day_type, 'normal') as resolved_day_type,
        rate.id as rate_id,
        rate.company_amount_huf,
        rate.courier_amount_huf,
        rate.calculation_unit
    from ranked r
    left join lateral (
        select d.day_type
        from settlement.cfg_jitt_day_definitions d
        where d.is_active and d.deleted_at is null
          and r.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and extract(isodow from r.work_date)::smallint = any(d.weekdays)
        order by d.priority, d.id
        limit 1
    ) day_rule on true
    left join lateral (
        select b.*
        from settlement.cfg_jitt_base_rates b
        where b.is_active and b.deleted_at is null
          and r.work_date between b.valid_from and coalesce(b.valid_to, 'infinity'::date)
          and b.day_type in (coalesce(day_rule.day_type, 'normal'), 'any')
          and b.route_type in (r.route_type, 'any')
        order by b.priority,
                 case when b.day_type = coalesce(day_rule.day_type, 'normal') then 0 else 1 end,
                 case when b.route_type = r.route_type then 0 else 1 end,
                 b.id
        limit 1
    ) rate on true
)
update settlement.jit_row j
set
    route_unique_id = resolved.route_unique_id,
    route_date = resolved.work_date,
    weekday_iso = case when resolved.work_date is not null then extract(isodow from resolved.work_date)::smallint end,
    calculated_day_type = resolved.resolved_day_type,
    company_base_rate_huf = case
        when resolved.route_rank <> 1 then 0
        when resolved.calculation_unit = 'per_order' then coalesce(resolved.company_amount_huf, 0) * resolved.orders
        when resolved.calculation_unit = 'per_route' then coalesce(resolved.company_amount_huf, 0)
        else 0
    end,
    courier_base_rate_huf = case
        when resolved.route_rank <> 1 then 0
        when resolved.calculation_unit = 'per_order' then coalesce(resolved.courier_amount_huf, 0) * resolved.orders
        when resolved.calculation_unit = 'per_route' then coalesce(resolved.courier_amount_huf, 0)
        else 0
    end,
    courier_tip_huf = case when resolved.route_rank = 1 then resolved.tip_huf else 0 end,
    is_route_primary = resolved.route_rank = 1,
    base_rate_status = case
        when resolved.route_rank <> 1 then 'duplicate_route_id'
        when resolved.work_date is null then 'missing_excel_date'
        when resolved.rate_id is null then 'missing_base_rate'
        when resolved.calculation_unit not in ('per_route', 'per_order') then 'unsupported_unit'
        else 'calculated'
    end,
    base_rate_calculated_at = now()
from resolved
where j.id = resolved.id;
$$;

create or replace view settlement.vw_parameterized_courier_base_summary as
select
    session_id,
    coalesce(nullif(normalized_data ->> 'Driver', ''), nullif(normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
    sum(courier_base_rate_huf) as courier_base_rate_huf,
    sum(company_base_rate_huf) as company_base_rate_huf,
    sum(courier_tip_huf) as tip_huf,
    count(*) filter (where is_route_primary and calculated_day_type = 'highlighted') as highlighted_routes,
    count(*) filter (where is_route_primary and calculated_day_type = 'normal') as normal_routes,
    count(*) filter (where is_route_primary and base_rate_status = 'calculated') as calculated_routes,
    count(*) filter (where is_route_primary and base_rate_status <> 'calculated') as uncalculated_routes
from settlement.jit_row
group by session_id, coalesce(nullif(normalized_data ->> 'Driver', ''), nullif(normalized_data ->> 'driver_name', ''), 'Ismeretlen futár');

grant usage on schema settlement to service_role;
grant select, insert, update, delete on settlement.cfg_jitt_day_definitions, settlement.cfg_jitt_base_rates, settlement.cfg_jitt_delay_bonus_rules, settlement.cfg_jitt_compliance_bonus_rules, settlement.cfg_jitt_periodic_fees, settlement.cfg_jitt_reserve_insurance_rules, settlement.cfg_jitt_loyalty_bonus_rules, settlement.cfg_jitt_life_insurance_rules, settlement.cfg_jitt_customer_rating_rules to service_role;
grant select, update on settlement.jit_row to service_role;
grant select on settlement.vw_parameterized_courier_base_summary to service_role;
grant execute on function settlement.recalculate_jitt_base_rates(uuid) to service_role;

/* Backfill every already imported JIT session immediately; no Excel re-upload. */
select settlement.recalculate_jitt_base_rates(session_id)
from (select distinct session_id from settlement.jit_row) sessions;

commit;
