-- Giriton Attendance raw export.
-- Egy sor = egy futar egy napi Giriton Attendance allapota.
-- Ezt a Supabase SQL Editorban futtasd le.

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
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint giriton_attendance_raw_unique
        unique (source_name, work_date, courier_name)
);

create index if not exists idx_giriton_attendance_raw_work_date
    on public.giriton_attendance_raw (work_date);

create index if not exists idx_giriton_attendance_raw_courier_name
    on public.giriton_attendance_raw (courier_name);

create index if not exists idx_giriton_attendance_raw_status
    on public.giriton_attendance_raw (activity_status);
