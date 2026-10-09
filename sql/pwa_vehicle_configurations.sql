create table if not exists public.pwa_vehicle_configurations (
    id uuid primary key default gen_random_uuid(),
    jitt_car_id text not null default ('JCAR-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10))),
    license_plate text not null,
    warehouse_code text not null,
    brand text null,
    model text null,
    ownership_type text not null default 'own',
    rental_company text null,
    toll_vignette_type text not null default 'none',
    toll_counties text[] not null default '{}'::text[],
    toll_valid_from date null,
    toll_valid_to date null,
    service_from date null,
    service_to date null,
    service_location text null,
    car_status text not null default 'assignable',
    condition_status text not null default 'ok',
    condition_description text null,
    minimum_daily_rounds integer null,
    enforce_minimum_daily_rounds boolean not null default false,
    dedicated_courier_id integer null,
    dedicated_courier_name text null,
    active boolean not null default true,
    created_by text null,
    updated_by text null,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now()
);

alter table public.pwa_vehicle_configurations
    alter column jitt_car_id set default ('JCAR-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10))),
    add column if not exists brand text,
    add column if not exists model text,
    add column if not exists ownership_type text not null default 'own',
    add column if not exists rental_company text,
    add column if not exists service_location text,
    add column if not exists condition_status text not null default 'ok',
    add column if not exists minimum_daily_rounds integer,
    add column if not exists enforce_minimum_daily_rounds boolean not null default false;

alter table public.pwa_vehicle_configurations
    drop constraint if exists pwa_vehicle_configurations_jitt_car_id_key,
    drop constraint if exists pwa_vehicle_configurations_license_plate_key,
    drop constraint if exists pwa_vehicle_configurations_warehouse_check,
    drop constraint if exists pwa_vehicle_configurations_toll_type_check,
    drop constraint if exists pwa_vehicle_configurations_status_check,
    drop constraint if exists pwa_vehicle_configurations_min_route_check,
    drop constraint if exists pwa_vehicle_configurations_condition_status_check,
    drop constraint if exists pwa_vehicle_configurations_ownership_type_check,
    drop constraint if exists pwa_vehicle_configurations_minimum_daily_rounds_check,
    add constraint pwa_vehicle_configurations_warehouse_check check (warehouse_code in ('BUD1', 'BUD2')),
    add constraint pwa_vehicle_configurations_toll_type_check check (toll_vignette_type in ('none', 'has', 'county', 'national')),
    add constraint pwa_vehicle_configurations_status_check check (car_status in ('service', 'garage_master', 'other', 'assignable', 'retired', 'out_of_order')),
    add constraint pwa_vehicle_configurations_condition_status_check check (condition_status in ('ok', 'attention', 'faulty')),
    add constraint pwa_vehicle_configurations_ownership_type_check check (ownership_type in ('own', 'rented')),
    add constraint pwa_vehicle_configurations_minimum_daily_rounds_check check (minimum_daily_rounds is null or minimum_daily_rounds >= 0);

drop index if exists public.idx_pwa_vehicle_configurations_jitt_car_id;
drop index if exists public.idx_pwa_vehicle_configurations_license_plate;

create index if not exists idx_pwa_vehicle_configurations_jitt_car_id
    on public.pwa_vehicle_configurations using btree (jitt_car_id);

create index if not exists idx_pwa_vehicle_configurations_license_plate_created
    on public.pwa_vehicle_configurations using btree (license_plate, created_at desc);

create index if not exists idx_pwa_vehicle_configurations_warehouse
    on public.pwa_vehicle_configurations using btree (warehouse_code);

create index if not exists idx_pwa_vehicle_configurations_status
    on public.pwa_vehicle_configurations using btree (car_status);

create index if not exists idx_pwa_vehicle_configurations_dedicated_courier
    on public.pwa_vehicle_configurations using btree (dedicated_courier_id);

create or replace view public.vw_pwa_vehicle_configurations_latest as
select distinct on (license_plate)
    *
from public.pwa_vehicle_configurations
order by license_plate, created_at desc, id desc;

grant select on public.pwa_vehicle_configurations to anon, authenticated;
grant select on public.vw_pwa_vehicle_configurations_latest to anon, authenticated;
grant all on public.pwa_vehicle_configurations to service_role;

notify pgrst, 'reload schema';
