-- DSP konfigurációs táblák létrehozása és feltöltése

create table if not exists public.dsp_order_arrivals (
    work_date date not null,
    driver_id integer not null,
    courier_id text,
    route_id text not null,
    checkpoint_id text not null,
    order_id text,
    position integer,
    address text,
    idoablak_kezdete timestamp,
    idoablak_vege timestamp,
    idoablak text,
    tervezett_erkezes timestamp,
    valos_erkezes timestamp,
    tervhez_kepest_perc integer,
    tervhez_kepest_statusz text,
    idoablak_vegehez_kepest_perc integer,
    idoablakhoz_kepest_statusz text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_date, driver_id, route_id, checkpoint_id)
);

create table if not exists public.dsp_route_delay_statistics (
    work_date date not null,
    driver_id integer not null,
    route_id text not null,
    orders integer not null,
    keso_rendelesek integer not null,
    korai_rendelesek integer not null,
    nem_idoben_rendelesek integer not null,
    keses_szazalek numeric(10,2),
    korai_szazalek numeric(10,2),
    nem_idoben_szazalek numeric(10,2),
    kesedelmi_kategoria text,
    megfelelesi_kategoria text,
    city_delay_bonus integer,
    city_compliance_bonus integer,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_date, driver_id, route_id)
);

create table if not exists public.dsp_driver_month_summary (
    work_month date not null,
    driver_id integer not null,
    courier_id integer,
    ledolgozott_napok integer,
    hetfo integer,
    kedd integer,
    szerda integer,
    csutortok integer,
    pentek integer,
    szombat integer,
    vasarnap integer,
    kiemelt_napok integer,
    sima_napok integer,
    kor_db integer,
    cim_db integer,
    kor_atlag_naponta numeric(10,2),
    cim_atlag_koronkent numeric(10,2),
    cim_atlag_naponta numeric(10,2),
    keso_rendeles_db integer,
    korai_rendeles_db integer,
    nem_idoben_rendeles_db integer,
    keses_szazalek numeric(10,2),
    korai_szazalek numeric(10,2),
    nem_idoben_szazalek numeric(10,2),
    kesedelmi_kategoria text,
    city_delay_bonus integer,
    megfelelesi_kategoria text,
    city_compliance_bonus integer,
    kiemelt_napok_osszege integer,
    sima_napok_osszege integer,
    alap_osszeg integer,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_month, driver_id)
);

create table if not exists public.dsp_day_rates (
    id bigserial primary key,
    valid_from date not null default '2026-01-01',
    valid_to date,
    service_type text not null,
    day_type text not null,
    loyalty_bonus boolean not null default false,
    amount integer not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (valid_from, service_type, day_type, loyalty_bonus)
);

create table if not exists public.dsp_bonus_rates (
    id bigserial primary key,
    valid_from date not null default '2026-01-01',
    valid_to date,
    metric_type text not null,
    service_type text not null,
    level_name text not null,
    min_value numeric(10,2) not null,
    max_value numeric(10,2) not null,
    amount integer not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (valid_from, metric_type, service_type, level_name)
);

create table if not exists public.dsp_band_rates (
    id bigserial primary key,
    valid_from date not null default '2026-01-01',
    valid_to date,
    service_type text not null,
    driver_level text not null,
    day_type text not null,
    amount integer not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (valid_from, service_type, driver_level, day_type)
);

-- Díjazási adatok feltöltése a PDF/kép alapján

insert into public.dsp_day_rates (valid_from, service_type, day_type, loyalty_bonus, amount, updated_at)
values
('2026-01-01', 'Expressz', 'KIEMELT', false, 3350, now()),
('2026-01-01', 'City',     'KIEMELT', false, 6500, now()),
('2026-01-01', 'Régió',    'KIEMELT', false, 9000, now()),
('2026-01-01', 'Expressz', 'KIEMELT', true,  3350, now()),
('2026-01-01', 'City',     'KIEMELT', true,  7500, now()),
('2026-01-01', 'Régió',    'KIEMELT', true, 10000, now()),
('2026-01-01', 'Expressz', 'SIMA',    false, 2650, now()),
('2026-01-01', 'City',     'SIMA',    false, 4500, now()),
('2026-01-01', 'Régió',    'SIMA',    false, 6300, now()),
('2026-01-01', 'Expressz', 'SIMA',    true,  2650, now()),
('2026-01-01', 'City',     'SIMA',    true,  5500, now()),
('2026-01-01', 'Régió',    'SIMA',    true,  7300, now())
on conflict (valid_from, service_type, day_type, loyalty_bonus)
do update set amount = excluded.amount, updated_at = now();

insert into public.dsp_bonus_rates (valid_from, metric_type, service_type, level_name, min_value, max_value, amount, updated_at)
values
-- Késedelmi mutató
('2026-01-01', 'DELAY', 'Expressz', 'Késedelmi-1', 0.00, 1.50, 1333, now()),
('2026-01-01', 'DELAY', 'Expressz', 'Késedelmi-2', 1.51, 3.00, 500, now()),
('2026-01-01', 'DELAY', 'Expressz', 'Késedelmi-3', 3.01, 5.00, 250, now()),
('2026-01-01', 'DELAY', 'City',     'Késedelmi-1', 0.00, 1.50, 3000, now()),
('2026-01-01', 'DELAY', 'City',     'Késedelmi-2', 1.51, 3.00, 1000, now()),
('2026-01-01', 'DELAY', 'City',     'Késedelmi-3', 3.01, 5.00, 500, now()),
('2026-01-01', 'DELAY', 'Régió',    'Késedelmi-1', 0.00, 1.50, 3330, now()),
('2026-01-01', 'DELAY', 'Régió',    'Késedelmi-2', 1.51, 3.00, 1000, now()),
('2026-01-01', 'DELAY', 'Régió',    'Késedelmi-3', 3.01, 5.00, 500, now()),
-- Túramegfelelési mutató
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Megfelelési-1', 0.00, 2.00, 1333, now()),
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Megfelelési-2', 2.01, 4.00, 500, now()),
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Megfelelési-3', 4.01, 10.00, 250, now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Megfelelési-1', 0.00, 2.00, 3000, now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Megfelelési-2', 2.01, 4.00, 1000, now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Megfelelési-3', 4.01, 10.00, 500, now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Megfelelési-1', 0.00, 2.00, 3300, now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Megfelelési-2', 2.01, 4.00, 1000, now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Megfelelési-3', 4.01, 10.00, 500, now()),
-- Ügyfélértékelés
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-1', 4.90, 5.00, 500, now()),
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-2', 4.80, 4.89, 300, now()),
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-3', 4.70, 4.79, 150, now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-1', 4.90, 5.00, 500, now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-2', 4.80, 4.89, 300, now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-3', 4.70, 4.79, 150, now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-1', 4.90, 5.00, 500, now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-2', 4.80, 4.89, 300, now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-3', 4.70, 4.79, 150, now())
on conflict (valid_from, metric_type, service_type, level_name)
do update set min_value = excluded.min_value, max_value = excluded.max_value, amount = excluded.amount, updated_at = now();

insert into public.dsp_band_rates (valid_from, service_type, driver_level, day_type, amount, updated_at)
values
('2026-01-01', 'Expressz', 'Megbízható Futár',      'KIEMELT',  6516, now()),
('2026-01-01', 'City',     'Megbízható Futár',      'KIEMELT', 14000, now()),
('2026-01-01', 'Régió',    'Megbízható Futár',      'KIEMELT', 17130, now()),
('2026-01-01', 'Expressz', 'Kezdő futár',           'KIEMELT',  4650, now()),
('2026-01-01', 'City',     'Kezdő futár',           'KIEMELT',  9800, now()),
('2026-01-01', 'Régió',    'Kezdő futár',           'KIEMELT', 12300, now()),
('2026-01-01', 'Expressz', 'Tréninget igénylő Futár','KIEMELT', 4000, now()),
('2026-01-01', 'City',     'Tréninget igénylő Futár','KIEMELT', 8650, now()),
('2026-01-01', 'Régió',    'Tréninget igénylő Futár','KIEMELT', 11150, now()),
('2026-01-01', 'Expressz', 'Megbízható Futár',      'SIMA',  5816, now()),
('2026-01-01', 'City',     'Megbízható Futár',      'SIMA', 12000, now()),
('2026-01-01', 'Régió',    'Megbízható Futár',      'SIMA', 14430, now()),
('2026-01-01', 'Expressz', 'Kezdő futár',           'SIMA',  3950, now()),
('2026-01-01', 'City',     'Kezdő futár',           'SIMA',  7800, now()),
('2026-01-01', 'Régió',    'Kezdő futár',           'SIMA',  9600, now()),
('2026-01-01', 'Expressz', 'Tréninget igénylő Futár','SIMA', 3300, now()),
('2026-01-01', 'City',     'Tréninget igénylő Futár','SIMA', 6650, now()),
('2026-01-01', 'Régió',    'Tréninget igénylő Futár','SIMA', 8450, now())
on conflict (valid_from, service_type, driver_level, day_type)
do update set amount = excluded.amount, updated_at = now();