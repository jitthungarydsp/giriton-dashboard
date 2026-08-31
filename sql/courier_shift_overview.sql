begin;

create table if not exists public.courier_shift_overview_raw (
    courier_id integer not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    shift_count integer not null default 0,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, year, month, dsp_id, warehouse_id)
);

create index if not exists courier_shift_overview_raw_period_idx
    on public.courier_shift_overview_raw (year, month, warehouse_id, courier_id);

create index if not exists courier_shift_overview_raw_json_idx
    on public.courier_shift_overview_raw using gin (response_json);

grant select, insert, update, delete on public.courier_shift_overview_raw to service_role;

create table if not exists public.courier_shift_overview (
    courier_id integer not null,
    work_date date not null,
    shift_key text not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    shift_id text,
    shift_name text,
    shift_start time,
    shift_end time,
    planned_start_at timestamptz,
    planned_end_at timestamptz,
    status text,
    raw_shift jsonb not null default '{}'::jsonb,
    request_url text,
    response_status_code integer not null,
    source_raw_updated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, work_date, shift_key, dsp_id, warehouse_id)
);

create index if not exists courier_shift_overview_date_idx
    on public.courier_shift_overview (work_date, warehouse_id, courier_id);

create index if not exists courier_shift_overview_courier_idx
    on public.courier_shift_overview (courier_id, year, month);

create index if not exists courier_shift_overview_shift_id_idx
    on public.courier_shift_overview (shift_id)
    where shift_id is not null;

create index if not exists courier_shift_overview_raw_shift_idx
    on public.courier_shift_overview using gin (raw_shift);

grant select, insert, update, delete on public.courier_shift_overview to service_role;

commit;
