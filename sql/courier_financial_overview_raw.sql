begin;

create table if not exists public.courier_financial_overview_raw (
    courier_id integer not null,
    courier_name text,
    year integer not null,
    month integer not null check (month between 1 and 12),
    route_layer text not null default 'COMBINED',
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, year, month, route_layer, dsp_id, warehouse_id)
);

create table if not exists public.courier_financial_overview_month_raw (
    year integer not null,
    month integer not null check (month between 1 and 12),
    route_layer text not null default 'COMBINED',
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (year, month, route_layer, dsp_id, warehouse_id)
);

create index if not exists courier_financial_overview_raw_period_idx
    on public.courier_financial_overview_raw (year, month, warehouse_id);

create index if not exists courier_financial_overview_raw_json_idx
    on public.courier_financial_overview_raw using gin (response_json);

create index if not exists courier_financial_overview_month_raw_period_idx
    on public.courier_financial_overview_month_raw (year, month, warehouse_id);

create index if not exists courier_financial_overview_month_raw_json_idx
    on public.courier_financial_overview_month_raw using gin (response_json);

grant select, insert, update, delete on public.courier_financial_overview_raw to service_role;
grant select, insert, update, delete on public.courier_financial_overview_month_raw to service_role;

create or replace function settlement.import_api_financial_overview_to_jit(
    p_year integer,
    p_month integer,
    p_warehouse_id integer default null
)
returns uuid
language plpgsql
security definer
set search_path = settlement, public
as $$
declare
    v_session_id uuid;
    v_processing_run_id uuid;
    v_imported_rows integer := 0;
begin
    if p_month < 1 or p_month > 12 then
        raise exception 'Invalid month: %', p_month;
    end if;

    v_session_id := (
        substr(md5('api-financial-overview:' || p_year || ':' || p_month || ':' || coalesce(p_warehouse_id::text, 'all')), 1, 8)
        || '-' || substr(md5('api-financial-overview:' || p_year || ':' || p_month || ':' || coalesce(p_warehouse_id::text, 'all')), 9, 4)
        || '-' || substr(md5('api-financial-overview:' || p_year || ':' || p_month || ':' || coalesce(p_warehouse_id::text, 'all')), 13, 4)
        || '-' || substr(md5('api-financial-overview:' || p_year || ':' || p_month || ':' || coalesce(p_warehouse_id::text, 'all')), 17, 4)
        || '-' || substr(md5('api-financial-overview:' || p_year || ':' || p_month || ':' || coalesce(p_warehouse_id::text, 'all')), 21, 12)
    )::uuid;

    insert into settlement.processing_run (
        session_id, status, started_at, finished_at, total_sheets, recognized_sheets,
        unknown_sheets, total_rows, accepted_rows, rejected_rows, critical_errors, summary
    )
    values (
        v_session_id, 'running', now(), null, 1, 1,
        0, 0, 0, 0, 0,
        jsonb_build_object(
            'source', 'courier_hub_api',
            'year', p_year,
            'month', p_month,
            'warehouse_id', p_warehouse_id
        )
    )
    returning id into v_processing_run_id;

    delete from settlement.jit_row
    where session_id = v_session_id
      and source_sheet like 'API financial overview%';

    with source_routes as (
        select
            raw.warehouse_id,
            raw.courier_id,
            coalesce(nullif(raw.courier_name, ''), raw.response_json ->> 'courierName', 'Ismeretlen futár') as courier_name,
            route.value as route_json,
            row_number() over (
                order by raw.warehouse_id, raw.courier_id, route.ordinality
            ) as source_row_no
        from public.courier_financial_overview_raw raw
        cross join lateral jsonb_array_elements(coalesce(raw.response_json -> 'routes', '[]'::jsonb)) with ordinality as route(value, ordinality)
        where raw.year = p_year
          and raw.month = p_month
          and raw.status_code = 200
          and (p_warehouse_id is null or raw.warehouse_id = p_warehouse_id)
    ), inserted as (
        insert into settlement.jit_row (
            processing_run_id,
            session_id,
            source_sheet,
            source_row_no,
            normalized_data
        )
        select
            v_processing_run_id,
            v_session_id,
            'API financial overview WH' || warehouse_id,
            source_row_no,
            jsonb_build_object(
                'source', 'courier_hub_api',
                'Driver', courier_name,
                'driver_name', courier_name,
                'Courier ID', courier_id::text,
                'courier_id', courier_id::text,
                'Route Unique ID', route_json ->> 'routeId',
                'route_unique_id', route_json ->> 'routeId',
                'Date', route_json ->> 'deliveryDate',
                'work_date', route_json ->> 'deliveryDate',
                'Route Type', case
                    when upper(coalesce(route_json ->> 'routeLayer', 'NORMAL')) = 'EXPRESS' then 'Express'
                    when upper(coalesce(route_json ->> 'routeLayer', 'NORMAL')) = 'REGIONAL' then 'Regional'
                    else 'Normal'
                end,
                'route_type', lower(coalesce(route_json ->> 'routeLayer', 'NORMAL')),
                'Orders', coalesce(route_json ->> 'orderCount', '0'),
                'orders', coalesce(route_json ->> 'orderCount', '0'),
                'Tip', coalesce(route_json #>> '{customerTipsTotal,amount}', '0'),
                'tip_huf', coalesce(route_json #>> '{customerTipsTotal,amount}', '0'),
                'Location', case when warehouse_id = 2 then 'BUD2' else 'BUD1' end,
                'Warehouse', case when warehouse_id = 2 then 'BUD2' else 'BUD1' end,
                'api_total_amount_huf', coalesce(route_json #>> '{totalAmount,amount}', '0'),
                'api_rule_breakdown', coalesce(route_json -> 'ruleBreakdown', '[]'::jsonb)
            )
        from source_routes
        returning 1
    )
    select count(*) into v_imported_rows from inserted;

    update settlement.processing_run
    set
        status = 'completed',
        finished_at = now(),
        total_rows = v_imported_rows,
        accepted_rows = v_imported_rows,
        summary = summary || jsonb_build_object('imported_rows', v_imported_rows)
    where id = v_processing_run_id;

    perform settlement.recalculate_jitt_base_rates(v_session_id);
    perform settlement.refresh_courier_settlement_summary(v_session_id);

    return v_session_id;
exception
    when others then
        if v_processing_run_id is not null then
            update settlement.processing_run
            set
                status = 'failed',
                finished_at = now(),
                critical_errors = 1,
                summary = summary || jsonb_build_object('error', sqlerrm)
            where id = v_processing_run_id;
        end if;
        raise;
end;
$$;

grant execute on function settlement.import_api_financial_overview_to_jit(integer, integer, integer) to service_role;

notify pgrst, 'reload schema';

commit;
