-- HUB_JOB_AUTOBOOKING sikertelen / nem foglalhato sorok naploja.
-- Egyedi kulcs: failure_key, ez fogja meg a duplikalt sheet/DB irasokat.
-- Ezt a Supabase SQL Editorban futtasd le egyszer.

create table if not exists public.hub_autobooking_failures (
    id uuid primary key default gen_random_uuid(),
    failure_key text not null,
    source_name text not null default 'hub-job-autobooking',
    run_at text,
    work_date date,
    warehouse text,
    courier_id integer,
    courier_name text,
    email text,
    muszakpro_shift_start time,
    hub_slot_from time,
    match_diff_minutes integer,
    match_kind text,
    shift_template_id integer,
    block_key text,
    reason text,
    timestamp_text text,
    serial text,
    source_row text,
    exported_at_text text,
    response_json jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint hub_autobooking_failures_unique unique (failure_key)
);

create index if not exists idx_hub_autobooking_failures_work_date
    on public.hub_autobooking_failures (work_date);

create index if not exists idx_hub_autobooking_failures_courier_id
    on public.hub_autobooking_failures (courier_id);

create index if not exists idx_hub_autobooking_failures_email
    on public.hub_autobooking_failures (email);

create index if not exists idx_hub_autobooking_failures_serial
    on public.hub_autobooking_failures (serial);

create index if not exists idx_hub_autobooking_failures_source_name
    on public.hub_autobooking_failures (source_name);
