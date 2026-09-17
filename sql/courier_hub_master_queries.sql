-- Courier Hub roster lekerdezesek.

-- BUD2 futarok adott idoszakban:
select
    roster_date,
    warehouse_code,
    courier_id,
    giriton_person_id,
    courier_name,
    phone_number,
    email,
    vehicle_registration_number,
    status,
    assignment_load,
    last_seen_at
from public.courier_hub_master_between(
    date '2026-09-17',
    date '2026-09-17',
    2,
    8
);

-- Minden raktar adott idoszakban:
select *
from public.courier_hub_master_between(
    date '2026-09-01',
    date '2026-09-17',
    null,
    8
);

-- Legfrissebb ismert futartorzzs:
select
    warehouse_code,
    courier_id,
    giriton_person_id,
    courier_name,
    phone_number,
    email,
    vehicle_registration_number,
    roster_date,
    last_seen_at
from public.courier_hub_master_latest
order by warehouse_code, courier_name, courier_id;
