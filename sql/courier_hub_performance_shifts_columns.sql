begin;

alter table public.courier_shift_overview_raw
    add column if not exists date_from date,
    add column if not exists date_to date,
    add column if not exists total_shifts integer not null default 0,
    add column if not exists no_show_shifts integer not null default 0,
    add column if not exists late_login_shifts integer not null default 0;

alter table public.courier_shift_overview
    add column if not exists actual_start_at timestamptz,
    add column if not exists evaluation text;

create index if not exists courier_shift_overview_raw_range_idx
    on public.courier_shift_overview_raw (date_from, date_to, warehouse_id, courier_id);

create index if not exists courier_shift_overview_evaluation_idx
    on public.courier_shift_overview (work_date, evaluation, warehouse_id);

commit;
