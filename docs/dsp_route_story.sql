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
    route_created_at timestamp,
    courier_registered_at timestamp,
    assigned_at timestamp,
    loading_time timestamp,
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
    gps_distance_km numeric(10,3),
    checkpoint_straight_km numeric(10,3),
    booking_shift_count integer not null default 0,
    next_booking_shift_text text,
    next_booking_shift_start timestamp,
    next_shift_delay_minutes integer,
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

alter table public.mart_dsp_route_stories
    add column if not exists gps_distance_km numeric(10,3),
    add column if not exists checkpoint_straight_km numeric(10,3),
    add column if not exists route_created_at timestamp,
    add column if not exists loading_time timestamp,
    add column if not exists booking_shift_count integer not null default 0,
    add column if not exists next_booking_shift_text text,
    add column if not exists next_booking_shift_start timestamp,
    add column if not exists next_shift_delay_minutes integer;
