begin;

create table if not exists public.courier_daily_vehicle_assignments (
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    courier_id integer not null,
    courier_name text,
    vehicle_plate text,
    observed_vehicle_plates text[] not null default '{}',
    route_ids text[] not null default '{}',
    route_count integer not null default 0,
    source text not null default 'courier-hub-live-monitoring',
    source_snapshot_at timestamptz,
    response_json jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (work_date, warehouse_id, dsp_id, courier_id)
);

create index if not exists idx_courier_daily_vehicle_assignments_date
    on public.courier_daily_vehicle_assignments (work_date desc, warehouse_id, courier_name);

create index if not exists idx_courier_daily_vehicle_assignments_plate
    on public.courier_daily_vehicle_assignments (vehicle_plate, work_date desc);

grant select on public.courier_daily_vehicle_assignments to anon, authenticated;
grant all on public.courier_daily_vehicle_assignments to service_role;

commit;

notify pgrst, 'reload schema';
