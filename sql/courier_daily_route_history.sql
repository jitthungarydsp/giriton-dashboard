begin;

create table if not exists public.courier_daily_route_history (
    courier_id integer not null,
    route_id bigint not null,
    work_date date not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    order_count integer not null default 0,
    stops_count integer not null default 0,
    planned_start_at timestamptz,
    actual_start_at timestamptz,
    route_assigned_at timestamptz,
    shift_available_at timestamptz,
    planned_departure_at timestamptz,
    departed_at timestamptz,
    last_order_finished_at timestamptz,
    warehouse_arrived_at timestamptz,
    vehicle_model text,
    vehicle_plate text,
    mileage_km numeric,
    vehicle_ownership text,
    response_status_code integer not null,
    source_raw_updated_at timestamptz,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    primary key (courier_id, route_id, year, month, dsp_id, warehouse_id)
);

create index if not exists courier_daily_route_history_courier_date_idx
    on public.courier_daily_route_history (courier_id, work_date desc);

create index if not exists courier_daily_route_history_date_idx
    on public.courier_daily_route_history (work_date desc, warehouse_id, courier_id);

grant select, insert, update, delete on public.courier_daily_route_history to service_role;

commit;

notify pgrst, 'reload schema';
