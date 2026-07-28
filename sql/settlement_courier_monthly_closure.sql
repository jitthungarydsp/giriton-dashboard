begin;

create table if not exists settlement.courier_monthly_closure (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text not null,
    session_id uuid,
    period_start date not null,
    period_end date not null,
    bank_account_number text,
    recipient_name text,
    payment_note text,
    invoice_number text,
    payable_huf numeric not null default 0,
    status text not null default 'done' check (status in ('done', 'reopened')),
    snapshot jsonb not null default '{}'::jsonb,
    closed_at timestamptz not null default now(),
    closed_by text,
    reopened_at timestamptz,
    reopened_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (courier_id, period_start, period_end)
);

create index if not exists courier_monthly_closure_period_idx
    on settlement.courier_monthly_closure (period_start, period_end, status);

grant select, insert, update, delete on settlement.courier_monthly_closure to service_role;

notify pgrst, 'reload schema';

commit;
