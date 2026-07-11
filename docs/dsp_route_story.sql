create table if not exists public.mart_dsp_route_stories (
    work_date date not null,
    courier_id integer not null,
    courier_name text,
    warehouse_name text,
    route_id bigint not null,
    shift_id bigint,
    shift_name text,
    shift_start timestamp,
    shift_end timestamp,
    available_for_shift_since timestamp,
    courier_registered_at timestamp,
    assigned_at timestamp,
    planned_departure timestamp,
    real_departure timestamp,
    planned_return timestamp,
    real_return timestamp,
    queue_entry_delta_minutes integer,
    queue_wait_minutes integer,
    planned_loading_minutes integer,
    real_loading_minutes integer,
    planned_route_minutes integer,
    real_route_minutes integer,
    assigned_to_return_minutes integer,
    address_count integer not null default 0,
    planned_early_count integer not null default 0,
    planned_late_count integer not null default 0,
    time_window_early_count integer not null default 0,
    time_window_late_count integer not null default 0,
    assignment_mode text not null,
    story_text text not null,
    source_summary_table text,
    source_arrivals_table text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (work_date, courier_id, route_id)
);

create index if not exists mart_dsp_route_stories_route_id_idx
    on public.mart_dsp_route_stories (route_id);

create index if not exists mart_dsp_route_stories_courier_date_idx
    on public.mart_dsp_route_stories (courier_id, work_date);

comment on table public.mart_dsp_route_stories is
'MART: route szintu szoveges DSP tortenet, attendance route, shift es cimszintu erkezes adatokbol.';
