create table if not exists public.pwa_vehicle_configurations (
    id uuid primary key default gen_random_uuid(),
    jitt_car_id text not null,
    license_plate text not null,
    warehouse_code text not null,
    toll_vignette_type text not null default 'none',
    toll_counties text[] not null default '{}'::text[],
    toll_valid_from date null,
    toll_valid_to date null,
    service_from date null,
    service_to date null,
    car_status text not null default 'assignable',
    condition_label text null,
    condition_description text null,
    minimum_route_length integer null,
    dedicated_courier_id integer null,
    dedicated_courier_name text null,
    active boolean not null default true,
    created_by text null,
    updated_by text null,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now(),
    constraint pwa_vehicle_configurations_jitt_car_id_key unique (jitt_car_id),
    constraint pwa_vehicle_configurations_license_plate_key unique (license_plate),
    constraint pwa_vehicle_configurations_warehouse_check check (warehouse_code in ('BUD1', 'BUD2')),
    constraint pwa_vehicle_configurations_toll_type_check check (toll_vignette_type in ('none', 'has', 'county', 'national')),
    constraint pwa_vehicle_configurations_status_check check (car_status in ('service', 'garage_master', 'other', 'assignable', 'retired', 'out_of_order')),
    constraint pwa_vehicle_configurations_min_route_check check (minimum_route_length is null or minimum_route_length >= 0)
);

create unique index if not exists idx_pwa_vehicle_configurations_jitt_car_id
    on public.pwa_vehicle_configurations using btree (jitt_car_id);

create unique index if not exists idx_pwa_vehicle_configurations_license_plate
    on public.pwa_vehicle_configurations using btree (license_plate);

create index if not exists idx_pwa_vehicle_configurations_warehouse
    on public.pwa_vehicle_configurations using btree (warehouse_code);

create index if not exists idx_pwa_vehicle_configurations_status
    on public.pwa_vehicle_configurations using btree (car_status);

create index if not exists idx_pwa_vehicle_configurations_dedicated_courier
    on public.pwa_vehicle_configurations using btree (dedicated_courier_id);

grant select on public.pwa_vehicle_configurations to anon, authenticated;
grant all on public.pwa_vehicle_configurations to service_role;

notify pgrst, 'reload schema';
