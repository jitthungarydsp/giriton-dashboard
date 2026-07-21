-- Settlement app alap DB struktura.
-- Futtasd Supabase SQL Editorban.
--
-- Cel:
-- - gyors futar torzs az elszamolasi PWA-hoz
-- - API hivas naplo, hogy latszodjon, mikor milyen forrasbol frissult
-- - settlement schema view-k, hogy logikailag kulon legyen az elszamolasi modul

create schema if not exists settlement;

create table if not exists public.settlement_courier_master (
    courier_id integer primary key,
    courier_name text not null,
    email text,
    phone_number text,
    warehouse_name text,
    active boolean,
    vehicle_type text,
    license_plate text,
    temperature numeric(10,2),
    last_measurement_timestamp timestamptz,
    current_state text,
    delay_minutes integer,
    next_stop text,
    route_assigned_at timestamptz,
    source_name text not null default 'fetch-drivers',
    organization_id text not null,
    dsp_id text not null default 'JIT',
    response_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_settlement_courier_master_name
    on public.settlement_courier_master (courier_name);

create index if not exists idx_settlement_courier_master_warehouse
    on public.settlement_courier_master (warehouse_name);

create index if not exists idx_settlement_courier_master_active
    on public.settlement_courier_master (active);

create index if not exists idx_settlement_courier_master_updated
    on public.settlement_courier_master (updated_at desc);

create table if not exists public.settlement_api_calls (
    id uuid primary key default gen_random_uuid(),
    source_name text not null,
    request_url text not null,
    status_code integer,
    row_count integer not null default 0,
    response_json jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists idx_settlement_api_calls_source_fetched
    on public.settlement_api_calls (source_name, fetched_at desc);

create table if not exists public.settlement_financial_overview_raw (
    source_name text not null default 'courier-hub-financial-overview-courier-overview',
    year integer not null,
    month integer not null,
    warehouse_id integer not null,
    dsp_id integer not null default 8,
    dsp_code text not null default 'JIT',
    request_url text not null,
    status_code integer,
    response_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, year, month, warehouse_id, dsp_id)
);

alter table public.settlement_financial_overview_raw
    alter column source_name set default 'courier-hub-financial-overview-courier-overview';

create index if not exists idx_settlement_financial_overview_raw_period
    on public.settlement_financial_overview_raw (year, month, warehouse_id);

create index if not exists idx_settlement_financial_overview_raw_fetched
    on public.settlement_financial_overview_raw (fetched_at desc);

create or replace view settlement.courier_master as
select
    courier_id,
    courier_name,
    email,
    phone_number,
    warehouse_name,
    active,
    vehicle_type,
    license_plate,
    temperature,
    last_measurement_timestamp,
    current_state,
    delay_minutes,
    next_stop,
    route_assigned_at,
    source_name,
    organization_id,
    dsp_id,
    fetched_at,
    created_at,
    updated_at
from public.settlement_courier_master;

create or replace view settlement.api_calls as
select
    id,
    source_name,
    request_url,
    status_code,
    row_count,
    fetched_at,
    created_at
from public.settlement_api_calls;

create or replace view settlement.financial_overview_raw as
select
    source_name,
    year,
    month,
    warehouse_id,
    dsp_id,
    dsp_code,
    request_url,
    status_code,
    response_json,
    fetched_at,
    created_at,
    updated_at
from public.settlement_financial_overview_raw;
