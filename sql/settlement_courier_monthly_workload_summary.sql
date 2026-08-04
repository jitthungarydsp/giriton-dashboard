begin;

create table if not exists settlement.courier_monthly_workload_summary (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    period_start date not null,
    period_end date not null,
    booked_shift_count integer not null default 0 check (booked_shift_count >= 0),
    advance_booked_shift_count integer not null default 0 check (advance_booked_shift_count >= 0),
    completed_route_count integer not null default 0 check (completed_route_count >= 0),
    order_count integer not null default 0 check (order_count >= 0),
    muszakpro_source text,
    route_source text,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint courier_monthly_workload_summary_unique unique (courier_id, period_start)
);

create index if not exists courier_monthly_workload_summary_period_idx
    on settlement.courier_monthly_workload_summary (period_start, period_end);

create index if not exists courier_monthly_workload_summary_courier_idx
    on settlement.courier_monthly_workload_summary (courier_id, period_start desc);

grant select, insert, update, delete on settlement.courier_monthly_workload_summary to service_role;

notify pgrst, 'reload schema';

commit;
