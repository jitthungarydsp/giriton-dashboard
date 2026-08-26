-- Backfill MuszakPro raw booking rows from courier_master.
-- Run in Supabase SQL Editor.
-- Matching rule: normalized raw booking email = normalized courier_master.email.

create or replace function public._tmp_muszakpro_normalized_email(value text)
returns text
language sql
immutable
as $$
    select regexp_replace(lower(trim(coalesce(value, ''))), '\s+', '', 'g')
$$;

update public.raw_muszakpro_bookings booking
set
    courier_id = coalesce(booking.courier_id, master.courier_id),
    courier_name = coalesce(nullif(booking.courier_name, ''), master.courier_name),
    serial = coalesce(
        nullif(booking.serial, ''),
        concat(
            to_char(booking.work_date, 'MM/DD'),
            '_',
            master.courier_id,
            '_',
            coalesce(nullif(booking.warehouse, ''), '-'),
            '_',
            regexp_replace(coalesce(booking.shift_text, ''), '^.*?([0-9]{1,2}:[0-9]{2}).*$', '\1')
        )
    ),
    updated_at = now()
from public.courier_master master
where public._tmp_muszakpro_normalized_email(booking.email) = public._tmp_muszakpro_normalized_email(master.email)
  and nullif(public._tmp_muszakpro_normalized_email(booking.email), '') is not null
  and (
      booking.courier_id is null
      or nullif(trim(booking.courier_name), '') is null
      or nullif(trim(booking.serial), '') is null
  );

update public.raw_muszakpro_bookings booking
set
    serial = concat(
        to_char(booking.work_date, 'MM/DD'),
        '_',
        booking.courier_id,
        '_',
        coalesce(nullif(booking.warehouse, ''), '-'),
        '_',
        regexp_replace(coalesce(booking.shift_text, ''), '^.*?([0-9]{1,2}:[0-9]{2}).*$', '\1')
    ),
    updated_at = now()
where booking.courier_id is not null
  and nullif(trim(booking.serial), '') is null;

update public.foglalasok_raw booking
set
    courier_id = coalesce(booking.courier_id, master.courier_id),
    courier_name = coalesce(nullif(booking.courier_name, ''), master.courier_name),
    serial = coalesce(
        nullif(booking.serial, ''),
        concat(
            to_char(booking.work_date, 'MM/DD'),
            '_',
            master.courier_id,
            '_',
            coalesce(nullif(booking.warehouse, ''), '-'),
            '_',
            regexp_replace(coalesce(booking.shift_text, ''), '^.*?([0-9]{1,2}:[0-9]{2}).*$', '\1')
        )
    ),
    updated_at = now()
from public.courier_master master
where public._tmp_muszakpro_normalized_email(booking.email) = public._tmp_muszakpro_normalized_email(master.email)
  and nullif(public._tmp_muszakpro_normalized_email(booking.email), '') is not null
  and (
      booking.courier_id is null
      or nullif(trim(booking.courier_name), '') is null
      or nullif(trim(booking.serial), '') is null
  );

update public.foglalasok_raw booking
set
    serial = concat(
        to_char(booking.work_date, 'MM/DD'),
        '_',
        booking.courier_id,
        '_',
        coalesce(nullif(booking.warehouse, ''), '-'),
        '_',
        regexp_replace(coalesce(booking.shift_text, ''), '^.*?([0-9]{1,2}:[0-9]{2}).*$', '\1')
    ),
    updated_at = now()
where booking.courier_id is not null
  and nullif(trim(booking.serial), '') is null;

select
    'raw_muszakpro_bookings' as table_name,
    count(*) filter (where courier_id is null) as missing_courier_id,
    count(*) filter (where nullif(trim(courier_name), '') is null) as missing_courier_name,
    count(*) filter (where nullif(trim(serial), '') is null) as missing_serial
from public.raw_muszakpro_bookings
union all
select
    'foglalasok_raw' as table_name,
    count(*) filter (where courier_id is null) as missing_courier_id,
    count(*) filter (where nullif(trim(courier_name), '') is null) as missing_courier_name,
    count(*) filter (where nullif(trim(serial), '') is null) as missing_serial
from public.foglalasok_raw;

drop function if exists public._tmp_muszakpro_normalized_email(text);
