/*
Supabase SQL Editorban futtasd.

Mit mutat:
- az adott hónap/futár Excel sorain jelenleg milyen alapdíj van mentve a jit_row táblában;
- milyen raktár/nap/túratípus alapján keres szabályt;
- melyik cfg_jitt_base_rates szabály illeszkedne rá most.

Átírandó:
- v_period_start: hónap első napja
- v_courier_id: futár ID, ha tudod
- v_driver_name: futárnév részlet, ha ID nélkül keresel
*/

with params as (
    select
        date '2026-07-01' as v_period_start,
        '8001'::text as v_courier_id,
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
latest_session as (
    select j.session_id
    from settlement.jit_row j
    join period p on true
    where j.route_date between p.v_period_start and p.v_period_end
    order by j.created_at desc nulls last, j.id desc
    limit 1
),
raw as (
    select
        j.id,
        j.session_id,
        nullif(coalesce(j.normalized_data ->> 'Courier ID', j.normalized_data ->> 'courier_id'), '') as courier_id,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        coalesce(nullif(j.normalized_data ->> 'Route Unique ID', ''), nullif(j.normalized_data ->> 'route_unique_id', ''), j.route_unique_id, j.id::text) as route_unique_id,
        coalesce(nullif(j.normalized_data ->> 'Location', ''), nullif(j.normalized_data ->> 'warehouse_code', ''), '') as warehouse_code,
        j.route_date as work_date,
        coalesce(j.calculated_day_type, 'normal') as day_type,
        case
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%express%' then 'express'
            when lower(coalesce(j.normalized_data ->> 'Route Type', j.normalized_data ->> 'route_type', '')) like '%region%' then 'regional'
            else 'normal'
        end as route_type,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders,
        j.is_route_primary,
        j.base_rate_status,
        j.courier_base_rate_huf as saved_courier_base_rate_huf,
        j.company_base_rate_huf as saved_company_base_rate_huf
    from settlement.jit_row j
    join period p on true
    join latest_session s on s.session_id = j.session_id
    where j.route_date between p.v_period_start and p.v_period_end
      and (
          coalesce(p.v_courier_id, '') = ''
          or nullif(coalesce(j.normalized_data ->> 'Courier ID', j.normalized_data ->> 'courier_id'), '') = p.v_courier_id
      )
      and (
          p.v_driver_name is null
          or lower(coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), '')) like '%' || lower(p.v_driver_name) || '%'
      )
),
matched as (
    select
        r.*,
        rate.id as matched_rate_id,
        rate.warehouse_code as matched_warehouse_code,
        rate.day_type as matched_day_type,
        rate.route_type as matched_route_type,
        rate.courier_amount_huf as matched_courier_amount_huf,
        rate.company_amount_huf as matched_company_amount_huf,
        rate.calculation_unit as matched_calculation_unit,
        rate.priority as matched_priority,
        case
            when rate.id is null then null
            when rate.calculation_unit = 'per_order' then rate.courier_amount_huf * r.orders
            when rate.calculation_unit = 'per_route' then rate.courier_amount_huf
            else 0
        end as expected_courier_base_rate_huf
    from raw r
    left join lateral (
        select b.*
        from settlement.cfg_jitt_base_rates b
        where b.is_active
          and b.deleted_at is null
          and r.work_date between b.valid_from and coalesce(b.valid_to, 'infinity'::date)
          and b.day_type in (r.day_type, 'any')
          and b.route_type in (r.route_type, 'any')
          and (
              nullif(trim(b.warehouse_code), '') is null
              or lower(trim(b.warehouse_code)) = lower(trim(r.warehouse_code))
          )
        order by b.priority,
                 case when b.day_type = r.day_type then 0 else 1 end,
                 case when b.route_type = r.route_type then 0 else 1 end,
                 case when nullif(trim(b.warehouse_code), '') is not null then 0 else 1 end,
                 b.id
        limit 1
    ) rate on true
)
select
    session_id,
    courier_id,
    driver_name,
    route_unique_id,
    work_date,
    warehouse_code,
    day_type,
    route_type,
    orders,
    is_route_primary,
    base_rate_status,
    saved_courier_base_rate_huf,
    expected_courier_base_rate_huf,
    saved_courier_base_rate_huf - coalesce(expected_courier_base_rate_huf, 0) as difference_huf,
    matched_courier_amount_huf,
    matched_company_amount_huf,
    matched_calculation_unit,
    matched_day_type,
    matched_route_type,
    matched_warehouse_code,
    matched_priority,
    matched_rate_id
from matched
order by work_date, route_unique_id
limit 200;
