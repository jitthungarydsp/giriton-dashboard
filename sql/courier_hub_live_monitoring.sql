create table if not exists public.courier_hub_live_monitoring_raw (
    snapshot_key text primary key,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    courier_count integer not null default 0,
    route_count integer not null default 0,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.courier_hub_live_monitoring_courier_raw (
    snapshot_key text not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    courier_id integer not null,
    courier_name text,
    route_id text,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (snapshot_key, courier_id)
);

create table if not exists public.courier_hub_live_monitoring_courier_latest (
    snapshot_key text not null,
    courier_id integer not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    courier_name text,
    route_id text,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, warehouse_id, dsp_id)
);

create index if not exists idx_ch_live_raw_fetched_at
    on public.courier_hub_live_monitoring_raw (fetched_at desc);

create index if not exists idx_ch_live_courier_raw_route
    on public.courier_hub_live_monitoring_courier_raw (route_id, fetched_at desc);

create index if not exists idx_ch_live_courier_latest_route
    on public.courier_hub_live_monitoring_courier_latest (route_id);
