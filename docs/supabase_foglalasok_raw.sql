-- MuszakPRO / Foglalasok raw import.
-- Egy sor = egy Foglalasok sheet sor.
-- Ezt a Supabase SQL Editorban futtasd le.

create table if not exists public.foglalasok_raw (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'google-sheet-foglalasok',
    source_row integer,
    timestamp_text text,
    work_date date not null,
    email text not null,
    shift_text text not null,
    warehouse text,
    booking_code text not null default '',
    admin_recorder text,
    giriton_uploaded text,
    system_check text,
    legacy_key text,
    courier_id integer,
    courier_name text,
    serial text,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint foglalasok_raw_unique
        unique (source_name, work_date, email, shift_text, booking_code)
);

create index if not exists idx_foglalasok_raw_work_date
    on public.foglalasok_raw (work_date);

create index if not exists idx_foglalasok_raw_email
    on public.foglalasok_raw (email);

create index if not exists idx_foglalasok_raw_courier_id
    on public.foglalasok_raw (courier_id);

create index if not exists idx_foglalasok_raw_serial
    on public.foglalasok_raw (serial);
