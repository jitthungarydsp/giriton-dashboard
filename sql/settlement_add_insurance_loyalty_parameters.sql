begin;

create table if not exists settlement.cfg_jitt_reserve_insurance_rules (
    id uuid primary key default gen_random_uuid(),
    insurance_fee_huf integer not null default 0 check (insurance_fee_huf >= 0),
    base_insurance_total_huf integer not null default 0 check (base_insurance_total_huf >= 0),
    deduction_percent numeric not null check (deduction_percent between 0 and 100),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists settlement.cfg_jitt_loyalty_bonus_rules (
    id uuid primary key default gen_random_uuid(),
    loyalty_start_date date not null,
    loyalty_months_required integer not null default 0 check (loyalty_months_required >= 0),
    route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    calculation_unit text not null default 'per_route' check (calculation_unit in ('per_route', 'per_order')),
    bonus_amount_huf integer not null default 0 check (bonus_amount_huf >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

alter table settlement.cfg_jitt_loyalty_bonus_rules
    add column if not exists loyalty_months_required integer not null default 0 check (loyalty_months_required >= 0),
    add column if not exists route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    add column if not exists calculation_unit text not null default 'per_route' check (calculation_unit in ('per_route', 'per_order'));

create table if not exists settlement.cfg_jitt_life_insurance_rules (
    id uuid primary key default gen_random_uuid(),
    life_insurance_amount_huf integer not null default 0 check (life_insurance_amount_huf >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

grant select, insert, update, delete on settlement.cfg_jitt_reserve_insurance_rules, settlement.cfg_jitt_loyalty_bonus_rules, settlement.cfg_jitt_life_insurance_rules to service_role;

commit;
