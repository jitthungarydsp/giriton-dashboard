-- Backfill MuszakPro raw booking rows from courier_master.
-- Run in Supabase SQL Editor.

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
where lower(trim(booking.email)) = lower(trim(master.email))
  and nullif(trim(booking.email), '') is not null
  and (
      booking.courier_id is null
      or nullif(booking.courier_name, '') is null
      or nullif(booking.serial, '') is null
  );

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
where lower(trim(booking.email)) = lower(trim(master.email))
  and nullif(trim(booking.email), '') is not null
  and (
      booking.courier_id is null
      or nullif(booking.courier_name, '') is null
      or nullif(booking.serial, '') is null
  );

select
    'raw_muszakpro_bookings' as table_name,
    count(*) filter (where courier_id is null) as missing_courier_id,
    count(*) filter (where nullif(courier_name, '') is null) as missing_courier_name,
    count(*) filter (where nullif(serial, '') is null) as missing_serial
from public.raw_muszakpro_bookings
union all
select
    'foglalasok_raw' as table_name,
    count(*) filter (where courier_id is null) as missing_courier_id,
    count(*) filter (where nullif(courier_name, '') is null) as missing_courier_name,
    count(*) filter (where nullif(serial, '') is null) as missing_serial
from public.foglalasok_raw;
