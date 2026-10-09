-- MuszakPro bookings vs Courier Hub recorded shift bookings.
--
-- Purpose:
--   One row per active muszakpro.bookings row, with the matching Courier Hub
--   shift block and the actual Hub booking state next to it.
--
-- Typical October query:
--   select *
--   from public.vw_muszakpro_hub_shift_comparison
--   where work_date >= date '2026-10-01'
--     and work_date <  date '2026-11-01'
--   order by work_date, warehouse_code, muszakpro_shift_start_time, courier_name;

create schema if not exists muszakpro;

create or replace view public.vw_muszakpro_hub_shift_comparison as
with muszakpro_rows as (
    select
        b.id as muszakpro_booking_id,
        b.source_row,
        b.timestamp_text,
        b.work_date,
        b.email,
        lower(regexp_replace(coalesce(b.email, ''), '\s+', '', 'g')) as email_normalized,
        b.shift_text as muszakpro_shift_text,
        coalesce(
            substring(upper(coalesce(b.warehouse, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.shift_text, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.booking_code, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.serial, '')) from '(BUD[12])')
        ) as warehouse_code,
        b.booking_code,
        b.legacy_key,
        b.courier_id as muszakpro_courier_id,
        b.courier_name as muszakpro_courier_name,
        b.serial,
        b.status as muszakpro_status,
        b.event_type,
        b.cancelled_at,
        b.fetched_at,
        b.updated_at,
        coalesce(
            substring(coalesce(b.shift_text, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])'),
            substring(coalesce(b.booking_code, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])'),
            substring(coalesce(b.serial, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])')
        )::time as muszakpro_shift_start_time,
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
                order by m.event_at desc nulls last, m.source_row desc nulls last, m.muszakpro_booking_id desc
            ) as latest_rank
        from muszakpro_rows m
    ) ranked
    where latest_rank = 1
      and not is_deleted
),
identity_match as (
    select
        m.*,
        i.courier_id as hub_courier_id,
        i.jitt_internal_id,
        i.name_without_identifier,
        i.name_json,
        i.email as hub_identity_email,
        i.phone_number as hub_phone_number,
        i.giriton_person_id,
        i.registered_since,
        i.last_seen_at as identity_last_seen_at
    from muszakpro_latest m
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
        sb.template_name as hub_template_name,
        sb.slot_from as hub_slot_from,
        sb.slot_to as hub_slot_to,
        sb.occupancy_from as hub_occupancy_from,
        sb.occupancy_to as hub_occupancy_to,
        sb.status as hub_block_status,
        sb.assigned as hub_assigned,
        sb.opened as hub_opened,
        sb.free_slots as hub_free_slots,
        sb.capacity_published,
        sb.updated_at as hub_block_updated_at,
        case
            when sb.block_key is null then null
            when sb.slot_from = i.muszakpro_shift_start_time then 0
            when sb.occupancy_from::time = i.muszakpro_shift_start_time then 0
            else least(
                abs(extract(epoch from (sb.slot_from - i.muszakpro_shift_start_time))) / 60,
                abs(extract(epoch from (sb.occupancy_from::time - i.muszakpro_shift_start_time))) / 60
            )::integer
        end as hub_slot_diff_minutes
    from identity_match i
    left join lateral (
        select sb.*
        from public.courier_hub_shift_blocks_raw sb
        where sb.work_date = i.work_date
          and upper(sb.warehouse_code) = i.warehouse_code
          and i.muszakpro_shift_start_time is not null
          and (
              sb.slot_from = i.muszakpro_shift_start_time
              or sb.occupancy_from::time = i.muszakpro_shift_start_time
              or abs(extract(epoch from (sb.slot_from - i.muszakpro_shift_start_time))) <= 1800
              or abs(extract(epoch from (sb.occupancy_from::time - i.muszakpro_shift_start_time))) <= 1800
          )
        order by
            case
                when sb.slot_from = i.muszakpro_shift_start_time then 0
                when sb.occupancy_from::time = i.muszakpro_shift_start_time then 1
                else 2
            end,
            least(
                abs(extract(epoch from (sb.slot_from - i.muszakpro_shift_start_time))),
                abs(extract(epoch from (sb.occupancy_from::time - i.muszakpro_shift_start_time)))
            ),
            sb.updated_at desc nulls last
        limit 1
    ) sb on true
),
hub_booking_match as (
    select
        b.*,
        chb.id as hub_booking_id,
        chb.courier_id as hub_booking_courier_id,
        chb.jitt_internal_id as hub_booking_jitt_internal_id,
        chb.courier_name as hub_booking_courier_name,
        chb.email as hub_booking_email,
        chb.phone_number as hub_booking_phone_number,
        chb.shift_text as hub_booking_shift_text,
        chb.slot_from as hub_booking_slot_from,
        chb.slot_to as hub_booking_slot_to,
        chb.status as hub_booking_status,
        chb.movement_type as hub_booking_movement_type,
        chb.active as hub_booking_active,
        chb.first_seen_at as hub_booking_first_seen_at,
        chb.last_seen_at as hub_booking_last_seen_at,
        chb.deleted_at as hub_booking_deleted_at
    from block_match b
    left join public.courier_hub_shift_bookings_raw chb
      on chb.work_date = b.work_date
     and chb.warehouse_id = b.warehouse_id
     and chb.dsp_id = b.dsp_id
     and chb.block_key = b.block_key
     and (
         chb.courier_id = b.hub_courier_id
         or (
             b.jitt_internal_id is not null
             and chb.jitt_internal_id = b.jitt_internal_id
         )
         or (
             b.email_normalized <> ''
             and lower(regexp_replace(coalesce(chb.email, ''), '\s+', '', 'g')) = b.email_normalized
         )
     )
)
select
    now() as comparison_generated_at,
    work_date,
    warehouse_code,
    coalesce(hub_courier_id, muszakpro_courier_id) as courier_id,
    coalesce(name_json, name_without_identifier, muszakpro_courier_name, hub_booking_courier_name) as courier_name,
    email as muszakpro_email,
    hub_identity_email,
    jitt_internal_id,
    giriton_person_id,
    muszakpro_shift_text,
    muszakpro_shift_start_time,
    booking_code as muszakpro_booking_code,
    serial as muszakpro_serial,
    muszakpro_status,
    source_row as muszakpro_source_row,
    fetched_at as muszakpro_fetched_at,
    block_key,
    shift_template_id,
    hub_template_name,
    hub_slot_from,
    hub_slot_to,
    hub_occupancy_from,
    hub_occupancy_to,
    hub_slot_diff_minutes,
    hub_block_status,
    hub_opened,
    hub_assigned,
    hub_free_slots,
    capacity_published,
    hub_booking_id,
    hub_booking_courier_id,
    hub_booking_jitt_internal_id,
    hub_booking_courier_name,
    hub_booking_email,
    hub_booking_shift_text,
    hub_booking_slot_from,
    hub_booking_slot_to,
    hub_booking_status,
    hub_booking_movement_type,
    hub_booking_active,
    hub_booking_first_seen_at,
    hub_booking_last_seen_at,
    hub_booking_deleted_at,
    case
        when warehouse_code is null
            then 'MUSZAKPRO_RAKTAR_HIANYZIK'
        when muszakpro_shift_start_time is null
            then 'MUSZAKPRO_MUSZAK_IDO_HIANYZIK'
        when hub_courier_id is null and jitt_internal_id is null
            then 'NINCS_HUB_FUTAR_AZONOSITAS'
        when block_key is null
            then 'NINCS_HUB_MUSZAK'
        when hub_booking_id is null
            then 'NINCS_HUB_FOGLALAS'
        when hub_booking_active is false
            then 'HUB_FOGLALAS_TOROLVE'
        when hub_slot_diff_minutes is not null and hub_slot_diff_minutes > 0
            then 'HUB_FOGLALAS_ELTERO_SLOT'
        else 'RENDBEN'
    end as comparison_status,
    case
        when warehouse_code is null
            then 'A MűszakPro sorból nem olvasható ki BUD1/BUD2 raktár.'
        when muszakpro_shift_start_time is null
            then 'A MűszakPro sorból nem olvasható ki műszakkezdés.'
        when hub_courier_id is null and jitt_internal_id is null
            then 'A MűszakPro courierId/e-mail alapján nincs Hub futár/JITT azonosítás.'
        when block_key is null
            then 'A dátum + raktár + műszakkezdés alapján nincs Hub műszak block.'
        when hub_booking_id is null
            then 'Van Hub műszak block, de ezen nincs rögzítve ez a futár.'
        when hub_booking_active is false
            then 'A Hub foglalás szerepel, de törölt/nem aktív.'
        when hub_slot_diff_minutes is not null and hub_slot_diff_minutes > 0
            then 'Van Hub foglalás, de nem pontosan ugyanarra a slotra illeszkedik.'
        else 'A MűszakPro foglalás és a Hubon rögzített műszak egyezik.'
    end as comparison_reason
from hub_booking_match;

drop view if exists public.vw_muszakpro_hub_shift_time_mismatch;

create or replace view public.vw_muszakpro_hub_shift_time_mismatch as
with muszakpro_rows as (
    select
        b.id as muszakpro_booking_id,
        b.source_row,
        b.work_date,
        b.email,
        lower(regexp_replace(coalesce(b.email, ''), '\s+', '', 'g')) as email_normalized,
        b.shift_text as muszakpro_shift_text,
        coalesce(
            substring(upper(coalesce(b.warehouse, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.shift_text, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.booking_code, '')) from '(BUD[12])'),
            substring(upper(coalesce(b.serial, '')) from '(BUD[12])')
        ) as warehouse_code,
        b.booking_code,
        b.legacy_key,
        b.courier_id as muszakpro_courier_id,
        b.courier_name as muszakpro_courier_name,
        b.serial,
        b.status as muszakpro_status,
        b.event_type,
        b.cancelled_at,
        b.fetched_at,
        b.updated_at,
        coalesce(
            substring(coalesce(b.shift_text, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])'),
            substring(coalesce(b.booking_code, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])'),
            substring(coalesce(b.serial, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])')
        )::time as muszakpro_shift_start_time,
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
                order by m.event_at desc nulls last, m.source_row desc nulls last, m.muszakpro_booking_id desc
            ) as latest_rank
        from muszakpro_rows m
    ) ranked
    where latest_rank = 1
      and not is_deleted
      and warehouse_code is not null
      and muszakpro_shift_start_time is not null
),
identity_match as (
    select
        m.*,
        i.courier_id as hub_courier_id,
        i.jitt_internal_id,
        i.name_without_identifier,
        i.name_json,
        i.email as hub_identity_email,
        i.phone_number as hub_phone_number,
        i.giriton_person_id
    from muszakpro_latest m
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
hub_bookings as (
    select
        chb.*,
        lower(regexp_replace(coalesce(chb.email, ''), '\s+', '', 'g')) as hub_booking_email_normalized,
        substring(coalesce(chb.shift_text, '') from '((0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9])')::time as hub_booking_shift_start_time
    from public.courier_hub_shift_bookings_raw chb
    where chb.active is true
),
exact_hub_matches as (
    select distinct
        hb.id as hub_booking_id
    from identity_match i
    join hub_bookings hb
      on hb.work_date = i.work_date
     and upper(hb.warehouse_code) = i.warehouse_code
     and hb.hub_booking_shift_start_time = i.muszakpro_shift_start_time
     and (
         hb.courier_id = i.hub_courier_id
         or (
             i.jitt_internal_id is not null
             and hb.jitt_internal_id = i.jitt_internal_id
         )
         or (
             i.email_normalized <> ''
             and hb.hub_booking_email_normalized = i.email_normalized
         )
     )
),
hub_booking_match as (
    select
        i.*,
        chb.id as hub_booking_id,
        chb.courier_id as hub_booking_courier_id,
        chb.jitt_internal_id as hub_booking_jitt_internal_id,
        chb.courier_name as hub_booking_courier_name,
        chb.email as hub_booking_email,
        chb.phone_number as hub_booking_phone_number,
        chb.warehouse_code as hub_warehouse_code,
        chb.block_key as hub_block_key,
        chb.shift_template_id as hub_shift_template_id,
        chb.shift_text as hub_shift_text,
        chb.hub_booking_shift_start_time,
        chb.slot_from as hub_slot_from,
        chb.slot_to as hub_slot_to,
        chb.status as hub_booking_status,
        chb.movement_type as hub_booking_movement_type,
        chb.active as hub_booking_active,
        chb.first_seen_at as hub_booking_first_seen_at,
        chb.last_seen_at as hub_booking_last_seen_at,
        chb.deleted_at as hub_booking_deleted_at,
        abs(extract(epoch from (chb.hub_booking_shift_start_time - i.muszakpro_shift_start_time)) / 60)::integer as absolute_diff_minutes,
        (extract(epoch from (chb.hub_booking_shift_start_time - i.muszakpro_shift_start_time)) / 60)::integer as signed_diff_minutes
    from identity_match i
    left join lateral (
        select chb.*
        from hub_bookings chb
        where chb.work_date = i.work_date
          and upper(chb.warehouse_code) = i.warehouse_code
          and chb.hub_booking_shift_start_time is not null
          and (
              chb.courier_id = i.hub_courier_id
              or (
                  i.jitt_internal_id is not null
                  and chb.jitt_internal_id = i.jitt_internal_id
              )
              or (
                  i.email_normalized <> ''
                  and chb.hub_booking_email_normalized = i.email_normalized
              )
          )
          and (
              chb.hub_booking_shift_start_time = i.muszakpro_shift_start_time
              or (
                  not exists (
                      select 1
                      from exact_hub_matches exact_match
                      where exact_match.hub_booking_id = chb.id
                  )
                  and abs(extract(epoch from (chb.hub_booking_shift_start_time - i.muszakpro_shift_start_time))) <= 3600
              )
          )
        order by
            case when chb.hub_booking_shift_start_time = i.muszakpro_shift_start_time then 0 else 1 end,
            abs(extract(epoch from (chb.hub_booking_shift_start_time - i.muszakpro_shift_start_time))) nulls last,
            chb.last_seen_at desc nulls last
        limit 1
    ) chb on true
)
select
    now() as comparison_generated_at,
    work_date,
    warehouse_code,
    coalesce(hub_courier_id, muszakpro_courier_id) as courier_id,
    coalesce(name_json, name_without_identifier, muszakpro_courier_name, hub_booking_courier_name) as courier_name,
    email as muszakpro_email,
    hub_identity_email,
    jitt_internal_id,
    giriton_person_id,
    muszakpro_shift_text,
    muszakpro_shift_start_time,
    booking_code as muszakpro_booking_code,
    serial as muszakpro_serial,
    muszakpro_status,
    source_row as muszakpro_source_row,
    hub_booking_id,
    hub_booking_courier_id,
    hub_booking_jitt_internal_id,
    hub_booking_courier_name,
    hub_booking_email,
    hub_warehouse_code,
    hub_block_key,
    hub_shift_template_id,
    hub_shift_text,
    hub_booking_shift_start_time,
    hub_slot_from,
    hub_slot_to,
    hub_booking_status,
    hub_booking_movement_type,
    hub_booking_active,
    absolute_diff_minutes,
    signed_diff_minutes,
    case
        when hub_courier_id is null and jitt_internal_id is null
            then 'NINCS_HUB_FUTAR_AZONOSITAS'
        when hub_booking_id is null
            then 'NINCS_AKTIV_HUB_FOGLALAS_ERRE_AZ_IDOPONTRA'
        when hub_booking_shift_start_time is null
            then 'HUB_MUSZAK_IDO_HIANYZIK'
        when hub_booking_shift_start_time = muszakpro_shift_start_time
            then 'PONTOS'
        else 'ELTERO_IDOPONT'
    end as comparison_status,
    case
        when hub_courier_id is null and jitt_internal_id is null
            then 'A MűszakPro courierId/e-mail alapján nincs Hub futár/JITT azonosítás.'
        when hub_booking_id is null
            then 'Ehhez a futárhoz ezen a napon/raktáron nincs aktív Hub foglalás erre a MűszakPro kezdésre.'
        when hub_booking_shift_start_time is null
            then 'A Hub foglalás shift_text mezőjéből nem olvasható ki kezdési időpont.'
        when hub_booking_shift_start_time = muszakpro_shift_start_time
            then 'A MűszakPro kezdés és a Hub foglalás kezdése konkrétan egyezik.'
        else 'A MűszakPro kezdés és a Hub foglalás kezdése eltér.'
    end as comparison_reason
from hub_booking_match;

create index if not exists idx_muszakpro_bookings_work_date
    on muszakpro.bookings (work_date);

create index if not exists idx_muszakpro_bookings_courier_id
    on muszakpro.bookings (courier_id);

create index if not exists idx_courier_hub_shift_bookings_lookup_for_comparison
    on public.courier_hub_shift_bookings_raw (work_date, warehouse_id, dsp_id, block_key, courier_id);

notify pgrst, 'reload schema';
