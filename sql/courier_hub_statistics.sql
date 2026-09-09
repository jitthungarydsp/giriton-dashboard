begin;

create table if not exists public.courier_hub_route_statistics (
    courier_id integer not null,
    work_date date not null,
    route_id bigint not null,
    warehouse_id integer not null,
    warehouse_code text,
    dsp_id integer not null default 8,
    courier_name text,
    shift_name text,
    queue_started_at timestamptz,
    actual_shift_start_at timestamptz,
    route_assigned_at timestamptz,
    departed_at timestamptz,
    returned_at timestamptz,
    planned_departure_at timestamptz,
    planned_return_at timestamptz,
    next_shift_same_day text,
    late_stop_count integer not null default 0,
    late_stop_minutes integer not null default 0,
    planned_route_minutes integer,
    actual_route_minutes integer,
    waiting_minutes integer,
    loading_minutes integer,
    total_minutes integer,
    planned_km numeric(10, 2),
    hub_mileage_km numeric(10, 2),
    google_route_km numeric(10, 2),
    google_route_minutes integer,
    google_traffic_delay_minutes integer,
    google_route_status text,
    actual_km numeric(10, 2),
    distance_delta_km numeric(10, 2),
    distance_source text,
    route_type text,
    route_type_label text,
    tip_huf numeric(12, 2) not null default 0,
    tip_source text,
    orders integer not null default 0,
    stops integer not null default 0,
    vehicle_plate text,
    warehouse_address text,
    story_text text,
    source_table text not null default 'courier_route_performance_detail_raw',
    source_updated_at timestamptz,
    request_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, work_date, route_id, warehouse_id, dsp_id)
);

alter table public.courier_hub_route_statistics
    add column if not exists warehouse_code text,
    add column if not exists courier_name text,
    add column if not exists shift_name text,
    add column if not exists queue_started_at timestamptz,
    add column if not exists actual_shift_start_at timestamptz,
    add column if not exists route_assigned_at timestamptz,
    add column if not exists departed_at timestamptz,
    add column if not exists returned_at timestamptz,
    add column if not exists planned_departure_at timestamptz,
    add column if not exists planned_return_at timestamptz,
    add column if not exists next_shift_same_day text,
    add column if not exists late_stop_count integer not null default 0,
    add column if not exists late_stop_minutes integer not null default 0,
    add column if not exists planned_route_minutes integer,
    add column if not exists actual_route_minutes integer,
    add column if not exists waiting_minutes integer,
    add column if not exists loading_minutes integer,
    add column if not exists total_minutes integer,
    add column if not exists planned_km numeric(10, 2),
    add column if not exists hub_mileage_km numeric(10, 2),
    add column if not exists google_route_km numeric(10, 2),
    add column if not exists google_route_minutes integer,
    add column if not exists google_traffic_delay_minutes integer,
    add column if not exists google_route_status text,
    add column if not exists actual_km numeric(10, 2),
    add column if not exists distance_delta_km numeric(10, 2),
    add column if not exists distance_source text,
    add column if not exists route_type text,
    add column if not exists route_type_label text,
    add column if not exists tip_huf numeric(12, 2) not null default 0,
    add column if not exists tip_source text,
    add column if not exists orders integer not null default 0,
    add column if not exists stops integer not null default 0,
    add column if not exists vehicle_plate text,
    add column if not exists warehouse_address text,
    add column if not exists story_text text,
    add column if not exists source_table text not null default 'courier_route_performance_detail_raw',
    add column if not exists source_updated_at timestamptz,
    add column if not exists request_url text,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now();

create index if not exists courier_hub_route_statistics_date_idx
    on public.courier_hub_route_statistics (work_date, warehouse_id, courier_id);

create index if not exists courier_hub_route_statistics_courier_idx
    on public.courier_hub_route_statistics (courier_id, work_date desc);

create index if not exists courier_hub_route_statistics_route_idx
    on public.courier_hub_route_statistics (route_id);

create index if not exists courier_route_performance_detail_raw_status_period_fast_idx
    on public.courier_route_performance_detail_raw (status_code, year, month, warehouse_id, courier_id, route_id);

create index if not exists courier_financial_overview_raw_bud1_status_period_fast_idx
    on public.courier_financial_overview_raw_bud1 (status_code, year, month, warehouse_id, courier_id);

create index if not exists courier_financial_overview_raw_bud2_status_period_fast_idx
    on public.courier_financial_overview_raw_bud2 (status_code, year, month, warehouse_id, courier_id);

create index if not exists courier_shift_overview_next_shift_fast_idx
    on public.courier_shift_overview (courier_id, warehouse_id, dsp_id, work_date, shift_start);

grant select, insert, update, delete on public.courier_hub_route_statistics to service_role;

create table if not exists public.courier_hub_courier_daily_statistics (
    courier_id integer not null,
    work_date date not null,
    warehouse_id integer not null,
    warehouse_code text,
    dsp_id integer not null default 8,
    courier_name text,
    shift_count integer not null default 0,
    route_count integer not null default 0,
    late_route_count integer not null default 0,
    late_stop_count integer not null default 0,
    late_stop_minutes integer not null default 0,
    no_show_shift_count integer not null default 0,
    late_login_shift_count integer not null default 0,
    planned_route_minutes_total integer,
    actual_route_minutes_total integer,
    waiting_minutes_total integer,
    loading_minutes_total integer,
    total_minutes_total integer,
    planned_km_total numeric(12, 2),
    hub_mileage_km_total numeric(12, 2),
    google_route_km_total numeric(12, 2),
    google_route_minutes_total integer,
    google_traffic_delay_minutes_total integer,
    actual_km_total numeric(12, 2),
    distance_delta_km_total numeric(12, 2),
    tip_huf_total numeric(12, 2) not null default 0,
    first_queue_started_at timestamptz,
    first_route_assigned_at timestamptz,
    last_returned_at timestamptz,
    route_types text[],
    daily_story_text text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, work_date, warehouse_id, dsp_id)
);

alter table public.courier_hub_courier_daily_statistics
    add column if not exists warehouse_code text,
    add column if not exists courier_name text,
    add column if not exists shift_count integer not null default 0,
    add column if not exists route_count integer not null default 0,
    add column if not exists late_route_count integer not null default 0,
    add column if not exists late_stop_count integer not null default 0,
    add column if not exists late_stop_minutes integer not null default 0,
    add column if not exists no_show_shift_count integer not null default 0,
    add column if not exists late_login_shift_count integer not null default 0,
    add column if not exists planned_route_minutes_total integer,
    add column if not exists actual_route_minutes_total integer,
    add column if not exists waiting_minutes_total integer,
    add column if not exists loading_minutes_total integer,
    add column if not exists total_minutes_total integer,
    add column if not exists planned_km_total numeric(12, 2),
    add column if not exists hub_mileage_km_total numeric(12, 2),
    add column if not exists google_route_km_total numeric(12, 2),
    add column if not exists google_route_minutes_total integer,
    add column if not exists google_traffic_delay_minutes_total integer,
    add column if not exists actual_km_total numeric(12, 2),
    add column if not exists distance_delta_km_total numeric(12, 2),
    add column if not exists tip_huf_total numeric(12, 2) not null default 0,
    add column if not exists first_queue_started_at timestamptz,
    add column if not exists first_route_assigned_at timestamptz,
    add column if not exists last_returned_at timestamptz,
    add column if not exists route_types text[],
    add column if not exists daily_story_text text,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now();

create index if not exists courier_hub_courier_daily_statistics_date_idx
    on public.courier_hub_courier_daily_statistics (work_date, warehouse_id, courier_id);

create index if not exists courier_hub_courier_daily_statistics_courier_idx
    on public.courier_hub_courier_daily_statistics (courier_id, work_date desc);

grant select, insert, update, delete on public.courier_hub_courier_daily_statistics to service_role;

drop view if exists public.courier_hub_route_raw_display;
drop view if exists public.courier_hub_route_statistics_display;
drop view if exists public.courier_hub_courier_daily_statistics_display;

create or replace view public.courier_hub_route_statistics_display as
select
    work_date as "Dátum",
    warehouse_code as "Raktár",
    courier_id as "Futár ID",
    courier_name as "Futár neve",
    route_id as "Route ID",
    shift_name as "Műszak neve",
    to_char(queue_started_at at time zone 'Europe/Budapest', 'HH24:MI') as "Sorbaállt",
    to_char(actual_shift_start_at at time zone 'Europe/Budapest', 'HH24:MI') as "Tényleges műszak kezdés",
    to_char(route_assigned_at at time zone 'Europe/Budapest', 'HH24:MI') as "Túrát kapott",
    late_stop_count as "Késés a túrán db",
    planned_route_minutes as "Tervezett hossz perc",
    case
        when planned_route_minutes is null then null
        else floor(planned_route_minutes / 60)::text || ':' || lpad((planned_route_minutes % 60)::text, 2, '0')
    end as "Tervezett hossz",
    to_char(planned_return_at at time zone 'Europe/Budapest', 'HH24:MI') as "Tervezett visszaérkezés",
    planned_km as "Tervezett km",
    actual_route_minutes as "Tényleges túraidő perc",
    case
        when actual_route_minutes is null then null
        else floor(actual_route_minutes / 60)::text || ':' || lpad((actual_route_minutes % 60)::text, 2, '0')
    end as "Tényleges túraidő",
    waiting_minutes as "Várakozás túrakiosztásig perc",
    loading_minutes as "Bepakolási idő perc",
    total_minutes as "Teljes túra perc",
    to_char(returned_at at time zone 'Europe/Budapest', 'HH24:MI') as "Tényleges visszaérkezés",
    actual_km as "Tényleges km",
    google_route_km as "Google Routes km",
    hub_mileage_km as "Hub mileage km",
    next_shift_same_day as "Következő műszakja aznap",
    route_type_label as "Túra típusa",
    tip_huf as "Borravaló",
    tip_source as "Borravaló forrás",
    story_text as "Napi szöveg route szerint"
from public.courier_hub_route_statistics;

create or replace view public.courier_hub_courier_daily_statistics_display as
select
    work_date as "Dátum",
    warehouse_code as "Raktár",
    courier_id as "Futár ID",
    courier_name as "Futár neve",
    shift_count as "Műszak db",
    route_count as "Túra db",
    late_route_count as "Késéses túra db",
    late_stop_count as "Késéses megálló db",
    no_show_shift_count as "No-show műszak db",
    late_login_shift_count as "Késő login db",
    planned_route_minutes_total as "Tervezett túraidő összesen perc",
    actual_route_minutes_total as "Tényleges túraidő összesen perc",
    waiting_minutes_total as "Várakozás összesen perc",
    planned_km_total as "Tervezett km összesen",
    actual_km_total as "Tényleges km összesen",
    google_route_km_total as "Google Routes km összesen",
    tip_huf_total as "Borravaló összesen",
    to_char(first_queue_started_at at time zone 'Europe/Budapest', 'HH24:MI') as "Első sorbaállás",
    to_char(first_route_assigned_at at time zone 'Europe/Budapest', 'HH24:MI') as "Első túra kiosztás",
    to_char(last_returned_at at time zone 'Europe/Budapest', 'HH24:MI') as "Utolsó visszaérkezés",
    route_types as "Túratípusok",
    daily_story_text as "Napi szöveges összefoglaló"
from public.courier_hub_courier_daily_statistics;

grant select on public.courier_hub_route_statistics_display to service_role;
grant select on public.courier_hub_courier_daily_statistics_display to service_role;

create or replace view public.courier_hub_route_raw_display as
with raw_events as (
    select
        raw.courier_id,
        raw.route_id,
        raw.year,
        raw.month,
        raw.dsp_id,
        raw.warehouse_id,
        event.value ->> 'type' as event_type,
        case
            when nullif(event.value ->> 'occurredAt', '') is not null
                then (event.value ->> 'occurredAt')::timestamptz
            else null
        end as occurred_at
    from public.courier_route_performance_detail_raw raw
    left join lateral jsonb_array_elements(
        coalesce(raw.response_json -> 'routeLogs', raw.response_json -> 'logs', raw.response_json -> 'log', '[]'::jsonb)
    ) event(value) on true
    where raw.status_code = 200
),
route_base as (
    select
        raw.courier_id,
        raw.route_id,
        raw.year,
        raw.month,
        raw.dsp_id,
        raw.warehouse_id,
        case
            when nullif(raw.response_json #>> '{shift,plannedStartAt}', '') is not null
                then (raw.response_json #>> '{shift,plannedStartAt}')::timestamptz
            else null
        end as planned_start_at
    from public.courier_route_performance_detail_raw raw
    where raw.status_code = 200
),
route_logs as (
    select
        base.courier_id,
        base.route_id,
        base.year,
        base.month,
        base.dsp_id,
        base.warehouse_id,
        shift_available.shift_available_at,
        route_assigned.route_assigned_at,
        departed.departed_at,
        warehouse_arrived.warehouse_arrived_at
    from route_base base
    left join lateral (
        select event.occurred_at as route_assigned_at
        from raw_events event
        where event.courier_id = base.courier_id
            and event.route_id = base.route_id
            and event.year = base.year
            and event.month = base.month
            and event.dsp_id = base.dsp_id
            and event.warehouse_id = base.warehouse_id
            and event.event_type = 'ROUTE_ASSIGNED'
            and event.occurred_at is not null
            and (
                base.planned_start_at is null
                or event.occurred_at between base.planned_start_at - interval '3 hours'
                    and base.planned_start_at + interval '4 hours'
            )
        order by
            case
                when base.planned_start_at is null then 0
                else abs(extract(epoch from (event.occurred_at - base.planned_start_at)))
            end,
            event.occurred_at
        limit 1
    ) route_assigned on true
    left join lateral (
        select event.occurred_at as shift_available_at
        from raw_events event
        where event.courier_id = base.courier_id
            and event.route_id = base.route_id
            and event.year = base.year
            and event.month = base.month
            and event.dsp_id = base.dsp_id
            and event.warehouse_id = base.warehouse_id
            and event.event_type = 'SHIFT_AVAILABLE'
            and event.occurred_at is not null
            and (
                route_assigned.route_assigned_at is null
                or event.occurred_at <= route_assigned.route_assigned_at
            )
        order by event.occurred_at desc
        limit 1
    ) shift_available on true
    left join lateral (
        select event.occurred_at as departed_at
        from raw_events event
        where event.courier_id = base.courier_id
            and event.route_id = base.route_id
            and event.year = base.year
            and event.month = base.month
            and event.dsp_id = base.dsp_id
            and event.warehouse_id = base.warehouse_id
            and event.event_type = 'DEPARTED'
            and event.occurred_at is not null
            and (
                route_assigned.route_assigned_at is null
                or event.occurred_at >= route_assigned.route_assigned_at
            )
        order by event.occurred_at
        limit 1
    ) departed on true
    left join lateral (
        select event.occurred_at as warehouse_arrived_at
        from raw_events event
        where event.courier_id = base.courier_id
            and event.route_id = base.route_id
            and event.year = base.year
            and event.month = base.month
            and event.dsp_id = base.dsp_id
            and event.warehouse_id = base.warehouse_id
            and event.event_type = 'WAREHOUSE_ARRIVED'
            and event.occurred_at is not null
            and (
                departed.departed_at is null
                or event.occurred_at >= departed.departed_at
            )
        order by event.occurred_at
        limit 1
    ) warehouse_arrived on true
),
financial_routes as (
    select
        fin.courier_id,
        fin.warehouse_id,
        case
            when coalesce(route.value ->> 'routeId', route.value ->> 'id', '') ~ '^[0-9]+$'
                then coalesce(route.value ->> 'routeId', route.value ->> 'id')::bigint
            else null
        end as route_id,
        max(
            case
                when jsonb_typeof(route.value -> 'customerTipsTotal') = 'object'
                    and nullif(route.value #>> '{customerTipsTotal,amount}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value #>> '{customerTipsTotal,amount}')::numeric
                when nullif(route.value ->> 'customerTipsTotal', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'customerTipsTotal')::numeric
                when nullif(route.value ->> 'tipsHuf', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'tipsHuf')::numeric
                when nullif(route.value ->> 'tipHuf', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'tipHuf')::numeric
                else null
            end
        ) as tip_huf,
        max(
            case
                when nullif(route.value ->> 'orderCount', '') ~ '^[0-9]+$'
                    then (route.value ->> 'orderCount')::integer
                when nullif(route.value ->> 'orders', '') ~ '^[0-9]+$'
                    then (route.value ->> 'orders')::integer
                else null
            end
        ) as order_count,
        max(route.value ->> 'routeLayer') as route_layer
    from public.courier_financial_overview_raw_bud1 fin
    join lateral jsonb_array_elements(coalesce(fin.response_json -> 'routes', '[]'::jsonb)) route(value) on true
    where fin.status_code = 200
    group by fin.courier_id, fin.warehouse_id, 3
    union all
    select
        fin.courier_id,
        fin.warehouse_id,
        case
            when coalesce(route.value ->> 'routeId', route.value ->> 'id', '') ~ '^[0-9]+$'
                then coalesce(route.value ->> 'routeId', route.value ->> 'id')::bigint
            else null
        end as route_id,
        max(
            case
                when jsonb_typeof(route.value -> 'customerTipsTotal') = 'object'
                    and nullif(route.value #>> '{customerTipsTotal,amount}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value #>> '{customerTipsTotal,amount}')::numeric
                when nullif(route.value ->> 'customerTipsTotal', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'customerTipsTotal')::numeric
                when nullif(route.value ->> 'tipsHuf', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'tipsHuf')::numeric
                when nullif(route.value ->> 'tipHuf', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'tipHuf')::numeric
                else null
            end
        ) as tip_huf,
        max(
            case
                when nullif(route.value ->> 'orderCount', '') ~ '^[0-9]+$'
                    then (route.value ->> 'orderCount')::integer
                when nullif(route.value ->> 'orders', '') ~ '^[0-9]+$'
                    then (route.value ->> 'orders')::integer
                else null
            end
        ) as order_count,
        max(route.value ->> 'routeLayer') as route_layer
    from public.courier_financial_overview_raw_bud2 fin
    join lateral jsonb_array_elements(coalesce(fin.response_json -> 'routes', '[]'::jsonb)) route(value) on true
    where fin.status_code = 200
    group by fin.courier_id, fin.warehouse_id, 3
),
stop_totals as (
    select
        raw.courier_id,
        raw.route_id,
        raw.year,
        raw.month,
        raw.dsp_id,
        raw.warehouse_id,
        count(*) as stop_count,
        count(*) filter (
            where case
                when nullif(stop.value ->> 'delayMinutes', '') ~ '^-?[0-9]+$'
                    then (stop.value ->> 'delayMinutes')::integer
                else 0
            end > 0
        ) as late_stop_count,
        sum(greatest(
            case
                when nullif(stop.value ->> 'delayMinutes', '') ~ '^-?[0-9]+$'
                    then (stop.value ->> 'delayMinutes')::integer
                else 0
            end,
            0
        )) as late_stop_minutes
    from public.courier_route_performance_detail_raw raw
    left join lateral jsonb_array_elements(coalesce(raw.response_json -> 'stops', '[]'::jsonb)) stop(value) on true
    where raw.status_code = 200
    group by raw.courier_id, raw.route_id, raw.year, raw.month, raw.dsp_id, raw.warehouse_id
)
select
    coalesce(
        nullif(raw.response_json ->> 'deliveryDate', '')::date,
        nullif(raw.response_json #>> '{shift,deliveryDate}', '')::date,
        (nullif(raw.response_json #>> '{shift,plannedStartAt}', '')::timestamptz at time zone 'Europe/Budapest')::date
    ) as "Dátum",
    case raw.warehouse_id when 1 then 'BUD1' when 2 then 'BUD2' else 'WH' || raw.warehouse_id::text end as "Raktár",
    raw.courier_id as "Futár ID",
    coalesce(
        nullif(raw.response_json ->> 'courierName', ''),
        nullif(raw.response_json ->> 'name', ''),
        nullif(raw.response_json #>> '{shift,courierName}', ''),
        master.courier_name
    ) as "Futár neve",
    raw.route_id as "Route ID",
    coalesce(
        nullif(raw.response_json #>> '{shift,shiftName}', ''),
        to_char(nullif(raw.response_json #>> '{shift,plannedStartAt}', '')::timestamptz at time zone 'Europe/Budapest', 'HH24:MI')
    ) as "Műszak neve",
    to_char(logs.shift_available_at at time zone 'Europe/Budapest', 'HH24:MI') as "Sorbaállt",
    to_char(logs.route_assigned_at at time zone 'Europe/Budapest', 'HH24:MI') as "Túrát kapott",
    round(extract(epoch from (logs.route_assigned_at - logs.shift_available_at)) / 60)::integer as "Várakozás túrakiosztásig perc",
    round(extract(epoch from (logs.departed_at - logs.route_assigned_at)) / 60)::integer as "Bepakolási idő perc",
    coalesce(stops.late_stop_count, 0) as "Késés a túrán db",
    round(extract(epoch from (
        nullif(raw.response_json #>> '{shift,plannedReturnAt}', '')::timestamptz
        - nullif(raw.response_json #>> '{shift,plannedDepartureAt}', '')::timestamptz
    )) / 60)::integer as "Tervezett hossz perc",
    round(coalesce(
        case
            when nullif(raw.response_json #>> '{shift,plannedKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json #>> '{shift,plannedKm}')::numeric
            else null
        end,
        case
            when nullif(raw.response_json ->> 'plannedKm', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json ->> 'plannedKm')::numeric
            else null
        end
    ), 2) as "Tervezett km",
    round(extract(epoch from (logs.warehouse_arrived_at - logs.departed_at)) / 60)::integer as "Tényleges túraidő perc",
    to_char(logs.warehouse_arrived_at at time zone 'Europe/Budapest', 'HH24:MI') as "Tényleges visszaérkezés",
    round(
        case
            when nullif(raw.response_json #>> '{shift,mileageKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json #>> '{shift,mileageKm}')::numeric
            else null
        end,
        2
    ) as "Hub mileage km",
    round(
        coalesce(
            stat.actual_km,
            case
                when nullif(raw.response_json #>> '{shift,mileageKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (raw.response_json #>> '{shift,mileageKm}')::numeric
                else null
            end
        ),
        2
    ) as "Tényleges km",
    stat.google_route_km as "Google Routes km",
    (
        select coalesce(nullif(next_shift.shift_name, ''), to_char(next_shift.shift_start, 'HH24:MI'))
        from public.courier_shift_overview next_shift
        where next_shift.courier_id = raw.courier_id
            and next_shift.warehouse_id = raw.warehouse_id
            and next_shift.dsp_id = raw.dsp_id
            and next_shift.work_date = coalesce(
                nullif(raw.response_json ->> 'deliveryDate', '')::date,
                nullif(raw.response_json #>> '{shift,deliveryDate}', '')::date,
                (nullif(raw.response_json #>> '{shift,plannedStartAt}', '')::timestamptz at time zone 'Europe/Budapest')::date
            )
            and next_shift.shift_start > (
                nullif(raw.response_json #>> '{shift,plannedStartAt}', '')::timestamptz
                at time zone 'Europe/Budapest'
            )::time
        order by next_shift.shift_start
        limit 1
    ) as "Következő műszakja aznap",
    case
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%city%' then 'City'
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%express%' then 'Express'
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%region%' then 'Regionális'
        else 'Normál'
    end as "Túra típusa",
    coalesce(fin.tip_huf, 0) as "Borravaló",
    case when fin.tip_huf is not null then 'financial-overview routes' else 'nincs adat' end as "Borravaló forrás",
    raw.request_url as "Forrás URL",
    raw.updated_at as "Raw frissítve"
from public.courier_route_performance_detail_raw raw
left join route_logs logs
    on logs.courier_id = raw.courier_id
    and logs.route_id = raw.route_id
    and logs.year = raw.year
    and logs.month = raw.month
    and logs.dsp_id = raw.dsp_id
    and logs.warehouse_id = raw.warehouse_id
left join stop_totals stops
    on stops.courier_id = raw.courier_id
    and stops.route_id = raw.route_id
    and stops.year = raw.year
    and stops.month = raw.month
    and stops.dsp_id = raw.dsp_id
    and stops.warehouse_id = raw.warehouse_id
left join financial_routes fin
    on fin.courier_id = raw.courier_id
    and fin.warehouse_id = raw.warehouse_id
    and fin.route_id = raw.route_id
left join public.courier_hub_route_statistics stat
    on stat.courier_id = raw.courier_id
    and stat.route_id = raw.route_id
    and stat.warehouse_id = raw.warehouse_id
    and stat.dsp_id = raw.dsp_id
left join public.courier_master master
    on master.courier_id = raw.courier_id
where raw.status_code = 200;

grant select on public.courier_hub_route_raw_display to service_role;

drop view if exists public.courier_hub_route_raw_display;

create or replace view public.courier_hub_route_raw_display as
with raw_base as (
    select
        raw.*,
        coalesce(
            nullif(raw.response_json ->> 'deliveryDate', '')::date,
            nullif(raw.response_json #>> '{shift,deliveryDate}', '')::date,
            (nullif(raw.response_json #>> '{shift,plannedStartAt}', '')::timestamptz at time zone 'Europe/Budapest')::date
        ) as work_date,
        case
            when nullif(raw.response_json #>> '{shift,plannedStartAt}', '') is not null
                then (raw.response_json #>> '{shift,plannedStartAt}')::timestamptz
            else null
        end as planned_start_at
    from public.courier_route_performance_detail_raw raw
    where raw.status_code = 200
)
select
    raw.work_date as "Dátum",
    case raw.warehouse_id when 1 then 'BUD1' when 2 then 'BUD2' else 'WH' || raw.warehouse_id::text end as "Raktár",
    raw.courier_id as "Futár ID",
    coalesce(
        nullif(raw.response_json ->> 'courierName', ''),
        nullif(raw.response_json ->> 'name', ''),
        nullif(raw.response_json #>> '{shift,courierName}', ''),
        master.courier_name
    ) as "Futár neve",
    raw.route_id as "Route ID",
    coalesce(
        nullif(raw.response_json #>> '{shift,shiftName}', ''),
        to_char(raw.planned_start_at at time zone 'Europe/Budapest', 'HH24:MI')
    ) as "Műszak neve",
    to_char(shift_available.occurred_at at time zone 'Europe/Budapest', 'HH24:MI') as "Sorbaállt",
    to_char(route_assigned.occurred_at at time zone 'Europe/Budapest', 'HH24:MI') as "Túrát kapott",
    round(extract(epoch from (route_assigned.occurred_at - shift_available.occurred_at)) / 60)::integer as "Várakozás túrakiosztásig perc",
    round(extract(epoch from (departed.occurred_at - route_assigned.occurred_at)) / 60)::integer as "Bepakolási idő perc",
    coalesce(stops.late_stop_count, 0) as "Késés a túrán db",
    round(extract(epoch from (
        nullif(raw.response_json #>> '{shift,plannedReturnAt}', '')::timestamptz
        - nullif(raw.response_json #>> '{shift,plannedDepartureAt}', '')::timestamptz
    )) / 60)::integer as "Tervezett hossz perc",
    round(coalesce(
        case
            when nullif(raw.response_json #>> '{shift,plannedKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json #>> '{shift,plannedKm}')::numeric
            else null
        end,
        case
            when nullif(raw.response_json ->> 'plannedKm', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json ->> 'plannedKm')::numeric
            else null
        end
    ), 2) as "Tervezett km",
    round(extract(epoch from (warehouse_arrived.occurred_at - departed.occurred_at)) / 60)::integer as "Tényleges túraidő perc",
    to_char(warehouse_arrived.occurred_at at time zone 'Europe/Budapest', 'HH24:MI') as "Tényleges visszaérkezés",
    round(
        coalesce(
            stat.actual_km,
            case
                when nullif(raw.response_json #>> '{shift,mileageKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (raw.response_json #>> '{shift,mileageKm}')::numeric
                else null
            end
        ),
        2
    ) as "Tényleges km",
    stat.google_route_km as "Google Routes km",
    round(
        case
            when nullif(raw.response_json #>> '{shift,mileageKm}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                then (raw.response_json #>> '{shift,mileageKm}')::numeric
            else null
        end,
        2
    ) as "Hub mileage km",
    next_shift.next_shift_name as "Következő műszakja aznap",
    case
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%city%' then 'City'
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%express%' then 'Express'
        when lower(coalesce(fin.route_layer, raw.response_json ->> 'routeLayer', raw.response_json ->> 'routeType', '')) like '%region%' then 'Regionális'
        else 'Normál'
    end as "Túra típusa",
    coalesce(fin.tip_huf, 0) as "Borravaló",
    case when fin.tip_huf is not null then 'financial-overview routes' else 'nincs adat' end as "Borravaló forrás",
    raw.request_url as "Forrás URL",
    raw.updated_at as "Raw frissítve"
from raw_base raw
left join lateral (
    select event.occurred_at
    from jsonb_array_elements(coalesce(raw.response_json -> 'routeLogs', raw.response_json -> 'logs', raw.response_json -> 'log', '[]'::jsonb)) log_event(value)
    cross join lateral (
        select
            log_event.value ->> 'type' as event_type,
            case
                when nullif(log_event.value ->> 'occurredAt', '') is not null
                    then (log_event.value ->> 'occurredAt')::timestamptz
                else null
            end as occurred_at
    ) event
    where event.event_type = 'ROUTE_ASSIGNED'
        and event.occurred_at is not null
        and (
            raw.planned_start_at is null
            or event.occurred_at between raw.planned_start_at - interval '3 hours'
                and raw.planned_start_at + interval '4 hours'
        )
    order by
        case
            when raw.planned_start_at is null then 0
            else abs(extract(epoch from (event.occurred_at - raw.planned_start_at)))
        end,
        event.occurred_at
    limit 1
) route_assigned on true
left join lateral (
    select event.occurred_at
    from jsonb_array_elements(coalesce(raw.response_json -> 'routeLogs', raw.response_json -> 'logs', raw.response_json -> 'log', '[]'::jsonb)) log_event(value)
    cross join lateral (
        select
            log_event.value ->> 'type' as event_type,
            case
                when nullif(log_event.value ->> 'occurredAt', '') is not null
                    then (log_event.value ->> 'occurredAt')::timestamptz
                else null
            end as occurred_at
    ) event
    where event.event_type = 'SHIFT_AVAILABLE'
        and event.occurred_at is not null
        and (route_assigned.occurred_at is null or event.occurred_at <= route_assigned.occurred_at)
    order by event.occurred_at desc
    limit 1
) shift_available on true
left join lateral (
    select event.occurred_at
    from jsonb_array_elements(coalesce(raw.response_json -> 'routeLogs', raw.response_json -> 'logs', raw.response_json -> 'log', '[]'::jsonb)) log_event(value)
    cross join lateral (
        select
            log_event.value ->> 'type' as event_type,
            case
                when nullif(log_event.value ->> 'occurredAt', '') is not null
                    then (log_event.value ->> 'occurredAt')::timestamptz
                else null
            end as occurred_at
    ) event
    where event.event_type = 'DEPARTED'
        and event.occurred_at is not null
        and (route_assigned.occurred_at is null or event.occurred_at >= route_assigned.occurred_at)
    order by event.occurred_at
    limit 1
) departed on true
left join lateral (
    select event.occurred_at
    from jsonb_array_elements(coalesce(raw.response_json -> 'routeLogs', raw.response_json -> 'logs', raw.response_json -> 'log', '[]'::jsonb)) log_event(value)
    cross join lateral (
        select
            log_event.value ->> 'type' as event_type,
            case
                when nullif(log_event.value ->> 'occurredAt', '') is not null
                    then (log_event.value ->> 'occurredAt')::timestamptz
                else null
            end as occurred_at
    ) event
    where event.event_type = 'WAREHOUSE_ARRIVED'
        and event.occurred_at is not null
        and (departed.occurred_at is null or event.occurred_at >= departed.occurred_at)
    order by event.occurred_at
    limit 1
) warehouse_arrived on true
left join lateral (
    select
        count(*) filter (
            where case
                when nullif(stop.value ->> 'delayMinutes', '') ~ '^-?[0-9]+$'
                    then (stop.value ->> 'delayMinutes')::integer
                else 0
            end > 0
        ) as late_stop_count
    from jsonb_array_elements(coalesce(raw.response_json -> 'stops', '[]'::jsonb)) stop(value)
) stops on true
left join lateral (
    select
        max(
            case
                when jsonb_typeof(route.value -> 'customerTipsTotal') = 'object'
                    and nullif(route.value #>> '{customerTipsTotal,amount}', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value #>> '{customerTipsTotal,amount}')::numeric
                when nullif(route.value ->> 'customerTipsTotal', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                    then (route.value ->> 'customerTipsTotal')::numeric
                else null
            end
        ) as tip_huf,
        max(route.value ->> 'routeLayer') as route_layer
    from (
        select response_json
        from public.courier_financial_overview_raw_bud1
        where raw.warehouse_id = 1
            and status_code = 200
            and courier_id = raw.courier_id
            and warehouse_id = raw.warehouse_id
            and year = raw.year
            and month = raw.month
        union all
        select response_json
        from public.courier_financial_overview_raw_bud2
        where raw.warehouse_id = 2
            and status_code = 200
            and courier_id = raw.courier_id
            and warehouse_id = raw.warehouse_id
            and year = raw.year
            and month = raw.month
    ) fin_row
    join lateral jsonb_array_elements(coalesce(fin_row.response_json -> 'routes', '[]'::jsonb)) route(value) on true
    where case
        when coalesce(route.value ->> 'routeId', route.value ->> 'id', '') ~ '^[0-9]+$'
            then coalesce(route.value ->> 'routeId', route.value ->> 'id')::bigint
        else null
    end = raw.route_id
) fin on true
left join lateral (
    select coalesce(nullif(next_shift.shift_name, ''), to_char(next_shift.shift_start, 'HH24:MI')) as next_shift_name
    from public.courier_shift_overview next_shift
    where next_shift.courier_id = raw.courier_id
        and next_shift.warehouse_id = raw.warehouse_id
        and next_shift.dsp_id = raw.dsp_id
        and next_shift.work_date = raw.work_date
        and raw.planned_start_at is not null
        and next_shift.shift_start > (raw.planned_start_at at time zone 'Europe/Budapest')::time
    order by next_shift.shift_start
    limit 1
) next_shift on true
left join public.courier_hub_route_statistics stat
    on stat.courier_id = raw.courier_id
    and stat.route_id = raw.route_id
    and stat.warehouse_id = raw.warehouse_id
    and stat.dsp_id = raw.dsp_id
left join public.courier_master master
    on master.courier_id = raw.courier_id;

grant select on public.courier_hub_route_raw_display to service_role;

drop view if exists public.courier_hub_route_raw_display;

create or replace view public.courier_hub_route_raw_display as
select
    "Dátum",
    "Raktár",
    "Futár ID",
    "Futár neve",
    "Route ID",
    "Műszak neve",
    "Sorbaállt",
    "Tényleges műszak kezdés",
    "Túrát kapott",
    "Várakozás túrakiosztásig perc",
    "Bepakolási idő perc",
    "Késés a túrán db",
    "Tervezett hossz perc",
    "Tervezett visszaérkezés",
    "Tervezett km",
    "Tényleges túraidő perc",
    "Tényleges visszaérkezés",
    "Tényleges km",
    "Google Routes km",
    "Hub mileage km",
    "Következő műszakja aznap",
    "Túra típusa",
    "Borravaló",
    "Borravaló forrás",
    "Napi szöveg route szerint",
    now() as "Raw frissítve"
from public.courier_hub_route_statistics_display;

grant select on public.courier_hub_route_raw_display to service_role;

commit;
