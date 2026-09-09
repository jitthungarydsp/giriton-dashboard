begin;

create table if not exists public.courier_hub_performance_endpoint_raw (
    endpoint_type text not null check (endpoint_type in ('routes', 'shifts')),
    courier_id integer not null,
    warehouse_id integer not null,
    dsp_id integer not null default 8,
    date_from date not null,
    date_to date not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    item_count integer not null default 0,
    total_count integer not null default 0,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (endpoint_type, courier_id, warehouse_id, dsp_id, date_from, date_to)
);

create index if not exists courier_hub_performance_endpoint_raw_period_idx
    on public.courier_hub_performance_endpoint_raw (endpoint_type, date_from, date_to, warehouse_id, courier_id);

create index if not exists courier_hub_performance_endpoint_raw_status_idx
    on public.courier_hub_performance_endpoint_raw (endpoint_type, status_code, fetched_at desc);

create index if not exists courier_hub_performance_endpoint_raw_json_idx
    on public.courier_hub_performance_endpoint_raw using gin (response_json);

grant select, insert, update, delete on public.courier_hub_performance_endpoint_raw to service_role;

create table if not exists public.courier_hub_performance_routes (
    courier_id integer not null,
    warehouse_id integer not null,
    dsp_id integer not null default 8,
    work_date date not null,
    route_id bigint not null,
    route_key text not null,
    courier_name text,
    route_type text,
    route_type_label text,
    shift_name text,
    planned_start_at timestamptz,
    actual_start_at timestamptz,
    planned_departure_at timestamptz,
    departed_at timestamptz,
    planned_return_at timestamptz,
    returned_at timestamptz,
    planned_route_minutes integer,
    actual_route_minutes integer,
    planned_km numeric(10, 2),
    mileage_km numeric(10, 2),
    order_count integer not null default 0,
    stops_total integer not null default 0,
    delivered_count integer not null default 0,
    delayed_count integer not null default 0,
    delay_minutes integer,
    customer_tips_huf numeric(12, 2) not null default 0,
    vehicle_plate text,
    raw_route jsonb not null default '{}'::jsonb,
    source_date_from date not null,
    source_date_to date not null,
    source_raw_updated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, warehouse_id, dsp_id, work_date, route_id)
);

create index if not exists courier_hub_performance_routes_date_idx
    on public.courier_hub_performance_routes (work_date, warehouse_id, courier_id);

create index if not exists courier_hub_performance_routes_courier_idx
    on public.courier_hub_performance_routes (courier_id, work_date desc);

create index if not exists courier_hub_performance_routes_route_idx
    on public.courier_hub_performance_routes (route_id);

create index if not exists courier_hub_performance_routes_raw_idx
    on public.courier_hub_performance_routes using gin (raw_route);

grant select, insert, update, delete on public.courier_hub_performance_routes to service_role;

commit;
