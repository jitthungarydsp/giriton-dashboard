begin;

create table if not exists settlement.courier_profile_change_log (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    changed_fields jsonb not null,
    changed_by text not null,
    created_at timestamptz not null default now()
);

create index if not exists courier_profile_change_log_courier_idx
    on settlement.courier_profile_change_log (courier_id, created_at desc);

grant select, insert on settlement.courier_profile_change_log to service_role;

commit;
