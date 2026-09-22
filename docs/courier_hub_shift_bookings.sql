create table if not exists public.courier_hub_shift_bookings_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'courier_hub_shift_booking_state',
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text,
    dsp_id integer not null,
    courier_id integer not null,
    jitt_internal_id text,
    courier_name text,
    email text,
    phone_number text,
    block_key text not null,
    shift_template_id integer,
    shift_text text,
    slot_from time,
    slot_to time,
    status text,
    movement_type text not null,
    active boolean not null default true,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    deleted_at timestamptz,
    request_url text,
    subscription_json jsonb not null default '{}'::jsonb,
    courier_json jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),

    constraint courier_hub_shift_bookings_raw_unique
        unique (work_date, warehouse_id, dsp_id, courier_id, block_key)
);

create index if not exists idx_courier_hub_shift_bookings_date
    on public.courier_hub_shift_bookings_raw (work_date);

create index if not exists idx_courier_hub_shift_bookings_courier
    on public.courier_hub_shift_bookings_raw (courier_id);

create index if not exists idx_courier_hub_shift_bookings_jitt
    on public.courier_hub_shift_bookings_raw (jitt_internal_id);

create index if not exists idx_courier_hub_shift_bookings_block
    on public.courier_hub_shift_bookings_raw (block_key);

create index if not exists idx_courier_hub_shift_bookings_movement
    on public.courier_hub_shift_bookings_raw (movement_type);

create or replace view public.vw_courier_hub_shift_bookings as
select
    work_date,
    warehouse_code,
    dsp_id,
    jitt_internal_id,
    courier_id,
    courier_name,
    email,
    phone_number,
    block_key,
    shift_template_id,
    shift_text,
    slot_from,
    slot_to,
    status,
    movement_type,
    active,
    first_seen_at,
    last_seen_at,
    deleted_at,
    updated_at
from public.courier_hub_shift_bookings_raw;
