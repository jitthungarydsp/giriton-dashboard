begin;

create or replace function settlement.import_excel_courier_basics(
    p_session_id uuid
)
returns table (
    courier_key text,
    courier_id text,
    courier_name text,
    total_routes integer,
    normal_routes integer,
    express_routes integer,
    regional_routes integer,
    tip_huf bigint
)
language sql
stable
security definer
set search_path = settlement, public
as $$
with excel_raw as (
    select
        coalesce(
            nullif(j.normalized_data ->> 'Courier ID', ''),
            nullif(j.normalized_data ->> 'courier_id', ''),
            nullif(j.normalized_data ->> 'Driver ID', ''),
            nullif(j.normalized_data ->> 'driver_id', ''),
            nullif(j.normalized_data ->> 'DSP ID', ''),
            nullif(j.normalized_data ->> 'dsp_id', '')
        ) as raw_courier_id,
        coalesce(
            nullif(j.normalized_data ->> 'Driver', ''),
            nullif(j.normalized_data ->> 'driver_name', ''),
            nullif(j.normalized_data ->> 'Driver Name', ''),
            nullif(j.normalized_data ->> 'courier_name', ''),
            nullif(j.normalized_data ->> 'Futár', ''),
            nullif(j.normalized_data ->> 'futar', '')
        ) as raw_courier_name,
        coalesce(
            nullif(j.route_unique_id, ''),
            nullif(j.normalized_data ->> 'Route Unique ID', ''),
            nullif(j.normalized_data ->> 'route_unique_id', ''),
            nullif(j.normalized_data ->> 'Route ID', ''),
            nullif(j.normalized_data ->> 'route_id', ''),
            nullif(j.normalized_data ->> 'routeId', ''),
            nullif(j.normalized_data ->> 'RouteId', ''),
            j.source_sheet || ':' || j.source_row_no::text
        ) as route_id,
        case
            when lower(coalesce(
                nullif(j.normalized_data ->> 'Route Type', ''),
                nullif(j.normalized_data ->> 'route_type', ''),
                nullif(j.normalized_data ->> 'routeType', ''),
                nullif(j.normalized_data ->> 'Routen type', ''),
                nullif(j.normalized_data ->> 'Routen Type', ''),
                ''
            )) like '%express%' then 'express'
            when lower(coalesce(
                nullif(j.normalized_data ->> 'Route Type', ''),
                nullif(j.normalized_data ->> 'route_type', ''),
                nullif(j.normalized_data ->> 'routeType', ''),
                nullif(j.normalized_data ->> 'Routen type', ''),
                nullif(j.normalized_data ->> 'Routen Type', ''),
                ''
            )) like '%reg%' then 'regional'
            else 'normal'
        end as route_type,
        coalesce(j.courier_tip_huf, 0)::numeric as tip_huf
    from settlement.jit_row j
    where j.session_id = p_session_id
      and coalesce(j.is_route_primary, false) is true
),
excel_routes as (
    select distinct on (courier_key, route_id)
        courier_key,
        name_key,
        courier_id,
        courier_name,
        route_id,
        route_type,
        tip_huf
    from (
        select
            case
                when courier_id is not null then 'id:' || courier_id
                else 'name:' || regexp_replace(lower(coalesce(clean_courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            regexp_replace(lower(coalesce(clean_courier_name, '')), '[^[:alnum:]]+', '', 'g') as name_key,
            courier_id,
            clean_courier_name as courier_name,
            route_id,
            route_type,
            tip_huf
        from (
            select
                nullif(trim(coalesce(raw_courier_id, (regexp_match(coalesce(raw_courier_name, ''), '(^|[^0-9])([0-9]{4})([^0-9]|$)'))[2])), '') as courier_id,
                nullif(trim(regexp_replace(coalesce(raw_courier_name, ''), '(^|[[:space:]])#?[0-9]{4}([[:space:]]|$)', ' ', 'g')), '') as clean_courier_name,
                route_id,
                route_type,
                tip_huf
            from excel_raw
        ) normalized
    ) keyed
    where courier_key <> 'name:'
    order by courier_key, route_id, tip_huf desc
),
excel_resolved as (
    select distinct on (resolved_key, route_id)
        resolved_key as courier_key,
        courier_id,
        courier_name,
        route_id,
        route_type,
        tip_huf
    from (
        select
            coalesce(
                case when name_key <> '' then 'id:' || max(courier_id) over (partition by name_key) end,
                courier_key
            ) as resolved_key,
            *
        from excel_routes
    ) resolved
    order by resolved_key, route_id, tip_huf desc
)
select
    courier_key,
    max(courier_id) as courier_id,
    max(courier_name) as courier_name,
    count(*)::integer as total_routes,
    count(*) filter (where route_type = 'normal')::integer as normal_routes,
    count(*) filter (where route_type = 'express')::integer as express_routes,
    count(*) filter (where route_type = 'regional')::integer as regional_routes,
    round(coalesce(sum(tip_huf), 0))::bigint as tip_huf
from excel_resolved
group by courier_key
order by max(courier_name), max(courier_id);
$$;

create or replace function settlement.hub_courier_basics(
    p_period_start date,
    p_period_end date default null
)
returns table (
    courier_key text,
    courier_id text,
    courier_name text,
    total_routes integer,
    normal_routes integer,
    express_routes integer,
    regional_routes integer,
    tip_huf bigint
)
language sql
stable
security definer
set search_path = settlement, public
as $$
with params as (
    select
        date_trunc('month', p_period_start)::date as period_start,
        coalesce(
            p_period_end,
            (date_trunc('month', p_period_start)::date + interval '1 month - 1 day')::date
        ) as period_end
),
hub_routes as (
    select distinct on (courier_key, route_key)
        courier_key,
        courier_id,
        courier_name,
        route_key,
        route_type,
        tip_huf
    from (
        select
            case
                when h.courier_id is not null then 'id:' || h.courier_id::text
                else 'name:' || regexp_replace(lower(coalesce(h.courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            h.courier_id::text as courier_id,
            h.courier_name,
            concat_ws(':', h.work_date::text, coalesce(h.warehouse_id::text, h.warehouse_code), h.route_id::text, h.dsp_id::text) as route_key,
            case
                when lower(coalesce(h.route_type, h.route_type_label, '')) like '%express%' then 'express'
                when lower(coalesce(h.route_type, h.route_type_label, '')) like '%reg%' then 'regional'
                else 'normal'
            end as route_type,
            coalesce(h.tip_huf, 0)::numeric as tip_huf
        from public.courier_hub_route_statistics h
        join params p on h.work_date between p.period_start and p.period_end
    ) keyed
    where courier_key <> 'name:'
    order by courier_key, route_key, tip_huf desc
)
select
    courier_key,
    max(courier_id) as courier_id,
    max(courier_name) as courier_name,
    count(*)::integer as total_routes,
    count(*) filter (where route_type = 'normal')::integer as normal_routes,
    count(*) filter (where route_type = 'express')::integer as express_routes,
    count(*) filter (where route_type = 'regional')::integer as regional_routes,
    round(coalesce(sum(tip_huf), 0))::bigint as tip_huf
from hub_routes
group by courier_key
order by max(courier_name), max(courier_id);
$$;

create or replace function settlement.import_hub_courier_reconciliation(
    p_session_id uuid,
    p_period_start date,
    p_period_end date default null
)
returns table (
    courier_key text,
    courier_id text,
    courier_name text,
    status text,
    issues text[],
    excel_total integer,
    excel_normal integer,
    excel_express integer,
    excel_regional integer,
    excel_tip_huf bigint,
    hub_total integer,
    hub_normal integer,
    hub_express integer,
    hub_regional integer,
    hub_tip_huf bigint,
    route_delta integer,
    tip_delta bigint
)
language sql
stable
security definer
set search_path = settlement, public
as $$
with params as (
    select
        p_session_id as session_id,
        date_trunc('month', p_period_start)::date as period_start,
        coalesce(
            p_period_end,
            (date_trunc('month', p_period_start)::date + interval '1 month - 1 day')::date
        ) as period_end
),
excel_raw as (
    select
        j.id,
        j.source_sheet,
        j.source_row_no,
        coalesce(
            nullif(j.normalized_data ->> 'Courier ID', ''),
            nullif(j.normalized_data ->> 'courier_id', ''),
            nullif(j.normalized_data ->> 'Driver ID', ''),
            nullif(j.normalized_data ->> 'driver_id', ''),
            nullif(j.normalized_data ->> 'DSP ID', ''),
            nullif(j.normalized_data ->> 'dsp_id', '')
        ) as raw_courier_id,
        coalesce(
            nullif(j.normalized_data ->> 'Driver', ''),
            nullif(j.normalized_data ->> 'driver_name', ''),
            nullif(j.normalized_data ->> 'Driver Name', ''),
            nullif(j.normalized_data ->> 'courier_name', ''),
            nullif(j.normalized_data ->> 'Futár', ''),
            nullif(j.normalized_data ->> 'futar', '')
        ) as raw_courier_name,
        coalesce(
            nullif(j.route_unique_id, ''),
            nullif(j.normalized_data ->> 'Route Unique ID', ''),
            nullif(j.normalized_data ->> 'route_unique_id', ''),
            nullif(j.normalized_data ->> 'Route ID', ''),
            nullif(j.normalized_data ->> 'route_id', ''),
            nullif(j.normalized_data ->> 'routeId', ''),
            nullif(j.normalized_data ->> 'RouteId', ''),
            j.source_sheet || ':' || j.source_row_no::text
        ) as route_id,
        case
            when lower(coalesce(
                nullif(j.normalized_data ->> 'Route Type', ''),
                nullif(j.normalized_data ->> 'route_type', ''),
                nullif(j.normalized_data ->> 'routeType', ''),
                nullif(j.normalized_data ->> 'Routen type', ''),
                nullif(j.normalized_data ->> 'Routen Type', ''),
                ''
            )) like '%express%' then 'express'
            when lower(coalesce(
                nullif(j.normalized_data ->> 'Route Type', ''),
                nullif(j.normalized_data ->> 'route_type', ''),
                nullif(j.normalized_data ->> 'routeType', ''),
                nullif(j.normalized_data ->> 'Routen type', ''),
                nullif(j.normalized_data ->> 'Routen Type', ''),
                ''
            )) like '%reg%' then 'regional'
            else 'normal'
        end as route_type,
        coalesce(j.courier_tip_huf, 0)::numeric as tip_huf
    from settlement.jit_row j
    join params p on p.session_id = j.session_id
    where coalesce(j.is_route_primary, false) is true
),
excel_routes as (
    select distinct on (courier_key, route_id)
        courier_key,
        name_key,
        courier_id,
        courier_name,
        route_id,
        route_type,
        tip_huf
    from (
        select
            case
                when courier_id is not null then 'id:' || courier_id
                else 'name:' || regexp_replace(lower(coalesce(clean_courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            regexp_replace(lower(coalesce(clean_courier_name, '')), '[^[:alnum:]]+', '', 'g') as name_key,
            courier_id,
            clean_courier_name as courier_name,
            route_id,
            route_type,
            tip_huf
        from (
            select
                nullif(trim(coalesce(raw_courier_id, (regexp_match(coalesce(raw_courier_name, ''), '(^|[^0-9])([0-9]{4})([^0-9]|$)'))[2])), '') as courier_id,
                nullif(trim(regexp_replace(coalesce(raw_courier_name, ''), '(^|[[:space:]])#?[0-9]{4}([[:space:]]|$)', ' ', 'g')), '') as clean_courier_name,
                route_id,
                route_type,
                tip_huf
            from excel_raw
        ) normalized
    ) keyed
    where courier_key <> 'name:'
    order by courier_key, route_id, tip_huf desc
),
excel_resolved as (
    select distinct on (resolved_key, route_id)
        resolved_key as courier_key,
        courier_id,
        courier_name,
        route_id,
        route_type,
        tip_huf
    from (
        select
            coalesce(
                case when name_key <> '' then 'id:' || max(courier_id) over (partition by name_key) end,
                courier_key
            ) as resolved_key,
            *
        from excel_routes
    ) resolved
    order by resolved_key, route_id, tip_huf desc
),
excel_grouped as (
    select
        courier_key,
        regexp_replace(
            regexp_replace(lower(coalesce(max(courier_name), '')), '(^|[[:space:]])#?[0-9]{4}([[:space:]]|$)', ' ', 'g'),
            '[^[:alnum:]]+',
            '',
            'g'
        ) as name_key,
        max(courier_id) as courier_id,
        max(courier_name) as courier_name,
        count(*)::integer as total,
        count(*) filter (where route_type = 'normal')::integer as normal,
        count(*) filter (where route_type = 'express')::integer as express,
        count(*) filter (where route_type = 'regional')::integer as regional,
        round(coalesce(sum(tip_huf), 0))::bigint as tip_huf
    from excel_resolved
    group by courier_key
),
hub_routes as (
    select distinct on (courier_key, route_key)
        courier_key,
        courier_id,
        courier_name,
        route_key,
        route_type,
        tip_huf
    from (
        select
            case
                when h.courier_id is not null then 'id:' || h.courier_id::text
                else 'name:' || regexp_replace(lower(coalesce(h.courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            h.courier_id::text as courier_id,
            h.courier_name,
            concat_ws(':', h.work_date::text, coalesce(h.warehouse_id::text, h.warehouse_code), h.route_id::text, h.dsp_id::text) as route_key,
            case
                when lower(coalesce(h.route_type, h.route_type_label, '')) like '%express%' then 'express'
                when lower(coalesce(h.route_type, h.route_type_label, '')) like '%reg%' then 'regional'
                else 'normal'
            end as route_type,
            coalesce(h.tip_huf, 0)::numeric as tip_huf
        from public.courier_hub_route_statistics h
        join params p on h.work_date between p.period_start and p.period_end
    ) keyed
    where courier_key <> 'name:'
    order by courier_key, route_key, tip_huf desc
),
hub_grouped as (
    select
        courier_key,
        regexp_replace(
            regexp_replace(lower(coalesce(max(courier_name), '')), '(^|[[:space:]])#?[0-9]{4}([[:space:]]|$)', ' ', 'g'),
            '[^[:alnum:]]+',
            '',
            'g'
        ) as name_key,
        max(courier_id) as courier_id,
        max(courier_name) as courier_name,
        count(*)::integer as total,
        count(*) filter (where route_type = 'normal')::integer as normal,
        count(*) filter (where route_type = 'express')::integer as express,
        count(*) filter (where route_type = 'regional')::integer as regional,
        round(coalesce(sum(tip_huf), 0))::bigint as tip_huf
    from hub_routes
    group by courier_key
),
joined as (
    select
        coalesce(e.courier_key, h.courier_key) as courier_key,
        coalesce(e.courier_id, h.courier_id) as courier_id,
        coalesce(e.courier_name, h.courier_name) as courier_name,
        coalesce(e.total, 0) as excel_total,
        coalesce(e.normal, 0) as excel_normal,
        coalesce(e.express, 0) as excel_express,
        coalesce(e.regional, 0) as excel_regional,
        coalesce(e.tip_huf, 0) as excel_tip_huf,
        coalesce(h.total, 0) as hub_total,
        coalesce(h.normal, 0) as hub_normal,
        coalesce(h.express, 0) as hub_express,
        coalesce(h.regional, 0) as hub_regional,
        coalesce(h.tip_huf, 0) as hub_tip_huf,
        e.courier_key is null as missing_excel,
        h.courier_key is null as missing_hub
    from excel_grouped e
    full join hub_grouped h
        on h.courier_key = e.courier_key
        or (
            e.name_key <> ''
            and h.name_key <> ''
            and h.name_key = e.name_key
        )
),
compared as (
    select
        *,
        array_remove(array[
            case when missing_excel then 'Nincs Excel/JIT sor' end,
            case when missing_hub then 'Nincs Hub DB sor' end,
            case when excel_total <> hub_total then 'Túraszám eltérés' end,
            case
                when excel_normal <> hub_normal
                  or excel_express <> hub_express
                  or excel_regional <> hub_regional
                then 'Túratípus eltérés'
            end,
            case when excel_tip_huf <> hub_tip_huf then 'Borravaló eltérés' end
        ], null) as issue_list
    from joined
)
select
    courier_key,
    courier_id,
    coalesce(courier_name, 'Ismeretlen futár') as courier_name,
    case when cardinality(issue_list) = 0 then 'ok' else 'error' end as status,
    issue_list as issues,
    excel_total,
    excel_normal,
    excel_express,
    excel_regional,
    excel_tip_huf,
    hub_total,
    hub_normal,
    hub_express,
    hub_regional,
    hub_tip_huf,
    excel_total - hub_total as route_delta,
    excel_tip_huf - hub_tip_huf as tip_delta
from compared
order by
    case when cardinality(issue_list) = 0 then 1 else 0 end,
    coalesce(courier_name, ''),
    courier_id;
$$;

grant execute on function settlement.import_excel_courier_basics(uuid) to service_role;
grant execute on function settlement.hub_courier_basics(date, date) to service_role;
grant execute on function settlement.import_hub_courier_reconciliation(uuid, date, date) to service_role;

commit;
