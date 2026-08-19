create table if not exists settlement.pwa_workflow_acceptance_snapshots (
    id bigserial primary key,
    courier_id text not null,
    courier_name text not null default '',
    period_start date not null,
    action_key text not null check (action_key in ('settlement', 'tig')),
    process_id text not null default '',
    payable_huf numeric not null default 0,
    tig_final_total_huf numeric not null default 0,
    snapshot jsonb not null default '{}'::jsonb,
    accepted_by text not null default '',
    accepted_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists idx_pwa_workflow_acceptance_snapshots_lookup
    on settlement.pwa_workflow_acceptance_snapshots (period_start, courier_id, action_key, accepted_at desc);

grant all on table settlement.pwa_workflow_acceptance_snapshots to service_role;
grant usage, select on sequence settlement.pwa_workflow_acceptance_snapshots_id_seq to service_role;
