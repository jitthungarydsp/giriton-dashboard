begin;

alter table settlement.courier_monthly_closure
    add column if not exists reopened_at timestamptz,
    add column if not exists reopened_by text;

alter table settlement.courier_monthly_closure
    drop constraint if exists courier_monthly_closure_status_check;

alter table settlement.courier_monthly_closure
    add constraint courier_monthly_closure_status_check
    check (status in ('done', 'reopened'));

create index if not exists courier_monthly_closure_reopened_idx
    on settlement.courier_monthly_closure (status, reopened_at);

notify pgrst, 'reload schema';

commit;
