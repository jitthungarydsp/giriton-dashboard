create table if not exists public.dsp_vehicle (
    vehicle_plate text primary key,
    owner_name text not null default '',
    service_name text not null default '',
    daily_rental_fee_huf numeric not null default 0,
    size_class text not null default '',
    vehicle_type text not null default '',
    highway_vignette text not null default '',
    highway_vignette_valid_until date,
    cooling_type text not null default '',
    ecofleet text not null default '',
    sticker_site text not null default '',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    updated_by text
);

alter table public.dsp_vehicle
    add column if not exists owner_name text not null default '',
    add column if not exists service_name text not null default '',
    add column if not exists daily_rental_fee_huf numeric not null default 0,
    add column if not exists size_class text not null default '',
    add column if not exists vehicle_type text not null default '',
    add column if not exists highway_vignette text not null default '',
    add column if not exists highway_vignette_valid_until date,
    add column if not exists cooling_type text not null default '',
    add column if not exists ecofleet text not null default '',
    add column if not exists sticker_site text not null default '',
    add column if not exists is_active boolean not null default true,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now(),
    add column if not exists updated_by text;

create index if not exists dsp_vehicle_owner_idx
    on public.dsp_vehicle (owner_name);

create index if not exists dsp_vehicle_active_idx
    on public.dsp_vehicle (is_active);

comment on table public.dsp_vehicle is
    'DSP kocsi torzs. Egy sor egy auto vegleges torzsadatait tartalmazza rendszam alapjan.';

comment on column public.dsp_vehicle.vehicle_plate is 'Rendszam, a jarmu egyedi azonositoja.';
comment on column public.dsp_vehicle.owner_name is 'Tulajdonos.';
comment on column public.dsp_vehicle.service_name is 'Szerviz.';
comment on column public.dsp_vehicle.daily_rental_fee_huf is 'Berlési dij naponta, HUF.';
comment on column public.dsp_vehicle.size_class is 'Meret osztaly.';
comment on column public.dsp_vehicle.vehicle_type is 'Gk-i tipusa.';
comment on column public.dsp_vehicle.highway_vignette is 'Autopalya matrica tipusa vagy allapota.';
comment on column public.dsp_vehicle.highway_vignette_valid_until is 'Autopalya matrica ervenyessegi ideje.';
comment on column public.dsp_vehicle.cooling_type is 'Huto.';
comment on column public.dsp_vehicle.ecofleet is 'ECOFLEET azonosito vagy allapot.';
comment on column public.dsp_vehicle.sticker_site is 'Matrica telephely.';
comment on column public.dsp_vehicle.is_active is 'Kocsi torzs statusza: true aktiv, false inaktiv.';

grant select, insert, update, delete on public.dsp_vehicle to service_role;
grant select on public.dsp_vehicle to authenticated;
