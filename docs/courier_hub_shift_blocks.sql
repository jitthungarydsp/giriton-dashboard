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
    kifli_booking text,
    muszakpro_booking text,
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

alter table public.courier_hub_shift_blocks_raw
    add column if not exists kifli_booking text,
    add column if not exists muszakpro_booking text;

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
with muszakpro_normalized as (
    select
        b.id,
        b.source_row,
        b.work_date,
        coalesce(
            substring(upper(coalesce(b.warehouse, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.shift_text, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.booking_code, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.serial, '')) from '(BUD[12])')
        ) as warehouse_code,
        coalesce(
            substring(coalesce(b.shift_text, '') from '(\d{1,2}:\d{2})'),
            substring(coalesce(b.booking_code, '') from '(\d{1,2}:\d{2})'),
            substring(coalesce(b.serial, '') from '(\d{1,2}:\d{2})')
        )::time as shift_start_time,
        b.courier_id,
        b.email,
        b.serial,
        coalesce(
            nullif(b.serial, ''),
            nullif(regexp_replace(coalesce(b.legacy_key, ''), '_[0-9]+$', ''), ''),
            concat_ws('|', b.work_date::text, lower(coalesce(b.email, '')), coalesce(b.shift_text, ''), coalesce(b.booking_code, ''))
        ) as logical_booking_key,
        (
            upper(coalesce(b.status, '')) in ('TÖRÖLVE', 'TOROLVE', 'CANCELLED', 'CANCELED', 'DELETED', 'DELETE')
            or upper(coalesce(b.event_type, '')) in ('DELETE', 'CANCEL', 'CANCELLED', 'CANCELED', 'DELETED')
            or b.cancelled_at is not null
        ) as is_deleted,
        coalesce(b.cancelled_at, b.updated_at, b.fetched_at, b.created_at) as event_at
    from muszakpro.bookings b
    where b.work_date is not null
),
muszakpro_latest as (
    select *
    from (
        select
            m.*,
            row_number() over (
                partition by m.logical_booking_key
                order by m.event_at desc nulls last, m.source_row desc nulls last, m.id desc
            ) as latest_rank
        from muszakpro_normalized m
    ) ranked
    where latest_rank = 1
      and not is_deleted
      and warehouse_code is not null
      and shift_start_time is not null
)
select
    sb.work_date,
    sb.warehouse_id,
    sb.warehouse_code,
    sb.dsp_id,
    sb.block_key,
    sb.shift_template_id,
    sb.template_name,
    sb.slot_from,
    sb.slot_to,
    sb.occupancy_from,
    sb.occupancy_to,
    sb.status,
    sb.assigned,
    sb.opened,
    sb.free_slots,
    sb.capacity_published,
    sb.fetched_at,
    sb.updated_at,
    sb.kifli_booking,
    coalesce(muszakpro_slot.muszakpro_booking, sb.muszakpro_booking) as muszakpro_booking
from public.courier_hub_shift_blocks_raw sb
left join lateral (
    select string_agg(distinct coalesce(m.courier_id::text, nullif(m.serial, ''), m.email), ';' order by coalesce(m.courier_id::text, nullif(m.serial, ''), m.email)) as muszakpro_booking
    from muszakpro_latest m
    where m.work_date = sb.work_date
      and m.warehouse_code = upper(sb.warehouse_code)
      and (
          m.shift_start_time = sb.slot_from
          or m.shift_start_time = sb.occupancy_from::time
      )
) muszakpro_slot on true;

notify pgrst, 'reload schema';
