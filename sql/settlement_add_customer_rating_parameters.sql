begin;

create table if not exists settlement.cfg_jitt_customer_rating_rules (
    id uuid primary key default gen_random_uuid(),
    level_code text not null default 'Customer rating',
    route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    rating_min_percent numeric,
    rating_max_percent numeric,
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
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
    check (valid_to is null or valid_to >= valid_from),
    check (rating_max_percent is null or rating_min_percent is null or rating_max_percent >= rating_min_percent)
);

alter table settlement.cfg_jitt_customer_rating_rules
    add column if not exists route_type text not null default 'normal'
    check (route_type in ('normal', 'express', 'regional', 'any'));

grant select, insert, update, delete on settlement.cfg_jitt_customer_rating_rules to service_role;

commit;
