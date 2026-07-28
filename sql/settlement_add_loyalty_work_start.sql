begin;

alter table public.courier_master
    add column if not exists work_start_date date;

alter table settlement.cfg_jitt_loyalty_bonus_rules
    add column if not exists loyalty_months_required integer not null default 0 check (loyalty_months_required >= 0),
    add column if not exists route_type text not null default 'normal' check (route_type in ('normal', 'express', 'regional', 'any')),
    add column if not exists calculation_unit text not null default 'per_route' check (calculation_unit in ('per_route', 'per_order'));

create index if not exists idx_courier_master_work_start_date
    on public.courier_master using btree (work_start_date);

notify pgrst, 'reload schema';

commit;
