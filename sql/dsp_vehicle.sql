create table if not exists public.dsp_vehicle (
    vehicle_plate text primary key,
    vehicle_type text not null default '',
    vehicle_brand text not null default '',
    vehicle_model text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    updated_by text
);

create index if not exists dsp_vehicle_brand_model_idx
    on public.dsp_vehicle (vehicle_brand, vehicle_model);

comment on table public.dsp_vehicle is
    'DSP jarmu torzs. Egy sor egy auto alapadatait tartalmazza rendszam alapjan.';

comment on column public.dsp_vehicle.vehicle_plate is 'Rendszam, a jarmu egyedi azonositoja.';
comment on column public.dsp_vehicle.vehicle_type is 'Jarmu tipusa / kategoriaja, peldaul furgon, szemelyauto.';
comment on column public.dsp_vehicle.vehicle_brand is 'Jarmu marka, peldaul Renault, Ford, Volkswagen.';
comment on column public.dsp_vehicle.vehicle_model is 'Jarmu modell / tipus, peldaul Trafic, Transit, Transporter.';

grant select, insert, update, delete on public.dsp_vehicle to service_role;
grant select on public.dsp_vehicle to authenticated;
