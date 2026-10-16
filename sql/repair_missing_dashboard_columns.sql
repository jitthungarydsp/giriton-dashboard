-- Repair columns expected by the current dashboard views and API.
-- Safe to run repeatedly: it only adds missing nullable columns and
-- backfills display values where the source data is already available.

begin;

do $$
begin
    if to_regclass('public.mart_dsp_route_stories') is not null then
        alter table public.mart_dsp_route_stories
            add column if not exists route_created_at timestamp;
    end if;

    if to_regclass('public.courier_shift_overview') is not null then
        alter table public.courier_shift_overview
            add column if not exists courier_name text;
    end if;

    if to_regclass('public.courier_hub_live_map_courier_latest') is not null then
        alter table public.courier_hub_live_map_courier_latest
            add column if not exists warehouse_code text;
    end if;

    if to_regclass('public.peopleforce_complaints') is not null then
        alter table public.peopleforce_complaints
            add column if not exists admin_response text,
            add column if not exists responded_by text,
            add column if not exists responded_at timestamptz;
    end if;
end $$;

update public.courier_shift_overview shifts
set courier_name = master.courier_name
from public.courier_master master
where shifts.courier_id = master.courier_id
  and nullif(trim(coalesce(shifts.courier_name, '')), '') is null;

update public.courier_hub_live_map_courier_latest live_map
set warehouse_code = case live_map.warehouse_id
    when 1 then 'BUD1'
    when 2 then 'BUD2'
    else nullif(live_map.warehouse_id::text, '')
end
where nullif(trim(coalesce(live_map.warehouse_code, '')), '') is null;

notify pgrst, 'reload schema';

commit;
