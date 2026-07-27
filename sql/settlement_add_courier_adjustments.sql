begin;

create table if not exists settlement.courier_settlement_adjustment (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    courier_id text not null,
    adjustment_type text not null check (adjustment_type in ('bonus', 'malus', 'atm_deduction', 'other_expense', 'customer_rating')),
    amount_huf numeric not null check (amount_huf >= 0),
    effective_date date not null default current_date,
    note text,
    is_active boolean not null default true,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text
);

create index if not exists courier_settlement_adjustment_session_courier_idx
    on settlement.courier_settlement_adjustment (session_id, courier_id)
    where deleted_at is null and is_active;

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

grant select, insert, update, delete on settlement.courier_settlement_adjustment to service_role;
grant select, insert on settlement.courier_settlement_adjustment_event to service_role;

commit;
