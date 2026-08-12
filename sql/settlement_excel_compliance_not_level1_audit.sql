-- Excel compliance audit:
-- Lista azon futarokrol/turakrol, ahol a turamegfeleles nem LEVEL-1 szinten
-- lett felismerve a legutobbi nem API eredetu JIT Excel importban.

begin;

create or replace view settlement.vw_excel_compliance_not_level1_detail as
with latest_session as (
    select j.session_id
    from settlement.jit_row j
    where coalesce(j.source_sheet, '') not ilike 'API financial overview%'
    group by j.session_id
    order by max(j.created_at) desc
    limit 1
),
raw as (
    select
        j.id,
        j.session_id,
        j.source_sheet,
        j.source_row_no,
        j.normalized_data,
        coalesce(
            nullif(j.normalized_data ->> 'Courier ID', ''),
            nullif(j.normalized_data ->> 'courier_id', '')
        ) as courier_id,
        coalesce(
            nullif(j.normalized_data ->> 'Driver', ''),
            nullif(j.normalized_data ->> 'driver_name', ''),
            'Ismeretlen futár'
        ) as courier_name,
        coalesce(
            nullif(j.normalized_data ->> 'Route Unique ID', ''),
            nullif(j.normalized_data ->> 'route_unique_id', ''),
            j.id::text
        ) as route_unique_id,
        coalesce(
            nullif(j.normalized_data ->> 'Location', ''),
            nullif(j.normalized_data ->> 'warehouse_code', ''),
            ''
        ) as warehouse_code,
        case
            when date_value.date_text ~ '^\d{4}-\d{2}-\d{2}' then left(date_value.date_text, 10)::date
            when date_value.date_text ~ '^\d{4}/\d{2}/\d{2}' then to_date(left(date_value.date_text, 10), 'YYYY/MM/DD')
            when date_value.date_text ~ '^\d{1,2}[./-]\d{1,2}[./-]\d{4}$' then to_date(replace(replace(date_value.date_text, '.', '/'), '-', '/'), 'DD/MM/YYYY')
            when date_value.date_text ~ '^\d+(\.0+)?$' then date '1899-12-30' + date_value.date_text::numeric::integer
        end as work_date,
        case
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%express%' then 'express'
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%region%' then 'regional'
            else 'normal'
        end as route_type,
        settlement.safe_excel_numeric(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0')) as orders,
        coalesce(j.courier_compliance_bonus_huf, 0)::numeric as actual_compliance_huf
    from settlement.jit_row j
    join latest_session latest on latest.session_id = j.session_id
    cross join lateral (
        select coalesce(
            nullif(j.normalized_data ->> 'Date', ''),
            nullif(j.normalized_data ->> 'date', ''),
            nullif(j.normalized_data ->> 'Dátum', ''),
            nullif(j.normalized_data ->> 'Datum', ''),
            nullif(j.normalized_data ->> 'work_date', ''),
            ''
        ) as date_text
    ) date_value
    where coalesce(j.source_sheet, '') not ilike 'API financial overview%'
),
enriched as (
    select
        raw.*,
        coalesce(day_rule.day_type, 'normal') as resolved_day_type
    from raw
    left join lateral (
        select d.day_type
        from settlement.cfg_jitt_day_definitions d
        where d.is_active
          and d.deleted_at is null
          and raw.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and extract(isodow from raw.work_date)::smallint = any(d.weekdays)
        order by d.priority, d.id
        limit 1
    ) day_rule on true
),
matched as (
    select
        enriched.*,
        matched_rule.level_code as matched_level_code,
        regexp_replace(lower(coalesce(matched_rule.level_code, '')), '[^a-z0-9]+', '', 'g') as matched_level_key,
        matched_rule.excel_source_field as matched_excel_source_field,
        matched_rule.excel_metric_value,
        coalesce(level1.level1_amount_huf, 0)::numeric as expected_level1_compliance_huf
    from enriched
    left join lateral (
        select
            d.level_code,
            d.excel_source_field,
            excel_value.value as excel_metric_value
        from settlement.cfg_jitt_compliance_bonus_rules d
        left join lateral (
            select item.value
            from jsonb_each_text(enriched.normalized_data) as item(key, value)
            where lower(trim(item.key)) = lower(trim(d.excel_source_field))
            limit 1
        ) source_value on true
        cross join lateral (
            select settlement.safe_excel_numeric(source_value.value) as value
        ) excel_value
        where d.is_active
          and d.deleted_at is null
          and d.calculation_mode = 'excel'
          and nullif(trim(d.excel_source_field), '') is not null
          and enriched.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and d.day_type in (enriched.resolved_day_type, 'any')
          and d.route_type in (enriched.route_type, 'any')
          and (nullif(trim(d.warehouse_code), '') is null or lower(trim(d.warehouse_code)) = lower(trim(enriched.warehouse_code)))
          and excel_value.value > 0
          and (
              (
                  (d.threshold_min is not null or d.threshold_max is not null)
                  and (d.threshold_min is null or excel_value.value >= d.threshold_min)
                  and (d.threshold_max is null or excel_value.value <= d.threshold_max)
              )
              or (
                  d.threshold_min is null
                  and d.threshold_max is null
                  and excel_value.value = d.company_amount_huf
              )
          )
        order by d.priority, d.id
        limit 1
    ) matched_rule on true
    left join lateral (
        select max(case d.calculation_unit
            when 'per_route' then d.courier_amount_huf
            when 'per_order' then d.courier_amount_huf * enriched.orders
            when 'fixed' then d.courier_amount_huf
            else 0
        end) as level1_amount_huf
        from settlement.cfg_jitt_compliance_bonus_rules d
        where d.is_active
          and d.deleted_at is null
          and d.calculation_mode = 'excel'
          and regexp_replace(lower(coalesce(d.level_code, '')), '[^a-z0-9]+', '', 'g') in ('level1', 'jitt1', 'szint1', '1')
          and enriched.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and d.day_type in (enriched.resolved_day_type, 'any')
          and d.route_type in (enriched.route_type, 'any')
          and (nullif(trim(d.warehouse_code), '') is null or lower(trim(d.warehouse_code)) = lower(trim(enriched.warehouse_code)))
    ) level1 on true
)
select
    session_id,
    courier_id,
    courier_name,
    route_unique_id,
    work_date,
    source_sheet,
    source_row_no,
    warehouse_code,
    route_type,
    resolved_day_type,
    orders,
    coalesce(matched_level_code, 'Nincs illeszkedő compliance szabály') as excel_compliance_level,
    matched_excel_source_field,
    matched_rule.excel_metric_value as excel_compliance_metric,
    actual_compliance_huf,
    expected_level1_compliance_huf,
    greatest(expected_level1_compliance_huf - actual_compliance_huf, 0) as missing_vs_level1_huf,
    case
        when expected_level1_compliance_huf <= 0 then 'Nincs LEVEL-1 compliance szabály erre a túrára'
        when matched_level_key in ('level1', 'jitt1', 'szint1', '1') then 'LEVEL-1'
        when matched_level_code is null then 'Nem olvasható / nincs illeszkedő compliance mutató'
        else 'Nem LEVEL-1'
    end as audit_status
from matched matched_rule
where coalesce(expected_level1_compliance_huf, 0) > 0
  and (
      matched_level_key is null
      or matched_level_key not in ('level1', 'jitt1', 'szint1', '1')
      or actual_compliance_huf < expected_level1_compliance_huf
  );

create or replace view settlement.vw_excel_compliance_not_level1_summary as
select
    session_id,
    courier_id,
    courier_name,
    count(*) as not_level1_route_count,
    sum(actual_compliance_huf)::numeric as actual_compliance_huf,
    sum(expected_level1_compliance_huf)::numeric as expected_level1_compliance_huf,
    sum(missing_vs_level1_huf)::numeric as missing_vs_level1_huf,
    jsonb_agg(
        jsonb_build_object(
            'route_id', route_unique_id,
            'date', work_date,
            'level', excel_compliance_level,
            'metric', excel_compliance_metric,
            'actual_huf', actual_compliance_huf,
            'level1_huf', expected_level1_compliance_huf,
            'missing_huf', missing_vs_level1_huf
        )
        order by work_date, route_unique_id
    ) as affected_routes
from settlement.vw_excel_compliance_not_level1_detail
group by session_id, courier_id, courier_name
order by missing_vs_level1_huf desc, not_level1_route_count desc, courier_name;

grant select on settlement.vw_excel_compliance_not_level1_detail to service_role;
grant select on settlement.vw_excel_compliance_not_level1_summary to service_role;

notify pgrst, 'reload schema';

commit;
