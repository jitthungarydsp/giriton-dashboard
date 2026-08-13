create table if not exists public.dsp_vehicle_service_status (
    vehicle_plate text primary key,
    car text,
    warehouse text,
    status text not null default 'active',
    odometer_km numeric,
    next_service_at date,
    service_place text,
    service_note text,
    updated_at timestamptz not null default now(),
    updated_by text
);

create index if not exists dsp_vehicle_service_status_next_service_idx
    on public.dsp_vehicle_service_status (next_service_at);

comment on table public.dsp_vehicle_service_status is
    'JITT Hub jarmu szerviz es flotta allapot tabla. A napi kiosztas tovabbra is a dsp_vehicle_assignments tablabol jon.';

comment on column public.dsp_vehicle_service_status.vehicle_plate is 'Rendszam, a jarmu azonositoja.';
comment on column public.dsp_vehicle_service_status.next_service_at is 'Kovetkezo tervezett szerviz napja.';
comment on column public.dsp_vehicle_service_status.service_place is 'Szerviz helye / partner neve.';
comment on column public.dsp_vehicle_service_status.odometer_km is 'Aktualis vagy utolso ismert km allas.';

grant select, insert, update, delete on public.dsp_vehicle_service_status to service_role;
grant select on public.dsp_vehicle_service_status to authenticated;
