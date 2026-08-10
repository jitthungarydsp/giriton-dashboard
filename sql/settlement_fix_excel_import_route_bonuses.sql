begin;

-- Safe patch for already installed settlement schemas.
-- It keeps Excel import content-based, but persists route-level JITT bonuses
-- from the JIT rows so devtest/PWA summaries can read one DB source.

alter table settlement.cfg_jitt_delay_bonus_rules
    add column if not exists excel_source_field text;

alter table settlement.cfg_jitt_compliance_bonus_rules
    add column if not exists excel_source_field text;

update settlement.cfg_jitt_delay_bonus_rules
set excel_source_field = 'Delay Bonus'
where calculation_mode = 'excel'
  and nullif(trim(coalesce(excel_source_field, '')), '') is null;

update settlement.cfg_jitt_compliance_bonus_rules
set excel_source_field = 'Compliance Bonus'
where calculation_mode = 'excel'
  and nullif(trim(coalesce(excel_source_field, '')), '') is null;

alter table settlement.jit_row
    add column if not exists route_unique_id text,
    add column if not exists route_date date,
    add column if not exists weekday_iso smallint,
    add column if not exists calculated_day_type text,
    add column if not exists company_base_rate_huf numeric not null default 0,
    add column if not exists courier_base_rate_huf numeric not null default 0,
    add column if not exists courier_tip_huf numeric not null default 0,
    add column if not exists courier_delay_bonus_huf numeric not null default 0,
    add column if not exists courier_compliance_bonus_huf numeric not null default 0,
    add column if not exists courier_other_bonus_huf numeric not null default 0,
    add column if not exists courier_bonus_total_huf numeric not null default 0,
    add column if not exists is_route_primary boolean not null default false,
    add column if not exists base_rate_status text not null default 'pending',
    add column if not exists base_rate_calculated_at timestamptz;

create or replace function settlement.recalculate_jitt_base_rates(p_session_id uuid)
returns void
language sql
security definer
set search_path = settlement, public
as $$
with raw as (
    select
        j.id,
        j.session_id,
        j.normalized_data,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        coalesce(nullif(j.normalized_data ->> 'Route Unique ID', ''), nullif(j.normalized_data ->> 'route_unique_id', ''), j.id::text) as route_unique_id,
        coalesce(nullif(j.normalized_data ->> 'Location', ''), nullif(j.normalized_data ->> 'warehouse_code', ''), '') as warehouse_code,
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
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Orders', j.normalized_data ->> 'orders', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as orders,
        coalesce(nullif(replace(regexp_replace(coalesce(j.normalized_data ->> 'Tip', j.normalized_data ->> 'tip_huf', '0'), '[^0-9,.-]', '', 'g'), ',', '.'), '')::numeric, 0) as tip_huf,
        coalesce((
            select sum(case when item.value like '%,%'
                then coalesce(nullif(replace(regexp_replace(item.value, '[^0-9,-]', '', 'g'), ',', '.'), '')::numeric, 0)
                else coalesce(nullif(regexp_replace(item.value, '[^0-9.-]', '', 'g'), '')::numeric, 0)
            end)
            from jsonb_each_text(j.normalized_data) as item(key, value)
            where lower(trim(item.key)) in ('fuel bonus', 'car & fridge bonus', 'fill rate bonus', 'branding')
        ), 0) as other_bonus_huf
    from settlement.jit_row j
    cross join lateral (
        select coalesce(
            nullif(j.normalized_data ->> 'Date', ''),
            nullif(j.normalized_data ->> 'date', ''),
            nullif(j.normalized_data ->> 'Dátum', ''),
            nullif(j.normalized_data ->> 'work_date', ''),
            (select item.value from jsonb_each_text(j.normalized_data) as item(key, value)
             where lower(trim(item.key)) in ('date', 'dátum', 'datum', 'work_date') limit 1),
            ''
        ) as date_text
    ) date_value
    where j.session_id = p_session_id
), ranked as (
    select raw.*, row_number() over (partition by route_unique_id order by id) as route_rank
    from raw
), resolved as (
    select
        r.*,
        coalesce(day_rule.day_type, 'normal') as resolved_day_type,
        rate.id as rate_id,
        rate.company_amount_huf,
        rate.courier_amount_huf,
        rate.calculation_unit,
        coalesce(delay_rule.excel_amount_huf, 0) as delay_amount_huf,
        coalesce(compliance_rule.excel_amount_huf, 0) as compliance_amount_huf
    from ranked r
    left join lateral (
        select d.day_type
        from settlement.cfg_jitt_day_definitions d
        where d.is_active and d.deleted_at is null
          and r.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and extract(isodow from r.work_date)::smallint = any(d.weekdays)
        order by d.priority, d.id
        limit 1
    ) day_rule on true
    left join lateral (
        select b.*
        from settlement.cfg_jitt_base_rates b
        where b.is_active and b.deleted_at is null
          and r.work_date between b.valid_from and coalesce(b.valid_to, 'infinity'::date)
          and b.day_type in (coalesce(day_rule.day_type, 'normal'), 'any')
          and b.route_type in (r.route_type, 'any')
        order by b.priority,
                 case when b.day_type = coalesce(day_rule.day_type, 'normal') then 0 else 1 end,
                 case when b.route_type = r.route_type then 0 else 1 end,
                 b.id
        limit 1
    ) rate on true
    left join lateral (
        select case d.calculation_unit
            when 'per_route' then d.courier_amount_huf
            when 'per_order' then d.courier_amount_huf * r.orders
            when 'fixed' then d.courier_amount_huf
            else 0
        end as excel_amount_huf
        from settlement.cfg_jitt_delay_bonus_rules d
        left join lateral (
            select item.value from jsonb_each_text(r.normalized_data) as item(key, value)
            where lower(trim(item.key)) = lower(trim(d.excel_source_field)) limit 1
        ) source_value on true
        cross join lateral (
            select case when source_value.value like '%,%'
                then coalesce(nullif(replace(regexp_replace(source_value.value, '[^0-9,-]', '', 'g'), ',', '.'), '')::numeric, 0)
                else coalesce(nullif(regexp_replace(source_value.value, '[^0-9.-]', '', 'g'), '')::numeric, 0)
            end as value
        ) excel_value
        where d.is_active and d.deleted_at is null and d.calculation_mode = 'excel'
          and nullif(trim(d.excel_source_field), '') is not null
          and r.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and d.day_type in (coalesce(day_rule.day_type, 'normal'), 'any')
          and d.route_type in (r.route_type, 'any')
          and (nullif(trim(d.warehouse_code), '') is null or lower(trim(d.warehouse_code)) = lower(trim(r.warehouse_code)))
          and excel_value.value > 0
          and (
              (
                  (d.threshold_min is not null or d.threshold_max is not null)
                  and (d.threshold_min is null or excel_value.value >= d.threshold_min)
                  and (d.threshold_max is null or excel_value.value <= d.threshold_max)
              )
              or (
                  d.threshold_min is null and d.threshold_max is null
                  and excel_value.value = d.company_amount_huf
              )
          )
        order by d.priority, d.id
        limit 1
    ) delay_rule on true
    left join lateral (
        select case d.calculation_unit
            when 'per_route' then d.courier_amount_huf
            when 'per_order' then d.courier_amount_huf * r.orders
            when 'fixed' then d.courier_amount_huf
            else 0
        end as excel_amount_huf
        from settlement.cfg_jitt_compliance_bonus_rules d
        left join lateral (
            select item.value from jsonb_each_text(r.normalized_data) as item(key, value)
            where lower(trim(item.key)) = lower(trim(d.excel_source_field)) limit 1
        ) source_value on true
        cross join lateral (
            select case when source_value.value like '%,%'
                then coalesce(nullif(replace(regexp_replace(source_value.value, '[^0-9,-]', '', 'g'), ',', '.'), '')::numeric, 0)
                else coalesce(nullif(regexp_replace(source_value.value, '[^0-9.-]', '', 'g'), '')::numeric, 0)
            end as value
        ) excel_value
        where d.is_active and d.deleted_at is null and d.calculation_mode = 'excel'
          and nullif(trim(d.excel_source_field), '') is not null
          and r.work_date between d.valid_from and coalesce(d.valid_to, 'infinity'::date)
          and d.day_type in (coalesce(day_rule.day_type, 'normal'), 'any')
          and d.route_type in (r.route_type, 'any')
          and (nullif(trim(d.warehouse_code), '') is null or lower(trim(d.warehouse_code)) = lower(trim(r.warehouse_code)))
          and excel_value.value > 0
          and (
              (
                  (d.threshold_min is not null or d.threshold_max is not null)
                  and (d.threshold_min is null or excel_value.value >= d.threshold_min)
                  and (d.threshold_max is null or excel_value.value <= d.threshold_max)
              )
              or (
                  d.threshold_min is null and d.threshold_max is null
                  and excel_value.value = d.company_amount_huf
              )
          )
        order by d.priority, d.id
        limit 1
    ) compliance_rule on true
)
update settlement.jit_row j
set
    route_unique_id = resolved.route_unique_id,
    route_date = resolved.work_date,
    weekday_iso = case when resolved.work_date is not null then extract(isodow from resolved.work_date)::smallint end,
    calculated_day_type = resolved.resolved_day_type,
    company_base_rate_huf = case
        when resolved.route_rank <> 1 then 0
        when resolved.calculation_unit = 'per_order' then coalesce(resolved.company_amount_huf, 0) * resolved.orders
        when resolved.calculation_unit = 'per_route' then coalesce(resolved.company_amount_huf, 0)
        else 0
    end,
    courier_base_rate_huf = case
        when resolved.route_rank <> 1 then 0
        when resolved.calculation_unit = 'per_order' then coalesce(resolved.courier_amount_huf, 0) * resolved.orders
        when resolved.calculation_unit = 'per_route' then coalesce(resolved.courier_amount_huf, 0)
        else 0
    end,
    courier_tip_huf = case when resolved.route_rank = 1 then resolved.tip_huf else 0 end,
    courier_delay_bonus_huf = case when resolved.route_rank = 1 then resolved.delay_amount_huf else 0 end,
    courier_compliance_bonus_huf = case when resolved.route_rank = 1 then resolved.compliance_amount_huf else 0 end,
    courier_other_bonus_huf = case when resolved.route_rank = 1 then resolved.other_bonus_huf else 0 end,
    courier_bonus_total_huf = case when resolved.route_rank = 1
        then resolved.delay_amount_huf + resolved.compliance_amount_huf + resolved.other_bonus_huf else 0 end,
    is_route_primary = resolved.route_rank = 1,
    base_rate_status = case
        when resolved.route_rank <> 1 then 'duplicate_route_id'
        when resolved.work_date is null then 'missing_excel_date'
        when resolved.rate_id is null then 'missing_base_rate'
        when resolved.calculation_unit not in ('per_route', 'per_order') then 'unsupported_unit'
        else 'calculated'
    end,
    base_rate_calculated_at = now()
from resolved
where j.id = resolved.id;
$$;

create or replace view settlement.vw_parameterized_courier_base_summary as
select
    session_id,
    coalesce(nullif(normalized_data ->> 'Driver', ''), nullif(normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
    sum(courier_base_rate_huf) as courier_base_rate_huf,
    sum(company_base_rate_huf) as company_base_rate_huf,
    sum(courier_tip_huf) as tip_huf,
    count(*) filter (where is_route_primary and calculated_day_type = 'highlighted') as highlighted_routes,
    count(*) filter (where is_route_primary and calculated_day_type = 'normal') as normal_routes,
    count(*) filter (where is_route_primary and base_rate_status = 'calculated') as calculated_routes,
    count(*) filter (where is_route_primary and base_rate_status <> 'calculated') as uncalculated_routes,
    sum(courier_delay_bonus_huf) as delay_bonus_huf,
    sum(courier_compliance_bonus_huf) as compliance_bonus_huf,
    sum(courier_other_bonus_huf) as other_route_bonus_huf,
    sum(courier_bonus_total_huf) as route_bonus_huf
from settlement.jit_row
group by session_id, coalesce(nullif(normalized_data ->> 'Driver', ''), nullif(normalized_data ->> 'driver_name', ''), 'Ismeretlen futár');

grant select on settlement.vw_parameterized_courier_base_summary to service_role;
grant execute on function settlement.recalculate_jitt_base_rates(uuid) to service_role;

do $$
declare
    session_record record;
begin
    for session_record in
        select distinct session_id
        from settlement.jit_row
        where session_id is not null
    loop
        perform settlement.recalculate_jitt_base_rates(session_record.session_id);

        if to_regprocedure('settlement.refresh_courier_settlement_summary(uuid)') is not null then
            perform settlement.refresh_courier_settlement_summary(session_record.session_id);
        end if;
    end loop;
end $$;

commit;
