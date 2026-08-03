begin;

create table if not exists public.courier_route_performance_detail_raw (
    courier_id integer not null,
    route_id bigint not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    stops_count integer not null default 0,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, route_id, year, month, dsp_id, warehouse_id)
);

create index if not exists courier_route_performance_detail_raw_period_idx
    on public.courier_route_performance_detail_raw (year, month, warehouse_id, courier_id);

create index if not exists courier_route_performance_detail_raw_route_idx
    on public.courier_route_performance_detail_raw (route_id);

create index if not exists courier_route_performance_detail_raw_json_idx
    on public.courier_route_performance_detail_raw using gin (response_json);

grant select, insert, update, delete on public.courier_route_performance_detail_raw to service_role;

commit;
