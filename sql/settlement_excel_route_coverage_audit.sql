create table if not exists settlement.excel_route_coverage_audit (
    id bigserial primary key,
    session_id text not null,
    period_start date not null,
    period_end date not null,
    courier_id text,
    courier_name text,
    courier_key text not null,
    excel_route_count integer not null default 0,
    dsp_route_count integer not null default 0,
    matched_route_count integer not null default 0,
    missing_route_count integer not null default 0,
    extra_excel_route_count integer not null default 0,
    excel_route_ids text[] not null default '{}',
    dsp_route_ids text[] not null default '{}',
    missing_route_ids text[] not null default '{}',
    extra_excel_route_ids text[] not null default '{}',
    coverage_status text not null default 'unknown',
    is_ok boolean not null default false,
    source text not null default 'jit_row_vs_mart_dsp_route_stories',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint excel_route_coverage_audit_session_courier_key
        unique (session_id, courier_key)
);

create index if not exists excel_route_coverage_audit_session_idx
    on settlement.excel_route_coverage_audit (session_id);

create index if not exists excel_route_coverage_audit_courier_idx
    on settlement.excel_route_coverage_audit (courier_id, period_start);

create or replace function settlement.refresh_excel_route_coverage_audit(
    p_session_id text,
    p_period_start date,
    p_period_end date
)
returns integer
language plpgsql
as $$
declare
    affected_rows integer := 0;
begin
    delete from settlement.excel_route_coverage_audit
    where session_id = p_session_id;

    with excel_import_route_candidates as (
        select
            ei.session_id::text as session_id,
            count(distinct route_match.route_id) as matched_route_candidates,
            max(ei.created_at) as last_imported_at
        from settlement.excel_import ei
        cross join lateral jsonb_each_text(ei.data) as raw_cell(key, value)
        cross join lateral (
            select r.match_value[1] as route_id
            from regexp_matches(raw_cell.value, '([0-9]{5,12})', 'g') as r(match_value)
        ) route_match
        join public.mart_dsp_route_stories m
            on m.route_id::text = route_match.route_id
            and m.work_date between p_period_start and p_period_end
        group by ei.session_id::text
    ),
    effective_excel_import_session as (
        select session_id
        from excel_import_route_candidates
        order by
            case
                when session_id = p_session_id and matched_route_candidates > 0 then 0
                when matched_route_candidates > 0 then 1
                else 2
            end,
            matched_route_candidates desc,
            last_imported_at desc
        limit 1
    ),
    jit_excel_raw as (
        select
            nullif(trim(coalesce(
                j.normalized_data ->> 'courier_id',
                j.normalized_data ->> 'Courier ID',
                j.normalized_data ->> 'driver_id',
                j.normalized_data ->> 'Driver ID',
                j.normalized_data ->> 'usernumber',
                j.normalized_data ->> 'Usernumber'
            )), '') as courier_id,
            nullif(trim(coalesce(
                j.normalized_data ->> 'courier_name',
                j.normalized_data ->> 'driver_name',
                j.normalized_data ->> 'Driver',
                j.normalized_data ->> 'Futár',
                j.normalized_data ->> 'futar',
                j.source_sheet
            )), '') as courier_name,
            nullif(trim(coalesce(
                j.route_unique_id,
                j.normalized_data ->> 'route_unique_id',
                j.normalized_data ->> 'route_id',
                j.normalized_data ->> 'Route Unique ID',
                j.normalized_data ->> 'routeId',
                j.normalized_data ->> 'Route ID',
                j.normalized_data ->> 'RouteId',
                j.normalized_data ->> 'route',
                j.normalized_data ->> 'Route',
                raw_route.route_id,
                dynamic_route.route_id
            )), '') as route_id
        from settlement.jit_row j
        left join settlement.excel_import ei
            on ei.session_id::text = j.session_id::text
            and ei.sheet_name = j.source_sheet
            and ei.source_row_no = j.source_row_no
        left join lateral (
            select r.match_value[1] as route_id
            from jsonb_each_text(ei.data) as raw_cell(key, value)
            cross join lateral regexp_matches(raw_cell.value, '([0-9]{5,12})', 'g') as r(match_value)
            join public.mart_dsp_route_stories m
                on m.route_id::text = r.match_value[1]
            order by
                case when m.work_date between p_period_start and p_period_end then 0 else 1 end,
                m.work_date desc
            limit 1
        ) raw_route on true
        left join lateral (
            select value as route_id
            from jsonb_each_text(j.normalized_data)
            where regexp_replace(lower(key), '[^a-z0-9]+', '', 'g') in (
                'routeid',
                'routeuniqueid',
                'routeazonosito'
            )
            or (
                regexp_replace(lower(key), '[^a-z0-9]+', '', 'g') like '%route%'
                and regexp_replace(lower(key), '[^a-z0-9]+', '', 'g') like '%id%'
            )
            limit 1
        ) dynamic_route on true
        where j.session_id::text = p_session_id
    ),
    raw_excel_route_values as (
        select distinct
            m.courier_id::text as courier_id,
            m.courier_name as courier_name,
            route_match.route_id as route_id
        from settlement.excel_import ei
        cross join lateral jsonb_each_text(ei.data) as raw_cell(key, value)
        cross join lateral (
            select r.match_value[1] as route_id
            from regexp_matches(raw_cell.value, '([0-9]{5,12})', 'g') as r(match_value)
        ) route_match
        join public.mart_dsp_route_stories m
            on m.route_id::text = route_match.route_id
            and m.work_date between p_period_start and p_period_end
        where ei.session_id::text in (
            select session_id
            from effective_excel_import_session
        )
    ),
    excel_raw as (
        select courier_id, courier_name, route_id
        from jit_excel_raw
        where route_id is not null
        union all
        select courier_id, courier_name, route_id
        from raw_excel_route_values
    ),
    excel_grouped as (
        select
            case
                when courier_id is not null then 'id:' || courier_id
                else 'name:' || regexp_replace(lower(coalesce(courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            max(courier_id) as courier_id,
            max(courier_name) as courier_name,
            array_agg(distinct route_id order by route_id) filter (where route_id is not null) as excel_route_ids
        from excel_raw
        where coalesce(courier_id, courier_name) is not null
        group by 1
    ),
    dsp_grouped as (
        select
            case
                when m.courier_id is not null then 'id:' || m.courier_id::text
                else 'name:' || regexp_replace(lower(coalesce(m.courier_name, '')), '[^[:alnum:]]+', '', 'g')
            end as courier_key,
            max(m.courier_id::text) as courier_id,
            max(m.courier_name) as courier_name,
            array_agg(distinct m.route_id::text order by m.route_id::text) filter (where m.route_id is not null) as dsp_route_ids
        from public.mart_dsp_route_stories m
        where m.work_date between p_period_start and p_period_end
        group by 1
    ),
    joined as (
        select
            coalesce(e.courier_key, d.courier_key) as courier_key,
            coalesce(e.courier_id, d.courier_id) as courier_id,
            coalesce(e.courier_name, d.courier_name) as courier_name,
            coalesce(e.excel_route_ids, '{}'::text[]) as excel_route_ids,
            coalesce(d.dsp_route_ids, '{}'::text[]) as dsp_route_ids
        from excel_grouped e
        full join dsp_grouped d on d.courier_key = e.courier_key
    ),
    compared as (
        select
            *,
            array(
                select route_id
                from unnest(dsp_route_ids) route_id
                except
                select route_id
                from unnest(excel_route_ids) route_id
                order by 1
            ) as missing_route_ids,
            array(
                select route_id
                from unnest(excel_route_ids) route_id
                except
                select route_id
                from unnest(dsp_route_ids) route_id
                order by 1
            ) as extra_excel_route_ids
        from joined
    )
    insert into settlement.excel_route_coverage_audit (
        session_id,
        period_start,
        period_end,
        courier_id,
        courier_name,
        courier_key,
        excel_route_count,
        dsp_route_count,
        matched_route_count,
        missing_route_count,
        extra_excel_route_count,
        excel_route_ids,
        dsp_route_ids,
        missing_route_ids,
        extra_excel_route_ids,
        coverage_status,
        is_ok,
        updated_at
    )
    select
        p_session_id,
        p_period_start,
        p_period_end,
        courier_id,
        courier_name,
        courier_key,
        cardinality(excel_route_ids),
        cardinality(dsp_route_ids),
        greatest(cardinality(dsp_route_ids) - cardinality(missing_route_ids), 0),
        cardinality(missing_route_ids),
        cardinality(extra_excel_route_ids),
        excel_route_ids,
        dsp_route_ids,
        missing_route_ids,
        extra_excel_route_ids,
        case
            when cardinality(dsp_route_ids) = 0 and cardinality(excel_route_ids) = 0 then 'unknown'
            when cardinality(dsp_route_ids) = 0 then 'no_dsp'
            when cardinality(excel_route_ids) = 0 then 'no_excel'
            when cardinality(missing_route_ids) = 0 then 'ok'
            else 'missing'
        end,
        cardinality(dsp_route_ids) > 0 and cardinality(missing_route_ids) = 0,
        now()
    from compared;

    get diagnostics affected_rows = row_count;
    return affected_rows;
end;
$$;

grant select, insert, update, delete on settlement.excel_route_coverage_audit to service_role;
grant usage, select on sequence settlement.excel_route_coverage_audit_id_seq to service_role;
grant execute on function settlement.refresh_excel_route_coverage_audit(text, date, date) to service_role;

notify pgrst, 'reload schema';
