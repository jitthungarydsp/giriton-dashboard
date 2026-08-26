-- Diagnose MuszakPro raw booking rows that cannot be joined to courier_master by email.
-- Run in Supabase SQL Editor.

create or replace function public._tmp_muszakpro_normalized_email(value text)
returns text
language sql
immutable
as $$
    select regexp_replace(lower(trim(coalesce(value, ''))), '\s+', '', 'g')
$$;

with booking_rows as (
    select
        'raw_muszakpro_bookings' as table_name,
        id,
        work_date,
        email,
        courier_id,
        courier_name,
        serial,
        shift_text,
        warehouse
    from public.raw_muszakpro_bookings
    union all
    select
        'foglalasok_raw' as table_name,
        id,
        work_date,
        email,
        courier_id,
        courier_name,
        serial,
        shift_text,
        warehouse
    from public.foglalasok_raw
)
select
    b.table_name,
    b.work_date,
    b.email,
    b.shift_text,
    b.warehouse,
    b.courier_id,
    b.courier_name,
    b.serial,
    public._tmp_muszakpro_normalized_email(b.email) as normalized_booking_email,
    public._tmp_muszakpro_normalized_email(m.email) as normalized_master_email,
    case
        when nullif(public._tmp_muszakpro_normalized_email(b.email), '') is null then 'missing raw email'
        when m.courier_id is null then 'email not found in courier_master'
        else 'matched'
    end as join_status,
    m.courier_id as master_courier_id,
    m.courier_name as master_courier_name,
    m.email as master_email
from booking_rows b
left join public.courier_master m
    on public._tmp_muszakpro_normalized_email(b.email) = public._tmp_muszakpro_normalized_email(m.email)
where
    b.courier_id is null
    or nullif(trim(b.courier_name), '') is null
    or nullif(trim(b.serial), '') is null
order by b.work_date desc, b.email nulls first, b.shift_text
limit 500;

drop function if exists public._tmp_muszakpro_normalized_email(text);
