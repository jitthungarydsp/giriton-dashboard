-- MuszakPro vs Giriton shift comparison.
-- Egy sor = egy futar/napi muszak osszehasonlitasa a merveado MuszakPro
-- Foglalasok sheet es a Giriton shift export kozott.
-- Ezt a Supabase SQL Editorban futtasd le egyszer.

create table if not exists public.ops_shift_comparison (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'shift-reconciliation',
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
    booking_recommendation_status text,
    giriton_offer time,
    muszakpro_shift_start time,
    difference_text text,
    recommendation_reason text,
    serial text,
    source_summary jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint ops_shift_comparison_unique
        unique (comparison_key)
);

alter table public.ops_shift_comparison
    add column if not exists source_name text not null default 'shift-reconciliation',
    add column if not exists booking_recommendation_status text,
    add column if not exists giriton_offer time,
    add column if not exists muszakpro_shift_start time,
    add column if not exists difference_text text,
    add column if not exists recommendation_reason text,
    add column if not exists serial text;

create index if not exists idx_ops_shift_comparison_work_date
    on public.ops_shift_comparison (work_date);

create index if not exists idx_ops_shift_comparison_courier_id
    on public.ops_shift_comparison (courier_id);

create index if not exists idx_ops_shift_comparison_email
    on public.ops_shift_comparison (email);

create index if not exists idx_ops_shift_comparison_status
    on public.ops_shift_comparison (missing_source);

create index if not exists idx_ops_shift_comparison_source_name
    on public.ops_shift_comparison (source_name);

create index if not exists idx_ops_shift_comparison_booking_recommendation
    on public.ops_shift_comparison (booking_recommendation_status);

create or replace view public.vw_courier_next_5_day_shifts as
select
    *
from public.ops_shift_comparison
where work_date >= current_date
  and work_date < current_date + interval '5 days'
order by work_date, shift_start, courier_name;

-- Ellenorzesek:
-- 1) Giritonban fent van, de MuszakProban nincs:
-- select *
-- from public.ops_shift_comparison
-- where giriton_status = 'OK'
--   and muszakpro_status <> 'OK'
-- order by work_date, shift_start, courier_name;

-- 2) MuszakProban fent van, de Giritonban nincs:
-- select *
-- from public.ops_shift_comparison
-- where muszakpro_status = 'OK'
--   and giriton_status <> 'OK'
-- order by work_date, shift_start, courier_name;

-- 3) Teljes eltéréslista mindkét irányból:
-- select *
-- from public.ops_shift_comparison
-- where missing_source <> ''
-- order by work_date, shift_start, courier_name;
