-- MuszakPro live DB bridge.
--
-- Cel:
-- - a helyi MuszakPro Google Apps Script tudjon kozvetlenul Supabase-be irni,
-- - a regi Foglalasok sheet importja mellett legyen sajat, aktiv DB tabla,
-- - a torles ne fizikai torles legyen, hanem status = CANCELLED.
--
-- Fontos:
-- Ha korabban lefutott a prefix alias SQL, akkor a public.raw_muszakpro_bookings
-- view lehet. View-t nem lehet ALTER TABLE-lel boviteni, ezert a script elobb
-- ledobja az alias view-t, majd letrehozza a valodi tablat.

do $$
declare
    target_kind text;
begin
    select c.relkind::text
    into target_kind
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'raw_muszakpro_bookings';

    if target_kind = 'v' then
        drop view public.raw_muszakpro_bookings;
        raise notice 'Dropped alias view public.raw_muszakpro_bookings.';
    elsif target_kind = 'm' then
        drop materialized view public.raw_muszakpro_bookings;
        raise notice 'Dropped materialized view public.raw_muszakpro_bookings.';
    end if;
end $$;

create table if not exists public.raw_muszakpro_bookings (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'muszakpro-app',
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
    status text not null default 'ACTIVE',
    event_type text,
    cancelled_at timestamptz,
    cancelled_by text,
    response_json jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint raw_muszakpro_bookings_unique
        unique (source_name, work_date, email, shift_text, booking_code)
);

alter table public.raw_muszakpro_bookings
    add column if not exists status text not null default 'ACTIVE',
    add column if not exists event_type text,
    add column if not exists cancelled_at timestamptz,
    add column if not exists cancelled_by text;

create index if not exists idx_raw_muszakpro_bookings_work_date
    on public.raw_muszakpro_bookings (work_date);

create index if not exists idx_raw_muszakpro_bookings_email
    on public.raw_muszakpro_bookings (email);

create index if not exists idx_raw_muszakpro_bookings_courier_id
    on public.raw_muszakpro_bookings (courier_id);

create index if not exists idx_raw_muszakpro_bookings_serial
    on public.raw_muszakpro_bookings (serial);

create index if not exists idx_raw_muszakpro_bookings_status
    on public.raw_muszakpro_bookings (status);

create table if not exists public.ops_muszakpro_events (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'muszakpro-app',
    action_type text not null,
    work_date date,
    email text,
    shift_text text,
    warehouse text,
    booking_code text,
    actor_email text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_ops_muszakpro_events_work_date
    on public.ops_muszakpro_events (work_date);

create index if not exists idx_ops_muszakpro_events_email
    on public.ops_muszakpro_events (email);

-- Ha a regi tabla meg letezik, kapja meg ugyanazokat az oszlopokat, hogy a kod
-- visszafele is kompatibilis maradjon.
do $$
declare
    legacy_kind text;
begin
    select c.relkind::text
    into legacy_kind
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'foglalasok_raw';

    if legacy_kind in ('r', 'p') then
        alter table public.foglalasok_raw
            add column if not exists status text not null default 'ACTIVE',
            add column if not exists event_type text,
            add column if not exists cancelled_at timestamptz,
            add column if not exists cancelled_by text;
    end if;
end $$;

-- Egyszeri seed: a regi foglalasok_raw aktiv sorait atemeli az uj nev ala.
-- Nem torol es nem ir felul rombolo modon.
do $$
declare
    legacy_kind text;
begin
    select c.relkind::text
    into legacy_kind
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'foglalasok_raw';

    if legacy_kind in ('r', 'p') then
        insert into public.raw_muszakpro_bookings (
            source_name,
            source_row,
            timestamp_text,
            work_date,
            email,
            shift_text,
            warehouse,
            booking_code,
            admin_recorder,
            giriton_uploaded,
            system_check,
            legacy_key,
            courier_id,
            courier_name,
            serial,
            status,
            event_type,
            response_json,
            fetched_at,
            updated_at
        )
        select
            coalesce(source_name, 'google-sheet-foglalasok'),
            source_row,
            timestamp_text,
            work_date,
            email,
            shift_text,
            warehouse,
            booking_code,
            admin_recorder,
            giriton_uploaded,
            system_check,
            legacy_key,
            courier_id,
            courier_name,
            serial,
            coalesce(status, 'ACTIVE'),
            coalesce(event_type, 'LEGACY_SEED'),
            response_json,
            fetched_at,
            now()
        from public.foglalasok_raw
        on conflict (source_name, work_date, email, shift_text, booking_code)
        do update set
            source_row = excluded.source_row,
            timestamp_text = excluded.timestamp_text,
            warehouse = excluded.warehouse,
            admin_recorder = excluded.admin_recorder,
            giriton_uploaded = excluded.giriton_uploaded,
            system_check = excluded.system_check,
            legacy_key = excluded.legacy_key,
            courier_id = excluded.courier_id,
            courier_name = excluded.courier_name,
            serial = excluded.serial,
            status = excluded.status,
            event_type = excluded.event_type,
            response_json = excluded.response_json,
            fetched_at = excluded.fetched_at,
            updated_at = now();
    end if;
end $$;
