create table if not exists public.dsp_route_distance_calculated (
    source_name text not null default 'fetch-drivers-detail',
    calculation_version text not null default 'gps_v1',
    driver_id integer not null,
    work_date date not null,
    route_id text not null,
    warehouse_name text,
    real_departure timestamptz,
    real_return timestamptz,
    planned_departure timestamptz,
    planned_return timestamptz,
    gps_distance_km numeric(10,3),
    checkpoint_straight_km numeric(10,3),
    gps_points_count integer not null default 0,
    gps_segments_count integer not null default 0,
    outlier_segments_count integer not null default 0,
    checkpoints_count integer not null default 0,
    max_speed_kmh numeric(10,2),
    max_segment_km numeric(10,3),
    first_location_at timestamptz,
    last_location_at timestamptz,
    calculated_at timestamptz not null default now(),
    raw_fetched_at timestamptz,

    primary key (calculation_version, driver_id, work_date, route_id)
);

create index if not exists idx_dsp_route_distance_work_date
    on public.dsp_route_distance_calculated (work_date);

create index if not exists idx_dsp_route_distance_driver_date
    on public.dsp_route_distance_calculated (driver_id, work_date);

create index if not exists idx_dsp_route_distance_route_id
    on public.dsp_route_distance_calculated (route_id);

create table if not exists public.stg_dsp_route_distance (
    source_name text not null default 'fetch-drivers-detail',
    calculation_version text not null default 'gps_v1',
    driver_id integer not null,
    work_date date not null,
    route_id text not null,
    warehouse_name text,
    real_departure timestamptz,
    real_return timestamptz,
    planned_departure timestamptz,
    planned_return timestamptz,
    gps_distance_km numeric(10,3),
    checkpoint_straight_km numeric(10,3),
    gps_points_count integer not null default 0,
    gps_segments_count integer not null default 0,
    outlier_segments_count integer not null default 0,
    checkpoints_count integer not null default 0,
    max_speed_kmh numeric(10,2),
    max_segment_km numeric(10,3),
    first_location_at timestamptz,
    last_location_at timestamptz,
    calculated_at timestamptz not null default now(),
    raw_fetched_at timestamptz,

    primary key (calculation_version, driver_id, work_date, route_id)
);

create index if not exists idx_stg_dsp_route_distance_work_date
    on public.stg_dsp_route_distance (work_date);

create index if not exists idx_stg_dsp_route_distance_driver_date
    on public.stg_dsp_route_distance (driver_id, work_date);

create index if not exists idx_stg_dsp_route_distance_route_id
    on public.stg_dsp_route_distance (route_id);
