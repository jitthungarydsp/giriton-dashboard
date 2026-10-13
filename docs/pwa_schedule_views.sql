-- PWA beosztas gyorsito view-k.
-- Normal view-k: mindig az aktualis tablakbol olvasnak, kulon refresh job nem kell.

create index if not exists idx_pwa_today_worker_attendance_work_date
  on public.pwa_today_worker_attendance (work_date, courier_id, warehouse, start_time, booking_code);

create index if not exists idx_courier_hub_route_statistics_schedule_day
  on public.courier_hub_route_statistics (work_date, courier_id, warehouse_id, route_id);

create index if not exists idx_courier_hub_live_map_courier_latest_fetched
  on public.courier_hub_live_map_courier_latest (fetched_at, courier_id, warehouse_id);

create or replace view public.pwa_schedule_worker_status_v as
select
  courier_id::text as courier_id,
  courier_name,
  work_date::date as work_date,
  start_time,
  end_time,
  warehouse,
  shift_name,
  booking_code,
  attendance_status,
  note,
  marked_by,
  marked_at,
  updated_at
from public.pwa_today_worker_attendance;

create or replace view public.pwa_schedule_day_route_counts_v as
with source_counts as (
  select
    work_date::date as work_date,
    courier_id::text as courier_id,
    max(courier_name) as courier_name,
    coalesce(
      nullif(upper(trim(warehouse_code::text)), ''),
      case
        when warehouse_id::text = '1' then 'BUD1'
        when warehouse_id::text = '2' then 'BUD2'
        else nullif(warehouse_id::text, '')
      end
    ) as warehouse,
    count(distinct route_id) as daily_route_count
  from public.courier_hub_route_statistics
  where courier_id is not null
    and route_id is not null
    and nullif(route_id::text, '') is not null
  group by
    work_date::date,
    courier_id::text,
    coalesce(
      nullif(upper(trim(warehouse_code::text)), ''),
      case
        when warehouse_id::text = '1' then 'BUD1'
        when warehouse_id::text = '2' then 'BUD2'
        else nullif(warehouse_id::text, '')
      end
    )

  union all

  select
    work_date::date as work_date,
    courier_id::text as courier_id,
    max(courier_name) as courier_name,
    coalesce(
      nullif(upper(trim(warehouse_code::text)), ''),
      case
        when warehouse_id::text = '1' then 'BUD1'
        when warehouse_id::text = '2' then 'BUD2'
        else nullif(warehouse_id::text, '')
      end
    ) as warehouse,
    sum(coalesce(route_count, 0))::bigint as daily_route_count
  from public.raw_jitt_invoice_perf_couriers_daily
  where courier_id is not null
  group by
    work_date::date,
    courier_id::text,
    coalesce(
      nullif(upper(trim(warehouse_code::text)), ''),
      case
        when warehouse_id::text = '1' then 'BUD1'
        when warehouse_id::text = '2' then 'BUD2'
        else nullif(warehouse_id::text, '')
      end
    )

  union all

  select
    work_date::date as work_date,
    courier_id::text as courier_id,
    max(courier_name) as courier_name,
    upper(nullif(trim(warehouse_name), '')) as warehouse,
    count(distinct route_id) as daily_route_count
  from public.mart_dsp_route_stories
  where courier_id is not null
    and route_id is not null
  group by work_date::date, courier_id::text, upper(nullif(trim(warehouse_name), ''))

  union all

  select
    (fetched_at at time zone 'Europe/Budapest')::date as work_date,
    courier_id::text as courier_id,
    max(courier_name) as courier_name,
    coalesce(
      nullif(upper(trim(warehouse_code::text)), ''),
      case
        when warehouse_id::text = '1' then 'BUD1'
        when warehouse_id::text = '2' then 'BUD2'
        else nullif(warehouse_id::text, '')
      end
    ) as warehouse,
    max(
      coalesce(finished_route_count, 0)
      + case
          when nullif(route_ids::text, '') is not null
           and route_ids::text not in ('[]', 'null')
          then 1
          else 0
        end
    )::bigint as daily_route_count
  from public.courier_hub_live_map_courier_latest
  where courier_id is not null
    and fetched_at is not null
  group by
    (fetched_at at time zone 'Europe/Budapest')::date,
    courier_id::text,
    case
      when warehouse_id::text = '1' then 'BUD1'
      when warehouse_id::text = '2' then 'BUD2'
      else nullif(warehouse_id::text, '')
    end
)
select
  work_date,
  courier_id,
  max(courier_name) as courier_name,
  warehouse,
  max(daily_route_count)::bigint as daily_route_count
from source_counts
group by work_date, courier_id, warehouse;

grant select on public.pwa_schedule_worker_status_v to anon, authenticated, service_role;
grant select on public.pwa_schedule_day_route_counts_v to anon, authenticated, service_role;
