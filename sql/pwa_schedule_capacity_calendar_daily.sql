begin;

create table if not exists public.pwa_schedule_capacity_calendar_daily (
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null default 8,
    required_slots integer not null default 0,
    booked_slots integer not null default 0,
    free_slots integer not null default 0,
    missing_slots integer not null default 0,
    extra_slots integer not null default 0,
    coverage_percent numeric(6, 2),
    source_block_count integer not null default 0,
    source_updated_at timestamptz,
    refresh_source text not null default 'HUB_JOB_AUTOBOOKING',
    refreshed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (work_date, warehouse_id, dsp_id)
);

create index if not exists pwa_schedule_capacity_calendar_daily_date_idx
    on public.pwa_schedule_capacity_calendar_daily (work_date);

create index if not exists pwa_schedule_capacity_calendar_daily_warehouse_date_idx
    on public.pwa_schedule_capacity_calendar_daily (warehouse_id, work_date);

comment on table public.pwa_schedule_capacity_calendar_daily is
    'PWA beosztas naptar napi toltottseg: Courier Hub shift block opened/assigned/free_slots osszesito, HUB_JOB_AUTOBOOKING utan frissitve.';

comment on column public.pwa_schedule_capacity_calendar_daily.required_slots is
    'Nyitott/tervezett slot osszesen az adott napra es raktarra.';

comment on column public.pwa_schedule_capacity_calendar_daily.booked_slots is
    'Foglalt slot osszesen az adott napra es raktarra.';

comment on column public.pwa_schedule_capacity_calendar_daily.coverage_percent is
    'booked_slots / required_slots * 100, PWA naptar kartyak toltottsege.';

grant select, insert, update, delete on public.pwa_schedule_capacity_calendar_daily to service_role;

notify pgrst, 'reload schema';

commit;
