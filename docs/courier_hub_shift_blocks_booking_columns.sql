alter table public.courier_hub_shift_blocks_raw
    add column if not exists kifli_booking text,
    add column if not exists muszakpro_booking text;

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
