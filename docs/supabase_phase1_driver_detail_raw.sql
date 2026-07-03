-- Phase 1: raw mentés egyetlen API-ra.
-- Egy sor = egy fetch-drivers-detail/{driver_id}/{work_date} válasz.
-- Ezt a Supabase SQL Editorban futtasd le.

create table if not exists public.dsp_driver_detail_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'fetch-drivers-detail',
    organization_id text not null,
    dsp_id text not null default 'JIT',
    driver_id integer not null,
    work_date date not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint dsp_driver_detail_raw_unique
        unique (source_name, driver_id, work_date)
);

create index if not exists idx_dsp_driver_detail_raw_work_date
    on public.dsp_driver_detail_raw (work_date);

create index if not exists idx_dsp_driver_detail_raw_driver_date
    on public.dsp_driver_detail_raw (driver_id, work_date);

create index if not exists idx_dsp_driver_detail_raw_response_json
    on public.dsp_driver_detail_raw using gin (response_json);
