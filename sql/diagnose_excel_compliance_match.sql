/*
Supabase SQL Editorban futtasd.

Mit mutat:
- az adott hónap/futár Excel route sorain milyen Túramegfelelés érték van mentve;
- az Excel melyik mezőjét nézi a compliance paraméter;
- express/normal route típusra melyik cfg_jitt_compliance_bonus_rules sor illeszkedne;
- hol nincs egyezés a vállalkozói/JITT díj és az Excel érték között.

Átírandó:
- v_period_start: hónap első napja
- v_courier_id: futár ID, ha tudod
- v_driver_name: futárnév részlet, ha ID nélkül keresel
*/

with params as (
    select
        date '2026-09-01' as v_period_start,
        null::text as v_courier_id,
        null::text as v_driver_name
),
period as (
    select
        v_period_start,
        (v_period_start + interval '1 month - 1 day')::date as v_period_end,
        v_courier_id,
        v_driver_name
    from params
),
raw_all as (
    select
        j.id,
        j.session_id,
        nullif(coalesce(j.normalized_data ->> 'Courier ID', j.normalized_data ->> 'courier_id'), '') as courier_id,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        coalesce(nullif(j.normalized_data ->> 'Route Unique ID', ''), nullif(j.normalized_data ->> 'route_unique_id', ''), j.route_unique_id, j.id::text) as route_unique_id,
        coalesce(nullif(j.normalized_data ->> 'Location', ''), nullif(j.normalized_data ->> 'warehouse_code', ''), '') as warehouse_code,
        coalesce(
            j.route_date,
            case
                when date_value.date_text ~ '^\d{4}-\d{2}-\d{2}' then left(date_value.date_text, 10)::date
                when date_value.date_text ~ '^\d{4}/\d{2}/\d{2}' then to_date(left(date_value.date_text, 10), 'YYYY/MM/DD')
                when date_value.date_text ~ '^\d{1,2}[./-]\d{1,2}[./-]\d{4}$' then to_date(replace(replace(date_value.date_text, '.', '/'), '-', '/'), 'DD/MM/YYYY')
                when date_value.date_text ~ '^\d+(\.0+)?$' then date '1899-12-30' + date_value.date_text::numeric::integer
            end
        ) as work_date,
        coalesce(j.calculated_day_type, 'normal') as day_type,
        case
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%express%' then 'express'
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%region%' then 'regional'
            else 'normal'
        end as route_type,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders,
        j.is_route_primary,
        j.courier_compliance_bonus_huf as saved_courier_compliance_huf,
        j.normalized_data
    from settlement.jit_row j
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
latest_session as (
    select r.session_id
    from raw_all r
    join period p on true
    where r.work_date between p.v_period_start and p.v_period_end
    order by r.id desc
    limit 1
),
raw as (
    select r.*
    from raw_all r
    join period p on true
    join latest_session s on s.session_id = r.session_id
    where r.work_date between p.v_period_start and p.v_period_end
      and r.is_route_primary is true
      and (
          coalesce(p.v_courier_id, '') = ''
          or r.courier_id = p.v_courier_id
      )
      and (
          p.v_driver_name is null
          or lower(r.driver_name) like '%' || lower(p.v_driver_name) || '%'
      )
),
rules as (
    select *
    from settlement.cfg_jitt_compliance_bonus_rules r
    where r.is_active
      and r.deleted_at is null
      and r.calculation_mode = 'excel'
      and nullif(trim(r.excel_source_field), '') is not null
),
matched as (
    select
        raw.*,
        rule_match.id as matched_rule_id,
        rule_match.level_code,
        rule_match.excel_source_field,
        rule_match.company_amount_huf,
        rule_match.courier_amount_huf,
        rule_match.calculation_unit,
        rule_match.excel_value,
        case
            when rule_match.id is null then null
            when rule_match.calculation_unit = 'per_order' then rule_match.courier_amount_huf * raw.orders
            when rule_match.calculation_unit in ('per_route', 'fixed') then rule_match.courier_amount_huf
            else 0
        end as expected_courier_compliance_huf
    from raw
    left join lateral (
        select
            r.*,
            excel_value.value as excel_value
        from rules r
        left join lateral (
            select item.value
            from jsonb_each_text(raw.normalized_data) as item(key, value)
            where lower(trim(item.key)) = lower(trim(r.excel_source_field))
            limit 1
        ) source_value on true
        cross join lateral (
            select settlement.safe_excel_numeric(source_value.value) as value
        ) excel_value
        where raw.work_date between r.valid_from and coalesce(r.valid_to, 'infinity'::date)
          and r.day_type in (raw.day_type, 'any')
          and r.route_type in (raw.route_type, 'any')
          and (
              nullif(trim(r.warehouse_code), '') is null
              or lower(trim(r.warehouse_code)) = lower(trim(raw.warehouse_code))
          )
          and excel_value.value > 0
          and (
              (
                  (r.threshold_min is not null or r.threshold_max is not null)
                  and (r.threshold_min is null or excel_value.value >= r.threshold_min)
                  and (r.threshold_max is null or excel_value.value <= r.threshold_max)
              )
              or (
                  r.threshold_min is null
                  and r.threshold_max is null
                  and excel_value.value = r.company_amount_huf
              )
          )
        order by r.priority, r.id
        limit 1
    ) rule_match on true
)
select
    session_id,
    courier_id,
    driver_name,
    route_unique_id,
    work_date,
    warehouse_code,
    route_type,
    day_type,
    orders,
    saved_courier_compliance_huf,
    matched_rule_id,
    level_code,
    excel_source_field,
    excel_value as excel_vallalkozo_dij,
    company_amount_huf as parameter_vallalkozo_dij,
    courier_amount_huf as parameter_futar_dij,
    expected_courier_compliance_huf,
    case
        when matched_rule_id is null then 'Nincs illeszkedő compliance szabály'
        when coalesce(saved_courier_compliance_huf, 0) = coalesce(expected_courier_compliance_huf, 0) then 'Egyezik'
        else 'Számolt érték eltér'
    end as status
from matched
order by route_type desc, work_date, route_unique_id
limit 500;
