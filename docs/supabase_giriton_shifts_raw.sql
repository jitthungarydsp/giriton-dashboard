-- Giriton Shift Subscription raw export.
-- Egy sor = egy Giritonban latott muszak/futar par.
-- Ezt a Supabase SQL Editorban futtasd le.

create table if not exists public.giriton_shifts_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'giriton-shifts-robot',
    work_date date not null,
    start_time time not null,
    end_time time,
    warehouse text,
    occupancy text,
    booked integer,
    maximum integer,
    courier_name text not null,
    email text,
    courier_id integer,
    serial text,
    status text not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint giriton_shifts_raw_unique
        unique (source_name, work_date, warehouse, start_time, courier_name)
);

create index if not exists idx_giriton_shifts_raw_work_date
    on public.giriton_shifts_raw (work_date);

create index if not exists idx_giriton_shifts_raw_courier_id
    on public.giriton_shifts_raw (courier_id);

create index if not exists idx_giriton_shifts_raw_serial
    on public.giriton_shifts_raw (serial);

create index if not exists idx_giriton_shifts_raw_status
    on public.giriton_shifts_raw (status);
