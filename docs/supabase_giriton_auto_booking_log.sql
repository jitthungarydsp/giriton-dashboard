-- Giriton automatikus muszakfoglalas log.
-- Egy sor = egy robot probalkozas egy Foglalasok sorra.

create table if not exists public.ops_giriton_auto_booking_log (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'giriton-auto-booking-robot',
    work_date date,
    courier_id integer,
    courier_name text,
    email text,
    warehouse text,
    shift_text text,
    shift_start text,
    booking_code text,
    serial text,
    status text not null,
    message text,
    response_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_ops_giriton_auto_booking_log_work_date
    on public.ops_giriton_auto_booking_log (work_date);

create index if not exists idx_ops_giriton_auto_booking_log_courier_id
    on public.ops_giriton_auto_booking_log (courier_id);

create index if not exists idx_ops_giriton_auto_booking_log_serial
    on public.ops_giriton_auto_booking_log (serial);

create index if not exists idx_ops_giriton_auto_booking_log_created_at
    on public.ops_giriton_auto_booking_log (created_at desc);
