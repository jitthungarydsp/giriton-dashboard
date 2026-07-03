-- Phase 1: fetch-vehicle-assignments mentése külön táblába.
-- Egy sor = egy napi autó hozzárendelés egy futárhoz.
-- Ezt a Supabase SQL Editorban futtasd le.

create table if not exists public.dsp_vehicle_assignments (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'fetch-vehicle-assignments',
    organization_id text not null,
    dsp_id text not null default 'JIT',
    work_date date not null,
    driver_name text not null,
    shift_start time,
    shift_end time,
    car text,
    license_plate text,
    shift_type text,
    vehicle_type_id text,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint dsp_vehicle_assignments_unique
        unique (source_name, work_date, driver_name, shift_start, shift_end)
);

create index if not exists idx_dsp_vehicle_assignments_work_date
    on public.dsp_vehicle_assignments (work_date);

create index if not exists idx_dsp_vehicle_assignments_driver_name
    on public.dsp_vehicle_assignments (driver_name);

create index if not exists idx_dsp_vehicle_assignments_license_plate
    on public.dsp_vehicle_assignments (license_plate);
