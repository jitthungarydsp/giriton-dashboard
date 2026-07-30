-- fetch-attendance API vs MuszakPro bookings comparison.
-- Ez egy uj, Giriton-Seleniumtol fuggetlen ag.
-- A gyujtes append-only: minden futas uj collection_id-val ir sort,
-- a lekerdezesek pedig view-bol olvasnak, nem frissitik a tablakat.

create table if not exists public.raw_fetch_attendance_shifts (
    id uuid primary key default gen_random_uuid(),
    collection_id uuid not null,
    source_name text not null default 'fetch-attendance',
    organization_id text not null,
    dsp_id text not null,
    work_date date not null,
    request_url text not null,
    status_code integer not null,
    courier_id integer,
    courier_name text,
    warehouse text,
    api_shift_id text,
    shift_name text,
    normalized_shift_name text,
    shift_start timestamptz,
    shift_end timestamptz,
    available_for_shift_since timestamptz,
    match_key text not null,
    source_json jsonb not null default '{}'::jsonb,
    collected_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

alter table public.raw_fetch_attendance_shifts
    add column if not exists normalized_shift_name text;

create index if not exists idx_raw_fetch_attendance_shifts_collection
    on public.raw_fetch_attendance_shifts (collection_id);

create index if not exists idx_raw_fetch_attendance_shifts_work_date
    on public.raw_fetch_attendance_shifts (work_date);

create index if not exists idx_raw_fetch_attendance_shifts_courier_id
    on public.raw_fetch_attendance_shifts (courier_id);

create index if not exists idx_raw_fetch_attendance_shifts_match_key
    on public.raw_fetch_attendance_shifts (match_key);


create table if not exists public.ops_attendance_muszakpro_comparison (
    id uuid primary key default gen_random_uuid(),
    collection_id uuid not null,
    work_date date not null,
    match_key text not null,
    courier_id integer,
    courier_name text,
    email text,
    warehouse text,
    shift_start time,
    shift_end time,
    attendance_status text not null default '-',
    muszakpro_status text not null default '-',
    missing_source text not null default '',
    attendance_shift_id text,
    attendance_shift_name text,
    muszakpro_shift_text text,
    muszakpro_booking_code text,
    source_summary jsonb not null default '{}'::jsonb,
    collected_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists idx_ops_attendance_muszakpro_collection
    on public.ops_attendance_muszakpro_comparison (collection_id);

create index if not exists idx_ops_attendance_muszakpro_work_date
    on public.ops_attendance_muszakpro_comparison (work_date);

create index if not exists idx_ops_attendance_muszakpro_courier_id
    on public.ops_attendance_muszakpro_comparison (courier_id);

create index if not exists idx_ops_attendance_muszakpro_missing
    on public.ops_attendance_muszakpro_comparison (missing_source);


create or replace view public.vw_attendance_muszakpro_latest_comparison as
with latest as (
    select
        work_date,
        max(collected_at) as collected_at
    from public.ops_attendance_muszakpro_comparison
    group by work_date
)
select c.*
from public.ops_attendance_muszakpro_comparison c
join latest l
  on l.work_date = c.work_date
 and l.collected_at = c.collected_at
order by c.work_date, c.shift_start, c.courier_name;


create or replace view public.vw_attendance_muszakpro_next_5_days as
select *
from public.vw_attendance_muszakpro_latest_comparison
where work_date >= current_date
  and work_date < current_date + interval '5 days'
order by work_date, shift_start, courier_name;


-- Ellenorzesek:
-- API-ban van, de MuszakProban nincs:
-- select *
-- from public.vw_attendance_muszakpro_latest_comparison
-- where attendance_status = 'OK'
--   and muszakpro_status <> 'OK'
-- order by work_date, shift_start, courier_name;

-- MuszakProban van, de API-ban nincs:
-- select *
-- from public.vw_attendance_muszakpro_latest_comparison
-- where muszakpro_status = 'OK'
--   and attendance_status <> 'OK'
-- order by work_date, shift_start, courier_name;

-- Regi hibas collection kezi torlese:
-- delete from public.ops_attendance_muszakpro_comparison
-- where collection_id = 'IDE_A_COLLECTION_ID';
--
-- delete from public.raw_fetch_attendance_shifts
-- where collection_id = 'IDE_A_COLLECTION_ID';
