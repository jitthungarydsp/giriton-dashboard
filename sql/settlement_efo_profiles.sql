begin;

alter table public.courier_master
    add column if not exists employment_type text not null default 'egyeni_vallalkozo'
        check (employment_type in ('efo', 'egyeni_vallalkozo', 'bejelentett')),
    add column if not exists employment_note text;

create table if not exists settlement.courier_efo_assignment (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    valid_from date not null,
    valid_to date,
    daily_deduction_huf integer not null default 0 check (daily_deduction_huf >= 0),
    is_active boolean not null default true,
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    check (valid_to is null or valid_to >= valid_from)
);

create index if not exists courier_efo_assignment_courier_idx
    on settlement.courier_efo_assignment (courier_id, valid_from desc);

create index if not exists courier_efo_assignment_period_idx
    on settlement.courier_efo_assignment (valid_from, valid_to);

grant select, insert, update, delete on settlement.courier_efo_assignment to service_role;

notify pgrst, 'reload schema';

commit;
