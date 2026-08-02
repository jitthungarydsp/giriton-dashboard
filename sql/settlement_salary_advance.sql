begin;

create table if not exists settlement.courier_salary_advance_plan (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text not null,
    requested_amount_huf numeric not null default 0 check (requested_amount_huf >= 0),
    installment_months integer not null default 1 check (installment_months > 0),
    monthly_amount_huf numeric not null default 0 check (monthly_amount_huf >= 0),
    start_date date not null,
    status text not null default 'open' check (status in ('open', 'done', 'cancelled')),
    note text,
    created_by text,
    closed_at timestamptz,
    closed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists settlement.courier_salary_advance_request (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text not null,
    requested_amount_huf numeric not null default 0 check (requested_amount_huf >= 0),
    installment_months integer not null default 1 check (installment_months > 0),
    monthly_amount_huf numeric not null default 0 check (monthly_amount_huf >= 0),
    start_date date not null,
    status text not null default 'requested' check (status in ('requested', 'approved', 'rejected', 'paid', 'closed')),
    process_id text,
    note text,
    requested_by text,
    requested_at timestamptz not null default now(),
    approved_by text,
    approved_at timestamptz,
    paid_by text,
    paid_at timestamptz,
    plan_id uuid references settlement.courier_salary_advance_plan(id) on delete set null,
    updated_at timestamptz not null default now()
);

create table if not exists settlement.courier_salary_advance_installment (
    id uuid primary key default gen_random_uuid(),
    plan_id uuid not null references settlement.courier_salary_advance_plan(id) on delete cascade,
    courier_id text not null,
    courier_name text not null,
    period_start date not null,
    period_end date not null,
    installment_no integer not null check (installment_no > 0),
    installment_count integer not null check (installment_count > 0),
    amount_huf numeric not null default 0 check (amount_huf >= 0),
    status text not null default 'open' check (status in ('open', 'done', 'cancelled')),
    closed_at timestamptz,
    closed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (plan_id, installment_no)
);

create index if not exists courier_salary_advance_plan_courier_idx
    on settlement.courier_salary_advance_plan (courier_id, status);

create index if not exists courier_salary_advance_request_courier_idx
    on settlement.courier_salary_advance_request (courier_id, status, requested_at desc);

create index if not exists courier_salary_advance_installment_period_idx
    on settlement.courier_salary_advance_installment (courier_id, period_start, period_end, status);

grant select, insert, update, delete on settlement.courier_salary_advance_plan to service_role;
grant select, insert, update, delete on settlement.courier_salary_advance_request to service_role;
grant select, insert, update, delete on settlement.courier_salary_advance_installment to service_role;

notify pgrst, 'reload schema';

commit;
