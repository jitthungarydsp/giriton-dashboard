create or replace view public.vw_dsp_route_delay_detail as
with ranked_routes as (
    select
        stories.*,
        row_number() over (
            partition by stories.work_date, stories.courier_id
            order by
                stories.shift_start nulls last,
                stories.assigned_at nulls last,
                stories.route_id
        ) as route_rank_in_day,
        extract(epoch from (
            stories.available_for_shift_since - stories.shift_start
        )) / 60.0 as available_delay_vs_shift_start_minutes,
        extract(epoch from (
            coalesce(stories.queue_started_at, stories.available_for_shift_since) - stories.shift_start
        )) / 60.0 as queue_started_delay_vs_shift_start_minutes,
        extract(epoch from (
            stories.real_departure - stories.planned_departure
        )) / 60.0 as departure_delay_vs_plan_minutes,
        extract(epoch from (
            stories.real_departure - stories.shift_start
        )) / 60.0 as departure_delay_vs_shift_start_minutes
    from public.mart_dsp_route_stories stories
)
select
    work_date,
    courier_id,
    courier_name,
    warehouse_name,
    route_id,
    shift_id,
    shift_name,
    shift_start,
    shift_end,
    available_for_shift_since,
    queue_started_at,
    assigned_at,
    planned_departure,
    real_departure,
    planned_return,
    real_return,
    route_rank_in_day,
    route_rank_in_day = 1 as is_first_route_of_day,
    round(available_delay_vs_shift_start_minutes)::integer as available_delay_vs_shift_start_minutes,
    round(queue_started_delay_vs_shift_start_minutes)::integer as queue_started_delay_vs_shift_start_minutes,
    round(departure_delay_vs_plan_minutes)::integer as departure_delay_vs_plan_minutes,
    round(departure_delay_vs_shift_start_minutes)::integer as departure_delay_vs_shift_start_minutes,
    queue_wait_minutes,
    planned_route_minutes,
    real_route_minutes,
    total_route_minutes,
    address_count,
    planned_late_count,
    time_window_late_count,
    booking_shift_count,
    next_booking_shift_text,
    next_booking_shift_start,
    next_shift_delay_minutes,
    assignment_mode,
    case
        when coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes) is null
            then 'Nincs sorbaállási adat'
        when coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes) > 0
            then 'Műszakkezdéshez képest későn állt sorba'
        when coalesce(departure_delay_vs_plan_minutes, 0) > 0
            then 'Tervezett induláshoz képest késés'
        when coalesce(time_window_late_count, 0) > 0
            then 'Időablakos késés'
        else 'Nincs késés'
    end as delay_status,
    (
        coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes, 0) > 0
        or coalesce(departure_delay_vs_plan_minutes, 0) > 0
        or coalesce(time_window_late_count, 0) > 0
    ) as has_delay,
    (
        route_rank_in_day = 1
        and (
            coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes, 0) > 0
            or coalesce(departure_delay_vs_plan_minutes, 0) > 0
            or coalesce(time_window_late_count, 0) > 0
        )
    ) as first_route_has_delay,
    updated_at
from ranked_routes;

create or replace view public.vw_dsp_courier_delay_daily as
select
    work_date,
    courier_id,
    max(courier_name) as courier_name,
    string_agg(distinct warehouse_name, ', ' order by warehouse_name) as warehouses,
    count(*) as route_count,
    sum(coalesce(address_count, 0)) as address_count,
    count(*) filter (where has_delay) as delayed_route_count,
    sum(coalesce(time_window_late_count, 0)) as time_window_late_count,
    count(*) filter (
        where coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes, 0) > 0
    ) as queue_late_route_count,
    sum(greatest(coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes, 0), 0))::integer
        as queue_late_total_minutes,
    max(greatest(coalesce(queue_started_delay_vs_shift_start_minutes, available_delay_vs_shift_start_minutes, 0), 0))::integer
        as queue_late_max_minutes,
    count(*) filter (where coalesce(departure_delay_vs_plan_minutes, 0) > 0) as departure_late_route_count,
    sum(greatest(coalesce(departure_delay_vs_plan_minutes, 0), 0))::integer as departure_late_total_minutes,
    max(greatest(coalesce(departure_delay_vs_plan_minutes, 0), 0))::integer as departure_late_max_minutes,
    max(route_id) filter (where is_first_route_of_day) as first_route_id,
    max(shift_name) filter (where is_first_route_of_day) as first_shift_name,
    max(shift_start) filter (where is_first_route_of_day) as first_shift_start,
    max(available_for_shift_since) filter (where is_first_route_of_day) as first_available_for_shift_since,
    max(queue_started_at) filter (where is_first_route_of_day) as first_queue_started_at,
    max(assigned_at) filter (where is_first_route_of_day) as first_assigned_at,
    max(planned_departure) filter (where is_first_route_of_day) as first_planned_departure,
    max(real_departure) filter (where is_first_route_of_day) as first_real_departure,
    max(planned_return) filter (where is_first_route_of_day) as first_planned_return,
    max(real_return) filter (where is_first_route_of_day) as first_real_return,
    max(queue_started_delay_vs_shift_start_minutes) filter (where is_first_route_of_day) as first_route_queue_delay_minutes,
    max(departure_delay_vs_plan_minutes) filter (where is_first_route_of_day) as first_route_departure_delay_minutes,
    max(time_window_late_count) filter (where is_first_route_of_day) as first_route_time_window_late_count,
    bool_or(first_route_has_delay) as first_route_has_delay,
    max(delay_status) filter (where is_first_route_of_day) as first_route_delay_status
from public.vw_dsp_route_delay_detail
group by work_date, courier_id;

create or replace view public.vw_dsp_courier_delay_monthly as
select
    date_trunc('month', work_date)::date as month_start,
    courier_id,
    max(courier_name) as courier_name,
    string_agg(distinct warehouses, ', ' order by warehouses) as warehouses,
    count(*) as workday_count,
    sum(route_count) as route_count,
    sum(address_count) as address_count,
    sum(delayed_route_count) as delayed_route_count,
    sum(time_window_late_count) as time_window_late_count,
    sum(queue_late_route_count) as queue_late_route_count,
    sum(queue_late_total_minutes) as queue_late_total_minutes,
    max(queue_late_max_minutes) as queue_late_max_minutes,
    sum(departure_late_route_count) as departure_late_route_count,
    sum(departure_late_total_minutes) as departure_late_total_minutes,
    max(departure_late_max_minutes) as departure_late_max_minutes,
    count(*) filter (where first_route_has_delay) as first_route_delay_day_count,
    sum(greatest(coalesce(first_route_queue_delay_minutes, 0), 0))::integer as first_route_queue_delay_total_minutes,
    max(greatest(coalesce(first_route_queue_delay_minutes, 0), 0))::integer as first_route_queue_delay_max_minutes,
    sum(greatest(coalesce(first_route_departure_delay_minutes, 0), 0))::integer as first_route_departure_delay_total_minutes,
    max(greatest(coalesce(first_route_departure_delay_minutes, 0), 0))::integer as first_route_departure_delay_max_minutes
from public.vw_dsp_courier_delay_daily
group by date_trunc('month', work_date)::date, courier_id;

create table if not exists settlement.dsp_route_delay_audit_detail (
    period_start date not null,
    period_end date not null,
    work_date date not null,
    courier_id integer not null,
    courier_name text,
    warehouse_name text,
    route_id bigint not null,
    shift_id bigint,
    shift_name text,
    shift_start timestamp,
    shift_end timestamp,
    available_for_shift_since timestamp,
    queue_started_at timestamp,
    assigned_at timestamp,
    planned_departure timestamp,
    real_departure timestamp,
    planned_return timestamp,
    real_return timestamp,
    route_rank_in_day integer,
    is_first_route_of_day boolean not null default false,
    available_delay_vs_shift_start_minutes integer,
    queue_started_delay_vs_shift_start_minutes integer,
    departure_delay_vs_plan_minutes integer,
    departure_delay_vs_shift_start_minutes integer,
    queue_wait_minutes integer,
    planned_route_minutes integer,
    real_route_minutes integer,
    total_route_minutes integer,
    address_count integer,
    planned_late_count integer,
    time_window_late_count integer,
    booking_shift_count integer,
    next_booking_shift_text text,
    next_booking_shift_start timestamp,
    next_shift_delay_minutes integer,
    assignment_mode text,
    delay_status text,
    has_delay boolean not null default false,
    first_route_has_delay boolean not null default false,
    refreshed_at timestamptz not null default now(),
    primary key (period_start, period_end, work_date, courier_id, route_id)
);

create table if not exists settlement.dsp_courier_delay_audit_daily (
    period_start date not null,
    period_end date not null,
    work_date date not null,
    courier_id integer not null,
    courier_name text,
    warehouses text,
    route_count integer,
    address_count integer,
    delayed_route_count integer,
    time_window_late_count integer,
    queue_late_route_count integer,
    queue_late_total_minutes integer,
    queue_late_max_minutes integer,
    departure_late_route_count integer,
    departure_late_total_minutes integer,
    departure_late_max_minutes integer,
    first_route_id bigint,
    first_shift_name text,
    first_shift_start timestamp,
    first_available_for_shift_since timestamp,
    first_queue_started_at timestamp,
    first_assigned_at timestamp,
    first_planned_departure timestamp,
    first_real_departure timestamp,
    first_planned_return timestamp,
    first_real_return timestamp,
    first_route_queue_delay_minutes integer,
    first_route_departure_delay_minutes integer,
    first_route_time_window_late_count integer,
    first_route_has_delay boolean not null default false,
    first_route_delay_status text,
    refreshed_at timestamptz not null default now(),
    primary key (period_start, period_end, work_date, courier_id)
);

create table if not exists settlement.dsp_time_window_delay_audit_monthly (
    period_start date not null,
    period_end date not null,
    courier_id integer not null,
    courier_name text,
    api_delayed_order_count integer not null default 0,
    mart_time_window_late_count integer not null default 0,
    difference_count integer not null default 0,
    delay_match_ok boolean not null default false,
    refreshed_at timestamptz not null default now(),
    primary key (period_start, period_end, courier_id)
);

create index if not exists dsp_route_delay_audit_detail_period_idx
    on settlement.dsp_route_delay_audit_detail (period_start, period_end, courier_id);

create index if not exists dsp_route_delay_audit_detail_first_idx
    on settlement.dsp_route_delay_audit_detail (work_date, courier_id)
    where is_first_route_of_day;

create index if not exists dsp_courier_delay_audit_daily_period_idx
    on settlement.dsp_courier_delay_audit_daily (period_start, period_end, courier_id);

create index if not exists dsp_time_window_delay_audit_monthly_period_idx
    on settlement.dsp_time_window_delay_audit_monthly (period_start, period_end, courier_id);

create or replace function settlement.refresh_dsp_route_delay_audit(
    p_period_start date,
    p_period_end date
)
returns jsonb
language plpgsql
as $$
declare
    detail_rows integer := 0;
    daily_rows integer := 0;
    monthly_compare_rows integer := 0;
begin
    delete from settlement.dsp_route_delay_audit_detail
    where period_start = p_period_start
      and period_end = p_period_end;

    delete from settlement.dsp_courier_delay_audit_daily
    where period_start = p_period_start
      and period_end = p_period_end;

    delete from settlement.dsp_time_window_delay_audit_monthly
    where period_start = p_period_start
      and period_end = p_period_end;

    insert into settlement.dsp_route_delay_audit_detail (
        period_start,
        period_end,
        work_date,
        courier_id,
        courier_name,
        warehouse_name,
        route_id,
        shift_id,
        shift_name,
        shift_start,
        shift_end,
        available_for_shift_since,
        queue_started_at,
        assigned_at,
        planned_departure,
        real_departure,
        planned_return,
        real_return,
        route_rank_in_day,
        is_first_route_of_day,
        available_delay_vs_shift_start_minutes,
        queue_started_delay_vs_shift_start_minutes,
        departure_delay_vs_plan_minutes,
        departure_delay_vs_shift_start_minutes,
        queue_wait_minutes,
        planned_route_minutes,
        real_route_minutes,
        total_route_minutes,
        address_count,
        planned_late_count,
        time_window_late_count,
        booking_shift_count,
        next_booking_shift_text,
        next_booking_shift_start,
        next_shift_delay_minutes,
        assignment_mode,
        delay_status,
        has_delay,
        first_route_has_delay,
        refreshed_at
    )
    select
        p_period_start,
        p_period_end,
        work_date,
        courier_id,
        courier_name,
        warehouse_name,
        route_id,
        shift_id,
        shift_name,
        shift_start,
        shift_end,
        available_for_shift_since,
        queue_started_at,
        assigned_at,
        planned_departure,
        real_departure,
        planned_return,
        real_return,
        route_rank_in_day,
        is_first_route_of_day,
        available_delay_vs_shift_start_minutes,
        queue_started_delay_vs_shift_start_minutes,
        departure_delay_vs_plan_minutes,
        departure_delay_vs_shift_start_minutes,
        queue_wait_minutes,
        planned_route_minutes,
        real_route_minutes,
        total_route_minutes,
        address_count,
        planned_late_count,
        time_window_late_count,
        booking_shift_count,
        next_booking_shift_text,
        next_booking_shift_start,
        next_shift_delay_minutes,
        assignment_mode,
        delay_status,
        has_delay,
        first_route_has_delay,
        now()
    from public.vw_dsp_route_delay_detail
    where work_date between p_period_start and p_period_end;

    get diagnostics detail_rows = row_count;

    insert into settlement.dsp_courier_delay_audit_daily (
        period_start,
        period_end,
        work_date,
        courier_id,
        courier_name,
        warehouses,
        route_count,
        address_count,
        delayed_route_count,
        time_window_late_count,
        queue_late_route_count,
        queue_late_total_minutes,
        queue_late_max_minutes,
        departure_late_route_count,
        departure_late_total_minutes,
        departure_late_max_minutes,
        first_route_id,
        first_shift_name,
        first_shift_start,
        first_available_for_shift_since,
        first_queue_started_at,
        first_assigned_at,
        first_planned_departure,
        first_real_departure,
        first_planned_return,
        first_real_return,
        first_route_queue_delay_minutes,
        first_route_departure_delay_minutes,
        first_route_time_window_late_count,
        first_route_has_delay,
        first_route_delay_status,
        refreshed_at
    )
    select
        p_period_start,
        p_period_end,
        work_date,
        courier_id,
        courier_name,
        warehouses,
        route_count,
        address_count,
        delayed_route_count,
        time_window_late_count,
        queue_late_route_count,
        queue_late_total_minutes,
        queue_late_max_minutes,
        departure_late_route_count,
        departure_late_total_minutes,
        departure_late_max_minutes,
        first_route_id,
        first_shift_name,
        first_shift_start,
        first_available_for_shift_since,
        first_queue_started_at,
        first_assigned_at,
        first_planned_departure,
        first_real_departure,
        first_planned_return,
        first_real_return,
        first_route_queue_delay_minutes,
        first_route_departure_delay_minutes,
        first_route_time_window_late_count,
        first_route_has_delay,
        first_route_delay_status,
        now()
    from public.vw_dsp_courier_delay_daily
    where work_date between p_period_start and p_period_end;

    get diagnostics daily_rows = row_count;

    with api_delay as (
        select
            courier_id,
            max(courier_name) as courier_name,
            sum(coalesce(delayed_order_count, 0))::integer as api_delayed_order_count
        from public.dsp_courier_quality_daily
        where work_date between p_period_start and p_period_end
        group by courier_id
    ),
    mart_delay as (
        select
            courier_id,
            max(courier_name) as courier_name,
            sum(coalesce(time_window_late_count, 0))::integer as mart_time_window_late_count
        from public.mart_dsp_route_stories
        where work_date between p_period_start and p_period_end
        group by courier_id
    ),
    compared as (
        select
            coalesce(api.courier_id, mart.courier_id) as courier_id,
            coalesce(api.courier_name, mart.courier_name) as courier_name,
            coalesce(api.api_delayed_order_count, 0) as api_delayed_order_count,
            coalesce(mart.mart_time_window_late_count, 0) as mart_time_window_late_count
        from api_delay api
        full join mart_delay mart on mart.courier_id = api.courier_id
    )
    insert into settlement.dsp_time_window_delay_audit_monthly (
        period_start,
        period_end,
        courier_id,
        courier_name,
        api_delayed_order_count,
        mart_time_window_late_count,
        difference_count,
        delay_match_ok,
        refreshed_at
    )
    select
        p_period_start,
        p_period_end,
        courier_id,
        courier_name,
        api_delayed_order_count,
        mart_time_window_late_count,
        mart_time_window_late_count - api_delayed_order_count,
        api_delayed_order_count = mart_time_window_late_count,
        now()
    from compared
    where courier_id is not null;

    get diagnostics monthly_compare_rows = row_count;

    return jsonb_build_object(
        'detail_rows', detail_rows,
        'daily_rows', daily_rows,
        'monthly_compare_rows', monthly_compare_rows
    );
end;
$$;

grant select on public.vw_dsp_route_delay_detail to service_role;
grant select on public.vw_dsp_courier_delay_daily to service_role;
grant select on public.vw_dsp_courier_delay_monthly to service_role;
grant select, insert, update, delete on settlement.dsp_route_delay_audit_detail to service_role;
grant select, insert, update, delete on settlement.dsp_courier_delay_audit_daily to service_role;
grant select, insert, update, delete on settlement.dsp_time_window_delay_audit_monthly to service_role;
grant execute on function settlement.refresh_dsp_route_delay_audit(date, date) to service_role;

notify pgrst, 'reload schema';
