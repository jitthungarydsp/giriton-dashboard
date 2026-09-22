-- MuszakPro tables in a separate schema.
-- Source sheets:
-- - Foglalasok (gid=520887482) -> muszakpro.bookings
-- - LOG        (gid=1961182696) -> muszakpro.events
--
-- Supabase API note:
-- Add the "muszakpro" schema under Project Settings -> API -> Exposed schemas,
-- otherwise REST writes with Accept-Profile/Content-Profile will not see it.

create schema if not exists muszakpro;

grant usage on schema muszakpro to anon, authenticated, service_role;

create table if not exists muszakpro.bookings (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'google-sheet-muszakpro-foglalasok',
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

    constraint muszakpro_bookings_unique
        unique (source_name, work_date, email, shift_text, booking_code)
);

alter table muszakpro.bookings
    add column if not exists source_row integer,
    add column if not exists timestamp_text text,
    add column if not exists admin_recorder text,
    add column if not exists giriton_uploaded text,
    add column if not exists system_check text,
    add column if not exists legacy_key text,
    add column if not exists courier_id integer,
    add column if not exists courier_name text,
    add column if not exists serial text,
    add column if not exists status text not null default 'ACTIVE',
    add column if not exists event_type text,
    add column if not exists cancelled_at timestamptz,
    add column if not exists cancelled_by text,
    add column if not exists response_json jsonb not null default '{}'::jsonb,
    add column if not exists fetched_at timestamptz not null default now(),
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now();

create unique index if not exists muszakpro_bookings_unique_idx
    on muszakpro.bookings (source_name, work_date, email, shift_text, booking_code);

create index if not exists idx_muszakpro_bookings_work_date
    on muszakpro.bookings (work_date);

create index if not exists idx_muszakpro_bookings_email
    on muszakpro.bookings (email);

create index if not exists idx_muszakpro_bookings_courier_id
    on muszakpro.bookings (courier_id);

create index if not exists idx_muszakpro_bookings_serial
    on muszakpro.bookings (serial);

create index if not exists idx_muszakpro_bookings_status
    on muszakpro.bookings (status);

create table if not exists muszakpro.events (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'google-sheet-muszakpro-log',
    source_row integer,
    timestamp_text text,
    action_type text not null,
    work_date date,
    email text,
    shift_text text,
    warehouse text,
    booking_code text,
    actor_email text,
    security_code text,
    details_text text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint muszakpro_events_source_row_unique
        unique (source_name, source_row)
);

alter table muszakpro.events
    add column if not exists source_row integer,
    add column if not exists timestamp_text text,
    add column if not exists work_date date,
    add column if not exists email text,
    add column if not exists shift_text text,
    add column if not exists warehouse text,
    add column if not exists booking_code text,
    add column if not exists actor_email text,
    add column if not exists security_code text,
    add column if not exists details_text text,
    add column if not exists payload jsonb not null default '{}'::jsonb,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now();

create unique index if not exists muszakpro_events_source_row_unique_idx
    on muszakpro.events (source_name, source_row);

create index if not exists idx_muszakpro_events_created_at
    on muszakpro.events (created_at);

create index if not exists idx_muszakpro_events_work_date
    on muszakpro.events (work_date);

create index if not exists idx_muszakpro_events_email
    on muszakpro.events (email);

create index if not exists idx_muszakpro_events_action_type
    on muszakpro.events (action_type);

grant all on all tables in schema muszakpro to service_role;
grant select on all tables in schema muszakpro to anon, authenticated;

-- Compatibility read views for older dashboard code that still reads public names.
-- If a real public table already exists under these names, this block leaves it alone.
do $$
begin
    if to_regclass('public.raw_muszakpro_bookings') is null then
        execute 'create view public.raw_muszakpro_bookings as select * from muszakpro.bookings';
    elsif exists (
        select 1
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = 'raw_muszakpro_bookings'
          and c.relkind = 'v'
    ) then
        execute 'create or replace view public.raw_muszakpro_bookings as select * from muszakpro.bookings';
    end if;

    if to_regclass('public.ops_muszakpro_events') is null then
        execute 'create view public.ops_muszakpro_events as select * from muszakpro.events';
    elsif exists (
        select 1
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = 'ops_muszakpro_events'
          and c.relkind = 'v'
    ) then
        execute 'create or replace view public.ops_muszakpro_events as select * from muszakpro.events';
    end if;
end $$;
