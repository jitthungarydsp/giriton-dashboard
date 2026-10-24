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
