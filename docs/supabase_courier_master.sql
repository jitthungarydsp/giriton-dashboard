-- Courier master data.
-- One row = one courier.
-- Run this in Supabase SQL Editor.

create table if not exists public.courier_master (
    courier_id integer primary key,
    courier_name text not null,
    phone_number text,
    email text,
    warehouse_name text,
    source_name text not null default 'fetch-drivers',
    organization_id text not null,
    dsp_id text not null default 'JIT',
    active boolean,
    response_json jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_courier_master_name
    on public.courier_master (courier_name);

create index if not exists idx_courier_master_warehouse
    on public.courier_master (warehouse_name);

create index if not exists idx_courier_master_email
    on public.courier_master (email);
