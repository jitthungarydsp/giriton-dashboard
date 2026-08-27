create table if not exists public.ops_shift_start_parameters (
    id bigserial primary key,
    warehouse text not null,
    shift_code text not null,
    shift_kind text not null default 'normal',
    route_count integer not null default 1,
    start_time time not null,
    end_time time not null,
    paid_duration interval not null,
    break_duration interval not null default interval '0 minutes',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (warehouse, shift_code)
);

create index if not exists idx_ops_shift_start_parameters_lookup
    on public.ops_shift_start_parameters (warehouse, is_active, start_time);

with warehouses as (
    select unnest(array['BUD1', 'BUD2']) as warehouse
),
normal_starts as (
    select
        warehouse,
        start_at::time as start_time
    from warehouses
    cross join generate_series(
        time '04:30',
        time '21:30',
        interval '15 minutes'
    ) as start_at
),
normal_seed as (
    select
        warehouse,
        warehouse || '_' || to_char(start_time, 'FMHH24:MI') as shift_code,
        'normal' as shift_kind,
        1 as route_count,
        start_time,
        case
            when start_time <= time '06:45' then start_time + interval '5 hours'
            when start_time <= time '18:15' then start_time + interval '4 hours 45 minutes'
            when start_time <= time '19:15' then start_time + interval '4 hours 30 minutes'
            else time '23:59'
        end::time as end_time,
        case
            when start_time <= time '06:45' then interval '5 hours'
            when start_time <= time '18:15' then interval '4 hours 45 minutes'
            when start_time <= time '19:15' then interval '4 hours 30 minutes'
            else time '23:59' - start_time
        end as paid_duration,
        interval '0 minutes' as break_duration,
        true as is_active
    from normal_starts
),
coordinator_seed as (
    select *
    from (
        values
            ('BUD1', 'Koordi_DE_FC1', 'coordinator', 1, time '04:00', time '14:30', interval '10 hours 30 minutes', interval '0 minutes', true),
            ('BUD1', 'Koordi_DU_FC1', 'coordinator', 1, time '13:30', time '23:00', interval '9 hours 30 minutes', interval '0 minutes', true),
            ('BUD2', 'Koordi_DE_FC2', 'coordinator', 1, time '04:00', time '14:30', interval '10 hours 30 minutes', interval '0 minutes', true),
            ('BUD2', 'Koordi_DU_FC2', 'coordinator', 1, time '13:30', time '23:00', interval '9 hours 30 minutes', interval '0 minutes', true),
            ('BUD1', 'Koordi_FULLTIME_FC1', 'coordinator', 1, time '04:00', time '23:00', interval '19 hours', interval '0 minutes', true),
            ('BUD2', 'Koordi_FULLTIME_FC2', 'coordinator', 1, time '04:00', time '23:00', interval '19 hours', interval '0 minutes', true)
    ) as seed(warehouse, shift_code, shift_kind, route_count, start_time, end_time, paid_duration, break_duration, is_active)
),
express_seed as (
    select *
    from (
        values
            ('BUD1', 'BUD1_EXP_5:00', 'express', 6, time '05:00', time '18:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_5:30', 'express', 6, time '05:30', time '18:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_6:00', 'express', 5, time '06:00', time '19:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_6:30', 'express', 5, time '06:30', time '19:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_7:00', 'express', 5, time '07:00', time '20:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_7:30', 'express', 4, time '07:30', time '20:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_8:00', 'express', 4, time '08:00', time '21:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_8:30', 'express', 4, time '08:30', time '21:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_9:00', 'express', 3, time '09:00', time '22:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_9:30', 'express', 3, time '09:30', time '22:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD1', 'BUD1_EXP_10:00', 'express', 3, time '10:00', time '23:30', interval '12 hours 45 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_5:00', 'express', 6, time '05:00', time '18:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_5:30', 'express', 6, time '05:30', time '18:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_6:00', 'express', 5, time '06:00', time '19:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_6:30', 'express', 5, time '06:30', time '19:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_7:00', 'express', 5, time '07:00', time '20:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_7:30', 'express', 4, time '07:30', time '20:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_8:00', 'express', 4, time '08:00', time '21:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_8:30', 'express', 4, time '08:30', time '21:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_9:00', 'express', 3, time '09:00', time '22:00', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_9:30', 'express', 3, time '09:30', time '22:30', interval '12 hours 15 minutes', interval '45 minutes', true),
            ('BUD2', 'BUD2_EXP_10:00', 'express', 3, time '10:00', time '23:30', interval '12 hours 45 minutes', interval '45 minutes', true)
    ) as seed(warehouse, shift_code, shift_kind, route_count, start_time, end_time, paid_duration, break_duration, is_active)
),
seed as (
    select * from normal_seed
    union all
    select * from coordinator_seed
    union all
    select * from express_seed
)
insert into public.ops_shift_start_parameters (
    warehouse,
    shift_code,
    shift_kind,
    route_count,
    start_time,
    end_time,
    paid_duration,
    break_duration,
    is_active
)
select
    warehouse,
    shift_code,
    shift_kind,
    route_count,
    start_time,
    end_time,
    paid_duration,
    break_duration,
    is_active
from seed
on conflict (warehouse, shift_code) do update set
    shift_kind = excluded.shift_kind,
    route_count = excluded.route_count,
    start_time = excluded.start_time,
    end_time = excluded.end_time,
    paid_duration = excluded.paid_duration,
    break_duration = excluded.break_duration,
    is_active = excluded.is_active,
    updated_at = now();

grant select on public.ops_shift_start_parameters to anon;
grant select on public.ops_shift_start_parameters to authenticated;
grant all on public.ops_shift_start_parameters to service_role;
