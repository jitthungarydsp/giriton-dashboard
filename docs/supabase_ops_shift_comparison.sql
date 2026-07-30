-- MuszakPro vs Giriton shift comparison.
-- Egy sor = egy futar/napi muszak osszehasonlitasa a merveado MuszakPro
-- Foglalasok sheet es a Giriton shift export kozott.
-- Ezt a Supabase SQL Editorban futtasd le egyszer.

create table if not exists public.ops_shift_comparison (
    id uuid primary key default gen_random_uuid(),
    comparison_key text not null,
    work_date date not null,
    courier_id integer,
    courier_name text,
    email text,
    warehouse text,
    shift_start time,
    shift_end time,
    giriton_status text not null default '-',
    muszakpro_status text not null default '-',
    missing_source text not null default '',
    giriton_check text,
    muszakpro_booking_code text,
    source_summary jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint ops_shift_comparison_unique
        unique (comparison_key)
);

create index if not exists idx_ops_shift_comparison_work_date
    on public.ops_shift_comparison (work_date);

create index if not exists idx_ops_shift_comparison_courier_id
    on public.ops_shift_comparison (courier_id);

create index if not exists idx_ops_shift_comparison_email
    on public.ops_shift_comparison (email);

create index if not exists idx_ops_shift_comparison_status
    on public.ops_shift_comparison (missing_source);

create or replace view public.vw_courier_next_5_day_shifts as
select
    *
from public.ops_shift_comparison
where work_date >= current_date
  and work_date < current_date + interval '5 days'
order by work_date, shift_start, courier_name;
