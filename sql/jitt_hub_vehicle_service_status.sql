create table if not exists public.dsp_vehicle_service_status (
    vehicle_plate text primary key,
    car text,
    warehouse text,
    status text not null default 'active',
    odometer_km numeric,
    assigned_courier_id text,
    assigned_courier_name text,
    manual_assignment_date date,
    next_service_at date,
    service_place text,
    service_note text,
    updated_at timestamptz not null default now(),
    updated_by text
);

alter table public.dsp_vehicle_service_status
    add column if not exists assigned_courier_id text,
    add column if not exists assigned_courier_name text,
    add column if not exists manual_assignment_date date;

create index if not exists dsp_vehicle_service_status_next_service_idx
    on public.dsp_vehicle_service_status (next_service_at);

comment on table public.dsp_vehicle_service_status is
    'JITT Hub jarmu szerviz es flotta allapot tabla. A napi kiosztas tovabbra is a dsp_vehicle_assignments tablabol jon.';

comment on column public.dsp_vehicle_service_status.vehicle_plate is 'Rendszam, a jarmu azonositoja.';
comment on column public.dsp_vehicle_service_status.next_service_at is 'Kovetkezo tervezett szerviz napja.';
comment on column public.dsp_vehicle_service_status.service_place is 'Szerviz helye / partner neve.';
comment on column public.dsp_vehicle_service_status.odometer_km is 'Aktualis vagy utolso ismert km allas.';
comment on column public.dsp_vehicle_service_status.assigned_courier_id is 'Hub feluleten kezzel megadott futar azonosito, akinek az autot kiosztjuk.';
comment on column public.dsp_vehicle_service_status.assigned_courier_name is 'Hub feluleten kezzel megadott futar neve, akinek az autot kiosztjuk.';
comment on column public.dsp_vehicle_service_status.manual_assignment_date is 'Kezi jarmukiosztas napja.';

grant select, insert, update, delete on public.dsp_vehicle_service_status to service_role;
grant select on public.dsp_vehicle_service_status to authenticated;
