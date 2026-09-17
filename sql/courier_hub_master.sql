begin;

create table if not exists public.courier_hub_master (
    courier_id integer not null,
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null default 8,
    courier_name text,
    giriton_person_id text,
    user_number text,
    email text,
    phone_number text,
    rfid text,
    status text,
    active boolean,
    vehicle_id integer,
    vehicle_registration_number text,
    vehicle_type text,
    registered_since timestamptz,
    assignment_load integer,
    roster_date date not null,
    source_page integer,
    source_row_index integer,
    request_url text not null,
    response_json jsonb not null,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (courier_id, warehouse_id, dsp_id, roster_date)
);

create index if not exists courier_hub_master_name_idx
    on public.courier_hub_master (courier_name);

create index if not exists courier_hub_master_user_number_idx
    on public.courier_hub_master (user_number);

create index if not exists courier_hub_master_giriton_person_idx
    on public.courier_hub_master (giriton_person_id);

create index if not exists courier_hub_master_vehicle_plate_idx
    on public.courier_hub_master (vehicle_registration_number);

create index if not exists courier_hub_master_last_seen_idx
    on public.courier_hub_master (last_seen_at desc);

create index if not exists courier_hub_master_roster_date_idx
    on public.courier_hub_master (roster_date, warehouse_id, dsp_id);

create index if not exists courier_hub_master_json_idx
    on public.courier_hub_master using gin (response_json);

create or replace view public.couer_hub_master as
select *
from public.courier_hub_master;

create or replace view public.courier_hub_master_latest as
select distinct on (courier_id, warehouse_id, dsp_id)
    *
from public.courier_hub_master
order by courier_id, warehouse_id, dsp_id, roster_date desc, last_seen_at desc;

create or replace function public.courier_hub_master_between(
    p_start_date date,
    p_end_date date,
    p_warehouse_id integer default null,
    p_dsp_id integer default 8
)
returns setof public.courier_hub_master
language sql
stable
as $$
    select *
    from public.courier_hub_master
    where roster_date between p_start_date and p_end_date
      and (p_warehouse_id is null or warehouse_id = p_warehouse_id)
      and (p_dsp_id is null or dsp_id = p_dsp_id)
    order by roster_date asc, warehouse_id asc, courier_name asc, courier_id asc;
$$;

grant select, insert, update, delete on public.courier_hub_master to service_role;
grant select on public.couer_hub_master to service_role;
grant select on public.courier_hub_master_latest to service_role;
grant execute on function public.courier_hub_master_between(date, date, integer, integer) to service_role;

commit;
