create table if not exists public.courier_hub_courier_identity_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'courier_hub_roster_identity',
    courier_id integer not null,
    dsp_id integer not null,
    warehouse_id integer,
    warehouse_code text,
    jitt_internal_id text not null,
    name_without_identifier text,
    name_json text,
    phone_number text,
    email text,
    giriton_person_id text,
    registered_since text,
    registered_since_date date,
    source_page integer,
    source_row_index integer,
    request_url text,
    response_json jsonb not null default '{}'::jsonb,
    last_seen_at timestamptz not null default now(),
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint courier_hub_courier_identity_unique
        unique (courier_id, dsp_id)
);

create unique index if not exists courier_hub_courier_identity_jitt_id_unique
    on public.courier_hub_courier_identity_raw (jitt_internal_id);

create index if not exists idx_courier_hub_courier_identity_courier
    on public.courier_hub_courier_identity_raw (courier_id);

create index if not exists idx_courier_hub_courier_identity_warehouse
    on public.courier_hub_courier_identity_raw (warehouse_id);

create index if not exists idx_courier_hub_courier_identity_registered
    on public.courier_hub_courier_identity_raw (registered_since_date);

create or replace view public.vw_courier_hub_courier_identity as
select
    jitt_internal_id,
    courier_id,
    warehouse_code,
    name_without_identifier,
    name_json,
    phone_number,
    email,
    giriton_person_id,
    registered_since,
    registered_since_date,
    last_seen_at,
    updated_at
from public.courier_hub_courier_identity_raw;
