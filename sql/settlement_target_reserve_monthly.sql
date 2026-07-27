begin;

alter table public.courier_target_reserve
    add column if not exists "CT_NY_FT" text not null default '0',
    add column if not exists reserve_status text not null default 'in_progress'
        check (reserve_status in ('in_progress', 'done'));

create table if not exists settlement.courier_target_reserve_monthly (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    session_id uuid,
    period_start date not null,
    period_end date not null,
    payable_before_insurance_huf numeric not null default 0,
    reserve_before_huf numeric not null default 0,
    reserve_addition_huf numeric not null default 0,
    insurance_fee_huf numeric not null default 0,
    payable_after_insurance_huf numeric not null default 0,
    reserve_after_huf numeric not null default 0,
    insurance_active_before boolean not null default false,
    insurance_active_after boolean not null default false,
    status text not null default 'in_progress'
        check (status in ('in_progress', 'done')),
    calculated_at timestamptz not null default now(),
    closed_at timestamptz,
    closed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (courier_id, period_start, period_end)
);

create index if not exists courier_target_reserve_monthly_status_idx
    on settlement.courier_target_reserve_monthly (status, period_start, period_end);

grant select, insert, update, delete on settlement.courier_target_reserve_monthly to service_role;
grant select, update on public.courier_target_reserve to service_role;

commit;
