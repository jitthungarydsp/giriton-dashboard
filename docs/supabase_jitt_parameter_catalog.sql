-- Parameter catalog for the devtest settlement prototype.
-- No seed data is inserted by this migration.

create extension if not exists pgcrypto;

create table if not exists public.cfg_jitt_rate_parameter_names (
    parameter_code text primary key,
    parameter_kind text not null check (
        parameter_kind in ('delay_bonus', 'compliance_bonus')
    ),
    display_name text not null,
    is_active boolean not null default true,
    sort_order integer not null default 100,
    created_at timestamptz not null default now(),
    unique (parameter_kind, display_name)
);

insert into public.cfg_jitt_rate_parameter_names (
    parameter_code,
    parameter_kind,
    display_name,
    sort_order
) values
    ('delay_bonus', 'delay_bonus', 'Delay bónusz', 10),
    ('compliance_bonus', 'compliance_bonus', 'Compliance bónusz', 20)
on conflict (parameter_code) do nothing;

create table if not exists public.cfg_jitt_rate_parameters (
    id uuid primary key default gen_random_uuid(),
    parameter_name text not null,
    parameter_kind text not null check (
        parameter_kind in (
            'base_rate',
            'delay_bonus',
            'compliance_bonus',
            'customer_rating_bonus',
            'other'
        )
    ),
    level_code text,
    day_type text not null default 'any' check (
        day_type in ('any', 'highlighted', 'not_highlighted')
    ),
    weekdays smallint[] not null default '{}'::smallint[] check (
        weekdays <@ array[1,2,3,4,5,6,7]::smallint[]
    ),
    route_type text not null default 'any' check (
        route_type in ('any', 'express', 'normal', 'regional')
    ),
    warehouse_code text,
    threshold_min numeric,
    threshold_max numeric,
    threshold_min_inclusive boolean not null default true,
    threshold_max_inclusive boolean not null default true,
    planned_duration_min_hours numeric,
    planned_duration_max_hours numeric,
    company_amount_huf integer not null default 0 check (company_amount_huf >= 0),
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    calculation_unit text not null default 'per_route' check (
        calculation_unit in ('fixed', 'per_route', 'per_order', 'per_hour', 'percent')
    ),
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
    check (threshold_max is null or threshold_min is null or threshold_max >= threshold_min),
    check (
        planned_duration_max_hours is null
        or planned_duration_min_hours is null
        or planned_duration_max_hours >= planned_duration_min_hours
    ),
    check (
        (deleted_at is null and deleted_by is null)
        or (deleted_at is not null and nullif(trim(deleted_by), '') is not null)
    )
);

alter table public.cfg_jitt_rate_parameters
    drop constraint if exists cfg_jitt_rate_parameters_supported_kind_check;

alter table public.cfg_jitt_rate_parameters
    add constraint cfg_jitt_rate_parameters_supported_kind_check
    check (parameter_kind in ('delay_bonus', 'compliance_bonus'));

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'cfg_jitt_rate_parameters_name_catalog_fk'
          and conrelid = 'public.cfg_jitt_rate_parameters'::regclass
    ) then
        alter table public.cfg_jitt_rate_parameters
            add constraint cfg_jitt_rate_parameters_name_catalog_fk
            foreign key (parameter_kind, parameter_name)
            references public.cfg_jitt_rate_parameter_names (
                parameter_kind,
                display_name
            )
            not valid;
    end if;
end
$$;

create table if not exists public.cfg_jitt_periodic_bonuses (
    id uuid primary key default gen_random_uuid(),
    bonus_name text not null,
    day_type text not null default 'any' check (
        day_type in ('any', 'highlighted', 'not_highlighted')
    ),
    weekdays smallint[] not null default '{}'::smallint[] check (
        weekdays <@ array[1,2,3,4,5,6,7]::smallint[]
    ),
    route_type text not null default 'any' check (
        route_type in ('any', 'express', 'normal', 'regional')
    ),
    warehouse_code text,
    courier_ids text[] not null default '{}'::text[],
    company_names text[] not null default '{}'::text[],
    condition_metric text not null default 'none' check (
        condition_metric in (
            'none',
            'orders_per_route',
            'routes_per_day',
            'routes_in_period',
            'orders_in_period'
        )
    ),
    condition_min numeric,
    condition_max numeric,
    company_amount_huf integer not null default 0 check (company_amount_huf >= 0),
    courier_amount_huf integer not null default 0 check (courier_amount_huf >= 0),
    calculation_unit text not null default 'per_route' check (
        calculation_unit in ('fixed', 'per_route', 'per_order', 'per_hour', 'percent')
    ),
    maximum_awards_per_courier integer check (maximum_awards_per_courier >= 0),
    valid_from date not null,
    valid_to date,
    priority integer not null default 100,
    is_active boolean not null default true,
    show_as_separate_invoice_line boolean not null default false,
    invoice_line_note text,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from),
    check (condition_max is null or condition_min is null or condition_max >= condition_min),
    check (
        show_as_separate_invoice_line = false
        or nullif(trim(invoice_line_note), '') is not null
    )
);

create index if not exists idx_jitt_rate_parameters_lookup
    on public.cfg_jitt_rate_parameters (
        is_active,
        parameter_kind,
        day_type,
        route_type,
        valid_from,
        valid_to
    )
    where deleted_at is null;

create index if not exists idx_jitt_periodic_bonuses_lookup
    on public.cfg_jitt_periodic_bonuses (
        is_active,
        day_type,
        route_type,
        valid_from,
        valid_to
    )
    where deleted_at is null;

grant select, insert, update, delete
    on public.cfg_jitt_rate_parameters,
       public.cfg_jitt_periodic_bonuses
    to service_role;

grant select
    on public.cfg_jitt_rate_parameter_names
    to service_role;

revoke insert, update, delete
    on public.cfg_jitt_rate_parameter_names
    from service_role;

comment on table public.cfg_jitt_rate_parameters is
    'Versioned JITT and courier base-rate, delay, compliance and other rate parameters.';

comment on table public.cfg_jitt_periodic_bonuses is
    'Independent, versioned periodic bonus rules with configurable scope and thresholds.';
