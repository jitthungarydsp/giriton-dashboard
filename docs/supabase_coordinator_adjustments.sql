-- Coordinator bonus/malus recording and future JITT compensation configuration.
-- These tables are intentionally NOT connected to the current invoice calculation.

create extension if not exists pgcrypto;

create table if not exists public.cfg_coordinator_bonus_items (
    id uuid primary key default gen_random_uuid(),
    item_name text not null,
    default_amount_huf integer not null default 0 check (default_amount_huf >= 0),
    description text,
    is_active boolean not null default true,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    unique (item_name)
);

create table if not exists public.cfg_coordinator_malus_items (
    id uuid primary key default gen_random_uuid(),
    item_name text not null,
    default_amount_huf integer not null default 0 check (default_amount_huf >= 0),
    description text,
    is_active boolean not null default true,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    unique (item_name)
);

create table if not exists public.ops_coordinator_bonus_entries (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text not null,
    item_id uuid references public.cfg_coordinator_bonus_items(id),
    item_name text not null,
    amount_huf integer not null check (amount_huf > 0),
    note text,
    effective_date date not null default current_date,
    recorded_by text not null,
    recorded_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    delete_reason text,
    check (
        (deleted_at is null and deleted_by is null)
        or (deleted_at is not null and nullif(trim(deleted_by), '') is not null)
    )
);

create table if not exists public.ops_coordinator_malus_entries (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text not null,
    item_id uuid references public.cfg_coordinator_malus_items(id),
    item_name text not null,
    amount_huf integer not null check (amount_huf > 0),
    note text,
    effective_date date not null default current_date,
    recorded_by text not null,
    recorded_at timestamptz not null default now(),
    deleted_at timestamptz,
    deleted_by text,
    delete_reason text,
    check (
        (deleted_at is null and deleted_by is null)
        or (deleted_at is not null and nullif(trim(deleted_by), '') is not null)
    )
);

create table if not exists public.audit_coordinator_adjustments (
    id uuid primary key default gen_random_uuid(),
    entry_kind text not null check (entry_kind in ('bonus', 'malus')),
    entry_id uuid not null,
    action text not null check (action in ('created', 'updated', 'deleted')),
    performed_by text not null,
    snapshot jsonb not null,
    performed_at timestamptz not null default now()
);

create or replace function public.log_coordinator_adjustment()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    row_snapshot jsonb;
    action_name text;
    actor_name text;
    kind_name text;
begin
    row_snapshot := to_jsonb(new);
    kind_name := case when tg_table_name like '%bonus%' then 'bonus' else 'malus' end;

    if tg_op = 'INSERT' then
        action_name := 'created';
        actor_name := coalesce(nullif(new.recorded_by, ''), 'unknown');
    elsif old.deleted_at is null and new.deleted_at is not null then
        action_name := 'deleted';
        actor_name := coalesce(nullif(new.deleted_by, ''), nullif(new.recorded_by, ''), 'unknown');
    else
        action_name := 'updated';
        actor_name := coalesce(nullif(new.deleted_by, ''), nullif(new.recorded_by, ''), 'unknown');
    end if;

    insert into public.audit_coordinator_adjustments (
        entry_kind, entry_id, action, performed_by, snapshot
    ) values (
        kind_name, new.id, action_name, actor_name, row_snapshot
    );
    return new;
end;
$$;

drop trigger if exists trg_audit_coordinator_bonus on public.ops_coordinator_bonus_entries;
create trigger trg_audit_coordinator_bonus
after insert or update on public.ops_coordinator_bonus_entries
for each row execute function public.log_coordinator_adjustment();

drop trigger if exists trg_audit_coordinator_malus on public.ops_coordinator_malus_entries;
create trigger trg_audit_coordinator_malus
after insert or update on public.ops_coordinator_malus_entries
for each row execute function public.log_coordinator_adjustment();

create index if not exists idx_coordinator_bonus_courier_date
    on public.ops_coordinator_bonus_entries (courier_id, effective_date desc)
    where deleted_at is null;
create index if not exists idx_coordinator_malus_courier_date
    on public.ops_coordinator_malus_entries (courier_id, effective_date desc)
    where deleted_at is null;
create index if not exists idx_coordinator_audit_entry
    on public.audit_coordinator_adjustments (entry_kind, entry_id, performed_at desc);

create table if not exists public.cfg_jitt_compensation_rules (
    id uuid primary key default gen_random_uuid(),
    rule_name text not null,
    rule_category text not null check (
        rule_category in ('base_rate', 'quality_bonus', 'temporary_bonus')
    ),
    day_type text not null default 'any' check (
        day_type in ('normal', 'highlighted', 'any')
    ),
    weekdays smallint[] not null default '{}'::smallint[] check (
        weekdays <@ array[1,2,3,4,5,6,7]::smallint[]
    ),
    tour_types text[] not null default '{}'::text[] check (
        tour_types <@ array['express','city','region']::text[]
    ),
    quality_metric text not null default 'none' check (
        quality_metric in ('none', 'delay', 'compliance', 'customer_rating')
    ),
    level_no smallint check (level_no between 1 and 3),
    threshold_min numeric,
    threshold_max numeric,
    threshold_unit text not null default 'percent' check (
        threshold_unit in ('percent', 'score', 'count', 'none')
    ),
    company_amount_huf integer not null default 0,
    courier_amount_huf integer not null default 0,
    valid_from date not null,
    valid_to date,
    is_active boolean not null default true,
    ignore_courier_classification boolean not null default true,
    show_as_separate_invoice_line boolean not null default false,
    invoice_line_note text,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    check (valid_to is null or valid_to >= valid_from),
    check (threshold_max is null or threshold_min is null or threshold_max >= threshold_min),
    check (
        show_as_separate_invoice_line = false
        or nullif(trim(invoice_line_note), '') is not null
    )
);

create index if not exists idx_jitt_compensation_rules_active_period
    on public.cfg_jitt_compensation_rules (is_active, valid_from, valid_to);
create index if not exists idx_jitt_compensation_rules_category
    on public.cfg_jitt_compensation_rules (rule_category, day_type, quality_metric, level_no);

comment on table public.ops_coordinator_bonus_entries is
    'Standalone coordinator bonus records. Not consumed by invoice calculations yet.';
comment on table public.ops_coordinator_malus_entries is
    'Standalone coordinator malus records. Not consumed by invoice calculations yet.';
comment on table public.cfg_jitt_compensation_rules is
    'Future compensation rules. Not consumed by invoice calculations yet.';
