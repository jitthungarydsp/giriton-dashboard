-- MuszakPro booking overview.
-- This is a read-only validation layer for the new blockKey based view.
-- It does not change the existing booking flow.

create schema if not exists muszakpro;

create or replace view public.vw_muszakpro_booking_overview as
with muszakpro_rows as (
    select
        b.id as muszakpro_row_id,
        b.source_row,
        b.timestamp_text,
        b.work_date,
        lower(regexp_replace(coalesce(b.email, ''), '\s+', '', 'g')) as email_normalized,
        b.email,
        b.shift_text,
        coalesce(
            substring(upper(coalesce(b.warehouse, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.shift_text, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.booking_code, '')) from '(BUD[12])')
        ) as warehouse_code,
        b.booking_code,
        b.admin_recorder,
        b.giriton_uploaded,
        b.system_check,
        b.legacy_key,
        b.courier_id as muszakpro_courier_id,
        b.courier_name as muszakpro_courier_name,
        b.serial,
        b.status as muszakpro_status,
        b.fetched_at,
        coalesce(
            substring(coalesce(b.shift_text, '') from '(\d{1,2}:\d{2})'),
            substring(coalesce(b.booking_code, '') from '(\d{1,2}:\d{2})')
        )::time as shift_start_time
    from public.raw_muszakpro_bookings b
    where b.work_date is not null
),
identity_match as (
    select
        m.*,
        i.jitt_internal_id,
        i.courier_id,
        i.name_without_identifier,
        i.name_json,
        i.phone_number,
        i.email as identity_email,
        i.giriton_person_id,
        i.registered_since
    from muszakpro_rows m
    left join lateral (
        select i.*
        from public.courier_hub_courier_identity_raw i
        where
            (
                m.muszakpro_courier_id is not null
                and i.courier_id = m.muszakpro_courier_id
            )
            or (
                m.email_normalized <> ''
                and lower(regexp_replace(coalesce(i.email, ''), '\s+', '', 'g')) = m.email_normalized
            )
        order by
            case
                when m.muszakpro_courier_id is not null and i.courier_id = m.muszakpro_courier_id then 0
                else 1
            end,
            i.last_seen_at desc nulls last
        limit 1
    ) i on true
),
block_match as (
    select
        i.*,
        sb.warehouse_id,
        sb.dsp_id,
        sb.block_key,
        sb.shift_template_id,
        sb.slot_from,
        sb.slot_to,
        sb.occupancy_from,
        sb.occupancy_to,
        sb.status as block_status,
        sb.assigned,
        sb.opened,
        sb.free_slots,
        sb.capacity_published
    from identity_match i
    left join lateral (
        select sb.*
        from public.courier_hub_shift_blocks_raw sb
        where sb.work_date = i.work_date
          and upper(sb.warehouse_code) = i.warehouse_code
          and i.shift_start_time is not null
          and (
              sb.slot_from = i.shift_start_time
              or sb.occupancy_from::time = i.shift_start_time
              or abs(extract(epoch from (sb.slot_from - i.shift_start_time))) <= 1800
              or abs(extract(epoch from (sb.occupancy_from::time - i.shift_start_time))) <= 1800
          )
        order by
            case
                when sb.slot_from = i.shift_start_time then 0
                when sb.occupancy_from::time = i.shift_start_time then 1
                else 2
            end,
            least(
                abs(extract(epoch from (sb.slot_from - i.shift_start_time))),
                abs(extract(epoch from (sb.occupancy_from::time - i.shift_start_time)))
            ),
            sb.updated_at desc nulls last
        limit 1
    ) sb on true
),
booking_match as (
    select
        b.*,
        chb.courier_id as kifli_booking_courier_id,
        chb.jitt_internal_id as kifli_booking_jitt_internal_id,
        chb.courier_name as kifli_booking_courier_name,
        chb.email as kifli_booking_email,
        chb.phone_number as kifli_booking_phone_number,
        chb.movement_type as kifli_movement_type,
        chb.active as kifli_booking_active,
        chb.first_seen_at as kifli_first_seen_at,
        chb.last_seen_at as kifli_last_seen_at,
        chb.deleted_at as kifli_deleted_at
    from block_match b
    left join public.courier_hub_shift_bookings_raw chb
      on chb.work_date = b.work_date
     and chb.warehouse_id = b.warehouse_id
     and chb.dsp_id = b.dsp_id
     and chb.block_key = b.block_key
     and (
         chb.courier_id = b.courier_id
         or (
             b.jitt_internal_id is not null
             and chb.jitt_internal_id = b.jitt_internal_id
         )
     )
)
select
    now() as overview_generated_at,
    work_date,
    warehouse_code,
    email,
    identity_email,
    coalesce(courier_id, muszakpro_courier_id) as courier_id,
    jitt_internal_id,
    name_without_identifier,
    coalesce(name_json, muszakpro_courier_name, kifli_booking_courier_name) as courier_name,
    phone_number,
    giriton_person_id,
    registered_since,
    shift_text,
    shift_start_time,
    booking_code,
    serial,
    muszakpro_status,
    source_row,
    block_key,
    case
        when block_key is not null and jitt_internal_id is not null
            then block_key || '_' || jitt_internal_id
        else ''
    end as booking_key,
    shift_template_id,
    slot_from,
    slot_to,
    occupancy_from,
    occupancy_to,
    block_status,
    assigned,
    opened,
    free_slots,
    capacity_published,
    kifli_booking_courier_id,
    kifli_booking_jitt_internal_id,
    kifli_booking_courier_name,
    kifli_booking_email,
    kifli_movement_type,
    kifli_booking_active,
    kifli_first_seen_at,
    kifli_last_seen_at,
    kifli_deleted_at,
    case
        when upper(coalesce(muszakpro_status, '')) not in ('', 'ACTIVE')
            then 'NEM AKTIV MUSZAKPRO SOR'
        when jitt_internal_id is null
            then 'NINCS ROBOT/JITT AZONOSITAS'
        when block_key is null
            then 'NINCS BLOCKKEY'
        when kifli_booking_courier_id is null
            then 'NINCS KIFLI FOGLALAS'
        when kifli_booking_active is false
            then 'TOROLT FOGLALAS'
        else 'JOGOS'
    end as validation_status,
    case
        when upper(coalesce(muszakpro_status, '')) not in ('', 'ACTIVE')
            then 'A MűszakPro sor nem aktív.'
        when jitt_internal_id is null
            then 'Az e-mail/courierId alapján nincs JITT azonosító.'
        when block_key is null
            then 'A dátum + raktár + műszakkezdés alapján nincs Kifli block.'
        when kifli_booking_courier_id is null
            then 'Van blockKey, de ezen a blockon nincs ilyen futár foglalva.'
        when kifli_booking_active is false
            then 'A foglalás korábban megvolt, de most törölt/nem aktív.'
        else 'blockKey + JITT azonosító alapján egyezik.'
    end as validation_reason,
    fetched_at
from booking_match;

create index if not exists idx_courier_hub_shift_bookings_raw_jitt
    on public.courier_hub_shift_bookings_raw (jitt_internal_id);

create index if not exists idx_courier_hub_shift_bookings_raw_lookup
    on public.courier_hub_shift_bookings_raw (work_date, warehouse_id, dsp_id, block_key, courier_id);
