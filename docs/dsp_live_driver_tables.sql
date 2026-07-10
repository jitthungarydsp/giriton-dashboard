create table if not exists public.dsp_drivers_live_raw (
    fetch_batch_id uuid not null,
    source_name text not null default 'fetch-drivers',
    organization_id text not null,
    dsp_id text not null,
    agency_id text,
    driver_id integer not null,
    courier_name text,
    warehouse_name text,
    active boolean,
    license_plate text,
    current_state text,
    route_assigned_at timestamptz,
    fetched_at timestamptz not null default now(),
    request_url text,
    status_code integer,
    response_json jsonb not null,
    created_at timestamptz not null default now(),
    primary key (fetch_batch_id, driver_id)
);

create index if not exists idx_dsp_drivers_live_raw_driver_fetched
    on public.dsp_drivers_live_raw (driver_id, fetched_at desc);

create index if not exists idx_dsp_drivers_live_raw_route_assigned
    on public.dsp_drivers_live_raw (route_assigned_at);

create table if not exists public.dsp_route_km_latest (
    driver_id integer not null,
    route_assigned_at timestamptz not null,
    courier_name text,
    warehouse_name text,
    license_plate text,
    active boolean,
    current_state text,
    next_stop text,
    is_departure_delayed boolean,
    delay_minutes integer,
    temperature numeric(10,2),
    last_measurement_timestamp timestamptz,
    loading_finished_at timestamptz,
    warehouse_departure_real timestamptz,
    total_distance_km numeric(10,3),
    distance_covered_km numeric(10,3),
    parcels_delivered integer,
    parcels_total integer,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    last_raw_fetch_batch_id uuid,
    updated_at timestamptz not null default now(),
    primary key (driver_id, route_assigned_at)
);

create index if not exists idx_dsp_route_km_latest_last_seen
    on public.dsp_route_km_latest (last_seen_at desc);

create index if not exists idx_dsp_route_km_latest_license_plate
    on public.dsp_route_km_latest (license_plate);
