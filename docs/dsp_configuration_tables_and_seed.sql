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
    route_duration_hours numeric(4,2) not null default 0,
    route_duration_label text not null default '',
    display_order integer not null default 0,
    amount integer not null,
    source_note text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (valid_from, metric_type, service_type, level_name, route_duration_hours)
);

alter table public.dsp_bonus_rates
    drop constraint if exists dsp_bonus_rates_valid_from_metric_type_service_type_level_name_key,
    add column if not exists route_duration_hours numeric(4,2) not null default 0,
    add column if not exists route_duration_label text not null default '',
    add column if not exists display_order integer not null default 0,
    add column if not exists source_note text;

create unique index if not exists uq_dsp_bonus_rates_metric_duration
    on public.dsp_bonus_rates (
        valid_from,
        metric_type,
        service_type,
        level_name,
        route_duration_hours
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

delete from public.dsp_bonus_rates
where metric_type in ('DELAY', 'COMPLIANCE');

insert into public.dsp_bonus_rates (
    valid_from,
    metric_type,
    service_type,
    level_name,
    min_value,
    max_value,
    route_duration_hours,
    route_duration_label,
    display_order,
    amount,
    source_note,
    updated_at
)
values
-- Késedelmi mutató
('2026-01-01', 'DELAY', 'Expressz', 'Szint 1', 0.00, 1.50, 2.00, '<= 2,0 óra / Expressz', 1, 1333, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,0 óra',  'Szint 1', 0.00, 1.50, 3.00, '3,0 óra',              2, 2000, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,5 óra',  'Szint 1', 0.00, 1.50, 3.50, '3,5 óra',              3, 2333, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '4,0 óra',  'Szint 1', 0.00, 1.50, 4.00, '4,0 óra',              4, 2666, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'City',     'Szint 1', 0.00, 1.50, 4.50, '4,5 óra / Városi alap', 5, 3000, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '5,0 óra',  'Szint 1', 0.00, 1.50, 5.00, '5,0 óra',              6, 3333, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'Régió',    'Szint 1', 0.00, 1.50, 5.50, '5,5 óra / Regionális alap', 7, 3666, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '6,0 óra',  'Szint 1', 0.00, 1.50, 6.00, '6,0 óra',              8, 4000, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'Expressz', 'Szint 2', 1.51, 3.00, 2.00, '<= 2,0 óra / Expressz', 1,  666, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,0 óra',  'Szint 2', 1.51, 3.00, 3.00, '3,0 óra',              2, 1000, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,5 óra',  'Szint 2', 1.51, 3.00, 3.50, '3,5 óra',              3, 1166, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '4,0 óra',  'Szint 2', 1.51, 3.00, 4.00, '4,0 óra',              4, 1333, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'City',     'Szint 2', 1.51, 3.00, 4.50, '4,5 óra / Városi alap', 5, 1500, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '5,0 óra',  'Szint 2', 1.51, 3.00, 5.00, '5,0 óra',              6, 1666, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'Régió',    'Szint 2', 1.51, 3.00, 5.50, '5,5 óra / Regionális alap', 7, 1833, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '6,0 óra',  'Szint 2', 1.51, 3.00, 6.00, '6,0 óra',              8, 2000, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'Expressz', 'Szint 3', 3.01, 5.00, 2.00, '<= 2,0 óra / Expressz', 1,  333, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,0 óra',  'Szint 3', 3.01, 5.00, 3.00, '3,0 óra',              2,  500, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '3,5 óra',  'Szint 3', 3.01, 5.00, 3.50, '3,5 óra',              3,  583, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '4,0 óra',  'Szint 3', 3.01, 5.00, 4.00, '4,0 óra',              4,  666, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'City',     'Szint 3', 3.01, 5.00, 4.50, '4,5 óra / Városi alap', 5,  750, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '5,0 óra',  'Szint 3', 3.01, 5.00, 5.00, '5,0 óra',              6,  833, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', 'Régió',    'Szint 3', 3.01, 5.00, 5.50, '5,5 óra / Regionális alap', 7,  916, 'contract_delay_table', now()),
('2026-01-01', 'DELAY', '6,0 óra',  'Szint 3', 3.01, 5.00, 6.00, '6,0 óra',              8, 1000, 'contract_delay_table', now()),
-- Túramegfelelési mutató
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Szint 1', 0.00, 2.00, 2.00, '<= 2,0 óra / Expressz', 1, 1333, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,0 óra',  'Szint 1', 0.00, 2.00, 3.00, '3,0 óra',              2, 2000, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,5 óra',  'Szint 1', 0.00, 2.00, 3.50, '3,5 óra',              3, 2333, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '4,0 óra',  'Szint 1', 0.00, 2.00, 4.00, '4,0 óra',              4, 2666, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Szint 1', 0.00, 2.00, 4.50, '4,5 óra / Városi alap', 5, 3000, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '5,0 óra',  'Szint 1', 0.00, 2.00, 5.00, '5,0 óra',              6, 3333, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Szint 1', 0.00, 2.00, 5.50, '5,5 óra / Regionális alap', 7, 3666, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '6,0 óra',  'Szint 1', 0.00, 2.00, 6.00, '6,0 óra',              8, 4000, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Szint 2', 2.01, 4.00, 2.00, '<= 2,0 óra / Expressz', 1,  666, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,0 óra',  'Szint 2', 2.01, 4.00, 3.00, '3,0 óra',              2, 1000, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,5 óra',  'Szint 2', 2.01, 4.00, 3.50, '3,5 óra',              3, 1166, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '4,0 óra',  'Szint 2', 2.01, 4.00, 4.00, '4,0 óra',              4, 1333, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Szint 2', 2.01, 4.00, 4.50, '4,5 óra / Városi alap', 5, 1500, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '5,0 óra',  'Szint 2', 2.01, 4.00, 5.00, '5,0 óra',              6, 1666, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Szint 2', 2.01, 4.00, 5.50, '5,5 óra / Regionális alap', 7, 1833, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '6,0 óra',  'Szint 2', 2.01, 4.00, 6.00, '6,0 óra',              8, 2000, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'Expressz', 'Szint 3', 4.01, 10.00, 2.00, '<= 2,0 óra / Expressz', 1,  333, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,0 óra',  'Szint 3', 4.01, 10.00, 3.00, '3,0 óra',              2,  500, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '3,5 óra',  'Szint 3', 4.01, 10.00, 3.50, '3,5 óra',              3,  583, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '4,0 óra',  'Szint 3', 4.01, 10.00, 4.00, '4,0 óra',              4,  666, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'City',     'Szint 3', 4.01, 10.00, 4.50, '4,5 óra / Városi alap', 5,  750, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '5,0 óra',  'Szint 3', 4.01, 10.00, 5.00, '5,0 óra',              6,  833, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', 'Régió',    'Szint 3', 4.01, 10.00, 5.50, '5,5 óra / Regionális alap', 7,  916, 'contract_compliance_table', now()),
('2026-01-01', 'COMPLIANCE', '6,0 óra',  'Szint 3', 4.01, 10.00, 6.00, '6,0 óra',              8, 1000, 'contract_compliance_table', now()),
-- Ügyfélértékelés
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-1', 4.90, 5.00, 0.00, '', 1, 500, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-2', 4.80, 4.89, 0.00, '', 2, 300, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'Expressz', 'Ügyfélértékelés-3', 4.70, 4.79, 0.00, '', 3, 150, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-1', 4.90, 5.00, 0.00, '', 1, 500, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-2', 4.80, 4.89, 0.00, '', 2, 300, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'City',     'Ügyfélértékelés-3', 4.70, 4.79, 0.00, '', 3, 150, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-1', 4.90, 5.00, 0.00, '', 1, 500, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-2', 4.80, 4.89, 0.00, '', 2, 300, 'contract_customer_rating_table', now()),
('2026-01-01', 'CUSTOMER_RATING', 'Régió',    'Ügyfélértékelés-3', 4.70, 4.79, 0.00, '', 3, 150, 'contract_customer_rating_table', now())
on conflict (valid_from, metric_type, service_type, level_name, route_duration_hours)
do update set
    min_value = excluded.min_value,
    max_value = excluded.max_value,
    route_duration_label = excluded.route_duration_label,
    display_order = excluded.display_order,
    amount = excluded.amount,
    source_note = excluded.source_note,
    updated_at = now();

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
