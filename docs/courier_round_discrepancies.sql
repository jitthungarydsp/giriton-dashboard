-- MűszakPro / Hub-Kifli körszám-eltérések naplója.
--
-- Egy sor egy összehasonlítási egység (nap + raktár + idősáv + futár).
-- A hub_round_count NULL értéke azt jelenti, hogy a Hub/Kifli forrás még
-- nem adott adatot; ez nem tekintendő nulla körnek.

create table if not exists public.courier_round_discrepancies (
    id uuid primary key default gen_random_uuid(),
    comparison_key text not null,
    work_date date not null,
    warehouse text not null,
    courier_id text,
    courier_name text,
    slot_start time,
    slot_end time,

    round_count integer not null default 0,
    muszakpro_round_count integer not null default 0,
    hub_round_count integer,

    discrepancy_type text not null default 'none',
    status text not null default 'open',
    details jsonb not null default '{}'::jsonb,
    note text,
    detected_at timestamptz not null default now(),
    resolved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint courier_round_discrepancies_comparison_key_unique
        unique (comparison_key),
    constraint courier_round_discrepancies_round_count_check
        check (round_count >= 0),
    constraint courier_round_discrepancies_muszakpro_count_check
        check (muszakpro_round_count >= 0),
    constraint courier_round_discrepancies_hub_count_check
        check (hub_round_count is null or hub_round_count >= 0),
    constraint courier_round_discrepancies_type_check
        check (discrepancy_type in (
            'none',
            'round_vs_muszakpro',
            'muszakpro_vs_hub',
            'round_vs_muszakpro_and_hub'
        )),
    constraint courier_round_discrepancies_status_check
        check (status in ('open', 'acknowledged', 'resolved', 'ignored'))
);

create index if not exists idx_courier_round_discrepancies_date_warehouse
    on public.courier_round_discrepancies (work_date, warehouse);

create index if not exists idx_courier_round_discrepancies_status
    on public.courier_round_discrepancies (status, work_date desc);

create index if not exists idx_courier_round_discrepancies_courier
    on public.courier_round_discrepancies (courier_id, work_date desc);

create index if not exists idx_courier_round_discrepancies_slot
    on public.courier_round_discrepancies (work_date, warehouse, slot_start);

comment on table public.courier_round_discrepancies is
    'MűszakPro, Hub/Kifli és a napi körszám összehasonlításának naplója';

comment on column public.courier_round_discrepancies.comparison_key is
    'Idempotens kulcs: nap|raktár|futár|idősáv';

comment on column public.courier_round_discrepancies.hub_round_count is
    'NULL = nincs Hub/Kifli adat, nem pedig nulla kör';

grant select, insert, update on public.courier_round_discrepancies to service_role;

-- Napi MűszakPro e-mail-egyeztetés.
-- Egy sor = egy nap + egy normalizált MűszakPro e-mail-cím.
-- A robot_id a Hub identitástáblában tárolt jitt_internal_id értéke.

create table if not exists public.muszakpro_booking_identity_matches (
    id uuid primary key default gen_random_uuid(),
    work_date date not null,
    muszakpro_email text not null,
    normalized_email text not null,
    muszakpro_entry_count integer not null default 0,
    muszakpro_booking_rows jsonb not null default '[]'::jsonb,

    robot_id text,
    robot_courier_id text,
    robot_courier_name text,
    robot_email text,

    hub_courier_id text,
    hub_courier_name text,
    hub_email text,
    hub_robot_id text,
    hub_warehouse text,

    robot_match_method text not null default 'unmatched',
    hub_match_method text not null default 'unmatched',
    match_status text not null default 'unmatched',
    match_details jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint muszakpro_booking_identity_matches_day_email_unique
        unique (work_date, normalized_email),
    constraint muszakpro_booking_identity_matches_count_check
        check (muszakpro_entry_count >= 0),
    constraint muszakpro_booking_identity_matches_robot_method_check
        check (robot_match_method in ('courier_id', 'email', 'name', 'unmatched', 'ambiguous')),
    constraint muszakpro_booking_identity_matches_hub_method_check
        check (hub_match_method in ('courier_id', 'email', 'name', 'robot_id', 'unmatched', 'ambiguous')),
    constraint muszakpro_booking_identity_matches_status_check
        check (match_status in ('matched', 'partial', 'unmatched', 'ambiguous'))
);

create index if not exists idx_muszakpro_booking_identity_matches_date
    on public.muszakpro_booking_identity_matches (work_date);

create index if not exists idx_muszakpro_booking_identity_matches_email
    on public.muszakpro_booking_identity_matches (normalized_email);

create index if not exists idx_muszakpro_booking_identity_matches_status
    on public.muszakpro_booking_identity_matches (match_status, work_date desc);

create index if not exists idx_muszakpro_booking_identity_matches_robot
    on public.muszakpro_booking_identity_matches (robot_id);

create index if not exists idx_muszakpro_booking_identity_matches_hub_courier
    on public.muszakpro_booking_identity_matches (hub_courier_id);

comment on table public.muszakpro_booking_identity_matches is
    'Napi MűszakPro e-mail sorösszesítés és RobotID/Hub futár-egyeztetés';

comment on column public.muszakpro_booking_identity_matches.robot_id is
    'Hub identitástáblából feloldott jitt_internal_id / RobotID';

comment on column public.muszakpro_booking_identity_matches.muszakpro_entry_count is
    'Az adott napon az adott e-mail címmel talált MűszakPro bejegyzések száma';

grant select, insert, update on public.muszakpro_booking_identity_matches to service_role;
