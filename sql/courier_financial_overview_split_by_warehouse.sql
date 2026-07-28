begin;

create table if not exists public.courier_financial_overview_raw_bud1 (
    like public.courier_financial_overview_raw including defaults including identity including constraints including indexes
);

create table if not exists public.courier_financial_overview_raw_bud2 (
    like public.courier_financial_overview_raw including defaults including identity including constraints including indexes
);

create table if not exists public.courier_financial_overview_month_raw_bud1 (
    like public.courier_financial_overview_month_raw including defaults including identity including constraints including indexes
);

create table if not exists public.courier_financial_overview_month_raw_bud2 (
    like public.courier_financial_overview_month_raw including defaults including identity including constraints including indexes
);

do $$
declare
    target_table text;
    id_data_type text;
    id_default text;
begin
    foreach target_table in array array[
        'courier_financial_overview_raw_bud1',
        'courier_financial_overview_raw_bud2',
        'courier_financial_overview_month_raw_bud1',
        'courier_financial_overview_month_raw_bud2'
    ]
    loop
        select data_type, column_default
        into id_data_type, id_default
        from information_schema.columns
        where table_schema = 'public'
          and table_name = target_table
          and column_name = 'id';

        if id_data_type is null or id_default is not null then
            continue;
        end if;

        if id_data_type = 'uuid' then
            execute format(
                'alter table public.%I alter column id set default gen_random_uuid()',
                target_table
            );
        elsif id_data_type in ('integer', 'bigint', 'smallint') then
            execute format(
                'create sequence if not exists public.%I',
                target_table || '_id_seq'
            );
            execute format(
                'select setval(%L::regclass, coalesce((select max(id) from public.%I), 0) + 1, false)',
                'public.' || target_table || '_id_seq',
                target_table
            );
            execute format(
                'alter table public.%I alter column id set default nextval(%L::regclass)',
                target_table,
                'public.' || target_table || '_id_seq'
            );
        end if;
    end loop;
end $$;

insert into public.courier_financial_overview_raw_bud1
select *
from public.courier_financial_overview_raw
where warehouse_id = 1
  and jsonb_array_length(coalesce(response_json -> 'routes', '[]'::jsonb)) > 0
on conflict (courier_id, year, month, route_layer, dsp_id, warehouse_id)
do update set
    courier_name = excluded.courier_name,
    request_url = excluded.request_url,
    status_code = excluded.status_code,
    response_json = excluded.response_json,
    fetched_at = excluded.fetched_at,
    updated_at = now();

insert into public.courier_financial_overview_raw_bud2
select *
from public.courier_financial_overview_raw
where warehouse_id = 2
  and jsonb_array_length(coalesce(response_json -> 'routes', '[]'::jsonb)) > 0
on conflict (courier_id, year, month, route_layer, dsp_id, warehouse_id)
do update set
    courier_name = excluded.courier_name,
    request_url = excluded.request_url,
    status_code = excluded.status_code,
    response_json = excluded.response_json,
    fetched_at = excluded.fetched_at,
    updated_at = now();

insert into public.courier_financial_overview_month_raw_bud1
select *
from public.courier_financial_overview_month_raw
where warehouse_id = 1
on conflict (year, month, route_layer, dsp_id, warehouse_id)
do update set
    request_url = excluded.request_url,
    status_code = excluded.status_code,
    response_json = excluded.response_json,
    fetched_at = excluded.fetched_at,
    updated_at = now();

insert into public.courier_financial_overview_month_raw_bud2
select *
from public.courier_financial_overview_month_raw
where warehouse_id = 2
on conflict (year, month, route_layer, dsp_id, warehouse_id)
do update set
    request_url = excluded.request_url,
    status_code = excluded.status_code,
    response_json = excluded.response_json,
    fetched_at = excluded.fetched_at,
    updated_at = now();

grant select, insert, update, delete on public.courier_financial_overview_raw_bud1 to service_role;
grant select, insert, update, delete on public.courier_financial_overview_raw_bud2 to service_role;
grant select, insert, update, delete on public.courier_financial_overview_month_raw_bud1 to service_role;
grant select, insert, update, delete on public.courier_financial_overview_month_raw_bud2 to service_role;

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

    with raw_union as (
        select *
        from public.courier_financial_overview_raw_bud1
        where p_warehouse_id is null or p_warehouse_id = 1
        union all
        select *
        from public.courier_financial_overview_raw_bud2
        where p_warehouse_id is null or p_warehouse_id = 2
    ), source_routes as (
        select
            raw.warehouse_id,
            raw.courier_id,
            coalesce(nullif(raw.courier_name, ''), raw.response_json ->> 'courierName', 'Ismeretlen futar') as courier_name,
            route.value as route_json,
            row_number() over (
                order by raw.warehouse_id, raw.courier_id, route.ordinality
            ) as source_row_no
        from raw_union raw
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
    with api_delay_source as (
        select
            j.id,
            j.route_date,
            coalesce(j.calculated_day_type, 'normal') as day_type,
            lower(coalesce(j.normalized_data ->> 'route_type', 'normal')) as route_type,
            coalesce(nullif(j.normalized_data ->> 'Warehouse', ''), nullif(j.normalized_data ->> 'Location', '')) as warehouse_code,
            coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders,
            max(nullif(item.value ->> 'matchedTier', '')) as matched_tier,
            coalesce(sum(
                case
                    when jsonb_typeof(item.value -> 'amount') = 'object'
                        then coalesce(nullif(item.value #>> '{amount,amount}', '')::numeric, 0)
                    when jsonb_typeof(item.value -> 'amount') in ('number', 'string')
                        then coalesce(nullif(item.value ->> 'amount', '')::numeric, 0)
                    else 0
                end
            ), 0) as amount_huf
        from settlement.jit_row j
        left join lateral jsonb_array_elements(coalesce(j.normalized_data -> 'api_rule_breakdown', '[]'::jsonb)) item(value) on true
        where j.session_id = v_session_id
          and j.source_sheet like 'API financial overview%'
          and j.is_route_primary
          and (
              item.value is null
              or lower(coalesce(item.value ->> 'feeType', '')) in (
                  'delay_performance',
                  'dataport_delay_performance'
                  )
          )
        group by
            j.id,
            j.route_date,
            coalesce(j.calculated_day_type, 'normal'),
            lower(coalesce(j.normalized_data ->> 'route_type', 'normal')),
            coalesce(nullif(j.normalized_data ->> 'Warehouse', ''), nullif(j.normalized_data ->> 'Location', '')),
            coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0)
    ), api_delay as (
        select
            source.id,
            coalesce(rule_amount.amount_huf, 0) as amount_huf
        from api_delay_source source
        left join lateral (
            select case d.calculation_unit
                when 'per_route' then d.courier_amount_huf
                when 'per_order' then d.courier_amount_huf * source.orders
                when 'fixed' then d.courier_amount_huf
                else 0
            end as amount_huf
            from settlement.cfg_jitt_delay_bonus_rules d
            where d.is_active
              and d.deleted_at is null
              and d.calculation_mode in ('api', 'excel')
              and source.route_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
              and d.day_type in (source.day_type, 'any')
              and d.route_type in (source.route_type, 'any')
              and (nullif(trim(d.warehouse_code), '') is null or lower(trim(d.warehouse_code)) = lower(trim(source.warehouse_code)))
              and (
                  (source.matched_tier is not null and lower(d.level_code) = lower(source.matched_tier))
                  or (
                      (d.threshold_min is not null or d.threshold_max is not null)
                      and (
                          d.threshold_min is null
                          or (d.threshold_min_inclusive and source.amount_huf >= d.threshold_min)
                          or (not d.threshold_min_inclusive and source.amount_huf > d.threshold_min)
                      )
                      and (
                          d.threshold_max is null
                          or (d.threshold_max_inclusive and source.amount_huf <= d.threshold_max)
                          or (not d.threshold_max_inclusive and source.amount_huf < d.threshold_max)
                      )
                  )
              )
            order by
                case when d.calculation_mode = 'api' then 0 else 1 end,
                d.priority,
                d.id
            limit 1
        ) rule_amount on true
    )
    update settlement.jit_row j
    set
        courier_delay_bonus_huf = api_delay.amount_huf,
        courier_bonus_total_huf = api_delay.amount_huf
            + coalesce(j.courier_compliance_bonus_huf, 0)
            + coalesce(j.courier_other_bonus_huf, 0)
    from api_delay
    where j.id = api_delay.id;

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
