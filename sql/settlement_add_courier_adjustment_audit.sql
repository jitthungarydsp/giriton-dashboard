begin;

alter table settlement.courier_settlement_adjustment
    add column if not exists deleted_by text;

create table if not exists settlement.courier_settlement_adjustment_event (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    courier_id text not null,
    event_type text not null check (event_type in ('created', 'reset')),
    adjustment_type text,
    amount_huf numeric,
    note text,
    performed_by text not null,
    created_at timestamptz not null default now()
);

grant select, insert on settlement.courier_settlement_adjustment_event to service_role;

commit;
