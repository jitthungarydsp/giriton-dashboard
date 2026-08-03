create table if not exists settlement.courier_loyalty_booking_log (
    id uuid primary key default gen_random_uuid(),
    courier_id text,
    courier_name text,
    user_email text,
    booked_at timestamptz,
    operation text,
    shift_date date,
    shift_time text,
    warehouse text,
    raw_shift_data text,
    source_sheet_id text not null,
    source_gid integer not null,
    source_row integer not null,
    source_key text not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists courier_loyalty_booking_log_source_key_uq
    on settlement.courier_loyalty_booking_log (source_key);

create index if not exists courier_loyalty_booking_log_period_idx
    on settlement.courier_loyalty_booking_log (shift_date, booked_at);

create index if not exists courier_loyalty_booking_log_courier_idx
    on settlement.courier_loyalty_booking_log (courier_id);

alter table settlement.cfg_jitt_loyalty_bonus_rules
    add column if not exists previous_normal_routes_min integer not null default 0 check (previous_normal_routes_min >= 0),
    add column if not exists require_acceptance boolean not null default false,
    add column if not exists require_advance_booking boolean not null default true,
    add column if not exists require_active_relationship boolean not null default true;

grant select, insert, update, delete on settlement.courier_loyalty_booking_log to service_role;
grant select, insert, update, delete on settlement.cfg_jitt_loyalty_bonus_rules to service_role;

alter table settlement.cfg_jitt_loyalty_bonus_rules
    alter column require_acceptance set default false;

update settlement.cfg_jitt_loyalty_bonus_rules
set require_acceptance = false
where require_acceptance is true;

notify pgrst, 'reload schema';
