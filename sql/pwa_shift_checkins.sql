begin;

create table if not exists public.courier_shift_checkins (
    id uuid primary key default gen_random_uuid(),
    courier_id integer not null,
    courier_name text not null,
    work_date date not null,
    start_time text,
    end_time text,
    warehouse text,
    shift_name text,
    booking_code text,
    event_type text not null default 'queued'
        check (event_type in ('queued', 'returned', 'shift_late')),
    created_at timestamptz not null default now()
);

alter table public.courier_shift_checkins
    drop constraint if exists courier_shift_checkins_event_type_check;

alter table public.courier_shift_checkins
    add constraint courier_shift_checkins_event_type_check
    check (event_type in ('queued', 'returned', 'shift_late'));

create index if not exists courier_shift_checkins_courier_date_idx
    on public.courier_shift_checkins (courier_id, work_date, created_at desc);

grant select, insert, update, delete on public.courier_shift_checkins to service_role;

notify pgrst, 'reload schema';

commit;
