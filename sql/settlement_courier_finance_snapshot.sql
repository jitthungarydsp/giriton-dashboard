begin;

create table if not exists settlement.courier_finance_snapshot (id uuid primary key default gen_random_uuid());

alter table settlement.courier_finance_snapshot add column if not exists period_start date;
alter table settlement.courier_finance_snapshot add column if not exists courier_id text;
alter table settlement.courier_finance_snapshot add column if not exists courier_name text;
alter table settlement.courier_finance_snapshot add column if not exists version integer;
alter table settlement.courier_finance_snapshot add column if not exists source text default 'devtest_finance';
alter table settlement.courier_finance_snapshot add column if not exists calculation_mode text;
alter table settlement.courier_finance_snapshot add column if not exists warehouse_label text;
alter table settlement.courier_finance_snapshot add column if not exists session_id text;
alter table settlement.courier_finance_snapshot add column if not exists fingerprint text;
alter table settlement.courier_finance_snapshot add column if not exists previous_snapshot_id uuid;
alter table settlement.courier_finance_snapshot add column if not exists previous_fingerprint text;
alter table settlement.courier_finance_snapshot add column if not exists changed_from_previous boolean default true;
alter table settlement.courier_finance_snapshot add column if not exists metadata jsonb default '{}'::jsonb;
alter table settlement.courier_finance_snapshot add column if not exists created_by text;
alter table settlement.courier_finance_snapshot add column if not exists created_at timestamptz default now();

alter table settlement.courier_finance_snapshot
    alter column period_start set not null,
    alter column courier_id set not null,
    alter column version set not null,
    alter column source set not null,
    alter column source set default 'devtest_finance',
    alter column fingerprint set not null,
    alter column changed_from_previous set not null,
    alter column changed_from_previous set default true,
    alter column metadata set not null,
    alter column metadata set default '{}'::jsonb,
    alter column created_at set not null,
    alter column created_at set default now();

alter table settlement.courier_finance_snapshot
    drop constraint if exists courier_finance_snapshot_fingerprint_unique;

create table if not exists settlement.courier_finance_snapshot_item (id uuid primary key default gen_random_uuid());

alter table settlement.courier_finance_snapshot_item add column if not exists snapshot_id uuid references settlement.courier_finance_snapshot(id) on delete cascade;
alter table settlement.courier_finance_snapshot_item add column if not exists section text;
alter table settlement.courier_finance_snapshot_item add column if not exists item_key text;
alter table settlement.courier_finance_snapshot_item add column if not exists item_label text;
alter table settlement.courier_finance_snapshot_item add column if not exists amount_value numeric default 0;
alter table settlement.courier_finance_snapshot_item add column if not exists amount_kind text default 'huf';
alter table settlement.courier_finance_snapshot_item add column if not exists note text;
alter table settlement.courier_finance_snapshot_item add column if not exists display_order integer default 0;
alter table settlement.courier_finance_snapshot_item add column if not exists created_at timestamptz default now();

alter table settlement.courier_finance_snapshot_item
    alter column snapshot_id set not null,
    alter column section set not null,
    alter column item_key set not null,
    alter column item_label set not null,
    alter column amount_value set not null,
    alter column amount_value set default 0,
    alter column amount_kind set not null,
    alter column amount_kind set default 'huf',
    alter column display_order set not null,
    alter column display_order set default 0,
    alter column created_at set not null,
    alter column created_at set default now();

alter table settlement.courier_finance_snapshot_item
    drop constraint if exists courier_finance_snapshot_item_amount_kind_check;

alter table settlement.courier_finance_snapshot_item
    add constraint courier_finance_snapshot_item_amount_kind_check
    check (amount_kind in ('huf', 'count'));

create table if not exists settlement.courier_finance_snapshot_source (id uuid primary key default gen_random_uuid());

alter table settlement.courier_finance_snapshot_source add column if not exists snapshot_id uuid references settlement.courier_finance_snapshot(id) on delete cascade;
alter table settlement.courier_finance_snapshot_source add column if not exists source_key text;
alter table settlement.courier_finance_snapshot_source add column if not exists source_table text;
alter table settlement.courier_finance_snapshot_source add column if not exists payload jsonb default '{}'::jsonb;
alter table settlement.courier_finance_snapshot_source add column if not exists row_count integer default 0;
alter table settlement.courier_finance_snapshot_source add column if not exists created_at timestamptz default now();

alter table settlement.courier_finance_snapshot_source
    alter column snapshot_id set not null,
    alter column source_key set not null,
    alter column payload set not null,
    alter column payload set default '{}'::jsonb,
    alter column row_count set not null,
    alter column row_count set default 0,
    alter column created_at set not null,
    alter column created_at set default now();

create unique index if not exists courier_finance_snapshot_version_unique
    on settlement.courier_finance_snapshot (period_start, courier_id, version);

create unique index if not exists courier_finance_snapshot_item_unique
    on settlement.courier_finance_snapshot_item (snapshot_id, section, item_key);

create unique index if not exists courier_finance_snapshot_source_unique
    on settlement.courier_finance_snapshot_source (snapshot_id, source_key);

create index if not exists idx_courier_finance_snapshot_courier_month
    on settlement.courier_finance_snapshot (courier_id, period_start, version desc);

create index if not exists idx_courier_finance_snapshot_item_snapshot
    on settlement.courier_finance_snapshot_item (snapshot_id, section, display_order);

create index if not exists idx_courier_finance_snapshot_source_snapshot
    on settlement.courier_finance_snapshot_source (snapshot_id, source_key);

grant select, insert, update, delete on settlement.courier_finance_snapshot to service_role;
grant select, insert, update, delete on settlement.courier_finance_snapshot_item to service_role;
grant select, insert, update, delete on settlement.courier_finance_snapshot_source to service_role;
grant select on settlement.courier_finance_snapshot to authenticated;
grant select on settlement.courier_finance_snapshot_item to authenticated;
grant select on settlement.courier_finance_snapshot_source to authenticated;

notify pgrst, 'reload schema';

commit;
