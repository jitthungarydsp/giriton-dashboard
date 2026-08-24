-- Giriton nyitott muszak kapacitas snapshotok.
-- Egy raw export futas tobb sort ir:
-- - datum + raktar bontas
-- - datum + ALL napi osszesito

create table if not exists public.ops_giriton_open_shift_snapshots (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'giriton-raw-export',
    snapshot_at timestamptz not null default now(),
    work_date date not null,
    warehouse text not null,
    open_shift_count integer not null default 0,
    total_capacity integer not null default 0,
    booked_capacity integer not null default 0,
    raw_row_count integer not null default 0,
    open_shift_detail jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_ops_giriton_open_shift_snapshots_date
    on public.ops_giriton_open_shift_snapshots (work_date, snapshot_at desc);

create index if not exists idx_ops_giriton_open_shift_snapshots_warehouse
    on public.ops_giriton_open_shift_snapshots (warehouse, work_date, snapshot_at desc);

create index if not exists idx_ops_giriton_open_shift_snapshots_snapshot
    on public.ops_giriton_open_shift_snapshots (snapshot_at desc);

grant select, insert on public.ops_giriton_open_shift_snapshots to service_role;
