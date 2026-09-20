begin;

create table if not exists settlement.courier_target_reserve_event (
    id uuid primary key default gen_random_uuid(),
    session_id uuid,
    courier_id text not null,
    courier_name text,
    period_start date not null,
    period_end date not null,
    event_type text not null
        check (event_type in ('payment', 'deduction')),
    amount_huf numeric not null default 0,
    note text,
    created_by text,
    created_at timestamptz not null default now(),
    deleted_at timestamptz
);

create index if not exists courier_target_reserve_event_courier_period_idx
    on settlement.courier_target_reserve_event (courier_id, period_start, period_end)
    where deleted_at is null;

create index if not exists courier_target_reserve_event_type_idx
    on settlement.courier_target_reserve_event (event_type, period_start)
    where deleted_at is null;

grant select, insert, update, delete on settlement.courier_target_reserve_event to service_role;

commit;
