begin;

create table if not exists public.courier_financial_overview_delay (
    courier_id integer not null,
    route_id bigint not null,
    delivery_date date not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    route_order_count integer not null default 0,
    stops_count integer not null default 0,
    delayed_stops_count integer not null default 0,
    total_delay_minutes integer not null default 0,
    max_delay_minutes integer not null default 0,
    slot_miss_projected_count integer not null default 0,
    rejected_stops_count integer not null default 0,
    response_status_code integer not null,
    source_raw_updated_at timestamptz,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    primary key (courier_id, route_id, year, month, dsp_id, warehouse_id)
);

create index if not exists courier_financial_overview_delay_date_idx
    on public.courier_financial_overview_delay (delivery_date, warehouse_id, courier_id);

create index if not exists courier_financial_overview_delay_courier_idx
    on public.courier_financial_overview_delay (courier_id, year, month);

grant select, insert, update, delete on public.courier_financial_overview_delay to service_role;

create table if not exists public.courier_financial_overview_compliance (
    courier_id integer not null,
    route_id bigint not null,
    shift_date date not null,
    year integer not null,
    month integer not null check (month between 1 and 12),
    dsp_id integer not null default 8,
    warehouse_id integer not null,
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
    fridge_config text,
    delay_reference text,
    returnables_status text,
    returnables_note text,
    planned_start_delay_minutes integer,
    departure_delay_minutes integer,
    return_delay_minutes integer,
    event_summary jsonb not null default '{}'::jsonb,
    response_status_code integer not null,
    source_raw_updated_at timestamptz,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    primary key (courier_id, route_id, year, month, dsp_id, warehouse_id)
);

create index if not exists courier_financial_overview_compliance_date_idx
    on public.courier_financial_overview_compliance (shift_date, warehouse_id, courier_id);

create index if not exists courier_financial_overview_compliance_courier_idx
    on public.courier_financial_overview_compliance (courier_id, year, month);

create index if not exists courier_financial_overview_compliance_events_idx
    on public.courier_financial_overview_compliance using gin (event_summary);

grant select, insert, update, delete on public.courier_financial_overview_compliance to service_role;

commit;

notify pgrst, 'reload schema';
