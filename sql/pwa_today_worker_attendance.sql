begin;

create table if not exists public.pwa_today_worker_attendance (
    id uuid primary key default gen_random_uuid(),
    work_date date not null,
    courier_id integer not null,
    courier_name text not null default '',
    start_time text not null default '',
    end_time text not null default '',
    warehouse text not null default '',
    shift_name text not null default '',
    booking_code text not null default '',
    attendance_status text not null
        check (attendance_status in ('present', 'absent')),
    note text not null default '',
    marked_by text not null default '',
    marked_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists pwa_today_worker_attendance_unique_shift_idx
    on public.pwa_today_worker_attendance (
        work_date,
        courier_id,
        start_time,
        warehouse,
        booking_code
    );

create index if not exists pwa_today_worker_attendance_date_status_idx
    on public.pwa_today_worker_attendance (work_date, attendance_status);

grant select, insert, update, delete on public.pwa_today_worker_attendance to service_role;

notify pgrst, 'reload schema';

commit;
