begin;

create table if not exists settlement.courier_monthly_workload_summary (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    period_start date not null,
    period_end date not null,
    booked_shift_count integer not null default 0 check (booked_shift_count >= 0),
    advance_booked_shift_count integer not null default 0 check (advance_booked_shift_count >= 0),
    giriton_shift_count integer not null default 0 check (giriton_shift_count >= 0),
    completed_route_count integer not null default 0 check (completed_route_count >= 0),
    normal_route_count integer not null default 0 check (normal_route_count >= 0),
    express_route_count integer not null default 0 check (express_route_count >= 0),
    regional_route_count integer not null default 0 check (regional_route_count >= 0),
    order_count integer not null default 0 check (order_count >= 0),
    tip_huf numeric not null default 0,
    muszakpro_source text,
    route_source text,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint courier_monthly_workload_summary_unique unique (courier_id, period_start)
);

alter table settlement.courier_monthly_workload_summary
    add column if not exists giriton_shift_count integer not null default 0 check (giriton_shift_count >= 0);

alter table settlement.courier_monthly_workload_summary
    add column if not exists normal_route_count integer not null default 0 check (normal_route_count >= 0),
    add column if not exists express_route_count integer not null default 0 check (express_route_count >= 0),
    add column if not exists regional_route_count integer not null default 0 check (regional_route_count >= 0),
    add column if not exists tip_huf numeric not null default 0;

create index if not exists courier_monthly_workload_summary_period_idx
    on settlement.courier_monthly_workload_summary (period_start, period_end);

create index if not exists courier_monthly_workload_summary_courier_idx
    on settlement.courier_monthly_workload_summary (courier_id, period_start desc);

with ranked_summary as (
    select
        summary.*,
        date_trunc('month', coalesce(summary.period_start, summary.period_end))::date as month_start,
        row_number() over (
            partition by summary.courier_id, date_trunc('month', coalesce(summary.period_start, summary.period_end))::date
            order by summary.calculated_at desc nulls last, summary.session_id desc
        ) as month_rank
    from settlement.courier_settlement_summary summary
    where nullif(summary.courier_id, '') is not null
      and coalesce(summary.period_start, summary.period_end) is not null
),
route_types as (
    select
        j.session_id,
        coalesce(nullif(j.normalized_data ->> 'Courier ID', ''), nullif(j.normalized_data ->> 'courier_id', '')) as courier_id,
        count(*) filter (
            where j.is_route_primary
              and route_type.route_type_text not like '%express%'
              and route_type.route_type_text not like '%region%'
              and route_type.route_type_text not like '%regio%'
        ) as normal_route_count,
        count(*) filter (
            where j.is_route_primary
              and route_type.route_type_text like '%express%'
        ) as express_route_count,
        count(*) filter (
            where j.is_route_primary
              and (
                  route_type.route_type_text like '%region%'
                  or route_type.route_type_text like '%regio%'
              )
        ) as regional_route_count
    from settlement.jit_row j
    cross join lateral (
        select translate(
            lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', 'normal')),
            'áéíóöőúüű',
            'aeiooouuu'
        ) as route_type_text
    ) route_type
    group by
        j.session_id,
        coalesce(nullif(j.normalized_data ->> 'Courier ID', ''), nullif(j.normalized_data ->> 'courier_id', ''))
)
insert into settlement.courier_monthly_workload_summary (
    courier_id,
    courier_name,
    period_start,
    period_end,
    completed_route_count,
    normal_route_count,
    express_route_count,
    regional_route_count,
    order_count,
    tip_huf,
    route_source,
    updated_by,
    updated_at
)
select
    ranked_summary.courier_id,
    ranked_summary.driver_name,
    ranked_summary.month_start,
    (ranked_summary.month_start + interval '1 month - 1 day')::date,
    greatest(coalesce(ranked_summary.route_count, 0), 0)::integer,
    greatest(coalesce(route_types.normal_route_count, ranked_summary.route_count, 0), 0)::integer,
    greatest(coalesce(route_types.express_route_count, 0), 0)::integer,
    greatest(coalesce(route_types.regional_route_count, 0), 0)::integer,
    greatest(round(coalesce(ranked_summary.order_count, 0)), 0)::integer,
    coalesce(ranked_summary.tip_huf, 0),
    'courier_settlement_summary',
    'migration',
    now()
from ranked_summary
left join route_types
    on route_types.session_id = ranked_summary.session_id
    and route_types.courier_id = ranked_summary.courier_id
where ranked_summary.month_rank = 1
on conflict (courier_id, period_start)
do update set
    courier_name = excluded.courier_name,
    period_end = excluded.period_end,
    completed_route_count = excluded.completed_route_count,
    normal_route_count = excluded.normal_route_count,
    express_route_count = excluded.express_route_count,
    regional_route_count = excluded.regional_route_count,
    order_count = excluded.order_count,
    tip_huf = excluded.tip_huf,
    route_source = excluded.route_source,
    updated_by = excluded.updated_by,
    updated_at = excluded.updated_at;

grant select, insert, update, delete on settlement.courier_monthly_workload_summary to service_role;

notify pgrst, 'reload schema';

commit;
