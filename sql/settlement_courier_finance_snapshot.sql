begin;

create table if not exists settlement.courier_finance_snapshot (
    id uuid primary key default gen_random_uuid(),
    period_start date not null,
    courier_id text not null,
    courier_name text,
    version integer not null,
    source text not null default 'devtest_finance',
    calculation_mode text,
    warehouse_label text,
    session_id text,
    fingerprint text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_by text,
    created_at timestamptz not null default now(),
    constraint courier_finance_snapshot_version_unique unique (period_start, courier_id, version),
    constraint courier_finance_snapshot_fingerprint_unique unique (period_start, courier_id, fingerprint)
);

create table if not exists settlement.courier_finance_snapshot_item (
    id uuid primary key default gen_random_uuid(),
    snapshot_id uuid not null references settlement.courier_finance_snapshot(id) on delete cascade,
    section text not null,
    item_key text not null,
    item_label text not null,
    amount_value numeric not null default 0,
    amount_kind text not null default 'huf' check (amount_kind in ('huf', 'count')),
    note text,
    display_order integer not null default 0,
    created_at timestamptz not null default now(),
    constraint courier_finance_snapshot_item_unique unique (snapshot_id, section, item_key)
);

create index if not exists idx_courier_finance_snapshot_courier_month
    on settlement.courier_finance_snapshot (courier_id, period_start, version desc);

create index if not exists idx_courier_finance_snapshot_item_snapshot
    on settlement.courier_finance_snapshot_item (snapshot_id, section, display_order);

grant select, insert, update, delete on settlement.courier_finance_snapshot to service_role;
grant select, insert, update, delete on settlement.courier_finance_snapshot_item to service_role;
grant select on settlement.courier_finance_snapshot to authenticated;
grant select on settlement.courier_finance_snapshot_item to authenticated;

notify pgrst, 'reload schema';

commit;
