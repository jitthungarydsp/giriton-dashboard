create table if not exists public.courier_hub_shift_blocks_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'courier_hub_shift_blocks',
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text,
    dsp_id integer not null,
    block_key text not null,
    shift_template_id integer,
    layer_id integer,
    dsp_company_id integer,
    template_name text,
    slot_from time,
    slot_to time,
    occupancy_from timestamptz,
    occupancy_to timestamptz,
    status text,
    assigned integer,
    opened integer,
    free_slots integer,
    capacity_published boolean,
    subscribe_locked boolean,
    unsubscribe_locked boolean,
    allow_subscribing_till timestamptz,
    allow_unsubscribing_till timestamptz,
    subscribe_seconds_remaining integer,
    unsubscribe_seconds_remaining integer,
    request_url text,
    response_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint courier_hub_shift_blocks_raw_unique
        unique (work_date, warehouse_id, dsp_id, block_key)
);

create index if not exists idx_courier_hub_shift_blocks_raw_work_date
    on public.courier_hub_shift_blocks_raw (work_date);

create index if not exists idx_courier_hub_shift_blocks_raw_block_key
    on public.courier_hub_shift_blocks_raw (block_key);

create index if not exists idx_courier_hub_shift_blocks_raw_template
    on public.courier_hub_shift_blocks_raw (shift_template_id);

create index if not exists idx_courier_hub_shift_blocks_raw_status
    on public.courier_hub_shift_blocks_raw (status);

create table if not exists public.courier_hub_roster_shift_subscribers_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'courier_hub_roster_shift_subscribers',
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text,
    dsp_id integer not null,
    courier_id integer not null,
    courier_name text,
    email text,
    phone_number text,
    subscriber_key text not null,
    block_key text,
    shift_template_id integer,
    shift_text text,
    slot_from time,
    slot_to time,
    status text,
    source_page integer,
    source_row_index integer,
    source_shift_index integer,
    request_url text,
    subscription_json jsonb not null default '{}'::jsonb,
    courier_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint courier_hub_roster_shift_subscribers_raw_unique
        unique (work_date, warehouse_id, dsp_id, courier_id, subscriber_key)
);

create index if not exists idx_courier_hub_roster_shift_subscribers_date
    on public.courier_hub_roster_shift_subscribers_raw (work_date);

create index if not exists idx_courier_hub_roster_shift_subscribers_courier
    on public.courier_hub_roster_shift_subscribers_raw (courier_id);

create index if not exists idx_courier_hub_roster_shift_subscribers_block
    on public.courier_hub_roster_shift_subscribers_raw (block_key);

create index if not exists idx_courier_hub_roster_shift_subscribers_template
    on public.courier_hub_roster_shift_subscribers_raw (shift_template_id);

create or replace view public.vw_courier_hub_shift_block_capacity as
select
    work_date,
    warehouse_id,
    warehouse_code,
    dsp_id,
    block_key,
    shift_template_id,
    template_name,
    slot_from,
    slot_to,
    occupancy_from,
    occupancy_to,
    status,
    assigned,
    opened,
    free_slots,
    capacity_published,
    fetched_at,
    updated_at
from public.courier_hub_shift_blocks_raw;
