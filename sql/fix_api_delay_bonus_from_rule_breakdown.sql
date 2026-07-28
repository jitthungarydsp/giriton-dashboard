begin;

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
    where j.source_sheet like 'API financial overview%'
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
          and d.calculation_mode = 'api'
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
        order by d.priority, d.id
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

select settlement.refresh_courier_settlement_summary(session_id)
from (
    select distinct session_id
    from settlement.jit_row
    where source_sheet like 'API financial overview%'
) sessions;

commit;
