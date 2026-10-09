begin;

create table if not exists public.courier_hub_departure_dashboard_raw (
    snapshot_key text primary key,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null default 8,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null default '{}'::jsonb,
    route_count integer not null default 0,
    couriers_without_route_count integer not null default 0,
    fetched_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists courier_hub_departure_dashboard_raw_fetched_idx
    on public.courier_hub_departure_dashboard_raw (fetched_at desc);

create table if not exists public.courier_hub_departure_dashboard_latest (
    snapshot_key text not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null default 8,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null default '{}'::jsonb,
    route_count integer not null default 0,
    couriers_without_route_count integer not null default 0,
    fetched_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (warehouse_id, dsp_id)
);

create index if not exists courier_hub_departure_dashboard_latest_fetched_idx
    on public.courier_hub_departure_dashboard_latest (fetched_at desc);

grant select, insert, update, delete on public.courier_hub_departure_dashboard_raw to service_role;
grant select, insert, update, delete on public.courier_hub_departure_dashboard_latest to service_role;
grant select on public.courier_hub_departure_dashboard_latest to authenticated, anon;

notify pgrst, 'reload schema';

commit;
