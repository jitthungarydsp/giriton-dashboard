-- Giriton bejelentkezes szinkron DB oldali javitas/ellenorzes.
-- Akkor futtasd, ha a Giriton Attendance UIDL workflow nem ment adatot,
-- vagy az upsert "ON CONFLICT" hibaval all meg.

create table if not exists public.giriton_attendance_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'giriton-attendance-robot',
    work_date date not null,
    courier_name text not null,
    shift_text text,
    activity_status text,
    checkin_start time,
    checkin_end time,
    raw_details text,
    response_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists giriton_attendance_raw_source_date_courier_uidx
    on public.giriton_attendance_raw (source_name, work_date, courier_name);

create index if not exists idx_giriton_attendance_raw_work_date
    on public.giriton_attendance_raw (work_date);

create index if not exists idx_giriton_attendance_raw_courier_name
    on public.giriton_attendance_raw (courier_name);

create index if not exists idx_giriton_attendance_raw_status
    on public.giriton_attendance_raw (activity_status);

grant select, insert, update, delete on public.giriton_attendance_raw to service_role;

select
    work_date,
    count(*) as rows,
    max(updated_at) as last_update
from public.giriton_attendance_raw
group by work_date
order by work_date desc
limit 10;
