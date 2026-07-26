/*
RESET MIGRATION - removes every earlier JITT parameter table from public.
Their data is intentionally deleted at the user's request. New parameter
tables are created exclusively in the settlement schema.
*/

create schema if not exists settlement;

drop table if exists settlement.cfg_jitt_rate_parameters cascade;
drop table if exists settlement.cfg_jitt_periodic_bonuses cascade;
drop table if exists settlement.cfg_jitt_rate_parameter_names cascade;
drop table if exists settlement.cfg_jitt_day_definitions cascade;
drop table if exists settlement.cfg_jitt_base_rates cascade;
drop table if exists settlement.cfg_jitt_delay_bonus_rules cascade;
drop table if exists settlement.cfg_jitt_compliance_bonus_rules cascade;
drop table if exists settlement.cfg_jitt_periodic_fees cascade;

drop table if exists public.cfg_jitt_rate_parameters cascade;
drop table if exists public.cfg_jitt_periodic_bonuses cascade;
drop table if exists public.cfg_jitt_rate_parameter_names cascade;
drop table if exists public.cfg_jitt_day_definitions cascade;
drop table if exists public.cfg_jitt_base_rates cascade;
drop table if exists public.cfg_jitt_delay_bonus_rules cascade;
drop table if exists public.cfg_jitt_compliance_bonus_rules cascade;
drop table if exists public.cfg_jitt_periodic_fees cascade;

create extension if not exists pgcrypto;

create table if not exists settlement.cfg_jitt_day_definitions (
    id uuid primary key default gen_random_uuid(),
    day_type text not null check (day_type in ('highlighted', 'normal')),
    weekdays smallint[] not null default '{}'::smallint[] check (
        weekdays <@ array[1,2,3,4,5,6,7]::smallint[]
        and cardinality(weekdays) > 0
    ),
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
    check (
        (deleted_at is null and deleted_by is null)
        or (deleted_at is not null and nullif(trim(deleted_by), '') is not null)
    )
);

create table if not exists settlement.cfg_jitt_base_rates (
    id uuid primary key default gen_random_uuid(),
    day_type text not null default 'any' check (day_type in ('highlighted', 'normal', 'any')),
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
    day_type text not null default 'any' check (day_type in ('highlighted', 'normal', 'any')),
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

/* Existing first-version day rows are preserved as one-element weekday arrays. */
alter table settlement.cfg_jitt_day_definitions
    add column if not exists weekdays smallint[] not null default '{}'::smallint[];

do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'settlement'
          and table_name = 'cfg_jitt_day_definitions'
          and column_name = 'weekday'
    ) then
        update settlement.cfg_jitt_day_definitions
        set weekdays = array[weekday]
        where cardinality(weekdays) = 0
          and weekday is not null;

        alter table settlement.cfg_jitt_day_definitions
            drop column weekday;
    end if;
end
$$;

alter table settlement.cfg_jitt_delay_bonus_rules
    add column if not exists calculation_mode text not null default 'excel'
    check (calculation_mode in ('excel', 'api', 'custom'));

alter table settlement.cfg_jitt_compliance_bonus_rules
    add column if not exists calculation_mode text not null default 'excel'
    check (calculation_mode in ('excel', 'api', 'custom'));

create table if not exists settlement.cfg_jitt_periodic_fees (
    id uuid primary key default gen_random_uuid(),
    fee_name text not null,
    day_type text not null default 'any' check (day_type in ('highlighted', 'normal', 'any')),
    route_type text not null default 'any' check (route_type in ('express', 'normal', 'regional', 'any')),
    warehouse_code text,
    condition_metric text not null default 'none' check (condition_metric in ('none', 'orders_per_route', 'routes_per_day', 'routes_in_period', 'orders_in_period')),
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
    check (condition_max is null or condition_min is null or condition_max >= condition_min)
);

drop index if exists settlement.idx_jitt_day_definitions_lookup;
create index if not exists idx_jitt_day_definitions_lookup on settlement.cfg_jitt_day_definitions (is_active, valid_from, valid_to) where deleted_at is null;
create index if not exists idx_jitt_base_rates_lookup on settlement.cfg_jitt_base_rates (is_active, day_type, route_type, valid_from, valid_to) where deleted_at is null;
create index if not exists idx_jitt_delay_bonus_lookup on settlement.cfg_jitt_delay_bonus_rules (is_active, day_type, route_type, valid_from, valid_to) where deleted_at is null;
create index if not exists idx_jitt_compliance_bonus_lookup on settlement.cfg_jitt_compliance_bonus_rules (is_active, day_type, route_type, valid_from, valid_to) where deleted_at is null;
create index if not exists idx_jitt_periodic_fees_lookup on settlement.cfg_jitt_periodic_fees (is_active, day_type, route_type, valid_from, valid_to) where deleted_at is null;

grant usage on schema settlement to service_role;
grant select, insert, update, delete on settlement.cfg_jitt_day_definitions, settlement.cfg_jitt_base_rates, settlement.cfg_jitt_delay_bonus_rules, settlement.cfg_jitt_compliance_bonus_rules, settlement.cfg_jitt_periodic_fees to service_role;
